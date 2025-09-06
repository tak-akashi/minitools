#!/usr/bin/env python3
"""
Medium Daily Digest to Notion
Gmail経由でMedium Daily Digestメールを取得し、記事情報を抽出して日本語要約と共にNotionに保存
並列処理により効率化
"""

import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pickle
import base64
import re
import argparse
import asyncio
import aiohttp
import signal
import socket
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional
import json
from dataclasses import dataclass
from urllib.parse import urlparse
import pytz

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import httplib2

import requests
from bs4 import BeautifulSoup
from notion_client import Client
import ollama
from dotenv import load_dotenv
from minitools.utils.logger import setup_logger

load_dotenv()

# スコープ設定
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

# Slack設定
SLACK_WEBHOOK_URL = os.getenv('SLACK_WEBHOOK_URL_MEDIUM_DAILY_DIGEST')

# 並列処理の設定
MAX_CONCURRENT_ARTICLES = 10  # 同時に処理する記事の最大数
MAX_CONCURRENT_OLLAMA = 3     # Ollama APIへの同時リクエスト数
MAX_CONCURRENT_NOTION = 3     # Notion APIへの同時リクエスト数
MAX_CONCURRENT_HTTP = 10      # HTTPリクエストの同時接続数

# ロガーの設定
logger = setup_logger(
    name=__name__,
    log_file="medium_daily_digest.log"
)

@dataclass
class Article:
    """記事情報を格納するデータクラス"""
    title: str
    url: str
    author: str
    japanese_title: str = ""
    summary: str = ""
    japanese_summary: str = ""
    date_processed: str = ""


class MediumDigestProcessorAsync:
    """Medium Daily Digestメールを処理してNotionに保存するクラス（非同期版）"""
    
    def __init__(self):
        self.gmail_service = None
        self.notion_client = None
        self.ollama_client = None
        self.http_session = None
        self.ollama_semaphore = None
        self.notion_semaphore = None
        self.setup_clients()
    
    def setup_clients(self):
        """各種APIクライアントの初期化"""
        # Gmail API
        self.gmail_service = self._authenticate_gmail()
        if self.gmail_service is None:
            raise ValueError("Gmail APIの初期化に失敗しました")
        
        # Notion API
        notion_token = os.getenv('NOTION_API_KEY')
        if not notion_token:
            raise ValueError("NOTION_API_KEY(環境変数)が設定されていません")
        self.notion_client = Client(auth=notion_token)
        
        # Ollama Client
        self.ollama_client = ollama.Client()
        
        # セマフォの初期化
        self.ollama_semaphore = asyncio.Semaphore(MAX_CONCURRENT_OLLAMA)
        self.notion_semaphore = asyncio.Semaphore(MAX_CONCURRENT_NOTION)
    
    async def __aenter__(self):
        """非同期コンテキストマネージャーのエントリー"""
        connector = aiohttp.TCPConnector(limit=MAX_CONCURRENT_HTTP)
        timeout = aiohttp.ClientTimeout(total=60, connect=30, sock_connect=30, sock_read=30)
        self.http_session = aiohttp.ClientSession(connector=connector, timeout=timeout)
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """非同期コンテキストマネージャーのクリーンアップ"""
        if self.http_session:
            await self.http_session.close()
    
    def _authenticate_gmail(self):
        """Gmail APIの認証"""
        try:
            creds = None
            token_path = 'token.pickle'
            
            if os.path.exists(token_path):
                with open(token_path, 'rb') as token:
                    creds = pickle.load(token)
            
            if not creds or not creds.valid:
                if creds and creds.expired and creds.refresh_token:
                    creds.refresh(Request())
                else:
                    credentials_path = os.getenv('GMAIL_CREDENTIALS_PATH', 'credentials.json')
                    if not os.path.exists(credentials_path):
                        raise FileNotFoundError(f"認証ファイル {credentials_path} が見つかりません")
                    
                    flow = InstalledAppFlow.from_client_secrets_file(credentials_path, SCOPES)
                    creds = flow.run_local_server(port=0)
                
                with open(token_path, 'wb') as token:
                    pickle.dump(creds, token)
            
            return build('gmail', 'v1', credentials=creds)
        except Exception as e:
            logger.error(f"Gmail認証エラー: {e}")
            raise
    
    async def get_medium_digest_emails_async(self, date: Optional[datetime] = None) -> List[Dict]:
        """Medium Daily Digestメールをスレッドから取得"""
        if date is None:
            date = datetime.now()
        
        # JSTタイムゾーンを設定
        jst = pytz.timezone('Asia/Tokyo')
        
        # dateがnaiveの場合はJSTとして扱う
        if date.tzinfo is None:
            date = jst.localize(date)
        
        # 指定された日付の開始と終了を計算（JST）
        start_date_jst = date.replace(hour=0, minute=0, second=0, microsecond=0)
        end_date_jst = start_date_jst + timedelta(days=1)
        
        # Unix タイムスタンプに変換（これによりタイムゾーンの問題を回避）
        start_timestamp = int(start_date_jst.timestamp())
        end_timestamp = int(end_date_jst.timestamp())
        
        # デバッグ情報を出力
        logger.info(f"検索期間 (JST): {start_date_jst} から {end_date_jst}")
        logger.info(f"タイムスタンプ: {start_timestamp} から {end_timestamp}")
        
        # 差出人とタイムスタンプ範囲で検索
        query = f'from:noreply@medium.com after:{start_timestamp} before:{end_timestamp}'
        logger.info(f"Gmail検索クエリ: {query}")
        
        try:
            # Gmail APIの呼び出しを非同期で実行
            loop = asyncio.get_event_loop()
            
            # DNS解決エラーの詳細情報を追加
            try:
                response = await loop.run_in_executor(
                    None,
                    lambda: self.gmail_service.users().threads().list(
                        userId='me',
                        q=query,
                        maxResults=1
                    ).execute()
                )
            except socket.gaierror as e:
                logger.error(f"DNS解決エラー: {e}")
                logger.error("ネットワーク接続を確認してください。")
                raise
            except Exception as e:
                logger.error(f"Gmail API呼び出しエラー: {e}")
                raise

            threads = response.get('threads', [])
            if not threads:
                return []

            thread_id = threads[0]['id']
            thread = await loop.run_in_executor(
                None,
                lambda: self.gmail_service.users().threads().get(
                    userId='me',
                    id=thread_id
                ).execute()
            )
            
            # スレッド内の最新メッセージを返す
            messages = thread.get('messages', [])
            if messages:
                # メッセージの受信時刻も確認（デバッグ用）
                msg = messages[-1]
                if 'internalDate' in msg:
                    received_timestamp = int(msg['internalDate']) / 1000
                    received_date = datetime.fromtimestamp(received_timestamp, tz=jst)
                    logger.info(f"メール受信日時 (JST): {received_date}")
                
                return [messages[-1]] # 最新のメッセージのみをリストで返す
            return []

        except HttpError as error:
            logger.error(f'Gmail APIエラー: {error}')
            return []
    
    async def get_email_content_async(self, message_id: str) -> str:
        """メールの本文を取得"""
        try:
            # Gmail APIの呼び出しを非同期で実行
            loop = asyncio.get_event_loop()
            message = await loop.run_in_executor(
                None,
                lambda: self.gmail_service.users().messages().get(
                    userId='me',
                    id=message_id
                ).execute()
            )
            
            payload = message['payload']
            body = self._extract_body_from_payload(payload)
            
            return body
        
        except HttpError as error:
            logger.error(f'メール取得エラー: {error}')
            return ""
    
    def _extract_body_from_payload(self, payload: Dict) -> str:
        """ペイロードからメール本文を抽出"""
        body = ""
        
        if 'parts' in payload:
            for part in payload['parts']:
                if part['mimeType'] == 'text/html':
                    data = part['body']['data']
                    body = base64.urlsafe_b64decode(data).decode('utf-8')
                    break
                elif 'parts' in part:
                    body = self._extract_body_from_payload(part)
                    if body:
                        break
        elif payload['body'].get('data'):
            body = base64.urlsafe_b64decode(payload['body']['data']).decode('utf-8')
        
        return body
    
    def parse_articles_from_email(self, html_content: str) -> List[Article]:
        """メールHTMLから記事情報を抽出"""
        soup = BeautifulSoup(html_content, 'html.parser')
        articles = []
      
        # Medium Daily Digestの記事リンクパターンを探す（class="ag"のaタグのみ）
        article_links = soup.find_all('a', class_='ag', href=re.compile(r'https://medium\.com/.*\?source=email'))
        
        seen_urls = set()
        
        for link in article_links:
            url = link.get('href', '')
            if not url or url in seen_urls:
                continue
            
            # URLクリーンアップ（トラッキングパラメータを完全に除去）
            clean_url = self._clean_url(url)
            if clean_url in seen_urls:
                logger.debug(f"重複URLをスキップ: {clean_url}")
                continue
            seen_urls.add(clean_url)
            
            # タイトルと著者の抽出
            title = link.get_text(strip=True)
            if not title or len(title) < 10:
                logger.debug(f"短いタイトルをスキップ: {title}")
                continue
            
            # 著者情報の抽出（リンクの近くにある場合が多い）
            author = "Unknown"
            parent = link.parent
            if parent:
                author_text = parent.get_text()
                author_match = re.search(r'by\s+([^•\n]+)', author_text)
                if author_match:
                    author = author_match.group(1).strip()
            
            article = Article(
                title=title,
                url=clean_url,
                author=author,
                date_processed=datetime.now().isoformat()
            )
            articles.append(article)
            logger.debug(f"記事を検出: {title[:50]}... by {author}")
        
        logger.info(f"合計{len(articles)}件の記事を抽出しました")
        return articles
    
    def _clean_url(self, url: str) -> str:
        """URLをクリーンアップ（トラッキングパラメータ除去）"""
        # URLからクエリパラメータを除去
        clean_url = url.split('?')[0]
        # 末尾のスラッシュを除去
        clean_url = clean_url.rstrip('/')
        # Mediumの特殊なパラメータを除去
        if '#' in clean_url:
            clean_url = clean_url.split('#')[0]
        return clean_url
    
    async def fetch_article_content_async(self, url: str, retry_count: int = 3) -> tuple[str, Optional[str]]:
        """記事のコンテンツを非同期で取得（リトライ機能付き）"""
        for attempt in range(retry_count):
            try:
                async with self.http_session.get(url) as response:
                    response.raise_for_status()
                    content = await response.text()
                    
                    soup = BeautifulSoup(content, 'html.parser')
                    
                    # より正確な著者名を取得
                    author_tag = soup.find('a', attrs={'data-testid': 'authorName'})
                    author = author_tag.get_text(strip=True) if author_tag else None
                    
                    # 記事本文の抽出
                    article_body = soup.find('article')
                    if not article_body:
                        article_body = soup.find('div', class_='postArticle-content')
                    
                    text_content = article_body.get_text(separator=' ', strip=True)[:3000] if article_body else soup.get_text(separator=' ', strip=True)[:3000]
                    
                    return text_content, author
                    
            except aiohttp.ClientError as e:
                if attempt < retry_count - 1:
                    wait_time = (attempt + 1) * 2  # 指数バックオフ
                    logger.warning(f"記事取得エラー ({url}): {e}. {wait_time}秒後にリトライ...")
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"記事取得エラー ({url}): {e}. リトライ回数を超えました")
                    return "", None
            except Exception as e:
                logger.error(f"予期しないエラー ({url}): {e}")
                return "", None
    
    async def generate_japanese_translation_and_summary_async(self, article: Article):
        """記事の日本語タイトル翻訳と要約を非同期で生成"""
        try:
            logger.debug(f"記事処理開始: {article.title[:50]}... ({article.url})")
            
            # 記事のコンテンツを非同期で取得
            text_content, author = await self.fetch_article_content_async(article.url)
            
            if author:
                article.author = author
            
            if not text_content:
                logger.warning(f"記事コンテンツ取得失敗: {article.title[:50]}...")
                article.japanese_title = "取得失敗"
                article.japanese_summary = "記事の取得に失敗しました"
                return
            
            # Ollama APIでタイトル翻訳と要約生成（セマフォで制限）
            async with self.ollama_semaphore:
                prompt = f"""You are a professional translator and summarizer. Respond in JSON format.

Translate the following article title to Japanese and summarize the article text in Japanese (around 200 characters).

Original Title: {article.title}
Author: {article.author}

Article Text:
{text_content}

---

Respond with a JSON object with two keys: 'japanese_title' and 'japanese_summary'.
Example:
{{
  "japanese_title": "ここに日本語のタイトル",
  "japanese_summary": "ここに日本語の要約"
}}
"""
                
                # Ollamaは同期APIなので、executor で実行
                loop = asyncio.get_event_loop()
                response = await loop.run_in_executor(
                    None,
                    lambda: self.ollama_client.chat(
                        model="gemma3:27b",
                        messages=[{"role": "user", "content": prompt}],
                        format="json"
                    )
                )
                
                # JSONレスポンスをパース
                result = json.loads(response.message.content)
                article.japanese_title = result.get('japanese_title', "翻訳失敗")
                article.japanese_summary = result.get('japanese_summary', "要約失敗")
                logger.debug(f"翻訳・要約完了: {article.japanese_title[:30]}...")

        except json.JSONDecodeError as e:
            logger.error(f"JSON解析エラー ({article.title[:50]}...): {e}")
            article.japanese_title = "翻訳失敗（JSON解析エラー）"
            article.japanese_summary = "要約の生成に失敗しました"
        except Exception as e:
            logger.error(f"翻訳・要約生成エラー ({article.title[:50]}...): {e}")
            article.japanese_title = "翻訳失敗"
            article.japanese_summary = "要約の生成に失敗しました"
    
    def format_slack_message(self, articles: List[Article], date: str) -> str:
        """記事データをSlack投稿用にフォーマット"""
        if not articles:
            return f"*{date}のMedium Daily Digest*\n本日は対象記事がありませんでした。"
        
        message = f"*{date}のMedium Daily Digest ({len(articles)}件)*\n\n"
        
        for i, article in enumerate(articles, 1):
            message += f"{i}. *{article.japanese_title or article.title}*\n"
            message += f"   👤 {article.author}\n"
            message += f"   📄 {article.japanese_summary}\n"
            message += f"   🔗 <{article.url}|記事を読む>\n\n"
        
        return message
    
    async def send_to_slack_async(self, message: str) -> bool:
        """Slackに非同期で投稿"""
        if not SLACK_WEBHOOK_URL:
            logger.error("SLACK_WEBHOOK_URL環境変数が設定されていません")
            return False
        
        payload = {"text": message}
        
        try:
            async with self.http_session.post(SLACK_WEBHOOK_URL, json=payload) as response:
                if response.status == 200:
                    logger.info("Slackへの送信が完了しました")
                    return True
                else:
                    logger.error(f"Slackへの送信に失敗しました。ステータスコード: {response.status}")
                    return False
        except Exception as e:
            logger.error(f"Slackへの送信エラー: {e}")
            return False
    
    async def save_to_notion_async(self, article: Article, target_date: datetime, retry_count: int = 3) -> str:
        """記事情報をNotionデータベースに非同期で保存（リトライ機能付き）
        
        Returns:
            'success': 成功
            'skipped': 既存のためスキップ
            'failed': 失敗
        """
        database_id = os.getenv('NOTION_DB_ID_DAILY_DIGEST')
        if not database_id:
            raise ValueError("NOTION_DATABASE_ID環境変数が設定されていません")
        
        async with self.notion_semaphore:
            for attempt in range(retry_count):
                try:
                    # Notion APIは同期APIなので、executor で実行
                    loop = asyncio.get_event_loop()
                    
                    # 既存のエントリをチェック
                    existing = await loop.run_in_executor(
                        None,
                        lambda: self.notion_client.databases.query(
                            database_id=database_id,
                            filter={
                                "property": "URL",
                                "url": {
                                    "equals": article.url
                                }
                            }
                        )
                    )

                    if existing['results']:
                        # 既存エントリの詳細情報を取得してログ出力
                        existing_entry = existing['results'][0]
                        existing_date = existing_entry.get('properties', {}).get('Date', {}).get('date', {}).get('start', 'Unknown')
                        logger.info(f"  -> 既に存在するためスキップ: {article.title[:50]}... (既存日付: {existing_date})")
                        return 'skipped'

                    # 新規ページ作成
                    logger.info(f"  -> Notionに保存中: {article.title[:50]}...")
                    await loop.run_in_executor(
                        None,
                        lambda: self.notion_client.pages.create(
                            parent={"database_id": database_id},
                            properties={
                                "Title": {
                                    "title": [
                                        {
                                            "text": {
                                                "content": article.title
                                            }
                                        }
                                    ]
                                },
                                "Japanese Title": { 
                                    "rich_text": [
                                        {
                                            "text": {
                                                "content": article.japanese_title
                                            }
                                        }
                                    ]
                                },
                                           
                                "URL": {
                                    "url": article.url
                                },
                                "Author": {
                                    "rich_text": [
                                        {
                                            "text": {
                                                "content": article.author
                                            }
                                        }
                                    ]
                                },
                                "Summary": {
                                    "rich_text": [
                                        {
                                            "text": {
                                                "content": article.japanese_summary
                                            }
                                        }
                                    ]
                                },                             
                                "Date": {
                                    "date": {
                                        "start": target_date.strftime("%Y-%m-%d")
                                    }
                                }
                            }
                        )
                    )

                    logger.info(f"  -> 保存完了: {article.title[:50]}... by {article.author}")
                    return 'success'  # 成功したら終了

                except Exception as e:
                    if attempt < retry_count - 1:
                        wait_time = (attempt + 1) * 2  # 指数バックオフ
                        logger.warning(f"  -> Notion保存エラー (試行 {attempt + 1}/{retry_count}): {article.title[:50]}...")
                        logger.warning(f"     エラー詳細: {e}")
                        logger.warning(f"     {wait_time}秒後にリトライします...")
                        await asyncio.sleep(wait_time)
                    else:
                        logger.error(f"  -> Notion保存失敗 (全{retry_count}回試行): {article.title[:50]}...")
                        logger.error(f"     最終エラー: {e}")
                        return 'failed'
    
    async def process_article_async(self, article: Article, target_date: datetime, save_notion: bool) -> tuple[Article, str]:
        """単一の記事を非同期で処理
        
        Returns:
            (Article, status): 記事とNotionへの保存ステータス('success'/'skipped'/'failed'/None)
        """
        # 翻訳と要約を生成
        await self.generate_japanese_translation_and_summary_async(article)
        
        # Notionに保存（有効な場合）
        status = None
        if save_notion:
            status = await self.save_to_notion_async(article, target_date)
        
        return article, status
    
    async def process_daily_digest_async(self, target_date: datetime, save_notion: bool = True, send_slack: bool = True):
        """デイリーダイジェストの処理メイン関数"""
        date_str = target_date.strftime('%Y-%m-%d')
        logger.info(f"Medium Daily Digest ({date_str}) の処理を開始します...")

        # Slack送信が有効な場合、環境変数をチェック
        if send_slack and not SLACK_WEBHOOK_URL:
            raise ValueError("SLACK_WEBHOOK_URL_MEDIUM_DAILY_DIGEST環境変数が設定されていません。Slack送信を行う場合は設定してください。")

        # 指定された日付のメールを取得
        messages = await self.get_medium_digest_emails_async(target_date)

        if not messages:
            logger.warning(f"{date_str} のDaily Digestメールが見つかりません")
            return

        # メール本文を取得
        message_id = messages[0]['id']
        email_content = await self.get_email_content_async(message_id)

        if not email_content:
            logger.error("メール本文の取得に失敗しました")
            return

        # 記事情報を抽出
        articles = self.parse_articles_from_email(email_content)
        logger.info(f"{len(articles)}件の記事を検出しました")

        if not articles:
            return

        # 記事を並列処理で処理
        logger.info(f"記事の翻訳と要約を開始します...")
        logger.info(f"最大{MAX_CONCURRENT_ARTICLES}件の記事を並列処理します")
        
        # 統計の初期化
        stats = {"success": 0, "skipped": 0, "failed": 0}
        
        # 記事をバッチに分割して処理
        processed_articles = []
        total_batches = (len(articles) + MAX_CONCURRENT_ARTICLES - 1) // MAX_CONCURRENT_ARTICLES
        
        for i in range(0, len(articles), MAX_CONCURRENT_ARTICLES):
            batch = articles[i:i + MAX_CONCURRENT_ARTICLES]
            batch_num = i // MAX_CONCURRENT_ARTICLES + 1
            logger.info(f"バッチ {batch_num}/{total_batches} を処理中 ({len(batch)}件)...")
            
            # バッチ内の記事を並列処理
            tasks = [
                self.process_article_async(article, target_date, save_notion)
                for article in batch
            ]
            
            # タスクを追跡
            for task in tasks:
                _running_tasks.add(task)
            
            try:
                batch_results = await asyncio.gather(*tasks, return_exceptions=True)
            finally:
                # 完了したタスクを削除
                for task in tasks:
                    _running_tasks.discard(task)
            
            # エラーをチェックして成功した記事のみを追加
            for idx, result in enumerate(batch_results):
                if isinstance(result, Exception):
                    logger.error(f"記事処理エラー: {batch[idx].title} - {result}")
                    if save_notion:
                        stats["failed"] += 1
                else:
                    article, status = result
                    processed_articles.append(article)
                    # 統計を更新
                    if status == 'success':
                        stats["success"] += 1
                    elif status == 'skipped':
                        stats["skipped"] += 1
                    elif status == 'failed':
                        stats["failed"] += 1

        # 処理結果の詳細をログ出力
        if save_notion:
            logger.info("=" * 60)
            logger.info(f"Notionへの保存結果:")
            logger.info(f"  成功: {stats['success']}件")
            logger.info(f"  スキップ (既存): {stats['skipped']}件")
            logger.info(f"  失敗: {stats['failed']}件")
            logger.info("=" * 60)
        
        # Slackに送信
        if send_slack and processed_articles:
            slack_message = self.format_slack_message(processed_articles, date_str)
            await self.send_to_slack_async(slack_message)

        logger.info(f"処理が完了しました")
        logger.info(f"  処理記事数: {len(processed_articles)}/{len(articles)}件")
        logger.info(f"  対象日付: {date_str}")


# グローバル変数でタスクを管理
_running_tasks = set()

def signal_handler(signum, frame):
    """シグナルハンドラー（Ctrl+C対応）"""
    logger.info("\n処理を中断しています...")
    # 実行中のタスクをキャンセル
    for task in _running_tasks:
        task.cancel()
    # イベントループを停止
    loop = asyncio.get_event_loop()
    loop.stop()

async def main_async():
    """メイン実行関数"""
    parser = argparse.ArgumentParser(description='Medium Daily Digestメールを取得してNotionに保存およびSlackに送信')
    parser.add_argument(
        '--date',
        type=str,
        help='取得する日付 (YYYY-MM-DD形式)。指定しない場合は今日の日付を使用',
        default=None
    )
    
    # 相互排他的なグループを作成
    exclusive_group = parser.add_mutually_exclusive_group()
    exclusive_group.add_argument(
        '--slack',
        action='store_true',
        help='Slackへの送信のみ実行（Notion保存をスキップ）',
        default=False
    )
    exclusive_group.add_argument(
        '--notion',
        action='store_true',
        help='Notionへの保存のみ実行（Slack送信をスキップ）',
        default=False
    )
    
    args = parser.parse_args()
    
    # 日付のパースと検証
    if args.date:
        try:
            target_date = datetime.strptime(args.date, '%Y-%m-%d')
        except ValueError:
            logger.error(f"エラー: 日付は YYYY-MM-DD 形式で指定してください (例: 2024-01-15)")
            return
    else:
        target_date = datetime.now()
    
    # フラグに基づいて動作を決定
    if args.slack:
        # --slackフラグがある場合：Slack送信のみ
        save_notion = False
        send_slack = True
    elif args.notion:
        # --notionフラグがある場合：Notion保存のみ
        save_notion = True
        send_slack = False
    else:
        # フラグなし（デフォルト）：両方実行
        save_notion = True
        send_slack = True
    
    try:
        async with MediumDigestProcessorAsync() as processor:
            await processor.process_daily_digest_async(target_date, save_notion=save_notion, send_slack=send_slack)
    except asyncio.CancelledError:
        logger.info("処理がキャンセルされました")
        raise
    except socket.gaierror as e:
        logger.error(f"ネットワーク接続エラー: {e}")
        logger.error("ネットワーク接続を確認して、再度実行してください。")
        logger.error("DNS設定に問題がある可能性があります。")
        raise
    except Exception as e:
        logger.error(f"エラーが発生しました: {e}")
        logger.error(f"エラーの詳細: {type(e).__name__}")
        import traceback
        logger.error(f"スタックトレース: {traceback.format_exc()}")
        raise


def main():
    """同期的なエントリーポイント"""
    # シグナルハンドラーを設定
    signal.signal(signal.SIGINT, signal_handler)
    
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        logger.info("\n処理が中断されました")
    except Exception as e:
        logger.error(f"予期しないエラー: {e}")
        raise


if __name__ == "__main__":
    main()