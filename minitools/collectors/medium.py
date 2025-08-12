"""
Medium Daily Digest collector module.
"""

import os
import pickle
import base64
import re
import asyncio
import aiohttp
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from dataclasses import dataclass
import pytz
from bs4 import BeautifulSoup

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from minitools.utils.logger import get_logger

logger = get_logger(__name__)

# Gmail API スコープ
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']


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


class MediumCollector:
    """Medium Daily Digestメールを収集するクラス"""
    
    def __init__(self, credentials_path: str = None):
        self.gmail_service = None
        self.http_session = None
        self.credentials_path = credentials_path or os.getenv('GMAIL_CREDENTIALS_PATH', 'credentials.json')
        self._authenticate_gmail()
    
    async def __aenter__(self):
        """非同期コンテキストマネージャーのエントリー"""
        connector = aiohttp.TCPConnector(limit=10)
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
                    if not os.path.exists(self.credentials_path):
                        raise FileNotFoundError(f"認証ファイル {self.credentials_path} が見つかりません")
                    
                    flow = InstalledAppFlow.from_client_secrets_file(self.credentials_path, SCOPES)
                    creds = flow.run_local_server(port=0)
                
                with open(token_path, 'wb') as token:
                    pickle.dump(creds, token)
            
            self.gmail_service = build('gmail', 'v1', credentials=creds)
            logger.info("Gmail API authenticated successfully")
            
        except Exception as e:
            logger.error(f"Gmail認証エラー: {e}")
            raise
    
    async def get_digest_emails(self, date: Optional[datetime] = None) -> List[Dict]:
        """
        Medium Daily Digestメールを取得
        
        Args:
            date: 取得する日付（指定しない場合は今日）
            
        Returns:
            メールメッセージのリスト
        """
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
        
        # Unix タイムスタンプに変換
        start_timestamp = int(start_date_jst.timestamp())
        end_timestamp = int(end_date_jst.timestamp())
        
        # 検索クエリ
        query = f'from:noreply@medium.com after:{start_timestamp} before:{end_timestamp}'
        logger.info(f"Searching Gmail with query: {query}")
        
        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self.gmail_service.users().threads().list(
                    userId='me',
                    q=query,
                    maxResults=1
                ).execute()
            )
            
            threads = response.get('threads', [])
            if not threads:
                logger.info("No Medium Daily Digest emails found")
                return []
            
            thread_id = threads[0]['id']
            thread = await loop.run_in_executor(
                None,
                lambda: self.gmail_service.users().threads().get(
                    userId='me',
                    id=thread_id
                ).execute()
            )
            
            messages = thread.get('messages', [])
            if messages:
                logger.info(f"Found {len(messages)} messages in thread")
                return [messages[-1]]  # 最新のメッセージのみを返す
            
            return []
            
        except HttpError as error:
            logger.error(f'Gmail APIエラー: {error}')
            return []
    
    def parse_articles(self, html_content: str) -> List[Article]:
        """
        メールHTMLから記事情報を抽出
        
        Args:
            html_content: メールのHTML内容
            
        Returns:
            記事情報のリスト
        """
        soup = BeautifulSoup(html_content, 'html.parser')
        articles = []
        
        # Medium Daily Digestの記事リンクパターンを探す
        article_links = soup.find_all('a', class_='ag', href=re.compile(r'https://medium\.com/.*\?source=email'))
        
        seen_urls = set()
        
        for link in article_links:
            url = link.get('href', '')
            if not url or url in seen_urls:
                continue
            
            # URLクリーンアップ
            clean_url = url.split('?')[0]
            seen_urls.add(clean_url)
            
            # タイトルと著者の抽出
            title = link.get_text(strip=True)
            if not title or len(title) < 10:
                continue
            
            # 著者情報の抽出
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
        
        logger.info(f"Parsed {len(articles)} articles from email")
        return articles
    
    async def fetch_article_content(self, url: str) -> tuple[str, Optional[str]]:
        """
        記事のコンテンツを非同期で取得
        
        Args:
            url: 記事のURL
            
        Returns:
            (記事内容, 著者名) のタプル
        """
        if not self.http_session:
            logger.error("HTTP session not initialized. Use async context manager.")
            return "", None
            
        try:
            async with self.http_session.get(url) as response:
                response.raise_for_status()
                content = await response.text()
                
                soup = BeautifulSoup(content, 'html.parser')
                
                # 著者名を取得
                author_tag = soup.find('a', attrs={'data-testid': 'authorName'})
                author = author_tag.get_text(strip=True) if author_tag else None
                
                # 記事本文の抽出
                article_body = soup.find('article')
                if not article_body:
                    article_body = soup.find('div', class_='postArticle-content')
                
                text_content = article_body.get_text(separator=' ', strip=True)[:3000] if article_body else ""
                
                return text_content, author
                
        except Exception as e:
            logger.error(f"Error fetching article from {url}: {e}")
            return "", None
    
    def extract_email_body(self, message: Dict) -> str:
        """
        メールメッセージから本文を抽出
        
        Args:
            message: Gmail APIのメッセージオブジェクト
            
        Returns:
            メール本文のHTML
        """
        payload = message.get('payload', {})
        body = self._extract_body_from_payload(payload)
        return body
    
    def _extract_body_from_payload(self, payload: Dict) -> str:
        """ペイロードからメール本文を抽出（内部メソッド）"""
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
        elif payload.get('body', {}).get('data'):
            body = base64.urlsafe_b64decode(payload['body']['data']).decode('utf-8')
        
        return body