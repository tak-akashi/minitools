"""Tests for TrendResearcher."""

import pytest
from unittest.mock import MagicMock, patch


class TestTrendResearcher:
    """TrendResearcherのテスト"""

    @pytest.mark.asyncio
    async def test_get_current_trends_success(self):
        """正常にトレンドを取得できるケース"""
        from minitools.researchers.trend import TrendResearcher

        # Tavily APIレスポンスのモック
        mock_response = {
            "results": [
                {
                    "title": "GPT-5 Release Announcement",
                    "url": "https://example.com/gpt5",
                    "content": "OpenAI has released GPT-5 with improved capabilities...",
                },
                {
                    "title": "Latest AI Trends in 2026",
                    "url": "https://example.com/trends",
                    "content": "The AI industry is seeing rapid advances in multimodal models...",
                },
            ],
            "answer": "Current AI trends focus on multimodal models and agent systems.",
        }

        with patch.dict("os.environ", {"TAVILY_API_KEY": "test-api-key"}):
            with patch("minitools.researchers.trend.TavilyClient") as mock_client_class:
                mock_client = MagicMock()
                mock_client.search.return_value = mock_response
                mock_client_class.return_value = mock_client

                researcher = TrendResearcher()
                result = await researcher.get_current_trends()

                assert result is not None
                assert "summary" in result
                assert "topics" in result
                assert "sources" in result
                mock_client.search.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_current_trends_no_api_key(self):
        """APIキー未設定時はNoneを返す"""
        from minitools.researchers.trend import TrendResearcher

        with patch.dict("os.environ", {}, clear=True):
            # TAVILY_API_KEYを環境変数から削除
            import os

            os.environ.pop("TAVILY_API_KEY", None)

            researcher = TrendResearcher()
            result = await researcher.get_current_trends()

            assert result is None

    @pytest.mark.asyncio
    async def test_get_current_trends_api_error(self):
        """API接続失敗時はNoneを返す"""
        from minitools.researchers.trend import TrendResearcher

        with patch.dict("os.environ", {"TAVILY_API_KEY": "test-api-key"}):
            with patch("minitools.researchers.trend.TavilyClient") as mock_client_class:
                mock_client = MagicMock()
                mock_client.search.side_effect = Exception("API connection failed")
                mock_client_class.return_value = mock_client

                researcher = TrendResearcher()
                result = await researcher.get_current_trends()

                assert result is None

    @pytest.mark.asyncio
    async def test_get_current_trends_custom_query(self):
        """カスタムクエリを使用できる"""
        from minitools.researchers.trend import TrendResearcher

        mock_response = {
            "results": [
                {"title": "Test", "url": "https://test.com", "content": "Test content"}
            ],
            "answer": "Test answer",
        }

        with patch.dict("os.environ", {"TAVILY_API_KEY": "test-api-key"}):
            with patch("minitools.researchers.trend.TavilyClient") as mock_client_class:
                mock_client = MagicMock()
                mock_client.search.return_value = mock_response
                mock_client_class.return_value = mock_client

                researcher = TrendResearcher()
                custom_query = "machine learning healthcare 2026"
                await researcher.get_current_trends(query=custom_query)

                # カスタムクエリが使用されていることを確認
                call_args = mock_client.search.call_args
                assert custom_query in str(call_args)
