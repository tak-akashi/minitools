"""
X (Twitter) trend collector using TwitterAPI.io.

Collects trending topics and related tweets for Japan and global regions.
Supports keyword search and user timeline monitoring.
"""

import asyncio
from dataclasses import dataclass, field
from typing import Any

import aiohttp

from minitools.utils.logger import get_logger

logger = get_logger(__name__)

# WOEID constants
WOEID_JAPAN = 23424856
WOEID_GLOBAL = 1

REGION_WOEID_MAP: dict[str, int] = {
    "japan": WOEID_JAPAN,
    "global": WOEID_GLOBAL,
}


@dataclass
class Trend:
    """トレンド情報"""

    name: str
    tweet_volume: int = 0
    region: str = ""  # "japan" or "global"


@dataclass
class Tweet:
    """ツイート情報"""

    text: str
    retweet_count: int = 0
    like_count: int = 0
    author: str = ""


@dataclass
class TrendWithTweets:
    """トレンドと関連ツイートのセット"""

    trend: Trend
    tweets: list[Tweet] = field(default_factory=list)


@dataclass
class KeywordSearchResult:
    """キーワード検索結果"""

    keyword: str
    tweets: list[Tweet] = field(default_factory=list)


@dataclass
class UserTimelineResult:
    """ユーザータイムライン結果"""

    username: str
    tweets: list[Tweet] = field(default_factory=list)


@dataclass
class CollectResult:
    """全収集結果を格納"""

    trends: dict[str, list[TrendWithTweets]] = field(default_factory=dict)
    keyword_results: list[KeywordSearchResult] = field(default_factory=list)
    timeline_results: list[UserTimelineResult] = field(default_factory=list)


class XTrendCollector:
    """TwitterAPI.ioを使用してトレンドとツイートを収集するクラス"""

    BASE_URL = "https://api.twitterapi.io"

    def __init__(
        self,
        api_key: str | None = None,
        max_retries: int = 3,
    ):
        """
        Args:
            api_key: TwitterAPI.io APIキー（省略時は環境変数から取得）
            max_retries: 最大リトライ回数
        """
        import os

        self.api_key = api_key or os.getenv("TWITTER_API_IO_KEY", "")
        self.max_retries = max_retries
        self.http_session: aiohttp.ClientSession | None = None

        if not self.api_key:
            logger.warning("TWITTER_API_IO_KEY is not set")

    async def __aenter__(self):
        """非同期コンテキストマネージャーのエントリー"""
        connector = aiohttp.TCPConnector(limit=10)
        timeout = aiohttp.ClientTimeout(total=60)
        self.http_session = aiohttp.ClientSession(
            connector=connector,
            timeout=timeout,
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """非同期コンテキストマネージャーのクリーンアップ"""
        if self.http_session:
            await self.http_session.close()

    async def _request_with_retry(
        self,
        url: str,
        params: dict[str, Any],
    ) -> dict[str, Any] | None:
        """
        指数バックオフ付きHTTPリクエスト

        Args:
            url: リクエストURL
            params: クエリパラメータ

        Returns:
            レスポンスJSON（失敗時はNone）
        """
        if not self.http_session:
            logger.error("HTTP session not initialized. Use async context manager.")
            return None

        headers: dict[str, str] = {"X-API-Key": self.api_key or ""}

        for attempt in range(self.max_retries):
            try:
                async with self.http_session.get(
                    url, headers=headers, params=params
                ) as response:
                    if response.status == 200:
                        return await response.json()
                    else:
                        logger.warning(
                            f"API request failed (attempt {attempt + 1}/{self.max_retries}): "
                            f"status={response.status}, url={url}"
                        )
            except Exception as e:
                logger.warning(
                    f"API request error (attempt {attempt + 1}/{self.max_retries}): "
                    f"{type(e).__name__}: {e}"
                )

            if attempt < self.max_retries - 1:
                delay = 2**attempt  # 1s, 2s, 4s
                logger.debug(f"Retrying in {delay}s...")
                await asyncio.sleep(delay)

        logger.error(f"All {self.max_retries} retries failed for {url}")
        return None

    async def get_trends(self, woeid: int) -> list[Trend]:
        """
        指定地域のトレンドを取得

        Args:
            woeid: Where On Earth ID

        Returns:
            トレンドリスト（失敗時は空リスト）
        """
        region = "japan" if woeid == WOEID_JAPAN else "global"
        logger.info(f"Fetching trends for region={region} (WOEID={woeid})")

        url = f"{self.BASE_URL}/twitter/trends"
        params = {"woeid": woeid}

        data = await self._request_with_retry(url, params)
        if not data:
            logger.warning(f"Failed to fetch trends for WOEID={woeid}")
            return []

        trends = []
        # TwitterAPI.ioのレスポンス形式に対応（ネスト構造にも対応）
        if isinstance(data, list):
            trend_list = data
        elif isinstance(data.get("data"), dict):
            trend_list = data["data"].get("trends", [])
        else:
            trend_list = data.get("trends", [])

        for item in trend_list:
            # "trend"キーがdict（ネストされた形式）の場合に対応
            trend_data = item.get("trend", {})
            if isinstance(trend_data, dict):
                name = item.get("name") or trend_data.get("name", "")
                volume = item.get("tweet_volume") or trend_data.get("tweet_volume") or 0
            else:
                name = item.get("name", trend_data or "")
                volume = item.get("tweet_volume", 0) or 0
            if name and isinstance(name, str):
                trends.append(Trend(name=name, tweet_volume=volume, region=region))

        logger.info(f"Found {len(trends)} trends for {region}")
        return trends

    def _parse_tweets(self, data: Any, count: int = 20) -> list[Tweet]:
        """
        APIレスポンスからツイートリストを解析

        Args:
            data: APIレスポンスデータ
            count: 最大取得件数

        Returns:
            ツイートリスト
        """
        tweets: list[Tweet] = []
        if isinstance(data, list):
            tweet_list = data
        elif isinstance(data.get("data"), dict):
            tweet_list = data["data"].get("tweets", [])
        else:
            tweet_list = data.get("tweets", [])

        for item in tweet_list:
            text = item.get("text", "")
            if not text:
                continue

            author_info = item.get("author", {})
            author_name = ""
            if isinstance(author_info, dict):
                author_name = str(
                    author_info.get("userName", author_info.get("name", ""))
                )
            elif isinstance(author_info, str):
                author_name = author_info

            tweets.append(
                Tweet(
                    text=text,
                    retweet_count=item.get("retweetCount", item.get("retweet_count", 0))
                    or 0,
                    like_count=item.get("likeCount", item.get("like_count", 0)) or 0,
                    author=author_name,
                )
            )

        return tweets[:count]

    async def get_tweets_for_trend(
        self,
        trend_name: str,
        count: int = 20,
    ) -> list[Tweet]:
        """
        トレンドに関連するツイートを取得

        Args:
            trend_name: トレンド名（またはキーワード）
            count: 取得件数

        Returns:
            ツイートリスト（失敗時は空リスト）
        """
        url = f"{self.BASE_URL}/twitter/tweet/advanced_search"
        params = {
            "query": trend_name,
            "queryType": "Top",
            "count": count,
        }

        data = await self._request_with_retry(url, params)
        if not data:
            return []

        tweets = self._parse_tweets(data, count)
        logger.debug(f"Found {len(tweets)} tweets for '{trend_name}'")
        return tweets

    async def search_by_keyword(
        self,
        keyword: str,
        count: int = 20,
    ) -> list[Tweet]:
        """
        キーワードでツイートを検索

        Args:
            keyword: 検索キーワード
            count: 取得件数

        Returns:
            ツイートリスト（失敗時は空リスト）
        """
        logger.debug(f"Searching tweets for keyword '{keyword}'")
        return await self.get_tweets_for_trend(keyword, count=count)

    async def get_user_timeline(
        self,
        username: str,
        count: int = 20,
    ) -> list[Tweet]:
        """
        ユーザーの最新ツイートを取得

        Args:
            username: Xのユーザー名（@なし）
            count: 取得件数

        Returns:
            ツイートリスト（失敗時は空リスト）
        """
        url = f"{self.BASE_URL}/twitter/user/last_tweets"
        params = {"userName": username}

        data = await self._request_with_retry(url, params)
        if not data:
            logger.warning(f"Failed to fetch timeline for @{username}")
            return []

        logger.debug(f"Timeline response for @{username}: keys={list(data.keys()) if isinstance(data, dict) else type(data).__name__}")
        tweets = self._parse_tweets(data, count)
        logger.debug(f"Found {len(tweets)} tweets from @{username}")
        return tweets

    async def collect_keywords(
        self,
        keywords: list[str],
        tweets_per_keyword: int = 20,
    ) -> list[KeywordSearchResult]:
        """
        全キーワードでツイートを並列検索

        Args:
            keywords: 検索キーワードリスト
            tweets_per_keyword: キーワードあたりのツイート取得件数

        Returns:
            キーワード検索結果リスト
        """
        if not keywords:
            return []

        logger.info(f"Collecting tweets for {len(keywords)} keywords")
        semaphore = asyncio.Semaphore(5)

        async def search_keyword(keyword: str) -> KeywordSearchResult:
            async with semaphore:
                tweets = await self.search_by_keyword(keyword, count=tweets_per_keyword)
                if not tweets:
                    logger.info(f"No tweets found for keyword '{keyword}'")
                return KeywordSearchResult(keyword=keyword, tweets=tweets)

        results = await asyncio.gather(*[search_keyword(k) for k in keywords])
        return list(results)

    async def collect_timelines(
        self,
        accounts: list[str],
        tweets_per_account: int = 20,
    ) -> list[UserTimelineResult]:
        """
        全アカウントのタイムラインを並列取得

        Args:
            accounts: 監視アカウントリスト（@なしのユーザー名）
            tweets_per_account: アカウントあたりのツイート取得件数

        Returns:
            タイムライン結果リスト
        """
        if not accounts:
            return []

        logger.info(f"Collecting timelines for {len(accounts)} accounts")
        semaphore = asyncio.Semaphore(5)

        async def fetch_timeline(username: str) -> UserTimelineResult:
            async with semaphore:
                tweets = await self.get_user_timeline(
                    username, count=tweets_per_account
                )
                if not tweets:
                    logger.warning(f"No tweets found for @{username}")
                return UserTimelineResult(username=username, tweets=tweets)

        results = await asyncio.gather(*[fetch_timeline(a) for a in accounts])
        return list(results)

    async def collect(
        self,
        regions: list[str] | None = None,
        tweets_per_trend: int = 20,
        fetch_tweets: bool = True,
    ) -> dict[str, list[TrendWithTweets]]:
        """
        指定地域のトレンドと関連ツイートを収集

        Args:
            regions: 対象地域リスト（デフォルト: ["japan", "global"]）
            tweets_per_trend: トレンドあたりのツイート取得件数
            fetch_tweets: ツイートも取得するか（Falseの場合はトレンド名のみ）

        Returns:
            地域ごとのTrendWithTweetsリスト
        """
        if regions is None:
            regions = ["japan", "global"]

        logger.info(f"Collecting trends for regions: {regions}")
        result: dict[str, list[TrendWithTweets]] = {}

        # 地域ごとにトレンドを並列取得
        async def collect_region(region: str) -> tuple[str, list[TrendWithTweets]]:
            woeid = REGION_WOEID_MAP.get(region)
            if woeid is None:
                logger.warning(f"Unknown region: {region}")
                return region, []

            trends = await self.get_trends(woeid)
            if not trends:
                return region, []

            if not fetch_tweets:
                return region, [TrendWithTweets(trend=t) for t in trends]

            # 各トレンドのツイートを並列取得（Semaphore制限）
            semaphore = asyncio.Semaphore(5)

            async def fetch_tweets_for(trend: Trend) -> TrendWithTweets:
                async with semaphore:
                    tweets = await self.get_tweets_for_trend(
                        trend.name, count=tweets_per_trend
                    )
                    return TrendWithTweets(trend=trend, tweets=tweets)

            trends_with_tweets = await asyncio.gather(
                *[fetch_tweets_for(t) for t in trends]
            )
            return region, list(trends_with_tweets)

        region_results = await asyncio.gather(*[collect_region(r) for r in regions])

        for region, trends_with_tweets in region_results:
            result[region] = trends_with_tweets

        total_trends = sum(len(v) for v in result.values())
        logger.info(f"Collected {total_trends} trends across {len(regions)} regions")
        return result

    async def collect_all(
        self,
        regions: list[str] | None = None,
        keywords: list[str] | None = None,
        watch_accounts: list[str] | None = None,
        tweets_per_trend: int = 20,
        tweets_per_keyword: int = 20,
        tweets_per_account: int = 20,
        enable_trends: bool = True,
        enable_keywords: bool = True,
        enable_timeline: bool = True,
    ) -> CollectResult:
        """
        3ソースを並列で収集

        Args:
            regions: 対象地域リスト
            keywords: 検索キーワードリスト
            watch_accounts: 監視アカウントリスト
            tweets_per_trend: トレンドあたりのツイート取得件数
            tweets_per_keyword: キーワードあたりのツイート取得件数
            tweets_per_account: アカウントあたりのツイート取得件数
            enable_trends: トレンド収集を有効にするか
            enable_keywords: キーワード検索を有効にするか
            enable_timeline: タイムライン監視を有効にするか

        Returns:
            全収集結果
        """
        logger.info(
            f"Collecting all sources (trends={enable_trends}, "
            f"keywords={enable_keywords}, timeline={enable_timeline})"
        )

        # トレンド収集（fetch_tweets=Falseでコスト最適化）
        async def collect_trends() -> dict[str, list[TrendWithTweets]]:
            if not enable_trends:
                return {}
            return await self.collect(
                regions=regions,
                tweets_per_trend=tweets_per_trend,
                fetch_tweets=False,
            )

        # キーワード検索
        async def collect_kw() -> list[KeywordSearchResult]:
            if not enable_keywords or not keywords:
                return []
            return await self.collect_keywords(
                keywords=keywords,
                tweets_per_keyword=tweets_per_keyword,
            )

        # タイムライン監視
        async def collect_tl() -> list[UserTimelineResult]:
            if not enable_timeline or not watch_accounts:
                return []
            return await self.collect_timelines(
                accounts=watch_accounts,
                tweets_per_account=tweets_per_account,
            )

        # 3ソースを並列実行（return_exceptions=Trueで個別エラーをキャッチ）
        results = await asyncio.gather(
            collect_trends(), collect_kw(), collect_tl(), return_exceptions=True
        )

        trends_result: dict[str, list[TrendWithTweets]] = {}
        if isinstance(results[0], BaseException):
            logger.error(f"Trend collection failed: {results[0]}")
        else:
            trends_result = results[0]

        keyword_result: list[KeywordSearchResult] = []
        if isinstance(results[1], BaseException):
            logger.error(f"Keyword collection failed: {results[1]}")
        else:
            keyword_result = results[1]

        timeline_result: list[UserTimelineResult] = []
        if isinstance(results[2], BaseException):
            logger.error(f"Timeline collection failed: {results[2]}")
        else:
            timeline_result = results[2]

        return CollectResult(
            trends=trends_result,
            keyword_results=keyword_result,
            timeline_results=timeline_result,
        )
