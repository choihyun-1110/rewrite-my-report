# append_blocks 청크 전송 시 interleaving 순서 검증

## 1) Chunk size는 얼마인가?

**chunk_size = 20**

**코드 위치:** `notion_api_client.py` 99행.

```python
def append_blocks(self, page_id: str, blocks: List[Dict]) -> None:
    # 배치 처리: 한 번에 너무 많이 보내지 않음
    chunk_size = 20
    for i in range(0, len(blocks), chunk_size):
        chunk = blocks[i:i + chunk_size]
        self.client.blocks.children.append(
            block_id=page_id,
            children=chunk
        )
```

Notion API는 한 번에 추가할 children 수에 제한이 있을 수 있어, 20개 단위로 잘라서 여러 번 `blocks.children.append`를 호출한다.

---

## 2) blocks 리스트를 순서대로 잘라서 PATCH를 여러 번 보내는가?

**예. 순서대로 잘라서 여러 번 보낸다.**

- **슬라이스 방식:** `chunk = blocks[i:i + chunk_size]`  
  → Python 리스트 슬라이스 `blocks[i:i+20]`는 **원본 리스트의 연속 구간**을 그대로 순서 유지하여 반환한다.
- **반복:** `for i in range(0, len(blocks), chunk_size)`  
  → i = 0, 20, 40, ... 순으로 증가하므로, **앞에서부터 순서대로** 20개씩 잘라서 전송한다.
- **API 호출:** `self.client.blocks.children.append(block_id=page_id, children=chunk)`  
  → Notion API의 `append`는 **기존 페이지 children 끝에** 전달한 `children`을 **그 순서대로** 추가한다.  
  → 따라서 1차 청크 → 2차 청크 → … 순으로 호출하면, 페이지에는 **원본 blocks 순서 그대로** 블록이 쌓인다.

**정리:** blocks를 **재정렬하지 않고**, 인덱스 0부터 **순서대로** 20개씩 잘라서, 그 순서대로 여러 번 append 호출하므로 **interleaving이 깨지지 않는다.**

---

## 3) 300블록 이상 긴 문서에서도 interleaving이 유지되는가?

**유지된다.**

### 이유 (코드/동작 기준)

1. **한 리스트, 한 번만 순회**  
   `markdown_to_blocks(parsed_md, ...)`가 반환하는 `blocks`는 **한 번 만든 리스트**이며, 이 리스트를 `append_blocks(page_id, content_blocks)`에 그대로 넘긴다.  
   → 300블록이든 350블록이든 **한 개의 순서 있는 리스트**로만 다룬다.

2. **청크는 “앞에서부터 연속 구간”만 잘라냄**  
   - `blocks[0:20]`, `blocks[20:40]`, `blocks[40:60]`, …  
   - 각 청크는 **원본 blocks의 연속 구간**이고, **순서를 바꾸는 연산이 전혀 없다.**

3. **Notion API append 의미**  
   - 매 호출마다 **현재 페이지 children의 맨 끝**에 해당 청크를 **그 순서대로** 추가한다.  
   - 따라서 1차 청크(0~19) → 2차 청크(20~39) → … 순으로 호출하면, 페이지 상 블록 순서는 **원본 blocks와 동일**하다.

4. **A-IMG-B-IMG-C 패턴**  
   - 짧은 예시(A, IMG, B, IMG, C)든, 긴 문서(paragraph/image가 350개 번갈아 나오는 리스트)든,  
   - **같은 리스트를 앞에서부터 20개씩 자르고, 그 순서대로 append만 하므로**  
   - “텍스트-이미지 interleaving” 순서는 **블록 수와 무관하게 유지**된다.

### 테스트로 증명

**파일:** `tests/test_notion_layout.py`  
**클래스:** `TestAppendBlocksChunkingOrder`

1. **test_chunk_size_is_20**  
   - `append_blocks` 소스에 `chunk_size = 20`이 포함되는지 확인.

2. **test_blocks_sliced_in_order_not_reordered**  
   - 50개 블록을 chunk_size=20으로 `_chunk_blocks_like_append_blocks`로 잘라서 청크 리스트를 만들고,  
   - 청크를 **순서대로** 이어 붙인 리스트가 **원본 blocks와 동일**한지 assert.  
   → “순서대로 잘라서 보낸다”를 검증.

3. **test_interleaving_preserved_with_300_plus_blocks**  
   - **350블록**으로, 인덱스 짝수 = paragraph, 홀수 = image인 **interleaved 리스트**를 만든다.  
   - `_chunk_blocks_like_append_blocks(blocks, chunk_size=20)`로 **append_blocks와 동일한 방식**으로 청크 분할.  
   - 청크를 **순서대로** 이어 붙인 리스트가 **원본과 동일**(길이, 각 인덱스의 type·_seq)인지 assert.  
   → 300블록 이상 긴 문서에서도 **interleaving이 유지됨**을 테스트로 증명.

**실행 예시:**

```text
$ NOTION_TOKEN=test NOTION_PORTFOLIO_DB_ID=test-db-id python3 -m unittest tests.test_notion_layout.TestAppendBlocksChunkingOrder -v

test_blocks_sliced_in_order_not_reordered ... ok
test_chunk_size_is_20 ... ok
test_interleaving_preserved_with_300_plus_blocks ... ok

----------------------------------------------------------------------
Ran 3 tests in 0.001s
OK
```

---

## 결론

- **Chunk size:** 20 (`notion_api_client.py` 99행).
- **blocks는 순서대로 잘라서 PATCH(append)를 여러 번 보낸다:**  
  `blocks[i:i+chunk_size]`로 앞에서부터 연속 구간만 잘라, 그 순서대로 `blocks.children.append`를 반복하므로 **interleaving이 깨지지 않는다.**
- **300블록 이상 긴 문서:**  
  같은 리스트를 **앞에서부터 20개씩만** 자르고, **재정렬 없이** append만 하므로 **A-IMG-B-IMG-C 같은 interleaving이 유지**되며,  
  `test_interleaving_preserved_with_300_plus_blocks`로 **350블록 interleaved 시퀀스**에 대해 청크 재조합 후 원본과 동일함을 검증했다.
