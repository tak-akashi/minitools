#!/usr/bin/env python3
"""
Medium Daily Digest to Notion
Gmail経由でMedium Daily Digestメールを取得し、記事情報を抽出して日本語要約と共にNotionに保存
"""

import os
import pickle
import base64
import re
import argparse
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

import requests
from bs4 import BeautifulSoup
from notion_client import Client
import ollama
from dotenv import load_dotenv

load_dotenv()

# スコープ設定
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


class MediumDigestProcessor:
    """Medium Daily Digestメールを処理してNotionに保存するクラス"""
    
    def __init__(self):
        self.gmail_service = None
        self.notion_client = None
        self.ollama_client = None
        self.setup_clients()
    
    def setup_clients(self):
        """各種APIクライアントの初期化"""
        # Gmail API
        self.gmail_service = self._authenticate_gmail()
        
        # Notion API
        notion_token = os.getenv('NOTION_API_KEY')
        if not notion_token:
            raise ValueError("NOTION_API_KEY(環境変数)が設定されていません")
        self.notion_client = Client(auth=notion_token)
        
        # Ollama Client
        self.ollama_client = ollama.Client()
    
    def _authenticate_gmail(self):
        """Gmail APIの認証"""
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
    
    def get_medium_digest_emails(self, date: Optional[datetime] = None) -> List[Dict]:
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
        print(f"検索期間 (JST): {start_date_jst} から {end_date_jst}")
        print(f"タイムスタンプ: {start_timestamp} から {end_timestamp}")
        
        # 差出人とタイムスタンプ範囲で検索
        query = f'from:noreply@medium.com after:{start_timestamp} before:{end_timestamp}'
        print(f"Gmail検索クエリ: {query}")
        
        try:
            response = self.gmail_service.users().threads().list(
                userId='me',
                q=query,
                maxResults=1
            ).execute()

            threads = response.get('threads', [])
            if not threads:
                return []

            thread_id = threads[0]['id']
            thread = self.gmail_service.users().threads().get(
                userId='me',
                id=thread_id
            ).execute()
            
            # スレッド内の最新メッセージを返す
            messages = thread.get('messages', [])
            if messages:
                # メッセージの受信時刻も確認（デバッグ用）
                msg = messages[-1]
                if 'internalDate' in msg:
                    received_timestamp = int(msg['internalDate']) / 1000
                    received_date = datetime.fromtimestamp(received_timestamp, tz=jst)
                    print(f"メール受信日時 (JST): {received_date}")
                
                return [messages[-1]] # 最新のメッセージのみをリストで返す
            return []

        except HttpError as error:
            print(f'Gmail APIエラー: {error}')
            return []
    
    def get_email_content(self, message_id: str) -> str:
        """メールの本文を取得"""
        try:
            message = self.gmail_service.users().messages().get(
                userId='me',
                id=message_id
            ).execute()
            
            payload = message['payload']
            body = self._extract_body_from_payload(payload)
            
            return body
        
        except HttpError as error:
            print(f'メール取得エラー: {error}')
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
            
            # URLクリーンアップ
            clean_url = url.split('?')[0]
            seen_urls.add(clean_url)
            
            # タイトルと著者の抽出
            title = link.get_text(strip=True)
            if not title or len(title) < 10:
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
        
        return articles
    
    def generate_japanese_translation_and_summary(self, article: Article):
        """記事の日本語タイトル翻訳と要約を生成"""
        try:
            # 記事のコンテンツを取得
            response = requests.get(article.url, timeout=30)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, 'html.parser')

            # 記事ページからより正確な著者名を取得
            author_tag = soup.find('a', attrs={'data-testid': 'authorName'})
            if author_tag:
                article.author = author_tag.get_text(strip=True)

            # 記事本文の抽出
            article_body = soup.find('article')
            if not article_body:
                article_body = soup.find('div', class_='postArticle-content')
            text_content = article_body.get_text(separator=' ', strip=True)[:3000] if article_body else soup.get_text(separator=' ', strip=True)[:3000]

            # Ollama APIでタイトル翻訳と要約生成
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

            response = self.ollama_client.generate(
                model="gemma3:27b",
                prompt=prompt,
                format="json"  # JSONモードを有効化
            )

            # JSONレスポンスをパース
            result = json.loads(response['response'])
            article.japanese_title = result.get('japanese_title', "翻訳失敗")
            article.japanese_summary = result.get('japanese_summary', "要約失敗")

        except Exception as e:
            print(f"翻訳・要約生成エラー ({article.title}): {e}")
            article.japanese_title = "翻訳失敗"
            article.japanese_summary = "要約の生成に失敗しました"

    def save_to_notion(self, article: Article, target_date: datetime):
        """記事情報をNotionデータベースに1件ずつ保存"""
        database_id = os.getenv('NOTION_DB_ID_DAILY_DIGEST')
        if not database_id:
            raise ValueError("NOTION_DATABASE_ID環境変数が設定されていません")
        try:
            # 既存のエントリをチェック
            existing = self.notion_client.databases.query(
                database_id=database_id,
                filter={
                    "property": "URL",
                    "url": {
                        "equals": article.url
                    }
                }
            )

            if existing['results']:
                print(f"  -> 既に存在するためスキップ: {article.title}")
                return

            # 新規ページ作成 (タイトルに日本語タイトルを使用)
            self.notion_client.pages.create(
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

            print(f"  -> 保存完了: {article.title}")

        except Exception as e:
            print(f"  -> Notion保存エラー ({article.title}): {e}")

    def process_daily_digest(self, target_date: datetime):
        """デイリーダイジェストの処理メイン関数"""
        date_str = target_date.strftime('%Y-%m-%d')
        print(f"Medium Daily Digest ({date_str}) の処理を開始します...")

        # 指定された日付のメールを取得
        messages = self.get_medium_digest_emails(target_date)

        if not messages:
            print(f"{date_str} のDaily Digestメールが見つかりません")
            return

        # メール本文を取得
        message_id = messages[0]['id']
        email_content = self.get_email_content(message_id)

        if not email_content:
            print("メール本文の取得に失敗しました")
            return

        # 記事情報を抽出
        articles = self.parse_articles_from_email(email_content)
        print(f"{len(articles)}件の記事を検出しました")

        # 各記事の日本語要約を生成し、都度Notionに保存
        for i, article in enumerate(articles):
            print(f"処理中 ({i + 1}/{len(articles)}): {article.title}")
            self.generate_japanese_translation_and_summary(article)

            # 翻訳・要約生成が成功した場合のみNotionに保存
            if "失敗" not in article.japanese_summary and "失敗" not in article.japanese_title:
                self.save_to_notion(article, target_date)
            else:
                print(f"  -> 翻訳・要約生成に失敗したため、Notionへの保存をスキップします。")

        print("処理が完了しました")


def main():
    """メイン実行関数"""
    parser = argparse.ArgumentParser(description='Medium Daily Digestメールを取得してNotionに保存')
    parser.add_argument(
        '--date',
        type=str,
        help='取得する日付 (YYYY-MM-DD形式)。指定しない場合は今日の日付を使用',
        default=None
    )
    
    args = parser.parse_args()
    
    # 日付のパースと検証
    if args.date:
        try:
            target_date = datetime.strptime(args.date, '%Y-%m-%d')
        except ValueError:
            print(f"エラー: 日付は YYYY-MM-DD 形式で指定してください (例: 2024-01-15)")
            return
    else:
        target_date = datetime.now()
    
    try:
        processor = MediumDigestProcessor()
        processor.process_daily_digest(target_date)
    except Exception as e:
        print(f"エラーが発生しました: {e}")
        raise


if __name__ == "__main__":
    main()