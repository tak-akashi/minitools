#!/usr/bin/env python3
"""
Medium Daily Digest collection script - backward compatibility wrapper.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
import argparse
import logging
from datetime import datetime
from dotenv import load_dotenv

from minitools.collectors.medium import MediumCollector
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
    """メイン処理（非同期版）"""
    parser = argparse.ArgumentParser(description='Medium Daily Digestメールを取得してNotionに保存')
    parser.add_argument('--date', type=str, help='取得する日付 (YYYY-MM-DD形式)')
    parser.add_argument('--slack', action='store_true', 
                       help='Slackへの送信のみ実行')
    parser.add_argument('--notion', action='store_true', 
                       help='Notionへの保存のみ実行')
    parser.add_argument('--debug', action='store_true',
                       help='デバッグモードで実行')
    parser.add_argument('--test', action='store_true',
                       help='テストモード（最初の1記事のみ処理）')
    
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
    logger = setup_logger("scripts.medium", log_file="medium_daily_digest.log", level=log_level)
    
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
    logger.info(f"Medium Daily Digest ({target_date.strftime('%Y-%m-%d')}) の処理を開始します...")
    
    async with collector:
        messages = await collector.get_digest_emails(target_date)
        
        if not messages:
            logger.info("Medium Daily Digestメールが見つかりません")
            return
        
        # メール本文から記事を抽出
        email_body = collector.extract_email_body(messages[0])
        articles = collector.parse_articles(email_body)
        
        if not articles:
            logger.info("メールに記事が見つかりません")
            return
        
        logger.info(f"{len(articles)}件の記事を検出しました")
        
        # テストモードの場合は最初の1件のみ処理
        if args.test:
            articles = articles[:1]
            logger.info("テストモード: 最初の1記事のみ処理します")
        
        # 翻訳と要約
        translator = Translator()
        processed_articles = []
        
        logger.info(f"記事の翻訳と要約を開始します...")
        # バッチ処理のための設定
        batch_size = 10  # 並列処理する記事数
        total_batches = (len(articles) + batch_size - 1) // batch_size
        
        async def process_article(article, index, total):
            """個別記事の処理"""
            try:
                logger.info(f"  記事 {index}/{total} 処理開始: {article.title[:50]}...")
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
                    logger.info(f"  -> 翻訳・要約完了: {article.japanese_title[:30]}...")
                else:
                    logger.warning(f"  -> コンテンツ取得失敗: {article.title[:50]}...")
                
                # 辞書形式に変換
                return {
                    'title': article.title,
                    'url': article.url,
                    'author': article.author,
                    'japanese_title': article.japanese_title,
                    'japanese_summary': article.japanese_summary,
                    'date': target_date.strftime('%Y-%m-%d')
                }
            except Exception as e:
                logger.error(f"  -> 処理エラー '{article.title[:50]}...': {e}")
                return None
        
        # バッチごとに処理
        for batch_num in range(total_batches):
            start_idx = batch_num * batch_size
            end_idx = min(start_idx + batch_size, len(articles))
            batch = articles[start_idx:end_idx]
            
            logger.info(f"バッチ {batch_num + 1}/{total_batches} を処理中 ({len(batch)}件)...")
            
            # バッチ内の記事を並列処理
            tasks = [
                process_article(article, start_idx + i + 1, len(articles))
                for i, article in enumerate(batch)
            ]
            
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # 成功した記事のみを追加
            for result in batch_results:
                if result and not isinstance(result, Exception):
                    processed_articles.append(result)
    
    # Notionに保存
    if save_notion and processed_articles:
        database_id = os.getenv('NOTION_DB_ID_DAILY_DIGEST')
        if database_id:
            try:
                logger.info(f"Notionに{len(processed_articles)}件の記事を保存中...")
                publisher = NotionPublisher()
                stats = await publisher.batch_save_articles(database_id, processed_articles)
                logger.info("=" * 60)
                logger.info(f"Notionへの保存結果:")
                logger.info(f"  成功: {stats.get('success', 0)}件")
                logger.info(f"  スキップ (既存): {stats.get('skipped', 0)}件")
                logger.info(f"  失敗: {stats.get('failed', 0)}件")
                logger.info("=" * 60)
            except Exception as e:
                logger.error(f"Notionへの保存エラー: {e}")
    
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
                logger.info("Slackへの送信が完了しました")
            except Exception as e:
                logger.error(f"Slackへの送信エラー: {e}")
    
    logger.info("処理が完了しました")
    if processed_articles:
        logger.info(f"  処理記事数: {len(processed_articles)}件")
        logger.info(f"  対象日付: {target_date.strftime('%Y-%m-%d')}")

if __name__ == "__main__":
    main()