#!/usr/bin/env python3
"""
Google Alerts collection script - backward compatibility wrapper.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
import argparse
import logging
from datetime import datetime, timedelta
from dotenv import load_dotenv

from minitools.collectors.google_alerts import GoogleAlertsCollector
from minitools.processors.translator import Translator
from minitools.publishers.notion import NotionPublisher
from minitools.publishers.slack import SlackPublisher
from minitools.utils.logger import setup_logger
from minitools.utils.config import get_config

load_dotenv()

# ロガーは後で初期化（argparseの前には基本設定のみ）
logger = None


def main():
    """エントリーポイント（同期版）"""
    asyncio.run(main_async())

async def main_async():
    parser = argparse.ArgumentParser(description='Google Alertsメールを処理してNotionに保存')
    parser.add_argument('--hours', type=int, default=6,
                       help='過去何時間分のメールを取得するか')
    parser.add_argument('--date', type=str,
                       help='特定の日付のメールを取得 (YYYY-MM-DD形式)')
    parser.add_argument('--notion', action='store_true',
                       help='Notionへの保存のみ実行')
    parser.add_argument('--slack', action='store_true',
                       help='Slackへの送信のみ実行')
    parser.add_argument('--debug', action='store_true',
                       help='デバッグモードで実行')
    
    args = parser.parse_args()
    
    # 設定ファイルからデフォルトログレベルを取得
    config = get_config()
    default_log_level = config.get('logging.level', 'INFO').upper()
    
    # デバッグオプションが指定されている場合は上書き
    if args.debug:
        log_level = logging.DEBUG
    else:
        log_level = getattr(logging, default_log_level, logging.INFO)
    
    # ロガーの初期化
    global logger
    logger = setup_logger("scripts.google_alerts", log_file="google_alerts.log", level=log_level)
    
    # 日付の設定
    target_date = None
    if args.date:
        try:
            target_date = datetime.strptime(args.date, '%Y-%m-%d')
        except ValueError:
            logger.error("日付は YYYY-MM-DD 形式で指定してください")
            return
    
    # フラグの処理
    save_notion = not args.slack or args.notion
    send_slack = not args.notion or args.slack
    
    # コレクターの初期化
    collector = GoogleAlertsCollector()
    
    # メールを取得
    logger.info(f"Fetching Google Alerts emails...")
    
    if target_date:
        emails = collector.get_alerts_emails(date=target_date)
    else:
        emails = collector.get_alerts_emails(hours_back=args.hours)
    
    if not emails:
        logger.info("No Google Alerts emails found")
        return
    
    # アラートを抽出
    all_alerts = []
    for email in emails:
        alerts = collector.parse_alerts(email)
        all_alerts.extend(alerts)
    
    if not all_alerts:
        logger.info("No alerts found in emails")
        return
    
    logger.info(f"Found {len(all_alerts)} alerts")
    
    # 記事の本文を取得
    await collector.fetch_articles_for_alerts(all_alerts)
    
    # 翻訳と要約
    translator = Translator()
    processed_alerts = []
    
    for alert in all_alerts:
        try:
            # 記事本文がある場合はそれを、ない場合はスニペットを使用
            content = alert.article_content if alert.article_content else alert.snippet
            
            # タイトルと内容を翻訳・要約
            result = await translator.translate_with_summary(
                title=alert.title,
                content=content,
                author=alert.source
            )
            
            # 辞書形式に変換
            processed_alerts.append({
                'title': alert.title,
                'url': alert.url,
                'source': alert.source,
                'japanese_title': result['japanese_title'],
                'japanese_summary': result['japanese_summary'],
                'date': datetime.now().strftime('%Y-%m-%d')
            })
            
        except Exception as e:
            logger.error(f"Error processing alert '{alert.title}': {e}")
    
    # Notionに保存
    if save_notion and processed_alerts:
        database_id = os.getenv('NOTION_DB_ID_GOOGLE_ALERTS')
        if database_id:
            try:
                publisher = NotionPublisher()
                stats = await publisher.batch_save_articles(database_id, processed_alerts)
                logger.info(f"Saved to Notion: {stats}")
            except Exception as e:
                logger.error(f"Error saving to Notion: {e}")
    
    # Slackに送信
    if send_slack and processed_alerts:
        webhook_url = os.getenv('SLACK_WEBHOOK_URL_GOOGLE_ALERTS')
        if webhook_url:
            try:
                async with SlackPublisher(webhook_url) as slack:
                    await slack.send_articles(
                        processed_alerts,
                        title="Google Alerts"
                    )
                logger.info("Sent to Slack")
            except Exception as e:
                logger.error(f"Error sending to Slack: {e}")
    
    logger.info("Processing completed")


if __name__ == "__main__":
    main()