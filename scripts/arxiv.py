#!/usr/bin/env python3
"""
ArXiv paper collection script - backward compatibility wrapper.
"""

import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import argparse
import asyncio
from datetime import datetime, timedelta

import pytz
from dotenv import load_dotenv

from minitools.collectors.arxiv import ArxivCollector
from minitools.processors.translator import Translator
from minitools.publishers.notion import NotionPublisher
from minitools.publishers.slack import SlackPublisher
from minitools.utils.logger import setup_logger

load_dotenv()

logger = setup_logger(__name__, log_file="arxiv.log")


def main():
    """エントリーポイント（同期版）"""
    asyncio.run(main_async())

async def main_async():
    # デフォルトの基準日（昨日）を計算
    jst = pytz.timezone('Asia/Tokyo')
    yesterday = (datetime.now(jst) - timedelta(days=1)).strftime("%Y-%m-%d")
    
    parser = argparse.ArgumentParser(description='arXiv論文を検索して要約をNotionに保存')
    parser.add_argument('--keywords', '-q', '--queries', nargs='+', 
                       default=["LLM", "(RAG OR FINETUNING OR AGENT)"], 
                       help='検索キーワード（複数指定可）')
    parser.add_argument('--days', type=int, default=1, 
                       help='何日前から検索するか')
    parser.add_argument('--date', '-d', type=str, default=yesterday,
                       help='基準日（YYYY-MM-DD形式）')
    parser.add_argument('--max-results', '-r', '--max_results', type=int, default=50, 
                       help='取得する最大論文数')
    parser.add_argument('--no-notion', action='store_true', 
                       help='Notion保存をスキップ')
    parser.add_argument('--no-slack', action='store_true', 
                       help='Slackへの投稿をスキップ')
    
    args = parser.parse_args()
    
    # 日付範囲の設定（base_dateを基準に計算）
    base_date = datetime.strptime(args.date, "%Y-%m-%d")
    start_date = base_date - timedelta(days=args.days - 1)
    end_date = base_date
    
    # コレクターの初期化
    collector = ArxivCollector()
    
    # 論文を検索
    logger.info(f"Searching max {args.max_results} papers from {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')} with queries: {args.keywords}")
    papers = collector.search(
        queries=args.keywords,
        start_date=start_date.strftime("%Y%m%d"),
        end_date=end_date.strftime("%Y%m%d"),
        max_results=args.max_results
    )
    
    if not papers:
        logger.info("No papers found")
    else:
        logger.info(f"Found {len(papers)} papers")
    
    # 翻訳と要約
    translator = Translator()
    processed_papers = []
    
    if papers:  # 論文がある場合のみ処理
        async with collector:
            for paper in papers:
                try:
                    # タイトルと要約を翻訳
                    result = await translator.translate_with_summary(
                        title=paper['title'],
                        content=paper['abstract'],
                        author=paper['authors']
                    )
                    
                    paper['japanese_title'] = result['japanese_title']
                    paper['japanese_summary'] = result['japanese_summary']
                    processed_papers.append(paper)
                    
                except Exception as e:
                    logger.error(f"Error processing paper '{paper['title']}': {e}")
    
    # Notionに保存
    if not args.no_notion and processed_papers:
        database_id = os.getenv('NOTION_DB_ID')
        if database_id:
            try:
                publisher = NotionPublisher()
                stats = await publisher.batch_save_articles(database_id, processed_papers)
                logger.info(f"Saved to Notion: {stats}")
            except Exception as e:
                logger.error(f"Error saving to Notion: {e}")
    
    # Slackに送信（論文が0件でも通知）
    if not args.no_slack:
        webhook_url = os.getenv('SLACK_WEBHOOK_URL')
        if webhook_url:
            try:
                async with SlackPublisher(webhook_url) as slack:
                    await slack.send_articles(
                        processed_papers,
                        date=end_date.strftime('%Y-%m-%d'),
                        title=f"arXiv Papers ({', '.join(args.keywords)})"
                    )
                logger.info("Sent to Slack")
            except Exception as e:
                logger.error(f"Error sending to Slack: {e}")
    
    logger.info("Processing completed")


if __name__ == "__main__":
    main()