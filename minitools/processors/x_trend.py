"""
X (Twitter) trend processor for filtering AI-related trends and generating summaries.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field

from minitools.collectors.x_trend import (
    CollectResult,
    KeywordSearchResult,
    TrendWithTweets,
    Tweet,
    UserTimelineResult,
    XTrendCollector,
)
from minitools.llm.base import BaseLLMClient, LLMError
from minitools.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class TrendSummary:
    """トレンド要約"""

    trend_name: str
    topics: list[str] = field(default_factory=list)  # 話題の箇条書き（最大5件）
    key_opinions: list[str] = field(default_factory=list)  # 主要意見（最大3件）
    retweet_total: int = 0  # RT数合計
    region: str = ""  # "japan" or "global"


@dataclass
class KeywordSummary:
    """キーワード検索要約"""

    keyword: str
    topics: list[str] = field(default_factory=list)
    key_opinions: list[str] = field(default_factory=list)
    retweet_total: int = 0


@dataclass
class TimelineSummary:
    """ユーザータイムライン要約"""

    username: str
    topics: list[str] = field(default_factory=list)
    key_opinions: list[str] = field(default_factory=list)
    retweet_total: int = 0


@dataclass
class ProcessResult:
    """全処理結果"""

    trend_summaries: dict[str, list[TrendSummary]] = field(default_factory=dict)
    keyword_summaries: list[KeywordSummary] = field(default_factory=list)
    timeline_summaries: list[TimelineSummary] = field(default_factory=list)


# AIトレンドフィルタリング用プロンプト
FILTER_PROMPT = """あなたはAI/機械学習分野の専門家です。
以下のX (Twitter) トレンドリストから、AI・LLM・機械学習・深層学習に関連するトレンドを選択してください。

## トレンドリスト
{trends_text}

## 選択基準
- AI、LLM、機械学習、深層学習、生成AI、ChatGPT、GPT、Claude、Gemini等に直接関連するもの
- AIを活用したサービスやプロダクトに関するもの
- AI業界のニュース（企業動向、規制、研究成果）に関するもの

## 回答形式（JSON）
最大{max_trends}件を関連度の高い順に選択し、以下の形式で回答:
{{
  "selected": [
    {{"index": 0, "relevance": "関連理由を10文字以内で"}},
    ...
  ]
}}

関連するトレンドが1件もない場合は {{"selected": []}} と回答してください。
"""

# トレンド要約用プロンプト
SUMMARIZE_PROMPT = """以下のX (Twitter) トレンド「{trend_name}」に関するツイート群を分析し、日本語で要約してください。

## ツイート一覧
{tweets_text}

## 回答形式（JSON）
{{
  "topics": [
    "<話題1（60文字以内）>",
    "<話題2（60文字以内）>",
    "<話題3（60文字以内）>"
  ],
  "key_opinions": [
    "<主要な意見1（50文字以内）>",
    "<主要な意見2（50文字以内）>",
    "<主要な意見3（50文字以内）>"
  ]
}}

注意:
- 英語のツイートも日本語で要約すること
- topicsは「何が話題になっているか」を項目ごとに箇条書きで（最大5件）
- 各topicは具体的な内容を含めること（例: 「○○がリリース、△△が大幅強化」）
- 主要意見は代表的な反応や見解を抽出（最大3件）
"""

# AIツイートフィルタリング用プロンプト
FILTER_TWEETS_PROMPT = """以下のツイートリストから、AI・LLM・機械学習・深層学習に関連するツイートのインデックスを選択してください。

## ツイート一覧
{tweets_text}

## 選択基準
- AI、LLM、機械学習、深層学習、生成AI等に直接関連するもの
- AI技術を活用したサービスやプロダクトに関するもの
- AI業界のニュース（企業動向、規制、研究成果）に関するもの

## 回答形式（JSON）
{{
  "selected_indices": [0, 2, 5]
}}

関連するツイートが1件もない場合は {{"selected_indices": []}} と回答してください。
"""


class XTrendProcessor:
    """トレンドのフィルタリングと要約を行うプロセッサ"""

    def __init__(
        self,
        llm_client: BaseLLMClient,
        max_concurrent: int = 3,
    ):
        """
        Args:
            llm_client: LLMクライアントインスタンス
            max_concurrent: 最大並列処理数
        """
        self.llm = llm_client
        self.max_concurrent = max_concurrent

    async def _call_llm_json(self, prompt: str) -> str:
        """LLMにJSONレスポンスをリクエスト"""
        if hasattr(self.llm, "chat_json"):
            return await self.llm.chat_json([{"role": "user", "content": prompt}])
        else:
            return await self.llm.generate(prompt)

    async def filter_ai_trends(
        self,
        trends: list[TrendWithTweets],
        max_trends: int = 10,
    ) -> list[TrendWithTweets]:
        """
        トレンドリストからAI/LLM関連をLLMでフィルタリング

        Args:
            trends: トレンドリスト
            max_trends: 最大選択数

        Returns:
            AI関連トレンドのリスト
        """
        if not trends:
            return []

        logger.info(f"Filtering {len(trends)} trends for AI relevance...")

        # トレンドリストをテキスト化
        trends_text_parts = []
        for i, twt in enumerate(trends):
            volume_str = (
                f" (tweet_volume: {twt.trend.tweet_volume})"
                if twt.trend.tweet_volume
                else ""
            )
            trends_text_parts.append(f"[{i}] {twt.trend.name}{volume_str}")

        trends_text = "\n".join(trends_text_parts)

        prompt = FILTER_PROMPT.format(
            trends_text=trends_text,
            max_trends=max_trends,
        )

        try:
            response = await self._call_llm_json(prompt)
            result = json.loads(response)
            selected_indices = [
                item["index"]
                for item in result.get("selected", [])
                if isinstance(item.get("index"), int)
                and 0 <= item["index"] < len(trends)
            ]

            filtered = [trends[i] for i in selected_indices[:max_trends]]
            logger.info(
                f"Selected {len(filtered)} AI-related trends from {len(trends)}"
            )
            return filtered

        except (json.JSONDecodeError, LLMError, TypeError, ValueError, KeyError) as e:
            logger.warning(
                f"LLM filtering failed ({type(e).__name__}: {e}), "
                f"returning all trends as fallback"
            )
            return trends[:max_trends]

    async def summarize_trend(
        self,
        trend_with_tweets: TrendWithTweets,
    ) -> TrendSummary:
        """
        トレンドのツイート群を要約

        Args:
            trend_with_tweets: トレンドと関連ツイート

        Returns:
            トレンド要約
        """
        trend = trend_with_tweets.trend
        tweets = trend_with_tweets.tweets

        if not tweets:
            return TrendSummary(
                trend_name=trend.name,
                topics=[f"{trend.name}に関するツイートが見つかりませんでした。"],
                region=trend.region,
            )

        tweets_text, retweet_total = self._format_tweets_for_prompt(tweets)

        prompt = SUMMARIZE_PROMPT.format(
            trend_name=trend.name,
            tweets_text=tweets_text,
        )

        try:
            response = await self._call_llm_json(prompt)
            result = json.loads(response)

            return TrendSummary(
                trend_name=trend.name,
                topics=[t[:60] for t in result.get("topics", ["要約なし"])[:5]],
                key_opinions=result.get("key_opinions", [])[:3],
                retweet_total=retweet_total,
                region=trend.region,
            )

        except (json.JSONDecodeError, LLMError, TypeError, ValueError) as e:
            logger.warning(
                f"Failed to summarize trend '{trend.name}': {type(e).__name__}: {e}"
            )
            return TrendSummary(
                trend_name=trend.name,
                topics=["要約の生成に失敗しました。"],
                retweet_total=retweet_total,
                region=trend.region,
            )

    def _format_tweets_for_prompt(self, tweets: list[Tweet]) -> tuple[str, int]:
        """ツイートをプロンプト用テキストに変換"""
        parts = []
        retweet_total = 0
        for tweet in tweets:
            rt_str = f" (RT: {tweet.retweet_count})" if tweet.retweet_count else ""
            author_str = f" - @{tweet.author}" if tweet.author else ""
            parts.append(f"- {tweet.text[:300]}{rt_str}{author_str}")
            retweet_total += tweet.retweet_count
        return "\n".join(parts), retweet_total

    async def filter_ai_tweets(
        self,
        tweets: list[Tweet],
    ) -> list[Tweet]:
        """
        ツイートリストからAI関連をLLMでフィルタリング

        Args:
            tweets: ツイートリスト

        Returns:
            AI関連ツイートのリスト
        """
        if not tweets:
            return []

        logger.info(f"Filtering {len(tweets)} tweets for AI relevance...")

        tweets_text_parts = []
        for i, tweet in enumerate(tweets):
            author_str = f" (@{tweet.author})" if tweet.author else ""
            tweets_text_parts.append(f"[{i}] {tweet.text[:300]}{author_str}")

        tweets_text = "\n".join(tweets_text_parts)
        prompt = FILTER_TWEETS_PROMPT.format(tweets_text=tweets_text)

        try:
            response = await self._call_llm_json(prompt)
            result = json.loads(response)
            selected_indices = [
                idx
                for idx in result.get("selected_indices", [])
                if isinstance(idx, int) and 0 <= idx < len(tweets)
            ]

            filtered = [tweets[i] for i in selected_indices]
            logger.info(
                f"Selected {len(filtered)} AI-related tweets from {len(tweets)}"
            )
            return filtered

        except (json.JSONDecodeError, LLMError, TypeError, ValueError, KeyError) as e:
            logger.warning(
                f"Tweet filtering failed ({type(e).__name__}: {e}), "
                f"returning all tweets as fallback"
            )
            return tweets

    async def summarize_keyword_results(
        self,
        results: list[KeywordSearchResult],
    ) -> list[KeywordSummary]:
        """
        キーワード検索結果を要約

        Args:
            results: キーワード検索結果リスト

        Returns:
            キーワード要約リスト
        """
        if not results:
            return []

        logger.info(f"Summarizing {len(results)} keyword search results...")
        semaphore = asyncio.Semaphore(self.max_concurrent)

        async def summarize_keyword(
            result: KeywordSearchResult,
        ) -> KeywordSummary | None:
            if not result.tweets:
                logger.info(f"Skipping keyword '{result.keyword}' (no tweets)")
                return None

            async with semaphore:
                tweets_text, retweet_total = self._format_tweets_for_prompt(
                    result.tweets
                )
                prompt = SUMMARIZE_PROMPT.format(
                    trend_name=result.keyword,
                    tweets_text=tweets_text,
                )

                try:
                    response = await self._call_llm_json(prompt)
                    parsed = json.loads(response)

                    return KeywordSummary(
                        keyword=result.keyword,
                        topics=[t[:60] for t in parsed.get("topics", ["要約なし"])[:5]],
                        key_opinions=parsed.get("key_opinions", [])[:3],
                        retweet_total=retweet_total,
                    )
                except (json.JSONDecodeError, LLMError, TypeError, ValueError) as e:
                    logger.warning(
                        f"Failed to summarize keyword '{result.keyword}': "
                        f"{type(e).__name__}: {e}"
                    )
                    return KeywordSummary(
                        keyword=result.keyword,
                        topics=["要約の生成に失敗しました。"],
                        retweet_total=retweet_total,
                    )

        summaries = await asyncio.gather(*[summarize_keyword(r) for r in results])
        return [s for s in summaries if s is not None]

    async def summarize_timeline_results(
        self,
        results: list[UserTimelineResult],
    ) -> list[TimelineSummary]:
        """
        ユーザータイムライン結果をフィルタリング・要約

        Args:
            results: タイムライン結果リスト

        Returns:
            タイムライン要約リスト
        """
        if not results:
            return []

        logger.info(f"Processing {len(results)} user timelines...")
        semaphore = asyncio.Semaphore(self.max_concurrent)

        async def process_timeline(
            result: UserTimelineResult,
        ) -> TimelineSummary | None:
            if not result.tweets:
                logger.info(f"Skipping @{result.username} (no tweets)")
                return None

            async with semaphore:
                # AI関連ツイートをフィルタリング
                ai_tweets = await self.filter_ai_tweets(result.tweets)
                if not ai_tweets:
                    logger.info(f"No AI-related tweets from @{result.username}")
                    return None

                tweets_text, retweet_total = self._format_tweets_for_prompt(ai_tweets)
                prompt = SUMMARIZE_PROMPT.format(
                    trend_name=f"@{result.username}",
                    tweets_text=tweets_text,
                )

                try:
                    response = await self._call_llm_json(prompt)
                    parsed = json.loads(response)

                    return TimelineSummary(
                        username=result.username,
                        topics=[t[:60] for t in parsed.get("topics", ["要約なし"])[:5]],
                        key_opinions=parsed.get("key_opinions", [])[:3],
                        retweet_total=retweet_total,
                    )
                except (json.JSONDecodeError, LLMError, TypeError, ValueError) as e:
                    logger.warning(
                        f"Failed to summarize @{result.username}: "
                        f"{type(e).__name__}: {e}"
                    )
                    return TimelineSummary(
                        username=result.username,
                        topics=["要約の生成に失敗しました。"],
                        retweet_total=retweet_total,
                    )

        summaries = await asyncio.gather(*[process_timeline(r) for r in results])
        return [s for s in summaries if s is not None]

    async def process(
        self,
        trends_by_region: dict[str, list[TrendWithTweets]],
        max_trends: int = 10,
    ) -> dict[str, list[TrendSummary]]:
        """
        地域ごとのトレンドをフィルタリング・要約

        Args:
            trends_by_region: 地域ごとのトレンドリスト
            max_trends: 地域ごとの最大トレンド数

        Returns:
            地域ごとのTrendSummaryリスト
        """
        logger.info("Starting X trend processing...")
        result: dict[str, list[TrendSummary]] = {}
        semaphore = asyncio.Semaphore(self.max_concurrent)

        for region, trends in trends_by_region.items():
            if not trends:
                result[region] = []
                continue

            logger.info(f"Processing {len(trends)} trends for {region}...")

            # AI関連トレンドをフィルタリング
            filtered = await self.filter_ai_trends(trends, max_trends=max_trends)

            if not filtered:
                logger.info(f"No AI-related trends found for {region}")
                result[region] = []
                continue

            # 各トレンドを並列で要約
            async def summarize_with_semaphore(
                twt: TrendWithTweets,
            ) -> TrendSummary | None:
                async with semaphore:
                    try:
                        return await self.summarize_trend(twt)
                    except Exception as e:
                        logger.warning(
                            f"Failed to summarize trend '{twt.trend.name}': {e}"
                        )
                        return None

            summaries = await asyncio.gather(
                *[summarize_with_semaphore(t) for t in filtered]
            )

            result[region] = [s for s in summaries if s is not None]
            logger.info(f"Completed {region}: {len(result[region])} trends summarized")

        total = sum(len(v) for v in result.values())
        logger.info(f"X trend processing completed: {total} trends total")
        return result

    async def process_all(
        self,
        collect_result: CollectResult,
        max_trends: int = 10,
        collector: XTrendCollector | None = None,
    ) -> ProcessResult:
        """
        3ソースの処理を統合するエントリポイント

        Args:
            collect_result: 全収集結果
            max_trends: 地域ごとの最大トレンド数
            collector: ツイート取得用のCollector（トレンドのコスト最適化用）

        Returns:
            全処理結果
        """
        logger.info("Starting process_all for 3 sources...")

        # 1. トレンド処理（フィルタリング → ツイート取得 → 要約）
        trend_summaries: dict[str, list[TrendSummary]] = {}
        if collect_result.trends:
            # まずフィルタリング（ツイートなしのトレンドでフィルタ）
            for region, trends in collect_result.trends.items():
                if not trends:
                    trend_summaries[region] = []
                    continue

                filtered = await self.filter_ai_trends(trends, max_trends=max_trends)
                if not filtered:
                    trend_summaries[region] = []
                    continue

                # フィルタ後のトレンドのみツイート取得（コスト最適化）
                if collector:
                    semaphore = asyncio.Semaphore(5)

                    async def fetch_and_summarize(
                        twt: TrendWithTweets,
                    ) -> TrendSummary | None:
                        async with semaphore:
                            if not twt.tweets:
                                tweets = await collector.get_tweets_for_trend(
                                    twt.trend.name, count=20
                                )
                                twt = TrendWithTweets(trend=twt.trend, tweets=tweets)
                            return await self.summarize_trend(twt)

                    summaries = await asyncio.gather(
                        *[fetch_and_summarize(t) for t in filtered]
                    )
                    trend_summaries[region] = [s for s in summaries if s is not None]
                else:
                    # collectorがない場合はツイートなしで要約
                    summaries = await asyncio.gather(
                        *[self.summarize_trend(t) for t in filtered]
                    )
                    trend_summaries[region] = [s for s in summaries if s is not None]

        # 2. キーワード検索結果の要約
        keyword_summaries = await self.summarize_keyword_results(
            collect_result.keyword_results
        )

        # 3. タイムライン結果の要約
        timeline_summaries = await self.summarize_timeline_results(
            collect_result.timeline_results
        )

        total = (
            sum(len(v) for v in trend_summaries.values())
            + len(keyword_summaries)
            + len(timeline_summaries)
        )
        logger.info(f"process_all completed: {total} items total")

        return ProcessResult(
            trend_summaries=trend_summaries,
            keyword_summaries=keyword_summaries,
            timeline_summaries=timeline_summaries,
        )
