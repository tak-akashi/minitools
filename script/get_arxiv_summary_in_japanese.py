#!/usr/bin/env python3
"""
arXiv論文要約ツール
arXivから指定したキーワードで論文を検索し、その要約を日本語に翻訳してNotionデータベースに保存し、結果をSlackに通知
並列処理により効率化
"""

import os
import json
import feedparser
import ollama
import asyncio
import aiohttp
from typing import List, Dict, Tuple, Optional
from datetime import datetime, timedelta
import pytz
import argparse
import logging
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# 並列処理の設定
MAX_CONCURRENT_PAPERS = 10    # 同時に処理する論文の最大数
MAX_CONCURRENT_OLLAMA = 5     # Ollama APIへの同時リクエスト数
MAX_CONCURRENT_NOTION = 3     # Notion APIへの同時リクエスト数

def setup_logger() -> logging.Logger:
    """ロガーの設定"""
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.INFO)
    
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    # コンソールハンドラ
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # ファイルハンドラ
    log_dir = Path("outputs/logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(log_dir / "arxiv.log", mode="a")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    
    return logger

logger = setup_logger()

NOTION_API_KEY = os.getenv("NOTION_API_KEY")
DATABASE_ID = os.getenv("NOTION_DB_ID")
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL")


class ArxivProcessorAsync:
    """arXiv論文を並列処理するクラス"""
    
    def __init__(self):
        self.ollama_client = ollama.Client()
        self.http_session = None
        self.ollama_semaphore = None
        self.notion_semaphore = None
        
    async def __aenter__(self):
        """非同期コンテキストマネージャーのエントリー"""
        connector = aiohttp.TCPConnector(limit=20)
        timeout = aiohttp.ClientTimeout(total=120)
        self.http_session = aiohttp.ClientSession(connector=connector, timeout=timeout)
        
        # セマフォの初期化
        self.ollama_semaphore = asyncio.Semaphore(MAX_CONCURRENT_OLLAMA)
        self.notion_semaphore = asyncio.Semaphore(MAX_CONCURRENT_NOTION)
        
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """非同期コンテキストマネージャーのクリーンアップ"""
        if self.http_session:
            await self.http_session.close()

    def search_arxiv(self, queries: List[str], start_date: str, end_date: str, max_results: int) -> List[Dict[str, str]]:
        """
        arXiv APIを使用して論文を検索
        
        Args:
            queries: 検索語のリスト
            start_date: 検索開始日（YYYYMMDD形式）
            end_date: 検索終了日（YYYYMMDD形式）
            max_results: 取得する最大結果数
        
        Returns:
            検索結果の論文情報のリスト
        """
        import requests  # 同期的な検索処理
        
        url = "http://export.arxiv.org/api/query"
        search_query = " AND ".join(queries)
        
        params = {
            "search_query": f"all:{search_query} AND submittedDate:[{start_date}000000 TO {end_date}235959]",
            "start": 0,
            "max_results": max_results,
            "sortBy": "submittedDate",
            "sortOrder": "ascending",
        }
        
        response = requests.get(url, params=params)
        feed = feedparser.parse(response.content)
        
        papers = []
        for entry in feed.entries:
            title = entry.title.replace("\n", "")
            pdf_url = next((link.href for link in entry.links if link.get('title') == 'pdf'), None)
            
            if pdf_url:
                papers.append({
                    "title": title,
                    "updated_date": entry.updated,
                    "published_date": entry.published,
                    "summary": entry.summary,
                    "pdf_url": pdf_url
                })
        
        return papers

    async def translate_to_japanese_async(self, text: str, model: str = "gemma3:27b", retry_count: int = 3) -> str:
        """
        ollamaを使用して日本語に翻訳（非同期版・リトライ機能付き）
        
        Args:
            text: 翻訳する英語のテキスト
            model: 使用するollamaモデル
            retry_count: リトライ回数
        
        Returns:
            日本語に翻訳されたテキスト
        """
        async with self.ollama_semaphore:
            for attempt in range(retry_count):
                try:
                    # Ollamaは同期APIなので、executorで実行
                    loop = asyncio.get_event_loop()
                    response = await loop.run_in_executor(
                        None,
                        lambda: self.ollama_client.chat(
                            model=model,
                            messages=[{
                                "role": "user",
                                "content": f"以下を日本語に翻訳して。\n\n{text}"
                            }]
                        )
                    )
                    return response["message"]["content"].strip()
                    
                except Exception as e:
                    if attempt < retry_count - 1:
                        wait_time = (attempt + 1) * 2  # 指数バックオフ
                        logger.warning(f"翻訳エラー: {e}. {wait_time}秒後にリトライ...")
                        await asyncio.sleep(wait_time)
                    else:
                        logger.error(f"翻訳エラー (リトライ回数超過): {e}")
                        return "翻訳に失敗しました"

    async def summarize_paper_briefly_async(self, title: str, summary: str, model: str = "gemma3:27b") -> str:
        """
        論文のタイトルと要約から簡潔な要約を生成（非同期版）
        """
        async with self.ollama_semaphore:
            try:
                prompt = f"""以下の論文のタイトルと要約を1〜2文で簡潔に要約してください。
        
タイトル: {title}
要約: {summary}

簡潔な要約:"""
                
                loop = asyncio.get_event_loop()
                response = await loop.run_in_executor(
                    None,
                    lambda: self.ollama_client.chat(
                        model=model,
                        messages=[{"role": "user", "content": prompt}]
                    )
                )
                return response["message"]["content"].strip()
                
            except Exception as e:
                logger.error(f"要約生成エラー: {e}")
                return f"{title}の要約生成に失敗しました"

    async def add_to_notion_async(
        self,
        title: str,
        published_date: str,
        updated_date: str,
        summary: str,
        translated_summary: str,
        url: str,
        retry_count: int = 3
    ) -> bool:
        """
        Notion APIにデータを送信（非同期版・リトライ機能付き）
        
        Returns:
            エラーが発生した場合True
        """
        if not NOTION_API_KEY or not DATABASE_ID:
            logger.error("Notion API key or Database ID not set")
            return True
        
        async with self.notion_semaphore:
            for attempt in range(retry_count):
                try:
                    api_url = "https://api.notion.com/v1/pages"
                    headers = {
                        "Authorization": f"Bearer {NOTION_API_KEY}",
                        "Content-Type": "application/json",
                        "Notion-Version": "2022-06-28"
                    }
                    
                    data = {
                        "parent": {"database_id": DATABASE_ID},
                        "properties": {
                            "タイトル": {
                                "title": [{"text": {"content": title}}]
                            },
                            "公開日": {
                                "date": {"start": published_date}
                            },
                            "更新日": {
                                "date": {"start": updated_date}
                            },
                            "概要": {
                                "rich_text": [{"text": {"content": summary[:2000]}}]  # Notion API limit
                            },
                            "日本語訳": {
                                "rich_text": [{"text": {"content": translated_summary[:2000]}}]
                            },
                            "URL": {
                                "url": url
                            }
                        }
                    }
                    
                    async with self.http_session.post(api_url, headers=headers, json=data) as response:
                        if response.status == 200:
                            logger.info(f"Added '{title}' to Notion.")
                            return False
                        else:
                            error_text = await response.text()
                            if attempt < retry_count - 1:
                                wait_time = (attempt + 1) * 2
                                logger.warning(f"Notion APIエラー (再試行 {attempt + 1}/{retry_count}): {response.status}. {wait_time}秒後にリトライ...")
                                await asyncio.sleep(wait_time)
                            else:
                                logger.error(f"Failed to add to Notion. Status: {response.status}, Response: {error_text}")
                                return True
                                
                except Exception as e:
                    if attempt < retry_count - 1:
                        wait_time = (attempt + 1) * 2
                        logger.warning(f"Notion保存エラー: {e}. {wait_time}秒後にリトライ...")
                        await asyncio.sleep(wait_time)
                    else:
                        logger.error(f"Error adding to Notion: {e}")
                        return True
            
            return True

    async def process_paper_async(self, paper: Dict[str, str], index: int, total: int) -> Tuple[bool, Dict[str, str]]:
        """
        単一の論文を非同期で処理
        
        Returns:
            (エラーが発生したかどうか, 処理済み論文データ)
        """
        logger.info(f"Processing {paper['title']} ({index + 1}/{total})")
        
        try:
            # 日本語に翻訳
            translated_summary = await self.translate_to_japanese_async(paper["summary"])
            
            # Notionに追加
            error = await self.add_to_notion_async(
                paper['title'],
                paper["published_date"],
                paper["updated_date"],
                paper["summary"],
                translated_summary,
                paper['pdf_url']
            )
            
            # 処理済みデータを準備
            processed_paper = paper.copy()
            processed_paper['translated_summary'] = translated_summary
            
            return error, processed_paper
            
        except Exception as e:
            logger.error(f"論文処理エラー ({paper['title']}): {e}")
            processed_paper = paper.copy()
            processed_paper['translated_summary'] = "処理に失敗しました"
            return True, processed_paper

    async def process_papers_async(self, papers: List[Dict[str, str]]) -> Tuple[int, List[Dict[str, str]]]:
        """
        論文を並列処理してNotionに保存
        
        Returns:
            (エラー数, 処理済み論文リスト)
        """
        if not papers:
            return 0, []
        
        error_count = 0
        processed_papers = []
        
        # 論文をバッチに分割して処理
        for i in range(0, len(papers), MAX_CONCURRENT_PAPERS):
            batch = papers[i:i + MAX_CONCURRENT_PAPERS]
            batch_num = i // MAX_CONCURRENT_PAPERS + 1
            total_batches = (len(papers) + MAX_CONCURRENT_PAPERS - 1) // MAX_CONCURRENT_PAPERS
            
            logger.info(f"バッチ {batch_num}/{total_batches} を処理中（{len(batch)}件）...")
            
            # バッチ内の論文を並列処理
            tasks = [
                self.process_paper_async(paper, i + idx, len(papers))
                for idx, paper in enumerate(batch)
            ]
            
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # 結果を処理
            for idx, result in enumerate(batch_results):
                if isinstance(result, Exception):
                    logger.error(f"論文処理エラー: {batch[idx]['title']} - {result}")
                    error_count += 1
                    # エラーでも基本データは保存
                    processed_paper = batch[idx].copy()
                    processed_paper['translated_summary'] = "処理に失敗しました"
                    processed_papers.append(processed_paper)
                else:
                    error, processed_paper = result
                    if error:
                        error_count += 1
                    processed_papers.append(processed_paper)
        
        return error_count, processed_papers

    async def format_slack_message_async(self, papers: List[dict], date: str) -> str:
        """
        論文データをSlack投稿用にフォーマット（非同期版）
        """
        if not papers:
            return f"*{date}のarXiv論文*\n本日は対象論文がありませんでした。"
        
        message = f"*{date}のarXiv論文 ({len(papers)}件)*\n\n"
        
        # 各論文の要約を並列生成
        tasks = [
            self.summarize_paper_briefly_async(paper['title'], paper['summary'])
            for paper in papers
        ]
        
        brief_summaries = await asyncio.gather(*tasks, return_exceptions=True)
        
        for i, (paper, brief_summary) in enumerate(zip(papers, brief_summaries), 1):
            if isinstance(brief_summary, Exception):
                brief_summary = f"{paper['title']}の要約生成に失敗しました"
            
            message += f"{i}. *{paper['title']}*\n"
            message += f"   📄 {brief_summary}\n"
            message += f"   🔗 <{paper['pdf_url']}|PDF>\n\n"
        
        return message

    async def send_to_slack_async(self, message: str) -> bool:
        """
        Slackに投稿（非同期版）
        """
        if not SLACK_WEBHOOK_URL:
            logger.error("SLACK_WEBHOOK_URL environment variable not set")
            return False
        
        payload = {"text": message}
        
        try:
            async with self.http_session.post(SLACK_WEBHOOK_URL, json=payload) as response:
                if response.status == 200:
                    logger.info("Successfully sent message to Slack")
                    return True
                else:
                    logger.error(f"Failed to send to Slack. Status code: {response.status}")
                    return False
        except Exception as e:
            logger.error(f"Error sending to Slack: {e}")
            return False

    async def main_async(
        self,
        queries: List[str],
        start_date: str,
        end_date: str,
        max_results: int,
        send_slack: bool = True
    ) -> None:
        """
        メイン処理
        """
        logger.info(
            f"Searching max {max_results} papers from {start_date} to {end_date} "
            f"with queries: {queries}"
        )
        
        # 論文を検索
        papers = self.search_arxiv(
            queries,
            start_date.replace("-", ""),
            end_date.replace("-", ""),
            max_results
        )
        logger.info(f"Found {len(papers)} papers")
        
        if not papers:
            logger.info("No papers found")
            if send_slack:
                slack_message = await self.format_slack_message_async([], end_date)
                await self.send_to_slack_async(slack_message)
            return
        
        # 論文を並列処理
        error_count, processed_papers = await self.process_papers_async(papers)
        
        logger.info(
            f"Processed {len(papers) - error_count} papers successfully. "
            f"{error_count} papers failed."
        )
        
        # Slackに投稿
        if send_slack:
            slack_message = await self.format_slack_message_async(processed_papers, end_date)
            await self.send_to_slack_async(slack_message)


def parse_args() -> argparse.Namespace:
    """コマンドライン引数を解析"""
    parser = argparse.ArgumentParser(
        description="arXivから論文を検索し、Notionに保存してSlackに通知"
    )
    
    jst = pytz.timezone('Asia/Tokyo')
    yesterday = (datetime.now(jst) - timedelta(days=1)).strftime("%Y-%m-%d")
    
    parser.add_argument(
        '-q', '--queries',
        nargs='+',
        default=["LLM", "(RAG OR FINETUNING OR AGENT)"],
        help="検索クエリ（複数指定可）"
    )
    parser.add_argument(
        '-d', '--days_before',
        type=int,
        default=1,
        help="何日前から検索するか"
    )
    parser.add_argument(
        '-b', '--base_date',
        type=str,
        default=yesterday,
        help="基準日（YYYY-MM-DD形式）"
    )
    parser.add_argument(
        '-r', '--max_results',
        type=int,
        default=50,
        help="取得する最大論文数"
    )
    parser.add_argument(
        '--no-slack',
        action='store_true',
        help="Slackへの投稿をスキップ"
    )
    
    return parser.parse_args()


async def main():
    """エントリーポイント"""
    args = parse_args()
    
    start_date = (
        datetime.strptime(args.base_date, "%Y-%m-%d") - 
        timedelta(days=args.days_before - 1)
    ).strftime("%Y-%m-%d")
    
    async with ArxivProcessorAsync() as processor:
        await processor.main_async(
            queries=args.queries,
            start_date=start_date,
            end_date=args.base_date,
            max_results=args.max_results,
            send_slack=not args.no_slack
        )


if __name__ == "__main__":
    asyncio.run(main())