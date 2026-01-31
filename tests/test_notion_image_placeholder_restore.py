"""
Notion 본문에 이미지가 들어가도록 "[Image: image]" / placeholder 복원 검증.

- 입력에 "[Image: image]"가 있을 때 치환 후 ![](assets/...) 로 변환되는지
- 변환된 markdown을 markdown_to_blocks에 넣었을 때 image block이 생성되는지
"""
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from notion_saver import _normalize_image_placeholders_for_notion

with patch.dict(os.environ, {"NOTION_TOKEN": "test", "NOTION_PORTFOLIO_DB_ID": "test-db-id"}):
    from notion_api_client import NotionClient


def _block_type(block):
    return block.get("type", "") if block else ""


class TestNotionImagePlaceholderRestore(unittest.TestCase):
    """[Image: image] 복원 후 markdown_to_blocks에서 image block 생성."""

    def test_normalize_image_image_to_assets_placeholder(self):
        """입력에 '[Image: image]'가 있으면 치환 후 ![](assets/<filename>) 형태가 되어야 함."""
        md = "A paragraph\n\n[Image: image]\n\nB paragraph"
        ordered = ["img_001.png", "img_002.png"]
        out = _normalize_image_placeholders_for_notion(md, ordered)
        self.assertNotIn("[Image: image]", out)
        self.assertIn("![](assets/img_001.png)", out)
        self.assertIn("A paragraph", out)
        self.assertIn("B paragraph", out)

    def test_normalize_multiple_image_image_in_order(self):
        """여러 개 [Image: image]는 등장 순서대로 assets/filename에 매칭."""
        md = "Intro\n[Image: image]\nMid\n[Image: image]\nOutro"
        ordered = ["fig1.png", "fig2.png"]
        out = _normalize_image_placeholders_for_notion(md, ordered)
        self.assertIn("![](assets/fig1.png)", out)
        self.assertIn("![](assets/fig2.png)", out)
        self.assertNotIn("[Image: image]", out)

    def test_normalize_image_placeholder_path(self):
        """![](/image/placeholder) 형태도 ![](assets/<filename>)로 치환."""
        md = "Text\n![image](/image/placeholder)\nMore"
        ordered = ["img_001.png"]
        out = _normalize_image_placeholders_for_notion(md, ordered)
        self.assertIn("![](assets/img_001.png)", out)
        self.assertNotIn("/image/placeholder", out)

    @patch.dict(os.environ, {"NOTION_TOKEN": "test", "NOTION_PORTFOLIO_DB_ID": "test-db-id"})
    def test_markdown_to_blocks_produces_image_after_restore(self):
        """복원된 markdown(![](assets/xxx))을 markdown_to_blocks에 넣으면 image block이 생성되어야 함."""
        client = NotionClient()
        image_url_map = {"img_001.png": "https://example.com/img_001.png"}
        # 복원 결과와 동일한 형태
        md = "A paragraph\n\n![](assets/img_001.png)\n\nB paragraph"
        blocks = client.markdown_to_blocks(md, image_url_map=image_url_map)
        self.assertGreaterEqual(len(blocks), 3)
        types = [_block_type(b) for b in blocks]
        self.assertIn("image", types)
        self.assertEqual(types[0], "paragraph")
        self.assertEqual(types[1], "image")
        self.assertEqual(types[2], "paragraph")

    @patch.dict(os.environ, {"NOTION_TOKEN": "test", "NOTION_PORTFOLIO_DB_ID": "test-db-id"})
    def test_full_flow_image_image_then_normalize_then_blocks(self):
        """[Image: image] 포함 문자열 → 정규화 → markdown_to_blocks → image block 존재."""
        md = "Intro\n[Image: image]\nOutro"
        ordered = ["img_001.png"]
        normalized = _normalize_image_placeholders_for_notion(md, ordered)
        self.assertIn("![](assets/img_001.png)", normalized)
        client = NotionClient()
        image_url_map = {"img_001.png": "https://example.com/img_001.png"}
        blocks = client.markdown_to_blocks(normalized, image_url_map=image_url_map)
        types = [_block_type(b) for b in blocks]
        self.assertIn("image", types, "정규화 후 markdown_to_blocks에서 image block이 생성되어야 함")

    def test_doc_order_matches_normalize_result_order(self):
        """doc_order_image_filenames(문서 레이아웃 순서)와 normalize 결과의 이미지 순서가 1:1 일치."""
        # elements 순회에서 얻는 순서 = ["first.png", "second.png"]
        doc_order_filenames = ["first.png", "second.png"]
        md = "A\n[Image: image]\nB\n[Image: image]\nC"
        out = _normalize_image_placeholders_for_notion(md, doc_order_filenames)
        first_pos = out.index("![](assets/first.png)")
        second_pos = out.index("![](assets/second.png)")
        self.assertLess(first_pos, second_pos, "첫 번째 이미지는 first.png, 두 번째는 second.png 순서")
        self.assertEqual(out.count("![](assets/first.png)"), 1)
        self.assertEqual(out.count("![](assets/second.png)"), 1)

    @patch.dict(os.environ, {"NOTION_TOKEN": "test", "NOTION_PORTFOLIO_DB_ID": "test-db-id"})
    def test_missing_image_produces_warning_block(self):
        """![](assets/<filename>)로 복원했는데 URL이 없으면 경고 문단 '[Missing image: <filename>]' 블록 생성 + missing_images_out 기록."""
        client = NotionClient()
        image_url_map = {"img_001.png": "https://example.com/img_001.png"}
        md = "Text\n![](assets/unknown.png)\nMore"
        missing: list = []
        blocks = client.markdown_to_blocks(md, image_url_map=image_url_map, missing_images_out=missing)
        self.assertTrue(any("unknown.png" in m for m in missing), "missing_images_out에 unknown.png(또는 path) 기록")
        types = [_block_type(b) for b in blocks]
        self.assertIn("paragraph", types)
        paragraph_contents = [
            b.get("paragraph", {}).get("rich_text", [{}])[0].get("text", {}).get("content", "")
            for b in blocks
            if b.get("type") == "paragraph"
        ]
        self.assertTrue(
            any("[Missing image:" in c and "unknown.png" in c for c in paragraph_contents),
            "경고 문단 '[Missing image: ...unknown.png]' 블록이 생성되어야 함",
        )

    def test_normalize_with_doc_id_produces_scoped_path(self):
        """doc_id가 있으면 ![](assets/<doc_id>/<filename>) 형태로 치환되어 문서 스코프 격리."""
        md = "A\n[Image: image]\nB"
        ordered = ["img_001.png"]
        out = _normalize_image_placeholders_for_notion(md, ordered, doc_id="abc123")
        self.assertIn("![](assets/abc123/img_001.png)", out)
        self.assertNotIn("![](assets/img_001.png)", out)
        self.assertNotIn("[Image: image]", out)

    def test_two_docs_no_cross_contamination(self):
        """doc1 처리 후 doc2 normalize 시 doc2의 parsed_md가 doc1의 assets 경로를 포함하지 않음."""
        doc1_id, doc2_id = "doc1hex", "doc2hex"
        doc2_md = "Intro\n[Image: image]\nOutro"
        doc2_ordered = ["img_001.png"]
        out = _normalize_image_placeholders_for_notion(doc2_md, doc2_ordered, doc_id=doc2_id)
        self.assertIn(f"![](assets/{doc2_id}/img_001.png)", out)
        self.assertNotIn(doc1_id, out, "doc2 결과에 doc1_id가 섞이면 안 됨")

    def test_normalize_placeholder_overflow_records_missing(self):
        """placeholder 개수 > ordered_filenames 길이면 '[Missing image: placeholder overflow]' 삽입 + missing_images_out 기록."""
        md = "A\n[Image: image]\nB\n[Image: image]\nC\n[Image: image]\nD"
        ordered = ["img_001.png", "img_002.png"]
        missing: list = []
        out = _normalize_image_placeholders_for_notion(md, ordered, missing_images_out=missing)
        self.assertIn("![](assets/img_001.png)", out)
        self.assertIn("![](assets/img_002.png)", out)
        self.assertIn("[Missing image: placeholder overflow]", out)
        self.assertIn("placeholder overflow", missing)

    @patch.dict(os.environ, {"NOTION_TOKEN": "test", "NOTION_PORTFOLIO_DB_ID": "test-db-id"})
    def test_resolve_image_url_prefers_full_path_then_basename(self):
        """같은 basename이 문서별 path로 있을 때 path 우선 lookup → doc2의 assets/<doc2_id>/img_001.png는 doc2 URL."""
        client = NotionClient()
        image_url_map = {
            "assets/doc1hex/img_001.png": "https://cdn.example.com/doc1/img_001.png",
            "assets/doc2hex/img_001.png": "https://cdn.example.com/doc2/img_001.png",
        }
        md = "Text\n![](assets/doc2hex/img_001.png)\nMore"
        blocks = client.markdown_to_blocks(md, image_url_map=image_url_map)
        types = [_block_type(b) for b in blocks]
        self.assertIn("image", types)
        img_block = next(b for b in blocks if b.get("type") == "image")
        url = img_block["image"]["external"]["url"]
        self.assertEqual(url, "https://cdn.example.com/doc2/img_001.png", "doc2 path는 doc2 URL로 resolve")


if __name__ == "__main__":
    unittest.main()
