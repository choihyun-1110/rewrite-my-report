"""
업로드 경로 doc_id 포함 및 Notion 페이지 격리 검증.

- 업로드 dest_path/public_url이 assets/{doc_id}/... 형태인지
- doc1/doc2 연속 처리 시 doc2에 doc1 id가 섞이지 않는지
- Notion: 기본 새 페이지 생성, reuse 시 purge 호출
"""
import os
import sys
import unittest
from unittest.mock import patch, MagicMock, mock_open

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from storage_client import GitHubStorageClient, StorageClient


class TestUploadDocScopePath(unittest.TestCase):
    """업로드 대상 경로가 doc_id를 포함하는지 검증."""

    def test_github_upload_path_in_repo_includes_doc_id(self):
        """path_in_repo=assets/{doc_id}/img_001.png 이면 반환 URL에 /assets/{doc_id}/img_001.png 포함."""
        with patch("storage_client.requests.put") as put_mock:
            put_mock.return_value.status_code = 201
            with patch("storage_client.requests.get") as get_mock:
                get_mock.return_value.status_code = 404
                client = GitHubStorageClient(token="dummy", repo="u/r", branch="main")
                with patch("os.path.exists", return_value=True):
                    with patch("builtins.open", mock_open(read_data=b"x")):
                        url = client.upload_image("/tmp/img_001.png", path_in_repo="assets/doc1hex/img_001.png")
                self.assertIsNotNone(url)
                self.assertIn("/assets/doc1hex/img_001.png", url, "URL에 doc_id 경로 포함")

    def test_storage_upload_passes_path_in_repo(self):
        """StorageClient.upload_image(image_path, path_in_repo=...) 호출 시 path_in_repo가 GitHub에 전달됨."""
        with patch.object(GitHubStorageClient, "upload_image") as gh_upload:
            gh_upload.return_value = "https://raw.githubusercontent.com/u/r/main/assets/doc2hex/img_001.png"
            client = StorageClient(provider="local", github_token="x", github_repo="u/r", github_branch="main")
            with patch("os.path.exists", return_value=True):
                url = client.upload_image("/tmp/img_001.png", path_in_repo="assets/doc2hex/img_001.png")
            self.assertIn("/assets/doc2hex/img_001.png", url)
            gh_upload.assert_called_once()
            args, kwargs = gh_upload.call_args
            self.assertEqual(kwargs.get("path_in_repo"), "assets/doc2hex/img_001.png")


class TestNotionSaverImageUrlMapDocScope(unittest.TestCase):
    """notion_saver가 image_url_map을 doc-scoped 키 우선으로 구성하는지."""

    @patch.dict(os.environ, {"NOTION_TOKEN": "test", "NOTION_PORTFOLIO_DB_ID": "test-db-id"})
    def test_resolved_urls_primary_key_is_doc_scoped_path(self):
        """image_urls에 assets/{doc_id}/fname 키가 우선으로 들어가고, URL이 doc_id 포함 경로 기반이어야 함."""
        from notion_saver import save_to_notion
        doc_id = "abc123"
        with patch("notion_saver.StorageClient") as StorageMock:
            inst = StorageMock.return_value
            # 업로드 시 path_in_repo=assets/abc123/img_001.png 로 호출되고, URL도 그에 맞게 반환
            inst.upload_image.return_value = "https://raw.githubusercontent.com/u/r/main/assets/abc123/img_001.png"
            with patch("notion_saver.NotionClient") as NotionMock:
                nc = NotionMock.return_value
                nc.client.databases.retrieve.return_value = {"properties": {"Name": {"type": "title"}}}
                nc.create_page.return_value = {"id": "page-123"}
                with patch("os.path.exists", return_value=True), patch("os.listdir", return_value=["img_001.png"]):
                        result = save_to_notion(
                            post_md="## TL;DR\nx",
                            parsed_md="Intro\nOutro",
                            assets_dir="/tmp/out/assets/abc123",
                            tags=[],
                            metadata={"name": "Test"},
                            doc_id=doc_id,
                            doc_order_image_filenames=["img_001.png"],
                        )
            # upload_image가 path_in_repo=assets/abc123/img_001.png 로 호출되었는지
            inst.upload_image.assert_called()
            calls = inst.upload_image.call_args_list
            self.assertGreater(len(calls), 0)
            for call in calls:
                kwargs = call.kwargs
                if "path_in_repo" in kwargs:
                    self.assertIn(doc_id, kwargs["path_in_repo"], "업로드 경로에 doc_id 포함")
                    self.assertIn("assets/", kwargs["path_in_repo"])


class TestNotionPageIsolation(unittest.TestCase):
    """Notion 페이지: 기본 새 페이지 생성, reuse 시 purge 후 append."""

    @patch.dict(os.environ, {"NOTION_TOKEN": "test", "NOTION_PORTFOLIO_DB_ID": "test-db-id"})
    def test_default_creates_new_page(self):
        """reuse_page_id 없으면 create_page가 호출되고 append_only 형태가 아님."""
        from notion_saver import save_to_notion
        with patch("notion_saver.StorageClient") as StorageMock:
            StorageMock.return_value.upload_image.return_value = None
            with patch("notion_saver.NotionClient") as NotionMock:
                nc = NotionMock.return_value
                nc.client.databases.retrieve.return_value = {"properties": {"Name": {"type": "title"}}}
                nc.create_page.return_value = {"id": "new-page-id"}
                with patch("os.path.exists", return_value=False):
                    save_to_notion(
                        post_md="## TL;DR\nx",
                        parsed_md="Intro",
                        assets_dir="/none",
                        tags=[],
                        metadata={"name": "Test"},
                    )
                nc.create_page.assert_called_once()
                nc.purge_children.assert_not_called()

    @patch.dict(os.environ, {"NOTION_TOKEN": "test", "NOTION_PORTFOLIO_DB_ID": "test-db-id"})
    def test_save_to_notion_creates_new_page_by_default(self):
        """reuse_page_id 없이 호출하면 create_page 호출 (새 페이지)."""
        self.test_default_creates_new_page()

    @patch.dict(os.environ, {"NOTION_TOKEN": "test", "NOTION_PORTFOLIO_DB_ID": "test-db-id"})
    def test_reuse_page_purges_children_first(self):
        """reuse_page_id가 있으면 purge_children 호출 후 append_blocks 호출 순서."""
        from notion_saver import save_to_notion
        call_order = []

        def track_purge(page_id):
            call_order.append(("purge_children", page_id))

        def track_append(page_id, blocks):
            call_order.append(("append_blocks", page_id))

        with patch("notion_saver.StorageClient") as StorageMock:
            StorageMock.return_value.upload_image.return_value = None
            with patch("notion_saver.NotionClient") as NotionMock:
                nc = NotionMock.return_value
                nc.client.databases.retrieve.return_value = {"properties": {"Name": {"type": "title"}}}
                nc.purge_children.side_effect = track_purge
                nc.append_blocks.side_effect = lambda page_id, blocks: track_append(page_id, blocks)
                nc.markdown_to_blocks.return_value = []
                with patch("os.path.exists", return_value=False):
                    save_to_notion(
                        post_md="## TL;DR\nx",
                        parsed_md="Intro",
                        assets_dir="/none",
                        tags=[],
                        metadata={"name": "Test"},
                        reuse_page_id="existing-page-id",
                    )
                purge_calls = [c for c in call_order if c[0] == "purge_children"]
                append_calls = [c for c in call_order if c[0] == "append_blocks"]
                self.assertGreater(len(purge_calls), 0, "purge_children이 호출되어야 함")
                self.assertGreater(len(append_calls), 0, "append_blocks가 호출되어야 함")
                self.assertLess(
                    call_order.index(purge_calls[0]),
                    call_order.index(append_calls[0]),
                    "purge_children이 append_blocks보다 먼저 호출되어야 함",
                )

    @patch.dict(os.environ, {"NOTION_TOKEN": "test", "NOTION_PORTFOLIO_DB_ID": "test-db-id"})
    def test_save_to_notion_reuse_calls_purge(self):
        """reuse_page_id 지정 시 purge_children 호출 후 append."""
        from notion_saver import save_to_notion
        with patch("notion_saver.StorageClient") as StorageMock:
            StorageMock.return_value.upload_image.return_value = None
            with patch("notion_saver.NotionClient") as NotionMock:
                nc = NotionMock.return_value
                nc.client.databases.retrieve.return_value = {"properties": {"Name": {"type": "title"}}}
                with patch("os.path.exists", return_value=False):
                    save_to_notion(
                        post_md="## TL;DR\nx",
                        parsed_md="Intro",
                        assets_dir="/none",
                        tags=[],
                        metadata={"name": "Test"},
                        reuse_page_id="existing-page-id",
                    )
                nc.purge_children.assert_called_once_with("existing-page-id")
                nc.create_page.assert_not_called()


class TestImagePathNamespacedByDocId(unittest.TestCase):
    """doc_id=A와 doc_id=B일 때 생성되는 URL/path가 서로 절대 같지 않아야 함."""

    @patch.dict(os.environ, {"NOTION_TOKEN": "test", "NOTION_PORTFOLIO_DB_ID": "test-db-id"})
    def test_image_path_is_namespaced_by_doc_id(self):
        """doc_id=A, doc_id=B 두 번 실행 시 업로드 path와 URL이 각각 A, B로 분리됨."""
        from notion_saver import save_to_notion
        doc_a, doc_b = "docAhex123", "docBhex456"
        upload_calls = []

        def capture_upload(image_path, path_in_repo=None):
            upload_calls.append({"path_in_repo": path_in_repo})
            base = "https://raw.githubusercontent.com/u/r/main/"
            path = path_in_repo or f"assets/{os.path.basename(image_path)}"
            return f"{base}{path}"

        with patch("notion_saver.StorageClient") as StorageMock:
            inst = StorageMock.return_value
            inst.upload_image.side_effect = capture_upload
            with patch("notion_saver.NotionClient") as NotionMock:
                nc = NotionMock.return_value
                nc.client.databases.retrieve.return_value = {"properties": {"Name": {"type": "title"}}}
                nc.create_page.return_value = {"id": "page-1"}
                with patch("os.path.exists", return_value=True), patch("os.listdir", return_value=["img_001.png"]):
                    save_to_notion(
                        post_md="## TL;DR\nx",
                        parsed_md="A doc\nOutro",
                        assets_dir="/tmp/assets/docA",
                        tags=[],
                        metadata={"name": "DocA"},
                        doc_id=doc_a,
                        doc_order_image_filenames=["img_001.png"],
                    )
                path_a = upload_calls[-1]["path_in_repo"]
                self.assertIn(doc_a, path_a, "doc_id=A일 때 path에 A 포함")
                self.assertIn("assets/", path_a)

                upload_calls.clear()
                nc.create_page.return_value = {"id": "page-2"}
                with patch("os.path.exists", return_value=True), patch("os.listdir", return_value=["img_001.png"]):
                    save_to_notion(
                        post_md="## TL;DR\nx",
                        parsed_md="B doc\nOutro",
                        assets_dir="/tmp/assets/docB",
                        tags=[],
                        metadata={"name": "DocB"},
                        doc_id=doc_b,
                        doc_order_image_filenames=["img_001.png"],
                    )
                path_b = upload_calls[-1]["path_in_repo"]
                self.assertIn(doc_b, path_b, "doc_id=B일 때 path에 B 포함")
                self.assertNotEqual(path_a, path_b, "A path와 B path가 달라야 함")
                self.assertNotIn(doc_a, path_b, "B path에 A doc_id가 섞이면 안 됨")


class TestNoStateLeakBetweenRuns(unittest.TestCase):
    """A 처리 후 B 처리 시 image_map/url이 섞이지 않음."""

    @patch.dict(os.environ, {"NOTION_TOKEN": "test", "NOTION_PORTFOLIO_DB_ID": "test-db-id"})
    def test_no_state_leak_between_runs(self):
        """save_to_notion A 호출 후 B 호출 시, B에 전달되는 image_url_map에 A의 doc_id/URL이 없어야 함."""
        from notion_saver import save_to_notion
        doc_a, doc_b = "leakA", "leakB"
        captured_image_url_map = []

        with patch("notion_saver.StorageClient") as StorageMock:
            def url_for(path_in_repo, _):
                return f"https://raw.example.com/{path_in_repo}?v=id"
            inst = StorageMock.return_value
            inst.upload_image.side_effect = lambda path, path_in_repo=None: f"https://raw.example.com/{path_in_repo or 'assets/x'}?v=id"
            with patch("notion_saver.NotionClient") as NotionMock:
                nc = NotionMock.return_value
                nc.client.databases.retrieve.return_value = {"properties": {"Name": {"type": "title"}}}
                nc.create_page.return_value = {"id": "p"}

                def capture_markdown_to_blocks(md, image_url_map=None, **kwargs):
                    captured_image_url_map.append(dict(image_url_map or {}))
                    return [{"object": "block", "type": "paragraph", "paragraph": {"rich_text": [{"type": "text", "text": {"content": "x"}}]}}]

                nc.markdown_to_blocks.side_effect = capture_markdown_to_blocks

                with patch("os.path.exists", return_value=True), patch("os.listdir", return_value=["img_001.png"]):
                    save_to_notion(
                        post_md="## TL;DR\nA",
                        parsed_md="A\nOutro",
                        assets_dir="/tmp/a",
                        tags=[],
                        metadata={"name": "A"},
                        doc_id=doc_a,
                        doc_order_image_filenames=["img_001.png"],
                    )
                    save_to_notion(
                        post_md="## TL;DR\nB",
                        parsed_md="B\nOutro",
                        assets_dir="/tmp/b",
                        tags=[],
                        metadata={"name": "B"},
                        doc_id=doc_b,
                        doc_order_image_filenames=["img_001.png"],
                    )

                # markdown_to_blocks는 요약용(빈 map) + 본문용(채워진 map) 각 1회씩 호출됨 → 총 4회
                body_maps = [m for m in captured_image_url_map if any(doc_b in str(k) for k in (m or {}))]
                self.assertGreaterEqual(len(body_maps), 1, "B 본문용 image_url_map이 있어야 함")
                map_b = body_maps[-1]
                for key, url in map_b.items():
                    self.assertNotIn(doc_a, key, "B의 image_url_map 키에 A doc_id가 있으면 안 됨")
                    self.assertNotIn(doc_a, url, "B의 image_url_map URL에 A doc_id가 있으면 안 됨")
                self.assertIn(f"assets/{doc_b}/", " ".join(map_b.keys()), "B map에는 B doc_id 경로가 있어야 함")


class TestMarkdownContainsCorrectPublicUrls(unittest.TestCase):
    """결과 markdown에 /assets/{doc_id}/img_001.png가 들어가고 flat /assets/img_001.png가 없어야 함."""

    def test_markdown_contains_correct_public_urls(self):
        """normalize 결과 body_md에 assets/{doc_id}/... 가 있고, assets/img_001.png(flat)가 없어야 함."""
        from notion_saver import _normalize_image_placeholders_for_notion
        doc_id = "abc12"
        md = "Intro\n[Image: image]\nOutro"
        ordered = ["img_001.png"]
        out = _normalize_image_placeholders_for_notion(md, ordered, doc_id=doc_id)
        self.assertIn(f"assets/{doc_id}/img_001.png", out, "path에 doc_id 포함")
        self.assertNotIn("](assets/img_001.png)", out, "flat path assets/img_001.png 없어야 함")
        self.assertNotIn("[Image: image]", out)

    def test_markdown_flat_path_rejected_when_doc_id_expected(self):
        """doc_id가 있을 때 출력에 flat assets/filename만 있으면 안 됨."""
        from notion_saver import _normalize_image_placeholders_for_notion
        out = _normalize_image_placeholders_for_notion(
            "x\n[Image: image]\ny", ["img_001.png"], doc_id="doc99"
        )
        self.assertIn("assets/doc99/img_001.png", out)
        self.assertNotRegex(out, r"!\[\]\(assets/img_\d+\.png\)", "flat ![](assets/img_001.png) 패턴 없어야 함")


if __name__ == "__main__":
    unittest.main()
