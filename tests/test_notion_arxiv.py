"""Tests for NotionReader ArXiv extension."""

import pytest
from unittest.mock import MagicMock, patch


class TestNotionReaderArxiv:
    """NotionReader.get_arxiv_papers_by_date_range()のテスト"""

    @pytest.mark.asyncio
    async def test_get_arxiv_papers_by_date_range_success(self):
        """正常に論文を取得できるケース"""
        from minitools.readers.notion import NotionReader

        # Notion APIレスポンスのモック
        mock_response = {
            "results": [
                {
                    "id": "page-1",
                    "properties": {
                        "タイトル": {
                            "type": "title",
                            "title": [{"plain_text": "Test Paper 1"}],
                        },
                        "公開日": {"type": "date", "date": {"start": "2026-01-20"}},
                        "日本語訳": {
                            "type": "rich_text",
                            "rich_text": [{"plain_text": "テスト論文1の概要"}],
                        },
                        "URL": {
                            "type": "url",
                            "url": "https://arxiv.org/abs/2601.00001",
                        },
                    },
                },
                {
                    "id": "page-2",
                    "properties": {
                        "タイトル": {
                            "type": "title",
                            "title": [{"plain_text": "Test Paper 2"}],
                        },
                        "公開日": {"type": "date", "date": {"start": "2026-01-19"}},
                        "日本語訳": {
                            "type": "rich_text",
                            "rich_text": [{"plain_text": "テスト論文2の概要"}],
                        },
                        "URL": {
                            "type": "url",
                            "url": "https://arxiv.org/abs/2601.00002",
                        },
                    },
                },
            ],
            "has_more": False,
            "next_cursor": None,
        }

        with patch.dict(
            "os.environ",
            {
                "NOTION_API_KEY": "test-api-key",
                "NOTION_ARXIV_DATABASE_ID": "test-db-id",
            },
        ):
            with patch("minitools.readers.notion.Client") as mock_client_class:
                mock_client = MagicMock()
                mock_client.databases.query.return_value = mock_response
                mock_client_class.return_value = mock_client

                reader = NotionReader()
                result = await reader.get_arxiv_papers_by_date_range(
                    start_date="2026-01-18",
                    end_date="2026-01-25",
                )

                assert len(result) == 2
                assert result[0]["タイトル"] == "Test Paper 1"
                assert result[0]["日本語訳"] == "テスト論文1の概要"

    @pytest.mark.asyncio
    async def test_get_arxiv_papers_by_date_range_empty(self):
        """論文0件の場合は空リストを返す"""
        from minitools.readers.notion import NotionReader

        mock_response = {
            "results": [],
            "has_more": False,
            "next_cursor": None,
        }

        with patch.dict(
            "os.environ",
            {
                "NOTION_API_KEY": "test-api-key",
                "NOTION_ARXIV_DATABASE_ID": "test-db-id",
            },
        ):
            with patch("minitools.readers.notion.Client") as mock_client_class:
                mock_client = MagicMock()
                mock_client.databases.query.return_value = mock_response
                mock_client_class.return_value = mock_client

                reader = NotionReader()
                result = await reader.get_arxiv_papers_by_date_range(
                    start_date="2026-01-18",
                    end_date="2026-01-25",
                )

                assert result == []

    @pytest.mark.asyncio
    async def test_get_arxiv_papers_by_date_range_uses_correct_date_property(self):
        """「公開日」プロパティでフィルタリングしている"""
        from minitools.readers.notion import NotionReader

        mock_response = {
            "results": [],
            "has_more": False,
            "next_cursor": None,
        }

        with patch.dict(
            "os.environ",
            {
                "NOTION_API_KEY": "test-api-key",
                "NOTION_ARXIV_DATABASE_ID": "test-db-id",
            },
        ):
            with patch("minitools.readers.notion.Client") as mock_client_class:
                mock_client = MagicMock()
                mock_client.databases.query.return_value = mock_response
                mock_client_class.return_value = mock_client

                reader = NotionReader()
                await reader.get_arxiv_papers_by_date_range(
                    start_date="2026-01-18",
                    end_date="2026-01-25",
                )

                # クエリに「公開日」が含まれていることを確認
                call_args = mock_client.databases.query.call_args
                filter_query = call_args.kwargs.get("filter", {})

                # フィルタ内に「公開日」プロパティが使われているか確認
                filter_str = str(filter_query)
                assert "公開日" in filter_str

    @pytest.mark.asyncio
    async def test_get_arxiv_papers_by_date_range_custom_database_id(self):
        """カスタムデータベースIDを使用できる"""
        from minitools.readers.notion import NotionReader

        mock_response = {
            "results": [],
            "has_more": False,
            "next_cursor": None,
        }

        with patch.dict("os.environ", {"NOTION_API_KEY": "test-api-key"}):
            with patch("minitools.readers.notion.Client") as mock_client_class:
                mock_client = MagicMock()
                mock_client.databases.query.return_value = mock_response
                mock_client_class.return_value = mock_client

                reader = NotionReader()
                custom_db_id = "custom-database-id"
                await reader.get_arxiv_papers_by_date_range(
                    start_date="2026-01-18",
                    end_date="2026-01-25",
                    database_id=custom_db_id,
                )

                # カスタムDBIDが使用されていることを確認
                call_args = mock_client.databases.query.call_args
                assert call_args.kwargs.get("database_id") == custom_db_id
