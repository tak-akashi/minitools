"""
Trend researcher module for fetching current AI trends using Tavily API.
"""

import os
from typing import Any, Dict, List, Optional

from minitools.utils.logger import get_logger

logger = get_logger(__name__)

# Tavily APIは実行時にインポート（APIキー未設定時のエラー回避）
TavilyClient = None


def _get_tavily_client():
    """Tavily Clientを遅延インポート"""
    global TavilyClient
    if TavilyClient is None:
        try:
            from tavily import TavilyClient as TC

            TavilyClient = TC
        except ImportError:
            logger.error("tavily-python is not installed. Run: uv add tavily-python")
            return None
    return TavilyClient


class TrendResearcher:
    """Tavily APIを使用して現在のAIトレンドを調査するクラス"""

    def __init__(self, api_key: Optional[str] = None):
        """
        Args:
            api_key: Tavily APIキー（省略時は環境変数TAVILY_API_KEYから取得）
        """
        self.api_key = api_key or os.getenv("TAVILY_API_KEY")
        self.client = None

        if self.api_key:
            client_class = _get_tavily_client()
            if client_class:
                try:
                    self.client = client_class(api_key=self.api_key)
                    logger.info("TrendResearcher initialized with Tavily API")
                except Exception as e:
                    logger.warning(f"Failed to initialize Tavily client: {e}")
                    self.client = None
        else:
            logger.warning("TAVILY_API_KEY not set. Trend research will be disabled.")

    async def get_current_trends(
        self,
        query: str = "AI machine learning latest trends breakthroughs",
        max_results: int = 5,
    ) -> Optional[Dict[str, Any]]:
        """
        現在のAIトレンドを調査

        Args:
            query: 検索クエリ（デフォルト: AI関連のトレンド検索）
            max_results: 取得する検索結果の最大数

        Returns:
            トレンド情報の辞書、またはエラー時はNone
            {
                "summary": "トレンドの要約（500文字程度）",
                "topics": ["トピック1", "トピック2", ...],
                "sources": [{"title": "...", "url": "..."}]
            }
        """
        if not self.api_key:
            logger.warning("TAVILY_API_KEY not set. Skipping trend research.")
            return None

        if not self.client:
            logger.warning("Tavily client not initialized. Skipping trend research.")
            return None

        try:
            logger.info(f"Searching for trends with query: {query}")

            # Tavily API呼び出し（同期的だがasync関数内で実行）
            import asyncio

            loop = asyncio.get_event_loop()

            def search():
                return self.client.search(
                    query=query,
                    search_depth="basic",
                    max_results=max_results,
                    include_answer=True,
                )

            response = await loop.run_in_executor(None, search)

            # レスポンスからトレンド情報を抽出
            result = self._extract_trends(response)

            logger.info(
                f"Trend research completed: {len(result.get('topics', []))} topics found"
            )
            return result

        except Exception as e:
            logger.warning(f"Failed to fetch trends from Tavily API: {e}")
            return None

    def _extract_trends(self, response: Dict[str, Any]) -> Dict[str, Any]:
        """
        Tavily APIレスポンスからトレンド情報を抽出

        Args:
            response: Tavily APIのレスポンス

        Returns:
            整形されたトレンド情報
        """
        # サマリー（Tavilyのanswer機能を使用）
        summary = response.get("answer", "")

        # 検索結果からトピックとソースを抽出
        results = response.get("results", [])
        topics: List[str] = []
        sources: List[Dict[str, str]] = []

        for result in results:
            title = result.get("title", "")
            url = result.get("url", "")

            # ソース情報を追加
            if title and url:
                sources.append({"title": title, "url": url})

            # タイトルからトピックを抽出（最初の20文字程度）
            if title:
                # タイトルの最初の部分をトピックとして使用
                topic = title.split(":")[0].strip()
                if topic and topic not in topics and len(topics) < 5:
                    topics.append(topic)

        # サマリーがない場合、検索結果のコンテンツから生成
        if not summary and results:
            summary = self._generate_summary_from_results(results)

        return {
            "summary": summary,
            "topics": topics,
            "sources": sources,
        }

    def _generate_summary_from_results(self, results: List[Dict[str, Any]]) -> str:
        """
        検索結果からサマリーを生成

        Args:
            results: Tavily検索結果のリスト

        Returns:
            生成されたサマリー
        """
        # 各結果のコンテンツを結合してサマリーを生成
        contents = []
        for result in results[:3]:  # 上位3件のみ使用
            content = result.get("content", "")
            if content:
                # 最初の200文字程度を使用
                contents.append(content[:200])

        if contents:
            combined = " ".join(contents)
            # 500文字以内に制限
            if len(combined) > 500:
                combined = combined[:497] + "..."
            return combined

        return "トレンド情報を取得できませんでした。"
