"""
OCR 숫자/측정 블록 강등(downgrade) 및 토글(toggle) 검증.

- Measurements for Transient Analysis 이후 과학표기 테이블이 (A) 이미지로 치환 또는 (B) toggle 아래로 들어가는지
- 자연어 본문은 손상되지 않는지
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ocr_numeric_downgrade import downgrade_ocr_numeric_blocks, _is_ocr_numeric_block, _split_into_blocks


class TestOcrNumericHeuristic(unittest.TestCase):
    """휴리스틱: OCR 숫자 블록 감지."""

    def test_scientific_plus_keywords_triggers(self):
        """과학표기(e-/e+) 다수 + delay/rise/fall 키워드 → OCR 블록."""
        block = """
        Measurements for Transient Analysis
        delay   rise   fall   targ
        1e-9    2e-9   3e-9   1e-8
        1.5e-9  2.5e-9 3.5e-9 1.2e-8
        """
        self.assertTrue(_is_ocr_numeric_block(block))

    def test_pipe_table_3plus_with_units_triggers(self):
        """파이프 테이블 3줄 이상 + ns/mV/V 단위 → OCR 블록."""
        block = """
        | time | V(n1) | V(n2) |
        | 0 ns | 0 mV  | 0 V   |
        | 1 ns | 100mV | 1.2 V |
        | 2 ns | 200mV | 2.1 A |
        """
        self.assertTrue(_is_ocr_numeric_block(block))

    def test_natural_prose_not_triggered(self):
        """자연어 문장은 OCR 블록으로 판별되지 않음."""
        block = "이 실험에서는 트랜지스터의 동작을 확인하였다. 결과는 다음 절에서 설명한다."
        self.assertFalse(_is_ocr_numeric_block(block))

    def test_short_block_not_triggered(self):
        """너무 짧은 블록은 무시."""
        self.assertFalse(_is_ocr_numeric_block("1e-9"))


class TestDowngradeOcrNumericBlocks(unittest.TestCase):
    """downgrade_ocr_numeric_blocks: 치환 후 ordered_filenames 소비."""

    def test_ocr_block_replaced_by_image_placeholder(self):
        """OCR 블록이 ![](assets/{doc_id}/img_001.png) 로 치환되고 ordered_filenames 1개 소비."""
        md = """Intro paragraph.

Measurements for Transient Analysis
delay   rise   fall
1e-9    2e-9   3e-9
1.5e-9  2.5e-9 3.5e-9

Outro paragraph."""
        ordered = ["img_001.png", "img_002.png"]
        out, remaining = downgrade_ocr_numeric_blocks(md, ordered, doc_id="abc12", mode="downgrade")
        self.assertIn("![](assets/abc12/img_001.png)", out)
        self.assertEqual(remaining, ["img_002.png"])
        self.assertIn("Intro paragraph", out)
        self.assertIn("Outro paragraph", out)
        self.assertNotIn("1e-9", out)

    def test_natural_prose_unchanged(self):
        """자연어 본문은 손상되지 않음."""
        md = """이 실험에서는 트랜지스터의 동작을 확인하였다.
결과는 다음 절에서 설명한다."""
        ordered = ["img_001.png"]
        out, remaining = downgrade_ocr_numeric_blocks(md, ordered, doc_id="x", mode="downgrade")
        self.assertEqual(remaining, ["img_001.png"])
        self.assertIn("트랜지스터", out)
        self.assertIn("다음 절", out)

    def test_toggle_mode_wraps_ocr_block(self):
        """mode=toggle 시 OCR 블록이 :::toggle ... :::endtoggle 로 감싸짐."""
        md = """Intro

| a | b |
| 1e-9 | 2 ns |
| 2e-9 | 3 mV |

Outro"""
        ordered = ["img_001.png"]
        out, remaining = downgrade_ocr_numeric_blocks(md, ordered, doc_id="x", mode="toggle")
        self.assertIn(":::toggle Measurements (OCR)", out)
        self.assertIn(":::endtoggle", out)
        self.assertIn("1e-9", out)
        self.assertEqual(remaining, ["img_001.png"])


class TestToggleParsingInMarkdownToBlocks(unittest.TestCase):
    """markdown_to_blocks에서 :::toggle ... :::endtoggle → toggle 블록 생성."""

    def test_toggle_produces_toggle_block(self):
        """:::toggle Title::: ... :::endtoggle 이 toggle 블록으로 변환됨."""
        try:
            from unittest.mock import patch
            with patch.dict(os.environ, {"NOTION_TOKEN": "test", "NOTION_PORTFOLIO_DB_ID": "test-db-id"}):
                from notion_api_client import NotionClient
                client = NotionClient()
                md = ":::toggle Measurements (OCR)\n| a | b |\n| 1 | 2 |\n:::endtoggle"
                blocks = client.markdown_to_blocks(md)
                self.assertGreaterEqual(len(blocks), 1)
                toggle = next((b for b in blocks if b.get("type") == "toggle"), None)
                self.assertIsNotNone(toggle)
                self.assertIn("Measurements (OCR)", str(toggle.get("toggle", {}).get("rich_text", [])))
        except ImportError:
            self.skipTest("NotionClient not available")


if __name__ == "__main__":
    unittest.main()
