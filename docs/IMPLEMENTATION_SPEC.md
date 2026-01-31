# Portfolio Migration Agent — 구현 명세표

과제 구현 블로그용으로, **우리가 실제로 구현한 기능**을 세세하게 정리한 문서입니다.

---

## 1. 개요

### 1.1 목적

- **입력**: PDF 보고서(과제/실험/설계 문서)
- **출력**: 채용·포트폴리오용 마크다운 + Notion DB 자동 저장 + 웹 미리보기
- **핵심 가치**: “과제 제출물”이 아니라 “LinkedIn에 올려도 자연스러운 포트폴리오 문서”로 재구성

### 1.2 사용자 시나리오

1. 사용자가 Streamlit 앱에서 PDF 업로드
2. 파이프라인이 PDF → 파싱 → 이미지 추출 → LLM 재작성 → 태그 추출까지 한 번에 수행
3. 미리보기에서 생성된 마크다운 + 이미지(base64) 확인
4. (선택) Notion DB에 저장 → 이미지는 GitHub 등 외부 URL로 업로드 후 Notion 이미지 블록에 연결

### 1.3 기술 스택

| 구분 | 기술 |
|------|------|
| 언어 | Python 3 |
| UI | Streamlit |
| PDF/OCR | Upstage Document Parse API |
| LLM | Upstage Solar API |
| 저장소 | Notion API, GitHub(이미지), 로컬 파일 |

---

## 2. 시스템 아키텍처

### 2.1 전체 구조

```
[PDF] → UpstageClient.document_parse()
         ↓
    elements (텍스트 + 이미지 base64)
         ↓
    image_processor.save_images() → assets/{doc_id}/img_001.png ...
    image_processor.replace_image_placeholders() → parsed.md
         ↓
    solar_prompts.build_user_prompt() + Solar API → post.md (포트폴리오 구조)
         ↓
    pipeline.fix_image_paths() + normalize_standalone_image_paths() → 경로 통일
         ↓
    tag_extractor.extract_tags_from_post() → tags.json
         ↓
[앱]  미리보기: post_md + _markdown_image_paths_to_data_urls() → base64 이미지 표시
[앱]  Notion 저장: notion_saver.save_to_notion() → 이미지 업로드(GitHub) + Notion 블록 생성
```

### 2.2 문서 스코프(doc_id)

- **요청당** `uuid.uuid4().hex[:12]` 로 `doc_id` 1회 생성
- 모든 산출물이 이 ID 아래로 격리됨:
  - `output/source/{doc_id}/parsed.md`
  - `output/assets/{doc_id}/img_001.png`, ...
  - `output/{doc_id}/post.md`, `tags.json`
- **이미지 경로**는 반드시 `assets/{doc_id}/filename` 형태로 통일 → 같은 세션에서 여러 PDF 처리 시 이미지/URL이 섞이지 않도록 함

---

## 3. 모듈별 구현 명세

### 3.1 config.py

- **역할**: 환경 변수 로드 및 앱/API 설정
- **주요 변수**:
  - `UPSTAGE_API_KEY`, `UPSTAGE_API_BASE`, `UPSTAGE_SOLAR_MODEL_BLOG`
  - `UPSTAGE_DOCUMENT_MAX_BYTES` (기본 20MB), `UPSTAGE_DOCUMENT_PARSE_TIMEOUT` (기본 300초)
  - `NOTION_TOKEN` / `NOTION_API_KEY`, `NOTION_PORTFOLIO_DB_ID` / `NOTION_DATABASE_ID`
  - `GITHUB_TOKEN` (환경변수 또는 `gh auth token`), `GITHUB_IMAGE_REPO`, `GITHUB_IMAGE_BRANCH`
  - `STORAGE_PROVIDER`, `STORAGE_PUBLIC_BASE_URL`
- **동작**: `dotenv` 로 `.env` 로드, `UPSTAGE_API_KEY` 없으면 시작 시 `ValueError`

---

### 3.2 upstage_client.py (UpstageClient)

- **document_parse(pdf_path)**
  - Upstage Document Parse API 호출 (`/document-digitization`)
  - 요청: `document`(파일), `model=document-parse`, `output_formats=["markdown"]`, `base64_encoding=["figure","chart","table"]`
  - 파일 크기 > `UPSTAGE_DOCUMENT_MAX_BYTES` 이면 예외
  - 반환: `{"elements": [{"content": {"markdown": "..."}, "category": "figure"|"chart"|..., "base64_encoding": "..."}, ...]}`
- **solar_chat(system_prompt, user_prompt)**
  - Solar 채팅 API로 포트폴리오용 본문 생성

---

### 3.3 image_processor.py

- **save_images(images, output_assets_dir, rel_path_prefix)**
  - `images`: Document Parse에서 나온 리스트 (항목당 `id`, `base64`, `mime` 등)
  - 각 이미지를 `output_assets_dir/img_001.png` 형태로 저장 (인덱스 기반 `img_{idx:03d}.{ext}`)
  - 반환: `(image_map, assets_manifest)`
    - `image_map`: `parse_image_id → "assets/{doc_id}/img_001.png"` 같은 상대 경로
    - `assets_manifest`: LLM에 넘길 메타정보 리스트 (`filename`, `origin_hint`, `page` 등)
- **replace_image_placeholders(markdown, image_map)**
  - `![](upstage://image/<id>)`, `<img src="upstage://image/<id>">` 등을 `image_map`으로 조회해 `![](assets/{doc_id}/img_001.png)` 등으로 치환

---

### 3.4 solar_prompts.py

- **SYSTEM_PROMPT**: “채용 담당자·타 개발자용 포트폴리오”, “과제 제출물 느낌 금지”, “LinkedIn에 올려도 자연스러워야 함”
- **build_user_prompt(source_md, assets_manifest, user_goal, target_channel)**
  - 고정 **문서 구조**를 프롬프트에 명시:
    1. Title (한 줄, 기술 스택+핵심 문제+환경)
    2. One-line Summary
    3. What I Built (역할·구현 중심)
    4. Key Results (No raw tables) — 문장 요약만
    5. Representative Visuals (Max 2~3) — 이미지 2~3개 + 한 줄 설명
    6. What I Learned / Engineering Insight
    7. Tech Stack (bullet)
    8. Suggested Tags
  - **금지 사항**: 원문 근거/과제 목표/Table X/표 전체, raw OCR 수치, **/__, [Missing image: ...]
  - **이미지**: assets_manifest 중 2~3개만 선택, 경로는 `assets/` 기준 상대 경로로 지시
- **build_github_readme_prompt(post_md)**, **build_linkedin_prompt(post_md)**: follow-up용

---

### 3.5 pipeline.py (run_pipeline)

- **입력**: `pdf_path`, `output_dir`, `user_goal`, `target_channel`, `return_result`
- **단계**:
  1. **doc_id 생성** 및 `source_dir`, `assets_dir` 생성
  2. **Document Parse** → `elements` 수집, 텍스트는 `raw_md_parts`에, figure/chart/image는 base64 + `![](upstage://image/{id})` placeholder 주입(순서 유지)
  3. **save_images** → `image_map`, `assets_manifest`, `doc_order_image_filenames` (문서 순서대로 파일명 리스트)
  4. **replace_image_placeholders(raw_md, image_map)** → `parsed_md` 저장 (`source_dir/parsed.md`)
  5. **build_user_prompt + Solar API** → `post_md`
  6. **fix_image_paths(post_md, assets_dir, output_dir)**  
     - `![](assets/filename.png)` → `![](assets/{doc_id}/filename.png)`  
     - `filename.png` → `![](assets/{doc_id}/filename.png)`  
     - 이미 `assets/{doc_id}/...` 이면 유지
  7. **normalize_standalone_image_paths(post_md, doc_id)**  
     - 한 줄이 `assets/xxx.png` 또는 `assets/{doc_id}/xxx.png` 만 있으면 → `![](해당 경로)` 로 감싸서 미리보기/Notion 구조 통일
  8. **post.md 저장** (`output/{doc_id}/post.md`)
  9. **extract_tags_from_post(post_md)** → `tags.json` 저장
  10. (선택) 문서 타입 추출 등
- **반환**: `success`, `doc_id`, 경로들, `post_md`, `parsed_md`, `tags`, `image_map`, `doc_order_image_filenames` 등 (앱/Notion 저장에 사용)

---

### 3.6 tag_extractor.py

- **extract_tags_from_post(post_md)**
  - `## Suggested Tags` 또는 `## Tags` / `## 태그` 섹션에서 `- tag` / `* tag` 패턴으로 태그 추출
  - 반환: `{"tags": ["tag1", "tag2", ...]}`

---

### 3.7 storage_client.py

- **GitHubStorageClient**
  - `upload_image(image_path, path_in_repo)`: 로컬 파일을 base64로 읽어 GitHub Contents API로 업로드
  - `path_in_repo` 예: `assets/{doc_id}/img_001.png` → 업로드 경로 및 Raw URL 경로에 doc_id 포함
  - 성공 시 `https://raw.githubusercontent.com/{repo}/{branch}/{path_encoded}` 반환 (쿼리 스트링 없음, Notion 호환)
- **StorageClient**
  - `_github` 있으면 GitHub 업로드 사용, 없으면 `STORAGE_PUBLIC_BASE_URL` + path 로 URL만 반환 가능
  - Notion에서 이미지를 보려면 **공개 URL**이어야 함 (비공개 저장소는 Notion에서 로드 불가)

---

### 3.8 notion_api_client.py (NotionClient)

- **create_page(name, properties, children)**: DB에 새 페이지 생성, Title 프로퍼티는 DB 스키마에서 title 타입으로 조회
- **append_blocks(page_id, blocks)**: 블록을 20개 단위로 나누어 연속 append, rate limit 완화용 sleep
- **purge_children(page_id)**: 페이지의 모든 자식 블록을 순차 삭제 (재사용 시 이전 콘텐츠 제거)
- **_resolve_image_url(image_url_map, resolve_key)**
  - `resolve_key`가 `assets/{doc_id}/filename` 형태일 때: 정확한 키 + unquote/공백 변형 시도 후, **같은 doc_id prefix 아래에서 파일명만 일치(대소문자 무시)** 해도 URL 반환 → “올라간 이미지는 무조건 매칭”하도록 완화
  - doc_id 없는 flat 경로일 때만 basename fallback
- **_is_caption_line(line)**  
  - Figure/Fig/그림/`*...*` 한 줄 이탤릭 등 캡션 패턴이면 True (다음 줄을 이미지 캡션으로 흡수할지 판단)
- **markdown_to_blocks(markdown, image_url_map, missing_images_out)**
  - 한 줄씩 파싱: `#`/`##`/`###`, `-`/`*` 리스트, ` ``` ` 코드 블록, `:::toggle` … `:::endtoggle` 토글, `![](path)` / `<img src="...">` 이미지, 나머지 문단
  - 이미지: `resolve_key`로 URL 조회 → 있으면 이미지 블록 추가, **없으면 블록 추가 안 함** + 다음 줄이 캡션이면 그 줄도 스킵(고아 캡션 방지)
  - 캡션은 `_is_caption_line`이면 다음 줄 흡수 후 이미지 블록 caption으로 사용
- **create_image_block(image_url, caption)**: Notion 이미지 블록 `type: "image", image: { type: "external", external: { url } }` 생성
- **_normalize_code_language(language)**: Notion 지원 코드 언어 목록에 맞게 정규화

---

### 3.9 notion_saver.py (save_to_notion)

- **입력**: `post_md`, `parsed_md`, `assets_dir`, `tags`, `metadata`, `output_dir`, `image_map`, `doc_order_image_filenames`, `doc_id`, `reuse_page_id` 등
- **본문 소스**: Notion 본문은 **parsed_md가 아니라 post_md**만 사용 (발표용 포트폴리오 톤)
- **처리 순서**:
  1. **이미지 업로드**: `assets_dir` 내 이미지 파일을 순회, `dest_path_relative = assets/{doc_id}/{filename}` 로 GitHub 업로드 → `image_urls[dest_path_relative] = public_url` (doc_id 있을 때 filename 단독 키는 넣지 않음)
  2. **resolved_image_urls**: `image_urls` 복사 + `image_map`(id→path)에 대해 path로 URL 찾아 id→url 추가
  3. **body_md**: `post_md` → (선택) `_normalize_image_placeholders_for_notion`([Image: x], placeholder → `![](assets/{doc_id}/fn)` 또는 빈 문자열) → **normalize_body_md_for_portfolio**
  4. **normalize_body_md_for_portfolio**: `**`/`__` 제거, `---` 한 줄 제거, `## Suggested Tags` / `## Tags` 섹션 제거, `※`/` -- ` 제거, 빈 줄 과다 정리
  5. **DB 프로퍼티**: Name, Type, Source, Date, Tags, Tech Stack, Status, Notion Save Version, Image Count, Job ID 등 DB에 있으면 설정
  6. **초기 블록**: “One-line Summary” 제목 + 요약 본문(post_md에서 `## One-line Summary`/`## 요약`/`## TL;DR` 추출) + 구분선
  7. **페이지**: `reuse_page_id` 있으면 purge 후 append, 없으면 create_page 후 append
  8. **본문 블록**: `markdown_to_blocks(body_md, resolved_image_urls, missing_images_out)` → 이미지 블록은 **최대 3개**만 유지, `[Missing image: ...]` 문단은 제거, 초과 시 “추가 이미지는 생략되었습니다.” 문단 1개
  9. **Tags 섹션**: 제목 “Tags” + 태그 문단 한 블록
- **반환**: `success`, `notion_page_url`, `notion_page_id`, `upload_report`(total/success/failed/missing)

---

### 3.10 app.py (Streamlit)

- **세션**: `result`, `processing` 등으로 변환 결과 유지
- **플로우**: PDF 업로드 → `run_pipeline(..., return_result=True)` → 결과 화면
- **_markdown_image_paths_to_data_urls(markdown, assets_dir, output_dir)**  
  - `![](assets/.../filename)` 를 찾아 `assets_dir` 또는 `output_dir + path` 에서 파일 읽고 → `data:image/...;base64,...` 로 치환해 미리보기에서 이미지 표시, alt가 경로 형태면 빈 문자열로
- **다운로드**: post.md, 이미지 zip, tags.json
- **미리보기**: `post_md`에서 TL;DR→요약 치환 후 `_markdown_image_paths_to_data_urls` 적용해 `st.markdown`으로 렌더링
- **Notion 저장**: 메타데이터 구성 후 `save_to_notion(post_md, parsed_md, assets_dir, tags_list, metadata, ..., doc_id)` 호출, 성공 시 공개 URL 안내(비공개 저장소 시 이미지 미표시 가능성)

---

## 4. 핵심 규칙·정책

### 4.1 포트폴리오 문서 구조 (Notion/웹 동일)

- Title → One-line Summary → What I Built → Key Results (No raw tables) → Representative Visuals (Max 2~3) → What I Learned / Engineering Insight → Tech Stack → Suggested Tags
- 금지: 원문 근거/과제 목표/Table X/표 전체, raw OCR 수치, **/__, [Missing image: ...]

### 4.2 이미지

- **경로**: 항상 `assets/{doc_id}/filename` (doc_id 있음). flat `assets/filename` 은 fix_image_paths/normalize_standalone_image_paths에서 통일
- **Notion**: URL 없으면 이미지 블록 생성 안 함, 다음 줄이 캡션이면 그 줄도 스킵; 본문 이미지는 최대 3개
- **미리보기**: `![](...)` 를 로컬 파일 읽어 base64 데이터 URL로 치환

### 4.3 Notion

- 저장 시 **새 페이지 생성**이 기본, `reuse_page_id` 있으면 **purge_children** 후 append
- DB 이름(“Blind Spot Logs” 등)은 코드에서 사용하지 않음 → Notion에서 “교내 프로젝트 정리” 등으로 이름 변경해도 동작 동일

---

## 5. 환경 설정 요약

- **필수**: `UPSTAGE_API_KEY`, (Notion 사용 시) `NOTION_TOKEN` 또는 `NOTION_API_KEY`, `NOTION_PORTFOLIO_DB_ID` 또는 `NOTION_DATABASE_ID`
- **이미지 공개 표시(Notion)**: `GITHUB_TOKEN`(또는 `gh auth token`) + `GITHUB_IMAGE_REPO` **공개** 저장소 권장
- **선택**: `UPSTAGE_DOCUMENT_MAX_BYTES`, `UPSTAGE_DOCUMENT_PARSE_TIMEOUT`, `GITHUB_IMAGE_BRANCH`, `STORAGE_PROVIDER`, `STORAGE_PUBLIC_BASE_URL`

---

## 6. 테스트 (tests/)

- **test_upload_doc_scope_and_notion_isolation.py**: doc_id별 업로드 경로, image_url_map 격리, purge 후 append, body_md 경로 형식
- **test_notion_image_placeholder_restore.py**: placeholder → `![](assets/...)` 치환, doc_id 시 스코프 경로
- **test_markdown_to_blocks_image_cases.py**: 이미지 라인 파싱, resolve_key, 캡션 흡수
- **test_ocr_numeric_downgrade.py**: ocr_numeric_downgrade 모듈 (파이프라인에서는 미사용, 테스트만 존재)
- **test_document_parse_placeholder.py**: elements → raw_md → replace_image_placeholders 흐름
- **test_notion_layout.py**: markdown_to_blocks 레이아웃

---

## 7. 파일·디렉터리 요약

| 경로 | 역할 |
|------|------|
| `config.py` | 환경 변수 및 API/저장소 설정 |
| `upstage_client.py` | Document Parse, Solar API 호출 |
| `image_processor.py` | 이미지 저장, placeholder 치환 |
| `solar_prompts.py` | 포트폴리오/README/LinkedIn 프롬프트 |
| `pipeline.py` | run_pipeline, fix_image_paths, normalize_standalone_image_paths, generate_followup |
| `tag_extractor.py` | post.md에서 Suggested Tags 추출 |
| `storage_client.py` | GitHub 이미지 업로드, Raw URL 반환 |
| `notion_api_client.py` | Notion 페이지/블록 API, markdown_to_blocks, 이미지 URL 해석 |
| `notion_saver.py` | 이미지 업로드, body_md 정규화, Notion 저장 오케스트레이션 |
| `app.py` | Streamlit UI, 미리보기 base64 치환, Notion 저장 호출 |
| `ocr_numeric_downgrade.py` | OCR 숫자 블록 처리 (현재 파이프라인에서 미사용, 테스트용) |

이 명세표는 위 모듈과 함수 단위로 **실제 구현된 동작**을 기준으로 작성되었습니다.
