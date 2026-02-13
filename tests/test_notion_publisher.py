"""Tests for NotionPublisher extensions (find_page_by_url, append_blocks)."""

import pytest
from unittest.mock import MagicMock, patch

from minitools.publishers.notion import NotionPublisher


class MockNotionClient:
    """Notion APIクライアントのモック"""

    def __init__(self):
        self.databases = MagicMock()
        self.pages = MagicMock()
        self.blocks = MagicMock()
        self.blocks.children = MagicMock()


@pytest.fixture
def publisher():
    """NotionPublisherをモック付きで初期化"""
    with patch.dict("os.environ", {"NOTION_API_KEY": "test-key"}):
        pub = NotionPublisher(source_type="medium")
        pub.client = MockNotionClient()
        return pub


class TestFindPageByUrl:
    """find_page_by_urlのテスト"""

    @pytest.mark.asyncio
    async def test_find_existing_page(self, publisher):
        """既存ページが見つかる場合"""
        publisher.client.databases.query.return_value = {
            "results": [{"id": "page-123"}]
        }

        result = await publisher.find_page_by_url("db-id", "https://medium.com/article")
        assert result == "page-123"

    @pytest.mark.asyncio
    async def test_page_not_found(self, publisher):
        """ページが見つからない場合"""
        publisher.client.databases.query.return_value = {"results": []}

        result = await publisher.find_page_by_url("db-id", "https://medium.com/article")
        assert result is None

    @pytest.mark.asyncio
    async def test_api_error_returns_none(self, publisher):
        """API呼び出しエラー時にNoneを返す"""
        publisher.client.databases.query.side_effect = Exception("API Error")

        result = await publisher.find_page_by_url("db-id", "https://medium.com/article")
        assert result is None


class TestAppendBlocks:
    """append_blocksのテスト"""

    @pytest.mark.asyncio
    async def test_append_small_block_list(self, publisher):
        """100ブロック以下の場合、1回のAPI呼び出しで追記"""
        publisher.client.blocks.children.append.return_value = {}

        blocks = [
            {
                "type": "paragraph",
                "paragraph": {"rich_text": [{"text": {"content": "test"}}]},
            }
            for _ in range(5)
        ]

        result = await publisher.append_blocks("page-id", blocks)
        assert result is True
        assert publisher.client.blocks.children.append.call_count == 1

    @pytest.mark.asyncio
    async def test_append_empty_blocks(self, publisher):
        """空ブロックリストの処理"""
        result = await publisher.append_blocks("page-id", [])
        assert result is False

    @pytest.mark.asyncio
    async def test_batch_append_over_100(self, publisher):
        """100ブロック超の場合のバッチ分割"""
        publisher.client.blocks.children.append.return_value = {}

        blocks = [
            {
                "type": "paragraph",
                "paragraph": {"rich_text": [{"text": {"content": f"test {i}"}}]},
            }
            for i in range(150)
        ]

        result = await publisher.append_blocks("page-id", blocks)
        assert result is True
        # 150ブロック = 100 + 50 = 2バッチ
        assert publisher.client.blocks.children.append.call_count == 2

    @pytest.mark.asyncio
    async def test_append_api_error(self, publisher):
        """API呼び出しエラー時にFalseを返す"""
        publisher.client.blocks.children.append.side_effect = Exception("API Error")

        blocks = [
            {
                "type": "paragraph",
                "paragraph": {"rich_text": [{"text": {"content": "test"}}]},
            }
        ]

        result = await publisher.append_blocks("page-id", blocks)
        assert result is False
