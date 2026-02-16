"""Tests for XTrendProcessor."""

import json

import pytest

from minitools.collectors.x_trend import (
    CollectResult,
    KeywordSearchResult,
    Trend,
    Tweet,
    TrendWithTweets,
    UserTimelineResult,
)
from minitools.processors.x_trend import (
    KeywordSummary,
    ProcessResult,
    TimelineSummary,
    TrendSummary,
    XTrendProcessor,
)

from tests.conftest import MockLLMClient


@pytest.fixture
def sample_trends_with_tweets():
    """テスト用のトレンド+ツイートデータ"""
    return [
        TrendWithTweets(
            trend=Trend(name="GPT-5", tweet_volume=50000, region="global"),
            tweets=[
                Tweet(text="GPT-5 is amazing!", retweet_count=1500, like_count=5000, author="user1"),
                Tweet(text="GPT-5 changes everything in AI", retweet_count=3000, like_count=10000, author="user2"),
            ],
        ),
        TrendWithTweets(
            trend=Trend(name="ランチ", tweet_volume=10000, region="global"),
            tweets=[
                Tweet(text="今日のランチは美味しかった", retweet_count=5, like_count=20, author="user3"),
            ],
        ),
        TrendWithTweets(
            trend=Trend(name="Claude 4", tweet_volume=30000, region="global"),
            tweets=[
                Tweet(text="Claude 4 outperforms GPT-5", retweet_count=2000, like_count=8000, author="user4"),
            ],
        ),
    ]


class TestXTrendProcessor:
    """XTrendProcessorのテスト"""

    @pytest.mark.asyncio
    async def test_filter_ai_trends(self, sample_trends_with_tweets):
        """AIトレンドフィルタリングのテスト"""
        filter_response = json.dumps({
            "selected": [
                {"index": 0, "relevance": "LLM新モデル"},
                {"index": 2, "relevance": "LLM新モデル"},
            ]
        })
        mock_llm = MockLLMClient(json_response=filter_response)
        processor = XTrendProcessor(llm_client=mock_llm)

        filtered = await processor.filter_ai_trends(
            sample_trends_with_tweets, max_trends=10
        )

        assert len(filtered) == 2
        assert filtered[0].trend.name == "GPT-5"
        assert filtered[1].trend.name == "Claude 4"
        assert len(mock_llm.chat_calls) == 1

    @pytest.mark.asyncio
    async def test_filter_ai_trends_empty_input(self):
        """空入力のフィルタリングテスト"""
        mock_llm = MockLLMClient()
        processor = XTrendProcessor(llm_client=mock_llm)

        filtered = await processor.filter_ai_trends([], max_trends=10)
        assert filtered == []

    @pytest.mark.asyncio
    async def test_filter_ai_trends_json_parse_failure_fallback(
        self, sample_trends_with_tweets
    ):
        """JSONパース失敗時のフォールバックテスト"""
        mock_llm = MockLLMClient(json_response="invalid json {{{")
        processor = XTrendProcessor(llm_client=mock_llm)

        filtered = await processor.filter_ai_trends(
            sample_trends_with_tweets, max_trends=10
        )

        # フォールバック: 全トレンドを返す
        assert len(filtered) == 3

    @pytest.mark.asyncio
    async def test_summarize_trend(self):
        """トレンド要約生成のテスト"""
        summary_response = json.dumps({
            "topics": [
                "GPT-5が正式発表、マルチモーダル性能が大幅向上",
                "API価格体系が刷新、開発者コミュニティで議論",
            ],
            "key_opinions": [
                "マルチモーダル性能が革新的",
                "実用性が大きく向上",
                "APIコストが懸念材料",
            ],
        })
        mock_llm = MockLLMClient(json_response=summary_response)
        processor = XTrendProcessor(llm_client=mock_llm)

        twt = TrendWithTweets(
            trend=Trend(name="GPT-5", tweet_volume=50000, region="global"),
            tweets=[
                Tweet(text="GPT-5 is amazing!", retweet_count=1500, author="user1"),
                Tweet(text="Great improvement", retweet_count=3000, author="user2"),
            ],
        )

        result = await processor.summarize_trend(twt)

        assert isinstance(result, TrendSummary)
        assert result.trend_name == "GPT-5"
        assert len(result.topics) == 2
        assert "GPT-5" in result.topics[0]
        assert len(result.key_opinions) == 3
        assert result.retweet_total == 4500
        assert result.region == "global"

    @pytest.mark.asyncio
    async def test_summarize_trend_no_tweets(self):
        """ツイートなしのトレンド要約テスト"""
        mock_llm = MockLLMClient()
        processor = XTrendProcessor(llm_client=mock_llm)

        twt = TrendWithTweets(
            trend=Trend(name="GPT-5", region="japan"),
            tweets=[],
        )

        result = await processor.summarize_trend(twt)

        assert result.trend_name == "GPT-5"
        assert any("見つかりませんでした" in t for t in result.topics)
        # LLM呼び出しなし
        assert len(mock_llm.chat_calls) == 0

    @pytest.mark.asyncio
    async def test_summarize_trend_llm_failure(self):
        """LLM要約失敗時のフォールバックテスト"""
        mock_llm = MockLLMClient(json_response="not valid json")
        processor = XTrendProcessor(llm_client=mock_llm)

        twt = TrendWithTweets(
            trend=Trend(name="GPT-5", region="global"),
            tweets=[Tweet(text="test", retweet_count=100)],
        )

        result = await processor.summarize_trend(twt)

        assert result.trend_name == "GPT-5"
        assert any("失敗" in t for t in result.topics)
        assert result.retweet_total == 100

    @pytest.mark.asyncio
    async def test_process_full_pipeline(self, sample_trends_with_tweets):
        """フルパイプラインのテスト"""
        # フィルタリングレスポンス
        filter_response = json.dumps({
            "selected": [{"index": 0, "relevance": "LLM"}]
        })
        # 要約レスポンス
        summary_response = json.dumps({
            "topics": ["GPT-5が話題になっている。"],
            "key_opinions": ["性能向上が著しい"],
        })

        # フィルタリング→要約の順でレスポンスを切り替え
        call_count = 0

        class SequentialMockLLM(MockLLMClient):
            async def chat_json(self, messages, model=None):
                nonlocal call_count
                call_count += 1
                self.chat_calls.append({"messages": messages, "model": model, "json": True})
                if call_count == 1:
                    return filter_response
                return summary_response

        mock_llm = SequentialMockLLM()
        processor = XTrendProcessor(llm_client=mock_llm)

        trends_by_region = {"global": sample_trends_with_tweets}
        result = await processor.process(trends_by_region, max_trends=10)

        assert "global" in result
        assert len(result["global"]) == 1
        assert result["global"][0].trend_name == "GPT-5"
        assert result["global"][0].topics == ["GPT-5が話題になっている。"]

    @pytest.mark.asyncio
    async def test_process_empty_regions(self):
        """空の地域データのテスト"""
        mock_llm = MockLLMClient()
        processor = XTrendProcessor(llm_client=mock_llm)

        result = await processor.process({"japan": [], "global": []})

        assert result["japan"] == []
        assert result["global"] == []


class TestKeywordSummarization:
    """キーワード検索結果の要約テスト"""

    @pytest.mark.asyncio
    async def test_summarize_keyword_results(self):
        """キーワード要約の正常系テスト"""
        summary_response = json.dumps({
            "topics": [
                "Claude Codeに関する議論が活発",
                "開発効率の向上が注目を集める",
            ],
            "key_opinions": [
                "コーディングの自動化が進む",
                "品質面での課題も指摘",
            ],
        })
        mock_llm = MockLLMClient(json_response=summary_response)
        processor = XTrendProcessor(llm_client=mock_llm)

        results = [
            KeywordSearchResult(
                keyword="Claude Code",
                tweets=[
                    Tweet(text="Claude Code is great!", retweet_count=500, author="dev1"),
                    Tweet(text="Using Claude Code for my project", retweet_count=200, author="dev2"),
                ],
            ),
        ]

        summaries = await processor.summarize_keyword_results(results)

        assert len(summaries) == 1
        assert isinstance(summaries[0], KeywordSummary)
        assert summaries[0].keyword == "Claude Code"
        assert any("Claude Code" in t for t in summaries[0].topics)
        assert summaries[0].retweet_total == 700

    @pytest.mark.asyncio
    async def test_summarize_keyword_results_empty_tweets(self):
        """ツイート0件のキーワードはスキップ"""
        mock_llm = MockLLMClient()
        processor = XTrendProcessor(llm_client=mock_llm)

        results = [
            KeywordSearchResult(keyword="nonexistent_topic", tweets=[]),
        ]

        summaries = await processor.summarize_keyword_results(results)
        assert summaries == []
        assert len(mock_llm.chat_calls) == 0

    @pytest.mark.asyncio
    async def test_summarize_keyword_results_empty_input(self):
        """空入力のテスト"""
        mock_llm = MockLLMClient()
        processor = XTrendProcessor(llm_client=mock_llm)

        summaries = await processor.summarize_keyword_results([])
        assert summaries == []


class TestTimelineProcessing:
    """タイムラインフィルタリング・要約テスト"""

    @pytest.mark.asyncio
    async def test_filter_ai_tweets(self):
        """AI関連ツイートフィルタリングのテスト"""
        filter_response = json.dumps({
            "selected_indices": [0, 2]
        })
        mock_llm = MockLLMClient(json_response=filter_response)
        processor = XTrendProcessor(llm_client=mock_llm)

        tweets = [
            Tweet(text="New LLM paper published", author="researcher"),
            Tweet(text="Great lunch today", author="user"),
            Tweet(text="GPT-5 benchmark results", author="dev"),
        ]

        filtered = await processor.filter_ai_tweets(tweets)

        assert len(filtered) == 2
        assert filtered[0].text == "New LLM paper published"
        assert filtered[1].text == "GPT-5 benchmark results"

    @pytest.mark.asyncio
    async def test_filter_ai_tweets_empty(self):
        """空入力のフィルタリングテスト"""
        mock_llm = MockLLMClient()
        processor = XTrendProcessor(llm_client=mock_llm)

        filtered = await processor.filter_ai_tweets([])
        assert filtered == []

    @pytest.mark.asyncio
    async def test_filter_ai_tweets_fallback(self):
        """フィルタリング失敗時のフォールバックテスト"""
        mock_llm = MockLLMClient(json_response="invalid json")
        processor = XTrendProcessor(llm_client=mock_llm)

        tweets = [Tweet(text="test tweet")]
        filtered = await processor.filter_ai_tweets(tweets)
        # フォールバック: 全ツイートを返す
        assert len(filtered) == 1

    @pytest.mark.asyncio
    async def test_summarize_timeline_results(self):
        """タイムライン要約の正常系テスト"""
        # フィルタリング→要約の順でレスポンスを返す
        call_count = 0
        filter_response = json.dumps({"selected_indices": [0]})
        summary_response = json.dumps({
            "topics": ["karpathyがLLMの推論能力について新しい知見を共有。"],
            "key_opinions": ["推論能力の限界について議論"],
        })

        class SequentialMockLLM(MockLLMClient):
            async def chat_json(self, messages, model=None):
                nonlocal call_count
                call_count += 1
                self.chat_calls.append({"messages": messages, "model": model, "json": True})
                if call_count == 1:
                    return filter_response
                return summary_response

        mock_llm = SequentialMockLLM()
        processor = XTrendProcessor(llm_client=mock_llm)

        results = [
            UserTimelineResult(
                username="karpathy",
                tweets=[
                    Tweet(text="New LLM reasoning research", retweet_count=3000, author="karpathy"),
                    Tweet(text="Great weather today", retweet_count=10, author="karpathy"),
                ],
            ),
        ]

        summaries = await processor.summarize_timeline_results(results)

        assert len(summaries) == 1
        assert isinstance(summaries[0], TimelineSummary)
        assert summaries[0].username == "karpathy"

    @pytest.mark.asyncio
    async def test_summarize_timeline_no_tweets(self):
        """ツイートなしのタイムラインはスキップ"""
        mock_llm = MockLLMClient()
        processor = XTrendProcessor(llm_client=mock_llm)

        results = [UserTimelineResult(username="user1", tweets=[])]
        summaries = await processor.summarize_timeline_results(results)
        assert summaries == []


class TestProcessAll:
    """process_all統合テスト"""

    @pytest.mark.asyncio
    async def test_process_all_basic(self):
        """process_allの基本テスト"""
        # トレンドフィルタ → トレンド要約 → キーワード要約 → TLフィルタ → TL要約
        call_count = 0
        filter_trends_response = json.dumps({
            "selected": [{"index": 0, "relevance": "AI"}]
        })
        summary_response = json.dumps({
            "topics": ["AIに関する話題。"],
            "key_opinions": ["注目度が高い"],
        })
        filter_tweets_response = json.dumps({
            "selected_indices": [0]
        })

        class SequentialMockLLM(MockLLMClient):
            async def chat_json(self, messages, model=None):
                nonlocal call_count
                call_count += 1
                self.chat_calls.append({"messages": messages, "model": model, "json": True})
                content = messages[0]["content"] if messages else ""
                if "トレンドリスト" in content:
                    return filter_trends_response
                if "ツイートリストから" in content:
                    return filter_tweets_response
                return summary_response

        mock_llm = SequentialMockLLM()
        processor = XTrendProcessor(llm_client=mock_llm)

        collect_result = CollectResult(
            trends={
                "global": [
                    TrendWithTweets(
                        trend=Trend(name="GPT-5", region="global"),
                        tweets=[Tweet(text="GPT-5 is great", retweet_count=100)],
                    ),
                ]
            },
            keyword_results=[
                KeywordSearchResult(
                    keyword="Claude Code",
                    tweets=[Tweet(text="Claude Code rocks", retweet_count=50)],
                ),
            ],
            timeline_results=[
                UserTimelineResult(
                    username="karpathy",
                    tweets=[Tweet(text="LLM research update", retweet_count=200)],
                ),
            ],
        )

        result = await processor.process_all(collect_result, max_trends=10)

        assert isinstance(result, ProcessResult)
        assert "global" in result.trend_summaries
        assert len(result.keyword_summaries) == 1
        assert result.keyword_summaries[0].keyword == "Claude Code"

    @pytest.mark.asyncio
    async def test_process_all_empty(self):
        """空のCollectResultのテスト"""
        mock_llm = MockLLMClient()
        processor = XTrendProcessor(llm_client=mock_llm)

        collect_result = CollectResult()
        result = await processor.process_all(collect_result)

        assert result.trend_summaries == {}
        assert result.keyword_summaries == []
        assert result.timeline_summaries == []
