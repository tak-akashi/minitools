#!/usr/bin/env python3
"""
Medium Daily Digest collection script - backward compatibility wrapper.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
import argparse
from datetime import datetime
from dotenv import load_dotenv

from minitools.collectors.medium import MediumCollector
from minitools.processors.translator import Translator
from minitools.publishers.notion import NotionPublisher
from minitools.publishers.slack import SlackPublisher
from minitools.utils.logger import setup_logger

load_dotenv()

logger = setup_logger(__name__, log_file="medium_daily_digest.log")




def main():
    """エントリーポイント（同期版）"""
    asyncio.run(main_async())

async def main_async():
    """メイン処理（非同期版）"""
    parser = argparse.ArgumentParser(description='Medium Daily Digestメールを取得してNotionに保存')
    parser.add_argument('--date', type=str, help='取得する日付 (YYYY-MM-DD形式)')
    parser.add_argument('--slack', action='store_true', 
                       help='Slackへの送信のみ実行')
    parser.add_argument('--notion', action='store_true', 
                       help='Notionへの保存のみ実行')
    
    args = parser.parse_args()
    
    # 日付の設定
    if args.date:
        try:
            target_date = datetime.strptime(args.date, '%Y-%m-%d')
        except ValueError:
            logger.error("日付は YYYY-MM-DD 形式で指定してください")
            return
    else:
        target_date = datetime.now()
    
    # フラグの処理
    save_notion = not args.slack or args.notion
    send_slack = not args.notion or args.slack
    
    # コレクターの初期化
    collector = MediumCollector()
    
    # メールを取得
    logger.info(f"Fetching Medium Daily Digest for {target_date.strftime('%Y-%m-%d')}")
    
    async with collector:
        messages = await collector.get_digest_emails(target_date)
        
        if not messages:
            logger.info("No Medium Daily Digest emails found")
            return
        
        # メール本文から記事を抽出
        email_body = collector.extract_email_body(messages[0])
        articles = collector.parse_articles(email_body)
        
        if not articles:
            logger.info("No articles found in email")
            return
        
        logger.info(f"Found {len(articles)} articles")
        
        # 翻訳と要約
        translator = Translator()
        processed_articles = []
        
        for article in articles:
            try:
                # 記事内容を取得
                content, author = await collector.fetch_article_content(article.url)
                if author:
                    article.author = author
                
                # 翻訳と要約
                if content:
                    result = await translator.translate_with_summary(
                        title=article.title,
                        content=content,
                        author=article.author
                    )
                    article.japanese_title = result['japanese_title']
                    article.japanese_summary = result['japanese_summary']
                
                # 辞書形式に変換
                processed_articles.append({
                    'title': article.title,
                    'url': article.url,
                    'author': article.author,
                    'japanese_title': article.japanese_title,
                    'japanese_summary': article.japanese_summary,
                    'date': target_date.strftime('%Y-%m-%d')
                })
                
            except Exception as e:
                logger.error(f"Error processing article '{article.title}': {e}")
    
    # Notionに保存
    if save_notion and processed_articles:
        database_id = os.getenv('NOTION_DB_ID_DAILY_DIGEST')
        if database_id:
            try:
                publisher = NotionPublisher()
                stats = await publisher.batch_save_articles(database_id, processed_articles)
                logger.info(f"Saved to Notion: {stats}")
            except Exception as e:
                logger.error(f"Error saving to Notion: {e}")
    
    # Slackに送信
    if send_slack and processed_articles:
        webhook_url = os.getenv('SLACK_WEBHOOK_URL_MEDIUM_DAILY_DIGEST')
        if webhook_url:
            try:
                async with SlackPublisher(webhook_url) as slack:
                    await slack.send_articles(
                        processed_articles,
                        date=target_date.strftime('%Y-%m-%d'),
                        title="Medium Daily Digest"
                    )
                logger.info("Sent to Slack")
            except Exception as e:
                logger.error(f"Error sending to Slack: {e}")
    
    logger.info("Processing completed")

if __name__ == "__main__":
    main()