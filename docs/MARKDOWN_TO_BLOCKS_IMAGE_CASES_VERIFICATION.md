# markdown_to_blocks 이미지 파서 케이스 검증

## 케이스별 resolve_key / URL map lookup / 커버 여부

| 케이스 | 입력 | resolve_key | URL map lookup | 커버 |
|--------|------|-------------|----------------|------|
| 1 | `![](./assets/img_001.png)` | `img_001.png` (basename) | ✓ `image_url_map.get("img_001.png")` | ✓ 원래부터 커버 |
| 2 | `![](assets/img 001.png)` | `img 001.png` (공백 포함 basename) | map에 `"img 001.png"` 있으면 ✓, `"img_001.png"`만 있으면 ✗ | ✓ 원래부터 커버 (map 키가 파일명과 일치할 때만) |
| 3 | `![](assets/img_001.png "caption")` | path에서 `"caption"` 제거 후 `img_001.png` | ✓ | ✓ **수정 후** 커버 |
| 4 | `<img src="assets/img_001.png" />` | `img_001.png` (src 추출 후 basename) | ✓ | ✓ **수정 후** 커버 |
| 5 | `![alt text](assets/img_001.png)` | `img_001.png` | ✓ | ✓ 원래부터 커버 |

---

## 1) `![](./assets/img_001.png)`

- **path:** `./assets/img_001.png` (group 2)
- **resolve_key:** `os.path.basename("./assets/img_001.png")` → **`img_001.png`**
- **lookup:** `image_url_map.get("img_001.png")` → **성공** (map에 `img_001.png` 있으면)
- **커버:** ✓ 수정 없이 커버됨

---

## 2) `![](assets/img 001.png)`

- **path:** `assets/img 001.png` (파일명에 공백)
- **resolve_key:** `os.path.basename("assets/img 001.png")` → **`img 001.png`**
- **lookup:**  
  - map에 **`"img 001.png"`** 가 있으면 → **성공**  
  - map에 **`"img_001.png"`** 만 있으면 → **실패** (paragraph로 fallback)
- **커버:** ✓ 원래부터 커버. map 키가 실제 파일명(공백 포함)과 같아야 함.  
  - 공백↔언더스코어 정규화는 하지 않음 (최소 수정 범위).

---

## 3) `![](assets/img_001.png "caption")`

- **원래:** path가 `assets/img_001.png "caption"` 로 잡혀서 `resolve_key` = `img_001.png "caption"` → lookup 실패.
- **수정:** path에서 마크다운 optional title 제거: `re.sub(r'\s+["\'][^"\']*["\']\s*$', '', path).strip()` 적용.
- **수정 후 path:** `assets/img_001.png`
- **resolve_key:** **`img_001.png`**
- **lookup:** ✓ **성공**
- **코드:** `notion_api_client.py` — `img_match` 분기 안에서 path 정규화 한 줄 추가.

---

## 4) `<img src="assets/img_001.png" />`

- **원래:** `![](...)` 패턴만 처리해서 매칭 안 됨 → **paragraph**로 들어감 (커버 안 됨).
- **수정:** 단일 줄이 `<img ...` 로 시작하면 `src="..."` 또는 `src='...'` 를 정규식으로 추출, 그 값으로 resolve.
- **resolve_key:** `os.path.basename("assets/img_001.png")` → **`img_001.png`**
- **lookup:** ✓ **성공**
- **코드:** `notion_api_client.py` — `elif image_url_map and re.match(r'^\s*<img\s', line, re.IGNORECASE):` 분기 추가, `re.search(r'src\s*=\s*["\']([^"\']+)["\']', ...)` 로 src 추출 후 basename으로 lookup.

---

## 5) `![alt text](assets/img_001.png)`

- **path:** `assets/img_001.png` (group 2)
- **resolve_key:** **`img_001.png`**
- **lookup:** ✓ **성공**
- **커버:** ✓ 수정 없이 커버됨

---

## 깨졌던 케이스와 최소 수정 요약

| 케이스 | 깨진 이유 | 최소 수정 |
|--------|-----------|-----------|
| 3 | path에 `"caption"` 이 포함되어 resolve_key가 `img_001.png "caption"` 로 나옴 | path 끝의 optional title 제거: `re.sub(r'\s+["\'][^"\']*["\']\s*$', '', path).strip()` |
| 4 | `<img src="...">` 를 전혀 파싱하지 않음 | 단일 줄 `<img ...>` 인 경우 `src` 속성 추출 후 basename으로 resolve_key 계산 및 image_url_map lookup |

---

## 테스트

**파일:** `tests/test_markdown_to_blocks_image_cases.py`

- `test_case1_relative_path_with_dot_slash` — 케이스 1  
- `test_case2_space_in_filename` — 케이스 2 (map에 `img 001.png` / `img_001.png` 각각일 때 동작)  
- `test_case3_markdown_title_quotes` — 케이스 3  
- `test_case4_html_img_tag` — 케이스 4  
- `test_case5_alt_text` — 케이스 5  

---

## 이미지 URL lookup fallback

- **basename(path) lookup 실패 시** 순차 적용:
  1. `unquote(resolve_key)` 로 URL 디코딩 후 lookup
  2. `resolve_key.replace(" ", "_")` 로 공백→언더스코어 후 lookup
  3. `unquote(resolve_key).replace(" ", "_")` 로 디코딩+공백→언더스코어 후 lookup

**코드:** `notion_api_client.py` — `_resolve_image_url(image_url_map, resolve_key)`  
→ `![](...)` / `<img src="...">` 양쪽에서 `image_url_map.get(resolve_key)` 대신 `self._resolve_image_url(...)` 사용.

**테스트:**
- `test_fallback_url_decode`: path에 `%20` (예: `img%20001.png`) → unquote 후 space→_ fallback으로 `img_001.png` lookup 성공
- `test_fallback_space_to_underscore`: `![](assets/img 001.png)` + map에 `img_001.png`만 있어도 fallback으로 성공

---

## (선택) 캡션 흡수

- **이미지 라인 바로 다음 줄**이 캡션 패턴이면:
  - 해당 줄을 Notion image **caption**으로 사용
  - 그 줄은 **paragraph로 중복 생성하지 않음** (skip_next로 한 번 더 i 증가)
- **캡션 패턴:** `_is_caption_line(line)` — 길이 ≤120, `#`/`-`/`*`/`````` 로 시작하지 않고,  
  `figure`/`fig.`/`fig `/`그림`/`[그림`/`[Figure` 로 시작하거나 `[` 로 시작해 30자 안에 `]` 있거나 길이 ≤50인 짧은 `[...]` 형태.

**테스트:** `test_caption_absorption` — `![](assets/img_001.png)\nFigure 1: 실험 결과` → 블록 1개(이미지), 캡션에 "Figure 1" 포함.

---

실행:  
`NOTION_TOKEN=test NOTION_PORTFOLIO_DB_ID=test-db-id python3 -m unittest discover -s tests -v`  
→ 15 tests OK (이미지 케이스 8 + Document Parse 2 + Notion 레이아웃 5).
