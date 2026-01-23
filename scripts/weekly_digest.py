#!/usr/bin/env python3
"""
Weekly AI Digest - Generate weekly summary of AI news from Notion DB.

Usage:
    uv run minitools-weekly-digest --days 7 --top 20
    uv run minitools-weekly-digest --provider openai --dry-run
    uv run minitools-weekly-digest --output outputs/digest.md
"""

import argparse
import asyncio
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

from minitools.llm import get_embedding_client, get_llm_client
from minitools.processors import WeeklyDigestProcessor
from minitools.publishers.slack import SlackPublisher
from minitools.readers.notion import NotionReader
from minitools.utils.config import get_config
from minitools.utils.logger import setup_logger

logger = setup_logger(name="scripts.weekly_digest", log_file="weekly_digest.log")


async def generate_digest(
    days: int,
    top_n: int,
    provider: str,
    dry_run: bool,
    output_file: str | None,
    no_dedup: bool = False,
    embedding_provider: str | None = None,
) -> None:
    """
    週次ダイジェストを生成

    Args:
        days: 過去何日分の記事を取得するか
        top_n: 上位何件の記事を選出するか
        provider: LLMプロバイダー（ollama/openai）
        dry_run: True の場合はSlack送信をスキップ
        output_file: 出力ファイルパス（指定時はファイルに保存）
        no_dedup: True の場合は類似記事除去をスキップ
        embedding_provider: Embeddingプロバイダー（ollama/openai、省略時はproviderと同じ）
    """
    # 日付範囲を計算
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)
    start_date_str = start_date.strftime("%Y-%m-%d")
    end_date_str = end_date.strftime("%Y-%m-%d")

    # Embeddingプロバイダーを決定（指定がなければLLMプロバイダーと同じ）
    embed_provider = embedding_provider or provider

    logger.info(f"Generating weekly digest for {start_date_str} to {end_date_str}")
    logger.info(f"LLM Provider: {provider}, Embedding Provider: {embed_provider}, Top articles: {top_n}")

    # Notion DBからGoogle Alertsの記事を取得
    database_id = os.getenv("NOTION_GOOGLE_ALERTS_DATABASE_ID")
    if not database_id:
        logger.error("NOTION_GOOGLE_ALERTS_DATABASE_ID is not set")
        sys.exit(1)

    reader = NotionReader()
    logger.info(f"Fetching articles from Notion DB: {database_id[:8]}...")

    try:
        articles = await reader.get_articles_by_date_range(
            database_id=database_id,
            start_date=start_date_str,
            end_date=end_date_str,
            date_property="Date",  # Google Alertsのデフォルト日付プロパティ
        )
    except Exception as e:
        logger.error(f"Failed to fetch articles from Notion: {e}")
        sys.exit(1)

    if not articles:
        logger.warning("No articles found in the specified date range")
        print(f"期間 {start_date_str} - {end_date_str} に該当する記事がありませんでした。")
        return

    logger.info(f"Found {len(articles)} articles")

    # LLMクライアントを取得
    try:
        llm_client = get_llm_client(provider=provider)
    except Exception as e:
        logger.error(f"Failed to initialize LLM client: {e}")
        sys.exit(1)

    # Embeddingクライアントを取得（重複除去が有効な場合のみ）
    embedding_client = None
    if not no_dedup:
        try:
            embedding_client = get_embedding_client(provider=embed_provider)
        except Exception as e:
            logger.error(f"Failed to initialize embedding client: {e}")
            sys.exit(1)

    # 週次ダイジェストを生成
    processor = WeeklyDigestProcessor(
        llm_client=llm_client,
        embedding_client=embedding_client,
    )
    # no_dedupがTrueの場合はdeduplicate=Falseを渡す
    result = await processor.process(
        articles=articles,
        top_n=top_n,
        deduplicate=not no_dedup if no_dedup else None,
    )

    trend_summary = result["trend_summary"]
    top_articles = result["top_articles"]

    logger.info(f"Processing complete: {len(top_articles)} top articles selected")

    # Slackフォーマットでメッセージを生成
    slack = SlackPublisher()
    message = slack.format_weekly_digest(
        start_date=start_date_str,
        end_date=end_date_str,
        trend_summary=trend_summary,
        articles=top_articles,
    )

    # ファイル出力
    if output_file:
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(message, encoding="utf-8")
        logger.info(f"Digest saved to: {output_path}")
        print(f"ダイジェストを保存しました: {output_path}")

    # dry-runの場合は標準出力に表示
    if dry_run:
        print("\n" + "=" * 60)
        print("【DRY RUN】以下のメッセージがSlackに送信されます:")
        print("=" * 60 + "\n")
        print(message)
        print("\n" + "=" * 60)
        logger.info("Dry run complete - Slack message not sent")
        return

    # Slackに送信
    webhook_url = os.getenv("SLACK_WEEKLY_DIGEST_WEBHOOK_URL")
    if not webhook_url:
        logger.warning("SLACK_WEEKLY_DIGEST_WEBHOOK_URL is not set. Skipping Slack notification.")
        print("Slack Webhook URLが設定されていないため、通知をスキップしました。")
        return

    async with SlackPublisher(webhook_url=webhook_url) as slack_publisher:
        success = await slack_publisher.send_message(message)
        if success:
            logger.info("Weekly digest sent to Slack successfully")
            print("週次ダイジェストをSlackに送信しました。")
        else:
            logger.error("Failed to send weekly digest to Slack")
            sys.exit(1)


def main():
    """CLIエントリーポイント"""
    config = get_config()

    parser = argparse.ArgumentParser(
        description="Generate weekly AI digest from Notion Google Alerts DB",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  uv run weekly-digest                              # デフォルト設定で実行
  uv run weekly-digest --days 14                    # 過去14日分を取得
  uv run weekly-digest --top 10                     # 上位10件を選出
  uv run weekly-digest --provider openai            # OpenAI APIを使用
  uv run weekly-digest --embedding openai           # Embeddingのみ OpenAI を使用
  uv run weekly-digest --dry-run                    # Slack送信をスキップ
  uv run weekly-digest --output out.md              # ファイルに保存
  uv run weekly-digest --no-dedup                   # 類似記事除去をスキップ
        """,
    )

    parser.add_argument(
        "--days",
        type=int,
        default=config.get("defaults.weekly_digest.days_back", 7),
        help="過去何日分の記事を取得するか（デフォルト: 7）",
    )

    parser.add_argument(
        "--top",
        type=int,
        default=config.get("defaults.weekly_digest.top_articles", 20),
        help="上位何件の記事を選出するか（デフォルト: 20）",
    )

    parser.add_argument(
        "--provider",
        choices=["ollama", "openai"],
        default=config.get("llm.provider", "ollama"),
        help="LLMプロバイダー（デフォルト: 設定ファイルの値）",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Slack送信をスキップし、出力内容を表示",
    )

    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="出力ファイルパス（指定時はファイルに保存）",
    )

    parser.add_argument(
        "--no-dedup",
        action="store_true",
        help="類似記事除去をスキップ",
    )

    parser.add_argument(
        "--embedding",
        choices=["ollama", "openai"],
        default=None,
        help="Embeddingプロバイダー（省略時はLLMプロバイダーと同じ）",
    )

    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("Weekly AI Digest")
    logger.info("=" * 60)
    logger.info(f"Days: {args.days}")
    logger.info(f"Top articles: {args.top}")
    logger.info(f"Provider: {args.provider}")
    logger.info(f"Embedding: {args.embedding or args.provider}")
    logger.info(f"Dry run: {args.dry_run}")
    logger.info(f"Output file: {args.output or 'None'}")
    logger.info(f"Deduplication: {'disabled' if args.no_dedup else 'enabled'}")
    logger.info("=" * 60)

    asyncio.run(
        generate_digest(
            days=args.days,
            top_n=args.top,
            provider=args.provider,
            dry_run=args.dry_run,
            output_file=args.output,
            no_dedup=args.no_dedup,
            embedding_provider=args.embedding,
        )
    )

    logger.info(f"処理完了: {args.top}件の記事を処理しました")


if __name__ == "__main__":
    main()
