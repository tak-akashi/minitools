"""Tests for SlackPublisher.format_x_trend_digest."""

import pytest

from minitools.processors.x_trend import (
    KeywordSummary,
    ProcessResult,
    TimelineSummary,
    TrendSummary,
)
from minitools.publishers.slack import SlackPublisher


@pytest.fixture
def sample_summaries():
    """テスト用のTrendSummaryデータ（dict形式、後方互換テスト用）"""
    return {
        "global": [
            TrendSummary(
                trend_name="GPT-5",
                topics=["OpenAIがGPT-5を正式発表", "マルチモーダル性能が大幅向上"],
                key_opinions=["推論能力が革新的", "APIコストが懸念材料", "日本語性能も向上"],
                retweet_total=12300,
                region="global",
            ),
            TrendSummary(
                trend_name="Claude 4",
                topics=["AnthropicがClaude 4を発表", "コーディング能力が飛躍的に向上"],
                key_opinions=["安全性が高い", "長文処理が優秀"],
                retweet_total=8500,
                region="global",
            ),
        ],
        "japan": [
            TrendSummary(
                trend_name="国内LLMベンチマーク",
                topics=["日本語処理性能の比較結果が公開", "注目を集めている"],
                key_opinions=["日本語モデルの進化が顕著", "実用レベルに到達"],
                retweet_total=2100,
                region="japan",
            ),
        ],
    }


@pytest.fixture
def sample_process_result():
    """テスト用のProcessResultデータ"""
    return ProcessResult(
        trend_summaries={
            "global": [
                TrendSummary(
                    trend_name="GPT-5",
                    topics=["OpenAIがGPT-5を正式発表", "マルチモーダル性能が大幅向上"],
                    key_opinions=["推論能力が革新的", "APIコストが懸念材料"],
                    retweet_total=12300,
                    region="global",
                ),
            ],
            "japan": [
                TrendSummary(
                    trend_name="国内LLMベンチマーク",
                    topics=["日本語処理性能の比較結果が公開"],
                    key_opinions=["日本語モデルの進化が顕著"],
                    retweet_total=2100,
                    region="japan",
                ),
            ],
        },
        keyword_summaries=[
            KeywordSummary(
                keyword="Claude Code",
                topics=["Claude Codeの開発体験が話題", "生産性の向上が注目"],
                key_opinions=["コーディング自動化が加速", "品質向上も実感"],
                retweet_total=856,
            ),
        ],
        timeline_summaries=[
            TimelineSummary(
                username="karpathy",
                topics=["LLMの推論能力に関する新しい知見を共有"],
                key_opinions=["推論の限界を指摘", "新たなアプローチを提案"],
                retweet_total=3200,
            ),
        ],
    )


class TestFormatXTrendDigest:
    """format_x_trend_digestのテスト"""

    def test_basic_format(self, sample_summaries):
        """日本+グローバルの基本フォーマットテスト（後方互換: dict入力）"""
        message = SlackPublisher.format_x_trend_digest(sample_summaries)

        assert "X AI トレンドダイジェスト" in message
        assert "グローバル AI トレンド" in message
        assert "日本 AI トレンド" in message
        assert "GPT-5" in message
        assert "Claude 4" in message
        assert "国内LLMベンチマーク" in message

    def test_rt_count_formatting(self, sample_summaries):
        """RT数のフォーマットテスト（1000以上はK表記、タイトル行に表示）"""
        message = SlackPublisher.format_x_trend_digest(sample_summaries)

        assert "12.3K RT" in message
        assert "8.5K RT" in message
        assert "2.1K RT" in message
        # RT数がタイトル行に表示されることを確認
        assert "*GPT-5*  (🔄 12.3K RT)" in message

    def test_empty_summaries(self):
        """トレンド0件時のメッセージテスト"""
        message = SlackPublisher.format_x_trend_digest({"japan": [], "global": []})

        assert "X AI トレンドダイジェスト" in message
        assert "見つかりませんでした" in message

    def test_single_region_only(self, sample_summaries):
        """片方の地域のみのテスト"""
        message = SlackPublisher.format_x_trend_digest(
            {"japan": sample_summaries["japan"]}
        )

        assert "日本 AI トレンド" in message
        assert "グローバル AI トレンド" not in message

    def test_character_limit(self):
        """3000文字制限テスト"""
        # 大量のトレンドを生成
        many_summaries = {
            "global": [
                TrendSummary(
                    trend_name=f"Very Long Trend Name {i} that takes up space",
                    topics=["A" * 60] * 5,
                    key_opinions=["Opinion " * 10] * 3,
                    retweet_total=1000 * i,
                    region="global",
                )
                for i in range(50)
            ],
            "japan": [
                TrendSummary(
                    trend_name=f"長いトレンド名 {i} テスト用の長い名前",
                    topics=["あ" * 60] * 5,
                    key_opinions=["意見" * 20] * 3,
                    retweet_total=500 * i,
                    region="japan",
                )
                for i in range(50)
            ],
        }

        message = SlackPublisher.format_x_trend_digest(many_summaries)
        assert len(message) <= 3100  # some margin for trailing chars

    def test_key_opinions_included(self, sample_summaries):
        """主要意見が含まれるテスト"""
        message = SlackPublisher.format_x_trend_digest(sample_summaries)

        assert "💬 主要な反応:" in message
        assert "推論能力が革新的" in message
        assert "安全性が高い" in message

    def test_no_data_for_region(self):
        """地域データなしのテスト"""
        message = SlackPublisher.format_x_trend_digest({})

        assert "見つかりませんでした" in message


class TestFormatXTrendDigestProcessResult:
    """ProcessResult入力でのformat_x_trend_digestテスト"""

    def test_three_section_format(self, sample_process_result):
        """3セクション構成のフォーマットテスト"""
        message = SlackPublisher.format_x_trend_digest(sample_process_result)

        assert "X AI トレンドダイジェスト" in message
        # トレンドセクション
        assert "グローバル AI トレンド" in message
        assert "日本 AI トレンド" in message
        assert "GPT-5" in message
        # キーワードセクション
        assert "キーワード検索ハイライト" in message
        assert "Claude Code" in message
        assert "856 RT" in message
        # タイムラインセクション
        assert "注目アカウントの発信" in message
        assert "@karpathy" in message
        assert "3.2K RT" in message
        # 新しいフォーマット要素
        assert "💬 主要な反応:" in message

    def test_partial_sections_keywords_only(self):
        """キーワードセクションのみのテスト"""
        result = ProcessResult(
            trend_summaries={"global": [], "japan": []},
            keyword_summaries=[
                KeywordSummary(
                    keyword="AI Agent",
                    topics=["AIエージェントの進化が話題"],
                    key_opinions=["自律的な判断能力"],
                    retweet_total=500,
                ),
            ],
            timeline_summaries=[],
        )

        message = SlackPublisher.format_x_trend_digest(result)

        assert "キーワード検索ハイライト" in message
        assert "AI Agent" in message
        assert "グローバル AI トレンド" not in message
        assert "注目アカウントの発信" not in message

    def test_partial_sections_timeline_only(self):
        """タイムラインセクションのみのテスト"""
        result = ProcessResult(
            trend_summaries={},
            keyword_summaries=[],
            timeline_summaries=[
                TimelineSummary(
                    username="svpino",
                    topics=["MLOps関連の発信"],
                    retweet_total=200,
                ),
            ],
        )

        message = SlackPublisher.format_x_trend_digest(result)

        assert "注目アカウントの発信" in message
        assert "@svpino" in message
        assert "キーワード検索ハイライト" not in message

    def test_empty_process_result(self):
        """空のProcessResultのテスト"""
        result = ProcessResult()
        message = SlackPublisher.format_x_trend_digest(result)

        assert "見つかりませんでした" in message

    def test_three_section_character_limit(self):
        """3セクション構成の3000文字制限テスト"""
        result = ProcessResult(
            trend_summaries={
                "global": [
                    TrendSummary(
                        trend_name=f"Trend {i}",
                        topics=["A" * 60] * 5,
                        key_opinions=["opinion " * 10] * 3,
                        retweet_total=1000 * i,
                        region="global",
                    )
                    for i in range(20)
                ],
            },
            keyword_summaries=[
                KeywordSummary(
                    keyword=f"keyword_{i}",
                    topics=["B" * 60] * 5,
                    key_opinions=["kw opinion " * 10] * 3,
                    retweet_total=500 * i,
                )
                for i in range(20)
            ],
            timeline_summaries=[
                TimelineSummary(
                    username=f"user_{i}",
                    topics=["C" * 60] * 5,
                    key_opinions=["tl opinion " * 10] * 3,
                    retweet_total=300 * i,
                )
                for i in range(20)
            ],
        )

        message = SlackPublisher.format_x_trend_digest(result)
        assert len(message) <= 3100
