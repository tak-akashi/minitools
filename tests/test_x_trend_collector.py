"""Tests for XTrendCollector."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from minitools.collectors.x_trend import (
    WOEID_GLOBAL,
    WOEID_JAPAN,
    CollectResult,
    KeywordSearchResult,
    Trend,
    Tweet,
    TrendWithTweets,
    UserTimelineResult,
    XTrendCollector,
)


@pytest.fixture
def sample_trends_response():
    """TwitterAPI.ioのトレンドAPIレスポンスのサンプル"""
    return {
        "trends": [
            {"name": "GPT-5", "tweet_volume": 50000},
            {"name": "Claude 4", "tweet_volume": 30000},
            {"name": "ランチ", "tweet_volume": 10000},
        ]
    }


@pytest.fixture
def sample_tweets_response():
    """TwitterAPI.ioのツイート検索APIレスポンスのサンプル"""
    return {
        "status": "success",
        "code": 0,
        "msg": "success",
        "data": {
            "tweets": [
                {
                    "text": "GPT-5がリリースされました！すごい性能です。",
                    "retweetCount": 1500,
                    "likeCount": 5000,
                    "author": {"userName": "ai_researcher"},
                },
                {
                    "text": "GPT-5 is a game changer for the AI industry.",
                    "retweetCount": 3000,
                    "likeCount": 10000,
                    "author": {"userName": "tech_news"},
                },
            ]
        },
    }


@pytest.fixture
def sample_timeline_response():
    """TwitterAPI.ioのユーザータイムラインAPIレスポンスのサンプル"""
    return {
        "status": "success",
        "code": 0,
        "msg": "success",
        "data": {
            "pin_tweet": None,
            "tweets": [
                {
                    "text": "New research on LLM reasoning capabilities",
                    "retweetCount": 500,
                    "likeCount": 2000,
                    "author": {"userName": "karpathy"},
                },
                {
                    "text": "Had a great lunch today!",
                    "retweetCount": 10,
                    "likeCount": 50,
                    "author": {"userName": "karpathy"},
                },
            ],
        },
    }


def _make_mock_session(response_data):
    """テスト用モックセッションを作成"""
    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.json = AsyncMock(return_value=response_data)
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock(return_value=False)

    mock_session = MagicMock()
    mock_session.get = MagicMock(return_value=mock_response)
    return mock_session


class TestTrendDataModels:
    """データモデルのテスト"""

    def test_trend_creation(self):
        """Trendデータクラスの基本作成テスト"""
        trend = Trend(name="GPT-5", tweet_volume=50000, region="global")
        assert trend.name == "GPT-5"
        assert trend.tweet_volume == 50000
        assert trend.region == "global"

    def test_trend_defaults(self):
        """Trendデータクラスのデフォルト値テスト"""
        trend = Trend(name="test")
        assert trend.tweet_volume == 0
        assert trend.region == ""

    def test_tweet_creation(self):
        """Tweetデータクラスの基本作成テスト"""
        tweet = Tweet(
            text="Hello world",
            retweet_count=100,
            like_count=500,
            author="user1",
        )
        assert tweet.text == "Hello world"
        assert tweet.retweet_count == 100
        assert tweet.like_count == 500
        assert tweet.author == "user1"

    def test_trend_with_tweets(self):
        """TrendWithTweetsデータクラスのテスト"""
        trend = Trend(name="AI", region="japan")
        tweets = [Tweet(text="test tweet")]
        twt = TrendWithTweets(trend=trend, tweets=tweets)
        assert twt.trend.name == "AI"
        assert len(twt.tweets) == 1

    def test_trend_with_tweets_default_empty_list(self):
        """TrendWithTweetsのデフォルト空リストテスト"""
        trend = Trend(name="test")
        twt = TrendWithTweets(trend=trend)
        assert twt.tweets == []

    def test_keyword_search_result(self):
        """KeywordSearchResultデータクラスのテスト"""
        result = KeywordSearchResult(
            keyword="Claude Code",
            tweets=[Tweet(text="Claude Code is amazing")],
        )
        assert result.keyword == "Claude Code"
        assert len(result.tweets) == 1

    def test_user_timeline_result(self):
        """UserTimelineResultデータクラスのテスト"""
        result = UserTimelineResult(
            username="karpathy",
            tweets=[Tweet(text="New AI paper")],
        )
        assert result.username == "karpathy"
        assert len(result.tweets) == 1

    def test_collect_result(self):
        """CollectResultデータクラスのテスト"""
        result = CollectResult()
        assert result.trends == {}
        assert result.keyword_results == []
        assert result.timeline_results == []


class TestXTrendCollector:
    """XTrendCollectorのテスト"""

    @pytest.mark.asyncio
    async def test_get_trends_success(self, sample_trends_response):
        """トレンド取得の正常系テスト"""
        collector = XTrendCollector(api_key="test-key")
        collector.http_session = _make_mock_session(sample_trends_response)

        trends = await collector.get_trends(WOEID_JAPAN)

        assert len(trends) == 3
        assert trends[0].name == "GPT-5"
        assert trends[0].tweet_volume == 50000
        assert trends[0].region == "japan"

    @pytest.mark.asyncio
    async def test_get_trends_global(self, sample_trends_response):
        """グローバルトレンド取得テスト"""
        collector = XTrendCollector(api_key="test-key")
        collector.http_session = _make_mock_session(sample_trends_response)

        trends = await collector.get_trends(WOEID_GLOBAL)

        assert len(trends) == 3
        assert trends[0].region == "global"

    @pytest.mark.asyncio
    async def test_get_tweets_for_trend_success(self, sample_tweets_response):
        """ツイート取得の正常系テスト"""
        collector = XTrendCollector(api_key="test-key")
        collector.http_session = _make_mock_session(sample_tweets_response)

        tweets = await collector.get_tweets_for_trend("GPT-5", count=20)

        assert len(tweets) == 2
        assert tweets[0].text == "GPT-5がリリースされました！すごい性能です。"
        assert tweets[0].retweet_count == 1500
        assert tweets[0].author == "ai_researcher"
        assert tweets[1].retweet_count == 3000

    @pytest.mark.asyncio
    async def test_retry_on_failure(self):
        """API失敗時のリトライテスト"""
        collector = XTrendCollector(api_key="test-key", max_retries=3)

        # 最初の2回は失敗、3回目で成功
        call_count = 0

        def mock_get(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            mock_resp = AsyncMock()
            if call_count < 3:
                mock_resp.status = 500
            else:
                mock_resp.status = 200
                mock_resp.json = AsyncMock(return_value={"trends": [{"name": "AI", "tweet_volume": 100}]})
            mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
            mock_resp.__aexit__ = AsyncMock(return_value=False)
            return mock_resp

        mock_session = MagicMock()
        mock_session.get = mock_get
        collector.http_session = mock_session

        with patch("minitools.collectors.x_trend.asyncio.sleep", new_callable=AsyncMock):
            trends = await collector.get_trends(WOEID_JAPAN)

        assert len(trends) == 1
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_all_retries_fail_returns_empty(self):
        """全リトライ失敗時の空リスト返却テスト"""
        collector = XTrendCollector(api_key="test-key", max_retries=3)

        mock_response = AsyncMock()
        mock_response.status = 500
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.get = MagicMock(return_value=mock_response)
        collector.http_session = mock_session

        with patch("minitools.collectors.x_trend.asyncio.sleep", new_callable=AsyncMock):
            trends = await collector.get_trends(WOEID_JAPAN)

        assert trends == []

    @pytest.mark.asyncio
    async def test_no_session_returns_none(self):
        """セッション未初期化時のテスト"""
        collector = XTrendCollector(api_key="test-key")
        # http_session is None
        trends = await collector.get_trends(WOEID_JAPAN)
        assert trends == []

    @pytest.mark.asyncio
    async def test_search_by_keyword(self, sample_tweets_response):
        """キーワード検索の正常系テスト"""
        collector = XTrendCollector(api_key="test-key")
        collector.http_session = _make_mock_session(sample_tweets_response)

        tweets = await collector.search_by_keyword("Claude Code", count=20)

        assert len(tweets) == 2
        assert tweets[0].retweet_count == 1500

    @pytest.mark.asyncio
    async def test_get_user_timeline(self, sample_timeline_response):
        """ユーザータイムライン取得の正常系テスト"""
        collector = XTrendCollector(api_key="test-key")
        collector.http_session = _make_mock_session(sample_timeline_response)

        tweets = await collector.get_user_timeline("karpathy", count=20)

        assert len(tweets) == 2
        assert tweets[0].text == "New research on LLM reasoning capabilities"
        assert tweets[0].author == "karpathy"

    @pytest.mark.asyncio
    async def test_get_user_timeline_failure(self):
        """ユーザータイムライン取得の失敗テスト"""
        collector = XTrendCollector(api_key="test-key", max_retries=1)

        mock_response = AsyncMock()
        mock_response.status = 404
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.get = MagicMock(return_value=mock_response)
        collector.http_session = mock_session

        tweets = await collector.get_user_timeline("nonexistent_user")
        assert tweets == []

    @pytest.mark.asyncio
    async def test_collect_all_integration(
        self, sample_trends_response, sample_tweets_response, sample_timeline_response
    ):
        """collect_allの統合テスト（3ソース並列実行）"""
        collector = XTrendCollector(api_key="test-key")

        # URLに応じて異なるレスポンスを返すモック
        def mock_get(*args, **kwargs):
            url = args[0] if args else kwargs.get("url", "")

            mock_resp = AsyncMock()
            mock_resp.status = 200
            mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
            mock_resp.__aexit__ = AsyncMock(return_value=False)

            if "trends" in str(url):
                mock_resp.json = AsyncMock(return_value=sample_trends_response)
            elif "last_tweets" in str(url):
                mock_resp.json = AsyncMock(return_value=sample_timeline_response)
            else:
                mock_resp.json = AsyncMock(return_value=sample_tweets_response)

            return mock_resp

        mock_session = MagicMock()
        mock_session.get = mock_get
        collector.http_session = mock_session

        result = await collector.collect_all(
            regions=["japan"],
            keywords=["Claude Code"],
            watch_accounts=["karpathy"],
            enable_trends=True,
            enable_keywords=True,
            enable_timeline=True,
        )

        assert isinstance(result, CollectResult)
        assert "japan" in result.trends
        assert len(result.keyword_results) == 1
        assert result.keyword_results[0].keyword == "Claude Code"
        assert len(result.timeline_results) == 1
        assert result.timeline_results[0].username == "karpathy"

    @pytest.mark.asyncio
    async def test_collect_all_disabled_sources(self, sample_trends_response):
        """ソース無効化時のcollect_allテスト"""
        collector = XTrendCollector(api_key="test-key")
        collector.http_session = _make_mock_session(sample_trends_response)

        result = await collector.collect_all(
            regions=["japan"],
            keywords=["test"],
            watch_accounts=["user1"],
            enable_trends=True,
            enable_keywords=False,
            enable_timeline=False,
        )

        assert isinstance(result, CollectResult)
        assert result.keyword_results == []
        assert result.timeline_results == []

    @pytest.mark.asyncio
    async def test_collect_all_source_failure_isolation(
        self, sample_tweets_response
    ):
        """個別ソース失敗時の独立性テスト"""
        collector = XTrendCollector(api_key="test-key", max_retries=1)

        call_count = 0

        def mock_get(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            url = args[0] if args else kwargs.get("url", "")

            mock_resp = AsyncMock()
            mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
            mock_resp.__aexit__ = AsyncMock(return_value=False)

            # トレンドAPIは失敗
            if "trends" in str(url):
                mock_resp.status = 500
            else:
                mock_resp.status = 200
                mock_resp.json = AsyncMock(return_value=sample_tweets_response)

            return mock_resp

        mock_session = MagicMock()
        mock_session.get = mock_get
        collector.http_session = mock_session

        result = await collector.collect_all(
            regions=["japan"],
            keywords=["Claude Code"],
            watch_accounts=[],
            enable_trends=True,
            enable_keywords=True,
            enable_timeline=False,
        )

        # トレンドは失敗するが空dictで返る
        assert result.trends.get("japan", []) == []
        # キーワード検索は成功
        assert len(result.keyword_results) == 1
        assert len(result.keyword_results[0].tweets) == 2

    @pytest.mark.asyncio
    async def test_collect_with_fetch_tweets_false(self, sample_trends_response):
        """fetch_tweets=Falseのテスト"""
        collector = XTrendCollector(api_key="test-key")
        collector.http_session = _make_mock_session(sample_trends_response)

        result = await collector.collect(
            regions=["japan"],
            fetch_tweets=False,
        )

        assert "japan" in result
        assert len(result["japan"]) == 3
        # ツイートは取得しない
        for twt in result["japan"]:
            assert twt.tweets == []
