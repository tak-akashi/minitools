"""
ArXiv weekly digest processor for generating paper importance rankings.
"""

import asyncio
import json
from typing import Any, Dict, List, Optional

from minitools.llm.base import BaseLLMClient, LLMError
from minitools.researchers.trend import TrendResearcher
from minitools.utils.logger import get_logger

logger = get_logger(__name__)

# トレンドあり版の重要度評価プロンプト（4観点）
IMPORTANCE_PROMPT_WITH_TRENDS = """あなたはAI/機械学習分野の専門研究者です。
以下のArXiv論文の重要度を評価してください。

## 現在のAIトレンド（参考情報）
{trend_summary}

注目されているトピック: {trend_topics}

## 評価基準（各項目1-10点）
1. **技術的新規性**: 新しい手法・アプローチの独創性
2. **業界インパクト**: 実務・産業への影響可能性
3. **実用性**: 実際に使える・応用できる度合い
4. **トレンド関連性**: 現在のAIトレンドとの関連度

## 論文情報
タイトル: {title}
概要（日本語訳）: {summary}

## 回答形式（JSON）
{{
  "technical_novelty": <1-10の整数>,
  "industry_impact": <1-10の整数>,
  "practicality": <1-10の整数>,
  "trend_relevance": <1-10の整数>,
  "reason": "<100文字以内の簡潔な評価理由>"
}}
"""

# トレンドなし版の重要度評価プロンプト（3観点）
IMPORTANCE_PROMPT_WITHOUT_TRENDS = """あなたはAI/機械学習分野の専門研究者です。
以下のArXiv論文の重要度を評価してください。

## 評価基準（各項目1-10点）
1. **技術的新規性**: 新しい手法・アプローチの独創性
2. **業界インパクト**: 実務・産業への影響可能性
3. **実用性**: 実際に使える・応用できる度合い

## 論文情報
タイトル: {title}
概要（日本語訳）: {summary}

## 回答形式（JSON）
{{
  "technical_novelty": <1-10の整数>,
  "industry_impact": <1-10の整数>,
  "practicality": <1-10の整数>,
  "reason": "<100文字以内の簡潔な評価理由>"
}}
"""

# トレンドサマリー日本語化プロンプト
TREND_SUMMARY_PROMPT = """以下のAIトレンド情報を日本語で要約してください。

## 英語サマリー
{english_summary}

## 注目トピック
{topics}

## 回答形式
- 250文字以内の日本語で要約
- 現在のAI業界で注目されているトレンドを簡潔に説明
- 専門用語はそのまま使用可（例: LLM, RAG, マルチモーダル等）
"""

# ハイライト生成プロンプト
HIGHLIGHTS_PROMPT = """以下のArXiv論文について、重要ポイントを抽出してください。

## 論文情報
タイトル: {title}
概要（日本語訳）: {summary}

## 回答形式（JSON）
{{
  "selection_reason": "<なぜこの論文を選出したかを50文字以内で>",
  "key_points": [
    "<重要ポイント1（30文字以内）>",
    "<重要ポイント2（30文字以内）>",
    "<重要ポイント3（30文字以内）>"
  ]
}}
"""


class ArxivWeeklyProcessor:
    """ArXiv週次ダイジェスト生成プロセッサ"""

    def __init__(
        self,
        llm_client: BaseLLMClient,
        trend_researcher: Optional[TrendResearcher] = None,
        max_concurrent: int = 3,
    ):
        """
        Args:
            llm_client: LLMクライアントインスタンス
            trend_researcher: TrendResearcherインスタンス（省略時は自動生成）
            max_concurrent: 最大並列処理数（デフォルト: 3）
        """
        self.llm = llm_client
        self.trend_researcher = trend_researcher
        self.max_concurrent = max_concurrent
        logger.info(
            f"ArxivWeeklyProcessor initialized (max_concurrent={max_concurrent})"
        )

    def _safe_get_score(self, value: Any, default: int = 5) -> int:
        """
        スコア値を安全に取得（型チェックと変換）

        Args:
            value: スコア値（整数、文字列、Noneなど）
            default: デフォルト値

        Returns:
            1-10の範囲の整数スコア
        """
        if value is None:
            return default

        if isinstance(value, int):
            return max(1, min(10, value))

        if isinstance(value, str):
            try:
                num_value = float(value)
                return max(1, min(10, int(num_value)))
            except (ValueError, TypeError):
                return default

        if isinstance(value, float):
            return max(1, min(10, int(value)))

        return default

    async def rank_papers_by_importance(
        self,
        papers: List[Dict[str, Any]],
        trends: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        各論文に重要度スコア(1-10)を付与

        Args:
            papers: 論文リスト
            trends: TrendResearcherから取得したトレンド情報

        Returns:
            importance_scoreが付与された論文リスト
        """
        if not papers:
            return []

        logger.info(f"Ranking {len(papers)} papers by importance...")
        semaphore = asyncio.Semaphore(self.max_concurrent)

        async def score_paper(paper: Dict[str, Any]) -> Dict[str, Any]:
            async with semaphore:
                title = paper.get("title", paper.get("タイトル", ""))
                # 日本語訳を優先的に使用
                summary = paper.get("日本語訳", paper.get("summary", ""))

                if not title and not summary:
                    logger.warning("Paper without title or summary, assigning score 0")
                    paper["importance_score"] = 0
                    paper["score_reason"] = "情報なし"
                    return paper

                # プロンプトを構築
                if trends:
                    prompt = IMPORTANCE_PROMPT_WITH_TRENDS.format(
                        trend_summary=trends.get("summary", "情報なし"),
                        trend_topics=", ".join(trends.get("topics", [])),
                        title=title,
                        summary=summary[:1000] if summary else "概要なし",
                    )
                else:
                    prompt = IMPORTANCE_PROMPT_WITHOUT_TRENDS.format(
                        title=title,
                        summary=summary[:1000] if summary else "概要なし",
                    )

                try:
                    # LLM呼び出し
                    if hasattr(self.llm, "chat_json"):
                        response = await self.llm.chat_json(
                            [{"role": "user", "content": prompt}]
                        )
                    else:
                        response = await self.llm.generate(prompt)

                    # JSONをパース
                    result = json.loads(response)

                    # スコアを計算
                    if trends:
                        # 4観点の平均
                        scores = [
                            self._safe_get_score(result.get("technical_novelty"), 5),
                            self._safe_get_score(result.get("industry_impact"), 5),
                            self._safe_get_score(result.get("practicality"), 5),
                            self._safe_get_score(result.get("trend_relevance"), 5),
                        ]
                    else:
                        # 3観点の平均
                        scores = [
                            self._safe_get_score(result.get("technical_novelty"), 5),
                            self._safe_get_score(result.get("industry_impact"), 5),
                            self._safe_get_score(result.get("practicality"), 5),
                        ]

                    avg_score = sum(scores) / len(scores)
                    paper["importance_score"] = round(avg_score, 1)
                    paper["score_reason"] = result.get("reason", "")
                    paper["score_details"] = result

                    logger.debug(
                        f"Scored '{title[:40]}...': {paper['importance_score']}"
                    )

                except (json.JSONDecodeError, LLMError, TypeError, ValueError) as e:
                    logger.warning(
                        f"Failed to score paper '{title[:40]}...': {type(e).__name__}: {e}"
                    )
                    paper["importance_score"] = 5.0  # デフォルトスコア
                    paper["score_reason"] = "スコアリング失敗"

                return paper

        # 全論文を並列処理
        tasks = [score_paper(paper) for paper in papers]
        scored_papers = await asyncio.gather(*tasks)

        logger.info(f"Completed scoring {len(scored_papers)} papers")
        return list(scored_papers)

    async def select_top_papers(
        self,
        papers: List[Dict[str, Any]],
        top_n: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        スコア上位N件を選出

        Args:
            papers: importance_scoreが付与された論文リスト
            top_n: 取得する論文数（デフォルト: 10）

        Returns:
            上位N件の論文リスト
        """
        if not papers:
            return []

        # スコア順でソート
        sorted_papers = sorted(
            papers,
            key=lambda x: x.get("importance_score", 0),
            reverse=True,
        )

        top_papers = sorted_papers[:top_n]

        if top_papers:
            logger.info(
                f"Selected top {len(top_papers)} papers "
                f"(score range: {top_papers[0].get('importance_score', 0):.1f} - "
                f"{top_papers[-1].get('importance_score', 0):.1f})"
            )
        else:
            logger.info("No papers selected")

        return top_papers

    async def generate_paper_highlights(
        self,
        papers: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        選出理由と重要ポイントを生成

        Args:
            papers: 論文リスト

        Returns:
            selection_reason, key_pointsが付与された論文リスト
        """
        if not papers:
            return []

        logger.info(f"Generating highlights for {len(papers)} papers...")
        semaphore = asyncio.Semaphore(self.max_concurrent)

        async def generate_highlight(paper: Dict[str, Any]) -> Dict[str, Any]:
            async with semaphore:
                title = paper.get("title", paper.get("タイトル", ""))
                summary = paper.get("日本語訳", paper.get("summary", ""))

                if not title and not summary:
                    paper["selection_reason"] = "ハイライト生成失敗"
                    paper["key_points"] = []
                    return paper

                prompt = HIGHLIGHTS_PROMPT.format(
                    title=title,
                    summary=summary[:1000] if summary else "概要なし",
                )

                try:
                    if hasattr(self.llm, "chat_json"):
                        response = await self.llm.chat_json(
                            [{"role": "user", "content": prompt}]
                        )
                    else:
                        response = await self.llm.generate(prompt)

                    result = json.loads(response)

                    paper["selection_reason"] = result.get(
                        "selection_reason", "選出理由なし"
                    )
                    paper["key_points"] = result.get("key_points", [])

                    logger.debug(f"Generated highlights for '{title[:40]}...'")

                except (json.JSONDecodeError, LLMError, TypeError, ValueError) as e:
                    logger.warning(
                        f"Failed to generate highlights for '{title[:40]}...': "
                        f"{type(e).__name__}: {e}"
                    )
                    paper["selection_reason"] = "ハイライト生成失敗"
                    paper["key_points"] = []

                return paper

        tasks = [generate_highlight(paper) for paper in papers]
        highlighted_papers = await asyncio.gather(*tasks)

        logger.info(
            f"Completed generating highlights for {len(highlighted_papers)} papers"
        )
        return list(highlighted_papers)

    async def _translate_trend_summary(
        self,
        trend_info: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        トレンドサマリーを日本語に翻訳

        Args:
            trend_info: TrendResearcherから取得したトレンド情報

        Returns:
            日本語化されたトレンド情報
        """
        english_summary = trend_info.get("summary", "")
        topics = trend_info.get("topics", [])

        if not english_summary:
            return trend_info

        prompt = TREND_SUMMARY_PROMPT.format(
            english_summary=english_summary,
            topics=", ".join(topics) if topics else "なし",
        )

        try:
            if hasattr(self.llm, "chat"):
                response = await self.llm.chat(
                    [{"role": "user", "content": prompt}]
                )
            else:
                response = await self.llm.generate(prompt)

            # 日本語サマリーで更新
            japanese_summary = response.strip()
            if japanese_summary:
                trend_info["summary"] = japanese_summary
                logger.info("Trend summary translated to Japanese")

        except (LLMError, Exception) as e:
            logger.warning(f"Failed to translate trend summary: {e}")
            # 翻訳失敗時は元のサマリーを維持

        return trend_info

    async def process(
        self,
        papers: List[Dict[str, Any]],
        top_n: int = 10,
        use_trends: bool = True,
    ) -> Dict[str, Any]:
        """
        一括処理: トレンド調査 → スコアリング → 選出 → ハイライト生成

        Args:
            papers: 全論文リスト
            top_n: 上位論文数（デフォルト: 10）
            use_trends: Trueの場合、Tavily APIでトレンドを調査してスコアリングに使用

        Returns:
            処理結果の辞書:
            - trend_info: トレンド情報（use_trends=Falseの場合はNone）
            - papers: 上位論文リスト（ハイライト付き）
            - total_papers: 処理した論文総数
        """
        logger.info(
            f"Starting ArXiv weekly digest processing ({len(papers)} papers)..."
        )

        # 1. トレンド調査（オプション）
        trend_info = None
        if use_trends and self.trend_researcher:
            trend_info = await self.trend_researcher.get_current_trends()
            if trend_info:
                logger.info(
                    f"Trend info obtained: {len(trend_info.get('topics', []))} topics"
                )
                # トレンドサマリーを日本語化
                trend_info = await self._translate_trend_summary(trend_info)
            else:
                logger.warning("Failed to get trend info, proceeding without trends")

        # 2. 重要度スコアリング
        scored_papers = await self.rank_papers_by_importance(papers, trends=trend_info)

        # 3. 上位N件を選出
        top_papers = await self.select_top_papers(scored_papers, top_n)

        # 4. ハイライト生成
        highlighted_papers = await self.generate_paper_highlights(top_papers)

        logger.info("ArXiv weekly digest processing completed")

        return {
            "trend_info": trend_info,
            "papers": highlighted_papers,
            "total_papers": len(papers),
        }
