"""
markdown_to_blocks 이미지 파서가 다음 케이스를 커버하는지 검증.

1) ![](./assets/img_001.png)
2) ![](assets/img 001.png)
3) ![](assets/img_001.png "caption")
4) <img src="assets/img_001.png" />
5) ![alt text](assets/img_001.png)
"""
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

with patch.dict(os.environ, {"NOTION_TOKEN": "test", "NOTION_PORTFOLIO_DB_ID": "test-db-id"}):
    from notion_api_client import NotionClient


def _run_single_line(client, line, image_url_map):
    """한 줄만 markdown_to_blocks에 넣어서 블록 1개 반환 (이미지면 image, 아니면 paragraph)."""
    blocks = client.markdown_to_blocks(line, image_url_map=image_url_map)
    return blocks[0] if blocks else None


def _block_type(block):
    return block.get("type", "") if block else None


class TestMarkdownToBlocksImageCases(unittest.TestCase):
    """각 이미지 문법 케이스별 resolve_key 및 lookup 검증."""

    @patch.dict(os.environ, {"NOTION_TOKEN": "test", "NOTION_PORTFOLIO_DB_ID": "test-db-id"})
    def test_case1_relative_path_with_dot_slash(self):
        """1) ![](./assets/img_001.png) → resolve_key=img_001.png, lookup 성공."""
        client = NotionClient()
        image_url_map = {"img_001.png": "https://example.com/img_001.png"}
        line = "![](./assets/img_001.png)"
        blocks = client.markdown_to_blocks(line, image_url_map=image_url_map)
        self.assertEqual(len(blocks), 1, "블록 1개")
        self.assertEqual(_block_type(blocks[0]), "image", "이미지 블록")
        self.assertIn("img_001", str(blocks[0].get("image", {}).get("external", {}).get("url", "")))

    @patch.dict(os.environ, {"NOTION_TOKEN": "test", "NOTION_PORTFOLIO_DB_ID": "test-db-id"})
    def test_case2_space_in_filename(self):
        """2) ![](assets/img 001.png) → map에 'img 001.png' 또는 fallback으로 img_001.png 있으면 성공."""
        client = NotionClient()
        image_url_map = {"img 001.png": "https://example.com/img_001.png"}
        line = "![](assets/img 001.png)"
        blocks = client.markdown_to_blocks(line, image_url_map=image_url_map)
        self.assertEqual(len(blocks), 1)
        self.assertEqual(_block_type(blocks[0]), "image", "map에 'img 001.png' 있으면 이미지 블록")
        image_url_map_underscore = {"img_001.png": "https://example.com/img_001.png"}
        blocks2 = client.markdown_to_blocks(line, image_url_map=image_url_map_underscore)
        self.assertEqual(_block_type(blocks2[0]), "image", "fallback 공백→언더스코어로 img_001.png lookup 성공")

    @patch.dict(os.environ, {"NOTION_TOKEN": "test", "NOTION_PORTFOLIO_DB_ID": "test-db-id"})
    def test_case3_markdown_title_quotes(self):
        """3) ![](assets/img_001.png \"caption\") → path에서 title 제거 후 resolve_key=img_001.png."""
        client = NotionClient()
        image_url_map = {"img_001.png": "https://example.com/img_001.png"}
        line = '[](assets/img_001.png "caption")'
        line_with_bang = '![](assets/img_001.png "caption")'
        blocks = client.markdown_to_blocks(line_with_bang, image_url_map=image_url_map)
        self.assertEqual(len(blocks), 1)
        self.assertEqual(_block_type(blocks[0]), "image", "title 제거 후 lookup 성공")

    @patch.dict(os.environ, {"NOTION_TOKEN": "test", "NOTION_PORTFOLIO_DB_ID": "test-db-id"})
    def test_case4_html_img_tag(self):
        """4) <img src=\"assets/img_001.png\" /> → src 추출, resolve_key=img_001.png."""
        client = NotionClient()
        image_url_map = {"img_001.png": "https://example.com/img_001.png"}
        line = '<img src="assets/img_001.png" />'
        blocks = client.markdown_to_blocks(line, image_url_map=image_url_map)
        self.assertEqual(len(blocks), 1)
        self.assertEqual(_block_type(blocks[0]), "image", "HTML img 파싱 시 이미지 블록")

    @patch.dict(os.environ, {"NOTION_TOKEN": "test", "NOTION_PORTFOLIO_DB_ID": "test-db-id"})
    def test_case5_alt_text(self):
        """5) ![alt text](assets/img_001.png) → resolve_key=img_001.png, lookup 성공."""
        client = NotionClient()
        image_url_map = {"img_001.png": "https://example.com/img_001.png"}
        line = "![alt text](assets/img_001.png)"
        blocks = client.markdown_to_blocks(line, image_url_map=image_url_map)
        self.assertEqual(len(blocks), 1)
        self.assertEqual(_block_type(blocks[0]), "image")

    @patch.dict(os.environ, {"NOTION_TOKEN": "test", "NOTION_PORTFOLIO_DB_ID": "test-db-id"})
    def test_fallback_url_decode(self):
        """Fallback: path에 %20 등 URL 인코딩 → unquote 후 lookup (img%20001.png → img 001.png → unquote 또는 space→_ )."""
        client = NotionClient()
        # map에는 디코딩/정규화된 파일명만 있음
        image_url_map = {"img_001.png": "https://example.com/img_001.png"}
        line = "![](assets/img%20001.png)"
        blocks = client.markdown_to_blocks(line, image_url_map=image_url_map)
        self.assertEqual(len(blocks), 1)
        self.assertEqual(_block_type(blocks[0]), "image", "unquote(img%20001.png)=img 001.png, then space→_ fallback으로 img_001.png lookup")

    @patch.dict(os.environ, {"NOTION_TOKEN": "test", "NOTION_PORTFOLIO_DB_ID": "test-db-id"})
    def test_fallback_space_to_underscore(self):
        """Fallback: basename에 공백(img 001.png) → map에 img_001.png만 있어도 공백→언더스코어 재시도로 성공."""
        client = NotionClient()
        image_url_map = {"img_001.png": "https://example.com/img_001.png"}
        line = "![](assets/img 001.png)"
        blocks = client.markdown_to_blocks(line, image_url_map=image_url_map)
        self.assertEqual(len(blocks), 1)
        self.assertEqual(_block_type(blocks[0]), "image")

    @patch.dict(os.environ, {"NOTION_TOKEN": "test", "NOTION_PORTFOLIO_DB_ID": "test-db-id"})
    def test_caption_absorption(self):
        """이미지 라인 다음 줄이 caption 패턴이면 Notion image caption으로 붙이고, 그 줄은 paragraph로 중복 생성하지 않음."""
        client = NotionClient()
        image_url_map = {"img_001.png": "https://example.com/img_001.png"}
        md = "![](assets/img_001.png)\nFigure 1: 실험 결과"
        blocks = client.markdown_to_blocks(md, image_url_map=image_url_map)
        self.assertEqual(len(blocks), 1, "캡션 흡수 시 블록 1개만 (paragraph 중복 없음)")
        self.assertEqual(_block_type(blocks[0]), "image")
        caption_rich = blocks[0].get("image", {}).get("caption", [])
        self.assertTrue(caption_rich, "캡션이 있음")
        caption_text = caption_rich[0].get("text", {}).get("content", "")
        self.assertIn("Figure 1", caption_text or "", "캡션에 다음 줄 내용 포함")


if __name__ == "__main__":
    unittest.main()
