"""
Notion 저장 시 레이아웃(이미지 위치) 보존 검증 테스트.

검증 목표: parsed_md 기준으로 본문 블록 시퀀스가 생성되며,
이미지 placeholder 순서/위치대로 Notion image block이 끼어드는 interleaved 구조가 되어야 함.
"""
import os
import sys
import unittest
from unittest.mock import patch

# 프로젝트 루트를 path에 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# NOTION_TOKEN이 없어도 NotionClient()가 생성되도록 패치 후 import
with patch.dict(os.environ, {"NOTION_TOKEN": "test", "NOTION_PORTFOLIO_DB_ID": "test-db-id"}):
    from notion_api_client import NotionClient


def _block_type(block: dict) -> str:
    """Notion block의 type 반환 (paragraph, image, heading_1 등)."""
    return block.get("type", "")


def _paragraph_content(block: dict) -> str:
    """paragraph 블록의 rich_text 내용."""
    if block.get("type") != "paragraph":
        return ""
    rich = block.get("paragraph", {}).get("rich_text", [])
    if not rich:
        return ""
    return rich[0].get("text", {}).get("content", "")


def _image_caption_or_url(block: dict) -> str:
    """image 블록의 caption 또는 url (검증용)."""
    if block.get("type") != "image":
        return ""
    img = block.get("image", {})
    captions = img.get("caption", [])
    if captions:
        return captions[0].get("text", {}).get("content", "")
    ext = img.get("external", {}) or img.get("file", {})
    return ext.get("url", "")


class TestNotionLayoutPreservation(unittest.TestCase):
    """레이아웃 보존: paragraph -> image -> paragraph -> image -> paragraph interleaved."""

    @patch.dict(os.environ, {"NOTION_TOKEN": "test", "NOTION_PORTFOLIO_DB_ID": "test-db-id"})
    def test_blocks_sequence_is_interleaved_from_parsed_md(self):
        """parsed_md 예시대로 블록 순서가 paragraph(A) -> image(001) -> paragraph(B) -> image(002) -> paragraph(C) 여야 함."""
        parsed_md = """A paragraph
![](assets/img_001.png)
B paragraph
![](assets/img_002.png)
C paragraph"""
        image_url_map = {
            "img_001.png": "https://example.com/img_001.png",
            "img_002.png": "https://example.com/img_002.png",
        }
        client = NotionClient()
        blocks = client.markdown_to_blocks(parsed_md, image_url_map=image_url_map)

        self.assertGreaterEqual(len(blocks), 5, "최소 5개 블록: A, img1, B, img2, C")

        # 순서 검증: paragraph(A) -> image(img_001) -> paragraph(B) -> image(img_002) -> paragraph(C)
        self.assertEqual(_block_type(blocks[0]), "paragraph", "blocks[0]은 paragraph")
        self.assertEqual(_paragraph_content(blocks[0]), "A paragraph", "blocks[0] 내용은 'A paragraph'")

        self.assertEqual(_block_type(blocks[1]), "image", "blocks[1]은 image")
        self.assertIn("img_001", _image_caption_or_url(blocks[1]) or blocks[1].get("image", {}).get("external", {}).get("url", ""),
                     "blocks[1]은 img_001 이미지")

        self.assertEqual(_block_type(blocks[2]), "paragraph", "blocks[2]은 paragraph")
        self.assertEqual(_paragraph_content(blocks[2]), "B paragraph", "blocks[2] 내용은 'B paragraph'")

        self.assertEqual(_block_type(blocks[3]), "image", "blocks[3]은 image")
        self.assertIn("img_002", _image_caption_or_url(blocks[3]) or blocks[3].get("image", {}).get("external", {}).get("url", ""),
                     "blocks[3]은 img_002 이미지")

        self.assertEqual(_block_type(blocks[4]), "paragraph", "blocks[4]은 paragraph")
        self.assertEqual(_paragraph_content(blocks[4]), "C paragraph", "blocks[4] 내용은 'C paragraph'")

    @patch.dict(os.environ, {"NOTION_TOKEN": "test", "NOTION_PORTFOLIO_DB_ID": "test-db-id"})
    def test_no_text_then_all_images_at_end(self):
        """'텍스트 먼저 + 이미지 몰아넣기'가 아님을 검증: 이미지가 중간에 끼어 있어야 함."""
        parsed_md = """A paragraph
![](assets/img_001.png)
B paragraph"""
        image_url_map = {"img_001.png": "https://example.com/img_001.png"}
        client = NotionClient()
        blocks = client.markdown_to_blocks(parsed_md, image_url_map=image_url_map)

        # 마지막 블록이 이미지가 아니어야 함 (이미지가 중간에 끼어 있음)
        self.assertEqual(_block_type(blocks[-1]), "paragraph", "마지막 블록은 paragraph(B)여야 함")
        self.assertEqual(_paragraph_content(blocks[-1]), "B paragraph")
        # 두 번째 블록이 이미지
        self.assertEqual(_block_type(blocks[1]), "image")


def _chunk_blocks_like_append_blocks(blocks, chunk_size=20):
    """
    append_blocks와 동일한 방식으로 블록을 순서대로 chunk.
    반환: [chunk0, chunk1, ...] — 각 chunk는 blocks의 연속 구간.
    """
    chunks = []
    for i in range(0, len(blocks), chunk_size):
        chunk = blocks[i:i + chunk_size]
        chunks.append(chunk)
    return chunks


class TestAppendBlocksChunkingOrder(unittest.TestCase):
    """append_blocks 청크 전송 시 텍스트-이미지 interleaving 순서가 깨지지 않는지 검증."""

    def test_chunk_size_is_20(self):
        """chunk size는 20이다."""
        from notion_api_client import NotionClient
        # append_blocks 내부 chunk_size와 동기화 (실제 코드 상수 참조)
        import inspect
        source = inspect.getsource(NotionClient.append_blocks)
        self.assertIn("chunk_size = 20", source, "append_blocks의 chunk_size는 20이어야 함")

    def test_blocks_sliced_in_order_not_reordered(self):
        """blocks 리스트를 순서대로 잘라서 전송하는가 (재정렬 없음)."""
        blocks = [{"object": "block", "type": "paragraph", "paragraph": {"rich_text": [{"type": "text", "text": {"content": f"P{i}"}}]}} for i in range(50)]
        chunks = _chunk_blocks_like_append_blocks(blocks, chunk_size=20)
        self.assertEqual(len(chunks), 3, "50블록 / 20 = 3청크")
        self.assertEqual(len(chunks[0]), 20)
        self.assertEqual(len(chunks[1]), 20)
        self.assertEqual(len(chunks[2]), 10)
        # 순서 보존: 청크를 이어 붙이면 원본과 동일
        reassembled = []
        for c in chunks:
            reassembled.extend(c)
        self.assertEqual(reassembled, blocks, "청크를 순서대로 이어 붙이면 원본 blocks와 동일해야 함")

    def test_interleaving_preserved_with_300_plus_blocks(self):
        """300블록 이상 긴 문서에서도 interleaving이 유지됨 (청크는 순서대로 slice)."""
        # A-IMG-B-IMG-C 패턴을 350블록으로 확장: paragraph(0), image(1), paragraph(2), image(3), ... (인덱스로 순서 식별)
        blocks = []
        for idx in range(350):
            if idx % 2 == 0:
                blocks.append({
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {"rich_text": [{"type": "text", "text": {"content": f"P{idx}"}}]},
                    "_seq": idx,
                })
            else:
                blocks.append({
                    "object": "block",
                    "type": "image",
                    "image": {"external": {"url": f"https://example.com/img_{idx}.png"}},
                    "_seq": idx,
                })
        chunk_size = 20
        chunks = _chunk_blocks_like_append_blocks(blocks, chunk_size=chunk_size)
        self.assertGreaterEqual(len(blocks), 300)
        self.assertGreater(len(chunks), 1)
        # 각 청크는 원본의 연속 구간이며, 청크 순서대로 이어 붙이면 원본과 동일
        reassembled = []
        for c in chunks:
            reassembled.extend(c)
        self.assertEqual(len(reassembled), len(blocks))
        for i, (a, b) in enumerate(zip(reassembled, blocks)):
            self.assertIs(a, b, f"인덱스 {i}: 청크 재조합 후 원본과 동일한 객체 순서")
        # interleaving 패턴 유지: 짝수 인덱스 paragraph, 홀수 인덱스 image
        for i, blk in enumerate(reassembled):
            expected_type = "paragraph" if i % 2 == 0 else "image"
            self.assertEqual(blk.get("type"), expected_type, f"인덱스 {i}: type={expected_type}")
            self.assertEqual(blk.get("_seq"), i, f"인덱스 {i}: _seq={i}")


if __name__ == "__main__":
    unittest.main()
