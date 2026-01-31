# 레이아웃 보존 검증 보고서

## 1) Notion 본문 block sequence를 만드는 입력

**결론: 입력은 반드시 `parsed_md`이다. `post_md`는 본문 레이아웃에 사용되지 않는다.**

**근거 (코드 위치):**

- `notion_saver.py` 206–207행:
```python
# 4. 본문 블록 추가 — parsed_md 기준으로 레이아웃 보존 (이미지 위치 = 원본 PDF 순서)
content_blocks = notion.markdown_to_blocks(parsed_md, image_url_map=resolved_image_urls)
```
- 본문 블록을 만드는 `markdown_to_blocks`의 첫 인자는 **`parsed_md`** 한 개뿐이며, `post_md`는 인자로 전달되지 않음.
- `post_md` 사용처는 170–173행의 **Summary(TL;DR) 추출**뿐:
```python
# TL;DR 추출 (post_md만 사용, 레이아웃은 parsed_md 기준)
if "## TL;DR" in post_md:
    tldr_section = post_md.split("## TL;DR")[1].split("##")[0].strip()
```

→ **기준 1 충족: 본문 block sequence 입력 = parsed_md.**

---

## 2) parsed_md placeholder 위치 기준 interleaving 보장

**결론: A, IMG1, B, IMG2, C 형태가 코드로 보장된다.**

**근거 (코드 위치):**

- `notion_api_client.py` 110–226행 `markdown_to_blocks`:
  - `markdown.split("\n")`으로 **줄 단위**로만 순회.
  - 각 줄이 `![...](path)` 형태면 **그 시점에** `blocks.append(create_image_block(...))`로 이미지 블록 1개 추가.
  - 그 외 줄은 heading/paragraph/리스트/코드 등으로 블록 1개 추가.
  - **한 리스트 `blocks`에 순서대로 append**하므로, 마크다운에서 “문단–이미지–문단–이미지–문단” 순서가 그대로 블록 시퀀스가 됨.
- “텍스트 전부 먼저 + 이미지 전부 나중”으로 나누어 append하는 코드는 없음. 본문 블록은 위 `content_blocks` 한 번만 `append_blocks`로 추가됨 (`notion_saver.py` 207–209행).

→ **기준 2 충족: parsed_md의 이미지 등장 위치 = Notion image block이 텍스트 블록 사이에 끼어드는 interleaved 구조.**

---

## 3) 이미지 매핑 (구체적 설명)

### parsed_md에서 이미지 링크 → lookup key 추출

**위치:** `notion_api_client.py` 195–201행.

- 마크다운 한 줄이 `![alt](path)` 형태로 매칭되면 `path`를 사용.
- **path가 `upstage://image/...`인 경우:**
  - `resolve_key = path.replace("upstage://image/", "").strip()`  
  → 예: `upstage://image/fig_1` → `resolve_key = "fig_1"` (Document Parse 이미지 id).
- **그 외 (일반 경로):**
  - `resolve_key = os.path.basename(path)`  
  → 예: `assets/img_001.png` → `resolve_key = "img_001.png"` (filename).

### image_url_map에서 URL 찾기

- `image_url = image_url_map.get(resolve_key)`로 URL 조회.
- `image_url_map`에는 다음이 들어감 (`notion_saver.py` 63–88행):
  1. **filename → url:** `assets_dir`에서 업로드한 파일의 `os.path.basename(image_path)` → `public_url`.
  2. **id → url (upstage용):** `image_map`(id → 상대경로)이 있으면,  
     `rel_path`에 대해 `fname = os.path.basename(rel_path)`로 filename을 구하고,  
     `fname in image_urls`일 때 `resolved_image_urls[img_id] = image_urls[fname]`로 id → url 추가.

따라서:

- `![](assets/img_001.png)` → `resolve_key = "img_001.png"` → `image_url_map["img_001.png"]`로 URL 조회.
- `![](upstage://image/fig_1)` → `resolve_key = "fig_1"` → `image_url_map["fig_1"]`로 URL 조회 (pipeline에서 `image_map`으로 id→경로를 넘기고, notion_saver에서 id→url로 확장).

→ **기준 3 충족: filename 추출 규칙, URL lookup, upstage://image/... 처리 모두 코드로 구현됨.**

---

## 4) 테스트 존재 및 통과

### 테스트 코드 존재

- **파일:** `tests/test_notion_layout.py`
- **클래스:** `TestNotionLayoutPreservation`
- **테스트 1:** `test_blocks_sequence_is_interleaved_from_parsed_md`  
  - 입력: parsed_md = "A paragraph" + `![](assets/img_001.png)` + "B paragraph" + `![](assets/img_002.png)` + "C paragraph"  
  - 기대: blocks 순서 = paragraph(A) → image(img_001) → paragraph(B) → image(img_002) → paragraph(C)  
  - 검증: `_block_type`, `_paragraph_content`, `_image_caption_or_url`로 5개 블록의 type과 내용을 순서대로 assert.
- **테스트 2:** `test_no_text_then_all_images_at_end`  
  - “텍스트 먼저 + 이미지 몰아넣기”가 아님을 검증 (마지막 블록이 paragraph, 중간에 image).

### 테스트 실행 및 통과 로그

```text
$ NOTION_TOKEN=test NOTION_PORTFOLIO_DB_ID=test-db-id python3 -m unittest tests.test_notion_layout -v

test_blocks_sequence_is_interleaved_from_parsed_md (tests.test_notion_layout.TestNotionLayoutPreservation.test_blocks_sequence_is_interleaved_from_parsed_md)
parsed_md 예시대로 블록 순서가 paragraph(A) -> image(001) -> paragraph(B) -> image(002) -> paragraph(C) 여야 함. ... ok
test_no_text_then_all_images_at_end (tests.test_notion_layout.TestNotionLayoutPreservation.test_no_text_then_all_images_at_end)
'텍스트 먼저 + 이미지 몰아넣기'가 아님을 검증: 이미지가 중간에 끼어 있어야 함. ... ok

----------------------------------------------------------------------
Ran 2 tests in 0.056s

OK
```

→ **기준 4 충족: interleaving 테스트가 코드에 존재하고, 위 로그대로 통과함.**

---

## 최종 결론

**레이아웃 보존 구현됨.**

**근거 요약:**

1. **입력 = parsed_md:** Notion 본문 block sequence는 `markdown_to_blocks(parsed_md, ...)`로만 생성되며, `post_md`는 본문 레이아웃에 사용되지 않음.
2. **Interleaving 보장:** `markdown_to_blocks`가 parsed_md를 줄 단위로 순회하며, 이미지 줄이 나오는 위치에 그대로 이미지 블록을 append하므로, A–IMG1–B–IMG2–C 형태가 코드로 보장됨.
3. **이미지 매핑:** filename은 `os.path.basename(path)`, upstage는 `path.replace("upstage://image/", "").strip()`으로 key를 만들고, `resolved_image_urls`(filename + id → url)로 URL을 조회하며, upstage://image/... 형태도 처리함.
4. **테스트:** `tests/test_notion_layout.py`에 interleaving 테스트가 있고, 위 명령으로 실행 시 2 tests, OK로 통과함.
