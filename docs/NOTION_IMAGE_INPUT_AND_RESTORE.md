# Notion 이미지 미삽입 원인 규명 및 수정

## 0) 제품 방향 (현재)

**Notion stores presentation-grade content, not raw OCR logs.**

- **Notion 본문 = post_md** (LLM이 재작성한 블로그/포트폴리오용 요약본). 웹 UI와 동일한 “이쁜 버전”을 저장.
- **parsed_md** (Document Parse/OCR 원문)는 본문에 사용하지 않음. 요약 섹션 추출 시 post_md와 함께 사용할 뿐.
- **이미지:** 본문에 최대 4장만 유지, 나머지는 “[추가 이미지는 생략되었습니다.]”로 대체.
- **OCR 억제:** Solar 프롬프트에서 측정 테이블/숫자 덤프를 본문에 넣지 말고, 요약 문장 또는 대표 이미지로만 표현하도록 지시.

---

## 1) 원인 규명 — markdown_to_blocks에 들어가는 입력 (과거 참고)

- **현재 입력 소스:** `notion_saver.save_to_notion`에서는 **post_md**를 본문 소스로 사용함.
  - `body_md = post_md`, `content_blocks = notion.markdown_to_blocks(body_md, ...)`.
- **(과거)** 이전에는 parsed_md를 본문 소스로 사용했음. 아래 “[Image: image]” 등은 그 시절 기준 설명.

- **"[Image: image]"가 보이는 경우:**
  - Document Parse API가 일부 요소에서 `content.markdown`에 `[Image: image]` 또는 `/image/placeholder` 형태를 넣어 주면, `replace_image_placeholders`는 **upstage://image/<id>** 만 치환하므로 해당 문자열이 **parsed_md에 그대로 남음**.
  - 이 상태로 `markdown_to_blocks`에 넣으면 `![](...)` / `<img src="...">` 규칙에 걸리지 않아 **이미지 블록이 아니라 paragraph로만 들어감**.

- **로그로 확인:**
  - `notion_saver`에서 `logger.info`로 다음을 남김:
    - Notion body input = parsed_md (길이), placeholder 정규화 후 (길이)
    - `Contains '[Image: image]'` / `'/image/placeholder'` 여부, Snippet
  - `parsed_md`에 위 잘못된 포맷이 있으면 콘솔에  
    `[Notion] 본문에 '[Image: image]' 또는 '/image/placeholder'가 있어 placeholder를 ![](assets/<filename>)로 복원했습니다. (원인 규명: 입력은 parsed_md 기반)`  
    가 한 줄 출력됨.

## 2) 수정 사항

### A. Notion 본문에 들어가는 markdown = parsed_md

- 이미 그렇게 되어 있음: `body_md`는 **parsed_md**를 `_normalize_image_placeholders_for_notion(parsed_md, ordered_filenames)` 로 복원한 결과이며, 이걸로 `markdown_to_blocks`를 호출함.

### B. parsed_md가 가져야 할 이미지 토큰

- 정상: `![](assets/<filename>)` 또는 `![](upstage://image/<id>)`
- 문제: `[Image: image]`, `![...](/image/placeholder)` 등은 **markdown_to_blocks의 이미지 규칙에 걸리지 않음** → **복원 단계에서 위 정상 토큰으로 치환**하도록 추가함.

### C. 포맷 복원 로직 (`_normalize_image_placeholders_for_notion`)

- **위치:** `notion_saver.py`
- **동작:**
  1. `[Image: image]` / `[Image: xxx]` → 등장 순서대로 `![](assets/<filename>)` 로 치환 (ordered_filenames 사용).
  2. `![](/image/placeholder)` / `![...](/image/placeholder)` → 마찬가지로 `![](assets/<filename>)` 로 치환.
- **ordered_filenames (문서 레이아웃 순서 고정):**  
  `doc_order_image_filenames`가 있으면 그대로 사용 (pipeline에서 Document Parse elements 순회 시 figure/image마다 `filename`을 순서대로 넣은 리스트).  
  없으면 `image_map` → `[os.path.basename(p) for p in image_map.values()]`, 둘 다 없으면 `list(image_urls.keys())`.
- **pipeline:** `doc_order_image_filenames = [os.path.basename(image_map[img["id"]]) for img in images if img["id"] in image_map]` 로 elements 순서와 1:1 리스트를 만들고 `result["doc_order_image_filenames"]`로 전달.

## 3) 테스트

- **파일:** `tests/test_notion_image_placeholder_restore.py`
- **내용:**
  - `test_normalize_image_image_to_assets_placeholder`: `[Image: image]` → `![](assets/img_001.png)` 치환 확인.
  - `test_normalize_multiple_image_image_in_order`: 여러 개 `[Image: image]`가 등장 순서대로 filename에 매칭되는지 확인.
  - `test_normalize_image_placeholder_path`: `![](/image/placeholder)` → `![](assets/...)` 치환 확인.
  - `test_markdown_to_blocks_produces_image_after_restore`: 복원된 markdown으로 `markdown_to_blocks` 호출 시 image block 생성 여부.
  - `test_full_flow_image_image_then_normalize_then_blocks`: `[Image: image]` 포함 문자열 → 정규화 → `markdown_to_blocks` → image block 존재 assert.

실행:  
`NOTION_TOKEN=test NOTION_PORTFOLIO_DB_ID=test-db-id python3 -m unittest tests.test_notion_image_placeholder_restore -v`  
→ 5 tests OK.

## image_url_map lookup 실패 (missing image)

- **동작:** `![](assets/<filename>)`로 복원했는데 URL이 없으면 이미지 블록을 만들지 않고 **경고 문단** `[Missing image: <filename>]` 블록으로 대체.
- **기록:** `markdown_to_blocks(..., missing_images_out=list)` 에 실패한 filename/id를 append. `notion_saver`는 이 리스트를 `upload_report["missing_images"]`에 넣어 반환.
- **테스트:** `test_missing_image_produces_warning_block` — URL 없는 이미지 시 paragraph에 `[Missing image: unknown.png]` 포함 및 `missing_images_out`에 `unknown.png` 기록.

---

## OCR 숫자/측정 블록 강등(downgrade) 및 토글(toggle)

회로/측정 PDF에서 “이미지로 넣은 표/수치 스샷”이 Document Parse로 OCR되어 본문에 숫자 테이블 폭탄으로 들어가는 문제를 완화.

### 휴리스틱 (OCR 숫자 블록 감지)

- **1)** 과학표기(e-/e+) 다수 + delay/rise/fall/targ/trig/transient/measure 등 키워드
- **2)** 파이프 테이블 3줄 이상 + ns/mV/V/A 단위 빈도 높음
- **3)** 숫자/기호 비율이 높고 단위 존재

### 모드

- **downgrade (기본):** 트리거된 연속 블록을 제거하고, 해당 위치에 `![](assets/{doc_id}/{next_image_filename})` 삽입. image placeholder는 `ordered_filenames` 순서대로 소비.
- **toggle:** 트리거된 블록을 `:::toggle Measurements (OCR)::: ... :::endtoggle` 로 감싸서 Notion에서 접기 블록으로 변환.
- **비활성:** `ocr_numeric_mode=""` 이면 OCR 강등/토글 미적용.

### 처리 순서

1. `downgrade_ocr_numeric_blocks(parsed_md, ordered_filenames, doc_id, mode)` → (pre_md, ordered_remaining)
2. `_normalize_image_placeholders_for_notion(pre_md, ordered_remaining, ...)` → body_md

### Notion toggle 파싱

- `markdown_to_blocks`에서 `:::toggle Title::: ... :::endtoggle` 를 Notion toggle 블록으로 변환. 내부는 code 블록(plain text)으로 children에 넣음.

### 테스트

- `tests/test_ocr_numeric_downgrade.py`: 휴리스틱 감지, downgrade/toggle 치환, 자연어 본문 미손상, toggle 블록 생성.

---

## 업로드 경로 doc_id 포함 및 Notion 페이지 격리 (이미지 겹침 방지)

### 원인

- **원격 URL이 doc_id 없이 고정** (`.../assets/img_001.png`) → 문서마다 같은 파일명이 덮어쓰거나 이전 문서 URL을 참조.
- **Notion 페이지 재사용 시 append만** 하면 기존 children이 남아 이전 문서 블록이 섞여 보임.

### 수정 사항

1. **업로드 dest_path / public_url에 doc_id 포함**
   - `storage_client.GitHubStorageClient.upload_image(image_path, path_in_repo=...)`
   - `path_in_repo` 없으면 `assets/{filename}` (기존), 있으면 `assets/{doc_id}/{filename}`.
   - `notion_saver`에서 업로드 시 `path_in_repo=assets/{doc_id}/{filename}` 전달 → GitHub Raw URL에 `/assets/{doc_id}/...` 포함.

2. **image_url_map 키**
   - 우선: `assets/{doc_id}/{fname}` → public_url
   - fallback: `fname` → public_url (최후 수단)

3. **캐시 무력화**
   - Notion/브라우저 캐시로 이전 문서 이미지가 남지 않도록, doc_id가 있을 때 공개 URL 끝에 `?v={doc_id}` 추가.
   - raw.githubusercontent.com은 쿼리스트링을 허용하므로 동작에 문제 없음.

4. **상태 격리**
   - `save_to_notion()` 진입 시 `image_urls` / `resolved_image_urls` / `ordered_filenames` 등 문서별 상태를 **매 호출마다 새로 생성** (이전 문서와 절대 섞이지 않음).
   - doc_id 없이 이미지 업로드 시 경고 로그: `[NOTION] doc_id가 없이 이미지 업로드 시도 — 경로가 assets/img_###.png로 고정되어 문서 간 충돌 가능`

5. **Notion 페이지**
   - **기본:** 매번 새 페이지 생성 (`reuse_page_id` 없음).
   - **재사용 시:** `reuse_page_id` 지정하면 `purge_children(page_id)` 후 append.

### 로그로 검증

로거 레벨을 INFO로 두면 다음 로그로 동작을 확인할 수 있음.

- **업로드:**  
  `[UPLOAD] doc_id=646e16ede739 dest_path=assets/646e16ede739/img_001.png public_url=https://raw.githubusercontent.com/.../assets/646e16ede739/img_001.png`
- **Notion 새 페이지:**  
  `[NOTION] page_id=... doc_id=646e16ede739 blocks=... images=... reuse_page=False`
- **Notion 재사용:**  
  `[NOTION] reuse_page_id=... purge completed, appending blocks`

### 테스트

- `tests/test_upload_doc_scope_and_notion_isolation.py`
  - **test_image_path_is_namespaced_by_doc_id**: doc_id=A, doc_id=B일 때 업로드 path/URL이 각각 A, B로 분리되고 서로 같지 않음.
  - **test_no_state_leak_between_runs**: A 처리 후 B 처리 시 B에 전달되는 image_url_map에 A의 doc_id/URL이 없음.
  - **test_markdown_contains_correct_public_urls** / **test_markdown_flat_path_rejected_when_doc_id_expected**: normalize 결과에 `assets/{doc_id}/...` 포함, flat `assets/img_001.png` 없음.
  - 업로드 path_in_repo에 doc_id 포함 → URL에 `/assets/{doc_id}/...` 포함.
  - `save_to_notion` 기본 시 `create_page` 호출, `reuse_page_id` 시 `purge_children` 호출.

---

## 결론

- **입력:** Notion 본문 블록을 만드는 입력은 **parsed_md**(복원 후 body_md)이며, post_md가 본문에 쓰이지 않음.
- **원인:** parsed_md에 `[Image: image]` 또는 `/image/placeholder` 형태가 남아 있으면 markdown_to_blocks의 이미지 규칙에 걸리지 않아 이미지 블록이 생성되지 않음.
- **수정:** `_normalize_image_placeholders_for_notion`으로 위 형태를 등장 순서대로 `![](assets/<filename>)` 또는 `![](assets/<doc_id>/<filename>)` 로 치환한 뒤 markdown_to_blocks에 넣어, Notion에 이미지 블록이 생성되도록 함.
- **이미지 겹침 방지:** 업로드 경로·공개 URL에 doc_id 포함, image_url_map doc-scoped 키 우선, URL에 `?v=doc_id` 캐시 무력화, 문서별 상태 매 호출 새로 생성, Notion은 기본 새 페이지(또는 reuse 시 purge 후 append).

### 수용 기준 (Acceptance Criteria)

- PDF A 업로드 후 같은 프로세스에서 PDF B 업로드해도 B의 이미지가 A로 바뀌지 않는다.
- Notion에서 hard refresh 없이도 B의 이미지가 정상 표시된다 (캐시 무력화 `?v=doc_id`).
- GitHub repo의 assets 디렉토리에 문서별 폴더(`assets/{doc_id}/`)가 생기고, 각 폴더에 img_###.png가 들어간다.
