# Document Parse 응답 처리 시 placeholder 보존 검증

## 1) raw_md/parsed_md를 만들 때 elements를 어떤 기준으로 결합하는가?

**기준: elements 배열의 순서를 그대로 유지하며, 각 요소가 기여하는 “마크다운 조각”을 순서대로 이어 붙인다.**

- **이전(위험) 방식:** `content.markdown`이 있는 요소만 `raw_md_parts`에 append → **text 요소만 join**하면 figure 요소가 content를 안 넣어줄 때 **placeholder가 빠짐**.
- **현재(보장) 방식** (`pipeline.py` 55–82행):
  1. **모든 요소를 `elements` 순서대로** 순회.
  2. **텍스트/문서 요소:** `content.markdown`(또는 html/text)가 있으면 그 문자열을 그대로 `raw_md_parts`에 append.
  3. **figure/chart/image 요소:** `category in ["figure","chart","image"]`이고 `base64_encoding`이 있으면:
     - `images` 리스트에 추가하고,
     - **이 요소가 `content.markdown`(등)을 전혀 기여하지 않았을 때만**  
       `![](upstage://image/{img_id})` 를 **그 자리에서** `raw_md_parts`에 append.
  4. `raw_md = "\n\n".join(raw_md_parts)` 로 **한 번에** 결합.

→ **text만 join하는 것이 아니라, figure 요소도 “content가 없으면 placeholder 주입”으로 elements 순서대로 interleave 된다.**

---

## 2) figure/image 요소의 markdown(placeholder)을 raw_md에 포함시키는가? interleave인가?

**포함시킨다. elements 순서 그대로 interleave 한다.**

- **포함 방식**
  - API가 figure 요소에 `content.markdown`(예: `![](upstage://image/fig_1)`)을 넣어 주면 → 그대로 append.
  - API가 figure 요소에 content를 안 넣어 주면 → **코드에서** `![](upstage://image/{img_id})` 를 append.
- **interleave 보장**
  - `for elem in elements:` 한 번만 돌면서,  
    (1) 해당 요소의 markdown이 있으면 append,  
    (2) 해당 요소가 figure/image이면 이미지 리스트에 넣고, content가 없었을 때만 placeholder append.  
  → **한 리스트 `raw_md_parts`에 “텍스트 조각 / placeholder”가 elements 순서대로 쌓이고**,  
  → `"\n\n".join(raw_md_parts)` 로 합치므로 **순서가 그대로 유지된다.**

**코드 위치:** `pipeline.py` 55–82행 (for elem in elements → markdown append 또는 figure일 때 placeholder 주입 → join).

---

## 3) Document Parse 샘플 응답 기준 비교 — “placeholder가 살아있음” 증명

### 샘플 응답 (실제 API와 유사한 구조)

```json
{
  "elements": [
    {
      "content": { "markdown": "A paragraph" },
      "category": "text"
    },
    {
      "content": {},
      "category": "figure",
      "id": "fig_1",
      "base64_encoding": "iVBORw0KGgo=",
      "page": 1
    },
    {
      "content": { "markdown": "B paragraph" },
      "category": "text"
    },
    {
      "content": {},
      "category": "image",
      "id": "fig_2",
      "base64_encoding": "iVBORw0KGgo=",
      "page": 1
    },
    {
      "content": { "markdown": "C paragraph" },
      "category": "text"
    }
  ]
}
```

- **elements 순서:** text(A) → figure(fig_1) → text(B) → image(fig_2) → text(C).  
- figure/image 요소는 **content가 비어 있음** (API가 placeholder를 안 넣어주는 경우).

### 현재 코드로 생성되는 raw_md

1. elem0: `content.markdown` = "A paragraph" → append → `raw_md_parts = ["A paragraph"]`
2. elem1: content 없음 → append 안 함. figure이고 base64 있음 → `images`에 fig_1 추가, content 없었으므로 **주입** → append `"![](upstage://image/fig_1)"` → `raw_md_parts = ["A paragraph", "![](upstage://image/fig_1)"]`
3. elem2: "B paragraph" append → `raw_md_parts = [..., "B paragraph"]`
4. elem3: content 없음 → figure와 동일 처리 → append `"![](upstage://image/fig_2)"` → `raw_md_parts = [..., "![](upstage://image/fig_2)"]`
5. elem4: "C paragraph" append → `raw_md_parts = [..., "C paragraph"]`

`raw_md = "\n\n".join(raw_md_parts)` 결과:

```text
A paragraph

![](upstage://image/fig_1)

B paragraph

![](upstage://image/fig_2)

C paragraph
```

### parsed_md (replace_image_placeholders 적용 후, image_map: fig_1→assets/img_001.png, fig_2→assets/img_002.png)

```text
A paragraph

![](assets/img_001.png)

B paragraph

![](assets/img_002.png)

C paragraph
```

### 비교 요약

| 구분 | elements 순서 | raw_md / parsed_md 일부 (placeholder 구간) |
|------|----------------|--------------------------------------------|
| elements | text(A) → figure(fig_1) → text(B) → image(fig_2) → text(C) | — |
| raw_md | — | A paragraph → ![](upstage://image/fig_1) → B paragraph → ![](upstage://image/fig_2) → C paragraph |
| parsed_md | — | A paragraph → ![](assets/img_001.png) → B paragraph → ![](assets/img_002.png) → C paragraph |

→ **placeholder가 elements 순서 그대로 raw_md에 포함되고, parsed_md에서도 같은 순서로 assets 경로로 치환되어 “placeholder가 살아있음”이 보장된다.**

**테스트:** `tests/test_document_parse_placeholder.py`의 `test_figure_without_content_gets_injected_placeholder`가 위와 동일한 샘플 elements로 raw_md/parsed_md 순서와 placeholder 존재를 assert함.

---

## 추가 수정 사항 (placeholder 보존을 위해 적용된 변경)

1. **pipeline.py**  
   - figure/chart/image 요소에 `content.markdown`(등)이 **없을 때** 해당 위치에 `![](upstage://image/{img_id})` 를 **주입**하도록 변경.  
   - elements 순서대로 한 리스트에 쌓은 뒤 `"\n\n".join`만 하므로 **interleave 보장**.

2. **image_processor.py**  
   - `replace_image_placeholders`에서 upstage URL 패턴의 **캡처 그룹**: group1=alt, group2=id.  
   - **image_id를 group(2)로 조회**하도록 수정 (기존 group(1)은 alt라서 id lookup이 잘못되던 부분 수정).

---

## 결론

**placeholder 보존이 보장됨.**

- **근거:**  
  1) elements를 **“텍스트만 join”이 아니라, elements 순서대로 markdown 또는 placeholder를 append한 뒤 join**하는 방식으로 결합함.  
  2) figure/image 요소는 **content가 있으면 그대로, 없으면 `![](upstage://image/{id})` 를 그 자리에 주입**해 raw_md에 포함시키고,  
  3) 위 Document Parse 샘플에 대해 **raw_md/parsed_md 일부(placeholder 구간)가 elements 순서와 일치**함을 코드와 테스트로 확인함.
