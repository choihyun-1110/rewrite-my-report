# Notion 저장 레이아웃 보존 검증 보고서

## 검증 기준별 답변

### 1. 원본 PDF(Document Parse 결과)에서 이미지 위치 정보를 코드에서 **명시적으로** 사용하는가?

**결론: 아니다.**

- **Document Parse 응답** (`pipeline.py` 48–76행): `elements` 배열을 순회하며
  - `content.markdown`가 있는 요소만 `raw_md_parts`에 추가
  - `category in ["figure", "chart", "image"]`인 요소는 별도 리스트 `images`에만 추가
- **위치 정보 사용 방식**:
  - `elements`의 **순서**나 **layout/coordinates/anchor** 같은 필드는 사용하지 않음.
  - `raw_md = "\n\n".join(raw_md_parts)"`로 **텍스트 요소의 markdown만** 이어 붙임.
  - 이미지 “위치”는 **API가 이미 markdown 안에 넣어 준 placeholder**(예: `![](upstage://image/xxx)`)에만 의존함. 즉, API가 한 요소의 markdown에 placeholder를 포함해 주는 경우에만 위치가 보존됨.
- **단순 “이미지 전부 append”가 아님**은 만족: Notion 측에서는 `post_md`를 **한 줄씩** 파싱하며, 이미지 줄을 만날 때마다 **그 자리**에 이미지 블록을 넣고, 맨 뒤에 이미지를 몰아서 append하는 코드는 제거된 상태임.

하지만 **“원본 PDF에서 이미지가 등장하던 위치 정보를 명시적으로 사용”**하는지는 **미만족**:  
코드 어디에서도 Document Parse의 layout/순서/좌표 등을 **별도 데이터로 읽어서** 사용하지 않음.

---

### 2. post.md / parsed.md의 이미지 placeholder를 기준으로, 해당 위치에 Notion image block이 텍스트 블록 사이에 삽입되는가?

**결론: 예 (post.md 기준으로만).**

- **Notion에 쓰는 본문의 출처**: `notion_saver.py` 196행에서 **`post_md`만** 사용함.  
  `parsed_md`는 Notion 블록 구성에 **전혀 사용되지 않음**.
- **삽입 로직** (`notion_api_client.py` 110–224행 `markdown_to_blocks`):
  - `post_md`를 `"\n".split("\n")`으로 줄 단위 순회.
  - 각 줄이 `![...](path)` 형태로 매칭되면, **그 순서 그대로** `blocks` 리스트에 `create_image_block(...)` 결과를 append.
  - 나머지 줄은 heading/paragraph/code 등으로 변환되어 같은 `blocks`에 append.
- 따라서 **post.md에 있는 `![](assets/xxx.png)` 등 placeholder의 등장 순서**가 곧 Notion에서의 이미지 블록 순서이며, 텍스트 블록과 이미지 블록은 **한 시퀀스(`blocks`) 안에서 interleaved**로 쌓임.

**주의**: 이게 “원본 PDF/parsed.md의 위치”와 일치하는지는 **post.md를 어떻게 만드느냐**에 전적으로 의존함. 현재는 **post.md = LLM(Solar) 출력**이므로, LLM이 이미지 위치를 바꾸면 원본 레이아웃과 어긋남.

---

### 3. Notion 페이지 실제 구조: (A) vs (B)

**결론: (B) 텍스트–이미지–텍스트가 섞인 interleaved 구조.**

- **이유**:  
  `content_blocks = notion.markdown_to_blocks(post_md, image_url_map=image_urls)` 한 번으로 **하나의 리스트**를 만들고, 이 리스트를 `notion.append_blocks(page_id, content_blocks)`로 **한 번에** 추가함.  
  리스트를 만드는 과정이 “먼저 텍스트 블록만 넣고, 그 다음 이미지 블록을 전부 append”가 아니라, **markdown 줄 순서대로** 텍스트/이미지 블록을 번갈아 넣는 방식이므로, Notion 상에서도 (B) 구조가 됨.

---

### 4. Interleaved 구조의 기준: 무엇으로 동작하는가?

**결론: “Markdown 파싱 단계에서 이미지 위치를 유지”에 해당.**

- **Document Parse의 layout/anchor 정보**: 사용하지 않음.
- **텍스트 분할 시 image placeholder 기준 split**: 사용하지 않음.  
  (placeholder로 문자열을 split한 뒤 조각을 재조합하는 로직 없음.)
- **실제 동작**:
  - **post.md**를 **줄 단위**로 순회하면서,
  - 각 줄이 이미지 문법이면 → 그 자리에서 이미지 블록 1개 push,
  - 그 외면 → 해당하는 텍스트 블록(헤딩/문단/리스트/코드 등) 1개 push.
  - 즉, **post.md라는 마크다운 문자열의 줄 순서**가 곧 “이미지 위치”이며, **마크다운 파싱 단계에서 이미지가 나온 위치를 그대로 블록 시퀀스에 반영**하는 방식임.

---

### 5. “이미지 전부 업로드”와 “레이아웃 보존(interleaving)”의 충돌 여부

**결론: 코드 레벨에서 충돌하지 않도록 처리됨.**

- **이미지 업로드** (`notion_saver.py` 64–77행):  
  `assets_dir` 내 이미지 파일을 순회하며 `image_urls[filename] = public_url` 형태로 **맵**만 채움.  
  업로드 순서(파일 시스템/디렉터리 순서)는 **Notion 블록 순서와 무관**.
- **Notion 블록 순서**:  
  `markdown_to_blocks(post_md, image_url_map=image_urls)`에서 **post.md의 줄 순서**로만 결정됨.  
  이미지는 `image_url_map.get(filename)`으로 URL만 조회할 뿐, “업로드 순서”는 사용하지 않음.
- 따라서 “업로드 순서 ≠ 삽입 순서”로 인한 레이아웃 깨짐은 없음.

---

## 산출: 이미지 삽입 순서 결정 로직 및 블록 시퀀스 조립

### 이미지 삽입 순서 결정 로직

- **결정 주체**: `post_md`(Solar LLM 출력)에 이미지가 **등장하는 줄의 순서**.
- **코드 위치**:  
  `notion_api_client.py` 110–224행 `markdown_to_blocks(self, markdown, image_url_map)`.
- **의사코드**:
  - `lines = markdown.split("\n")`
  - `for each line in lines`:
    - if 줄이 `![...](path)` 형태:
      - `filename = os.path.basename(path)`
      - `image_url = image_url_map.get(filename)`
      - 있으면 `blocks.append(create_image_block(image_url, caption))`
    - else:
      - heading/paragraph/code 등으로 블록 생성 후 `blocks.append(...)`
  - 반환: `blocks` (텍스트 블록과 이미지 블록이 줄 순서대로 섞인 리스트)

### 텍스트 블록과 이미지 블록을 하나의 시퀀스로 조립하는 부분

- **조립 위치**:  
  `notion_api_client.py` 110–224행 `markdown_to_blocks` 전체.  
  여기서 만든 `blocks`가 곧 “하나의 시퀀스”.
- **Notion 반영 위치**:  
  `notion_saver.py` 196–199행:
  - `content_blocks = notion.markdown_to_blocks(post_md, image_url_map=image_urls)`
  - `notion.append_blocks(page_id, content_blocks)`  
  → 동일한 `content_blocks` 순서 그대로 페이지에 append.

---

## 기준 미달 시: 무엇이 부족한지, 어디서 정보가 소실되는지

### 1번 미달: “원본 PDF 위치 정보를 명시적으로 사용”하지 않음

- **왜 안 되는지**:  
  Document Parse의 **elements 순서**, **layout/coordinates/anchor** 등을 읽어서 “이미지 N번은 문단 M 다음”처럼 **명시적으로** 쓰는 코드가 없음.
- **정보 소실 구간**:  
  - **가능한 소실 1**: API가 요소를 [텍스트1, 그림1, 텍스트2, …]처럼 주는데, 우리가 `raw_md_parts`에는 **텍스트 요소의 markdown만** 넣고 `join`하면, figure 요소는 markdown에 포함되지 않아 **위치 정보가 빠질 수 있음**.  
  - **가능한 소실 2**: 설령 `raw_md`/`parsed_md`에 placeholder 순서가 올바르더라도, Notion에 쓸 때 사용하는 건 **post_md**뿐이라, **Solar가 이미지 위치를 바꾸거나 끝으로 몰면** 원본 레이아웃이 깨짐.

### 고치려면 필요한 변경 (방향)

- **Document Parse → Markdown 정규화**:
  - `elements` 배열의 **순서**를 보존해서, “텍스트 요소”와 “이미지 요소”를 **interleave**한 뒤 하나의 markdown 문자열을 만드는 단계가 필요.
  - 또는 API가 주는 **layout/coordinates**가 있다면, 그걸 기준으로 “어느 문단 다음에 어떤 이미지”를 명시적으로 계산해 markdown/메타데이터에 반영.
- **Notion append**:
  - **옵션 A**: 지금처럼 `post_md`만 쓰되, Solar 프롬프트에서 **“원문(parsed_md)에서 이미지가 나오는 순서와 위치를 그대로 유지하라”**고 명시하고, 필요 시 `parsed_md`의 이미지 순서를 검증/보정하는 후처리 추가.
  - **옵션 B**: Notion 블록을 만들 때 **parsed_md**(원문)의 이미지 등장 순서/위치를 기준으로 하고, post_md는 “텍스트만”으로 보거나, parsed_md와 post_md를 합쳐서 “위치 정보는 parsed_md, 문장은 post_md”처럼 조합하는 설계로 단계를 나누어 수정.

---

## 최종 결론 (구현 반영 후)

**레이아웃 보존이 구현됨.**

- Notion 본문 블록 시퀀스는 **parsed_md**를 기준으로 생성함 (`notion_saver.py`: `markdown_to_blocks(parsed_md, ...)`).
- post_md는 레이아웃 결정에 사용하지 않으며, Summary(TL;DR) 추출에만 사용함.
- 이미지 placeholder 순서/위치는 parsed_md의 등장 순서대로 Notion image block이 끼어드는 **interleaved** 구조로 보존됨.
- 검증: `tests/test_notion_layout.py`에서 `parsed_md` 예시로 paragraph(A) -> image(img_001) -> paragraph(B) -> image(img_002) -> paragraph(C) 순서를 assert함.

---

## (이하: 구현 전 검증 시 결론)

**레이아웃 보존이 구현되어 있지 않음 (아래 사유).**

1. **검증 기준 1 미충족**:  
   원본 PDF(Document Parse 결과)에서 이미지가 등장하던 **위치 정보를 코드에서 명시적으로 사용하지 않음**.  
   elements의 layout/순서/좌표를 읽어서 “이미지 위치”로 쓰는 부분이 없고, API가 markdown 안에 넣어 주는 placeholder 순서에만 의존하며, 그 마크다운도 **Notion에는 사용하지 않고** post_md(LLM 출력)만 사용함.

2. **최종 Notion 레이아웃의 결정 요인**:  
   **post.md** 한 개.  
   즉, **Solar LLM이 이미지를 어디에 두느냐**에 전적으로 의존하므로, LLM이 이미지를 본문 끝으로 몰거나 순서를 바꾸면 **원본 PDF의 맥락/위치와 무관한 구조**가 됨.

3. **현재 구현이 보장하는 것**:  
   “post.md에 이미지가 **글 사이사이에** 어떻게 배치되어 있든, 그 순서대로 Notion에 텍스트–이미지가 섞여 나온다”는 점만 보장함.  
   “원본 PDF에서의 이미지 등장 맥락/위치를 정확히 반영한다”는 것은 **보장하지 않음**.
