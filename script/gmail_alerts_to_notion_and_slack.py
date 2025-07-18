#!/usr/bin/env python3
"""
Google Alerts to Notion and Slack
Gmail経由でGoogle Alertsメールを取得し、各アラートの内容を日本語要約と共にNotionに保存してSlackに送信

デフォルトでは過去6時間のメールを取得（定期実行想定）
--dateで日付を指定した場合は、その日の全メールを取得
"""

import os
import pickle
import base64
import re
import argparse
import logging
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional
import json
from dataclasses import dataclass
from urllib.parse import urlparse, urljoin
import pytz
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

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

# Slack設定
SLACK_WEBHOOK_URL = os.getenv('SLACK_WEBHOOK_URL_GOOGLE_ALERTS')

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
    file_handler = logging.FileHandler(log_dir / "google_alerts.log", mode="a")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    
    return logger

logger = setup_logger()

@dataclass
class Alert:
    """アラート情報を格納するデータクラス"""
    title: str
    url: str
    source: str
    snippet: str = ""
    japanese_title: str = ""
    japanese_summary: str = ""
    date_processed: str = ""


class GoogleAlertsProcessor:
    """Google Alertsメールを処理してNotionに保存してSlackに送信するクラス"""
    
    def __init__(self):
        self.gmail_service = None
        self.notion_client = None
        self.ollama_client = None
        self.log_lock = threading.Lock()  # ログ出力の同期用
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
    
    def safe_print(self, message: str):
        """スレッドセーフなログ出力"""
        with self.log_lock:
            logger.info(message)
    
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
    
    def get_google_alerts_emails(self, date: Optional[datetime] = None, date_specified: bool = False, hours: int = 6) -> List[Dict]:
        """Google Alertsメールを取得
        
        Args:
            date: 検索対象の日付。Noneの場合は現在時刻を使用
            date_specified: 日付が明示的に指定されたかどうか
                - True: 指定された日付の全日 (0:00-23:59)
                - False: 過去hours時間のデータ
            hours: 過去何時間のメールを取得するか（date_specified=Falseの場合のみ使用）
        """
        if date is None:
            date = datetime.now()
        
        # JSTタイムゾーンを設定
        jst = pytz.timezone('Asia/Tokyo')
        
        # dateがnaiveの場合はJSTとして扱う
        if date.tzinfo is None:
            date = jst.localize(date)
        
        if date_specified:
            # 日付が指定されている場合：その日の全日を対象
            start_date_jst = date.replace(hour=0, minute=0, second=0, microsecond=0)
            end_date_jst = start_date_jst + timedelta(days=1)
            logger.info(f"検索期間 (JST): {start_date_jst} から {end_date_jst} (指定日全日)")
        else:
            # 日付が指定されていない場合：過去hours時間を対象
            end_date_jst = date
            start_date_jst = date - timedelta(hours=hours)
            logger.info(f"検索期間 (JST): {start_date_jst} から {end_date_jst} (過去{hours}時間)")
        
        # Unix タイムスタンプに変換
        start_timestamp = int(start_date_jst.timestamp())
        end_timestamp = int(end_date_jst.timestamp())
        
        # デバッグ情報を出力
        logger.info(f"タイムスタンプ: {start_timestamp} から {end_timestamp}")
        
        # Google Alertsの差出人とタイムスタンプ範囲で検索
        query = f'from:googlealerts-noreply@google.com after:{start_timestamp} before:{end_timestamp}'
        logger.info(f"Gmail検索クエリ: {query}")
        
        try:
            response = self.gmail_service.users().messages().list(
                userId='me',
                q=query,
                maxResults=50  # Google Alertsは複数メールになる可能性があるので多めに設定
            ).execute()

            messages = response.get('messages', [])
            logger.info(f"Gmail検索結果: {len(messages)}件のメッセージが見つかりました")
            
            if not messages:
                # より広い範囲で検索してみる
                logger.info("範囲を拡大してGoogle Alertsメールを検索中...")
                broader_query = 'from:googlealerts-noreply@google.com'
                logger.info(f"拡大検索クエリ: {broader_query}")
                
                broader_response = self.gmail_service.users().messages().list(
                    userId='me',
                    q=broader_query,
                    maxResults=10
                ).execute()
                
                broader_messages = broader_response.get('messages', [])
                logger.info(f"拡大検索結果: {len(broader_messages)}件のメッセージが見つかりました")
                
                if broader_messages:
                    logger.info("最新のGoogle Alertsメールを確認中...")
                    for msg in broader_messages[:3]:  # 最新3件を確認
                        message = self.gmail_service.users().messages().get(
                            userId='me',
                            id=msg['id']
                        ).execute()
                        
                        # メール日時を取得
                        if 'internalDate' in message:
                            msg_timestamp = int(message['internalDate']) / 1000
                            msg_date = datetime.fromtimestamp(msg_timestamp, tz=pytz.timezone('Asia/Tokyo'))
                            logger.info(f"  メールID: {msg['id']}, 日時: {msg_date}")
                        
                        # 件名を取得
                        headers = message['payload'].get('headers', [])
                        subject = next((h['value'] for h in headers if h['name'] == 'Subject'), 'No Subject')
                        logger.info(f"  件名: {subject}")
                
                return []

            # メッセージIDのリストを返す
            return messages

        except HttpError as error:
            logger.error(f'Gmail APIエラー: {error}')
            return []
    
    def get_email_content_and_date(self, message_id: str) -> tuple[str, Optional[datetime]]:
        """メールの本文と配信日時を取得"""
        try:
            message = self.gmail_service.users().messages().get(
                userId='me',
                id=message_id
            ).execute()
            
            payload = message['payload']
            body = self._extract_body_from_payload(payload)
            
            # メール配信日時を取得
            email_date = None
            if 'internalDate' in message:
                email_timestamp = int(message['internalDate']) / 1000
                email_date = datetime.fromtimestamp(email_timestamp, tz=pytz.timezone('Asia/Tokyo'))
                logger.info(f"  -> メール配信日時を取得: {email_date} (タイムスタンプ: {message['internalDate']})")
            else:
                logger.warning(f"  -> 警告: メールにinternalDateが見つかりません (メッセージID: {message_id})")
            
            return body, email_date
        
        except HttpError as error:
            logger.error(f'メール取得エラー: {error}')
            return "", None
        except Exception as error:
            logger.error(f'メール処理エラー (メッセージID: {message_id}): {error}')
            return "", None
    
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
    
    def process_single_message(self, message: Dict, jst: pytz.timezone) -> List[Alert]:
        """単一のメッセージを処理してアラートを抽出"""
        message_id = message['id']
        self.safe_print(f"メール処理中: {message_id}")
        
        try:
            email_content, email_date = self.get_email_content_and_date(message_id)
            
            if not email_content:
                self.safe_print(f"メール本文の取得に失敗しました: {message_id}")
                return []
            
            if email_date:
                self.safe_print(f"メール配信日時: {email_date}")
            
            # アラート情報を抽出
            alerts = self.parse_alerts_from_email(email_content)
            self.safe_print(f"抽出されたアラート数: {len(alerts)}")
            
            # 各アラートにメール配信日時を設定
            for alert in alerts:
                if email_date:
                    alert.date_processed = email_date.strftime('%Y-%m-%d')
                    self.safe_print(f"  -> メール配信日時を設定: {email_date} -> {alert.date_processed}")
                else:
                    current_time = datetime.now(jst)
                    alert.date_processed = current_time.strftime('%Y-%m-%d')
                    self.safe_print(f"  -> 警告: メール配信日時が取得できないため現在時刻を使用: {current_time} -> {alert.date_processed}")
            
            return alerts
            
        except Exception as e:
            self.safe_print(f"メッセージ処理エラー ({message_id}): {e}")
            return []
    
    def process_messages_parallel(self, messages: List[Dict], max_workers: int = 3) -> List[Alert]:
        """メッセージを並列処理してアラートを抽出"""
        jst = pytz.timezone('Asia/Tokyo')
        all_alerts = []
        
        logger.info(f"メール並列処理開始: {len(messages)}件のメッセージを{max_workers}並列で処理")
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # 各メッセージの処理を並列で実行
            future_to_message = {
                executor.submit(self.process_single_message, message, jst): message 
                for message in messages
            }
            
            # 完了した処理から結果を取得
            for future in as_completed(future_to_message):
                try:
                    alerts = future.result()
                    all_alerts.extend(alerts)
                except Exception as e:
                    message = future_to_message[future]
                    logger.error(f"メッセージ処理で予期しないエラー ({message['id']}): {e}")
        
        return all_alerts
    
    def parse_alerts_from_email(self, html_content: str) -> List[Alert]:
        """Google AlertsメールHTMLからアラート情報を抽出"""
        soup = BeautifulSoup(html_content, 'html.parser')
        alerts = []
        
        # Google Alertsのリンクパターンを探す
        alert_links = soup.find_all('a', href=re.compile(r'https://www\.google\.com/url\?'))
        logger.info(f"Google Alertsリンクを {len(alert_links)}個発見")
        
        if not alert_links:
            logger.warning("Google Alertsリンクが見つかりません")
            return []
        
        seen_urls = set()
        
        for link in alert_links:
            href = link.get('href', '')
            if not href:
                continue
            
            # Google URLから実際のURLを抽出
            try:
                # Google URL形式: https://www.google.com/url?url=ACTUAL_URL&... または ?q=ACTUAL_URL&...
                href_str = str(href)  # 型を明示的にstrに変換
                parsed_url = urlparse(href_str)
                from urllib.parse import parse_qs
                query_params = parse_qs(parsed_url.query)
                
                actual_url = None
                # 複数のパラメータパターンを試す
                for param in ['url', 'q']:
                    if param in query_params:
                        actual_url = query_params[param][0]
                        break
                
                if actual_url:
                    
                    # 重複チェック
                    if actual_url in seen_urls:
                        continue
                    seen_urls.add(actual_url)
                    
                    # タイトルを取得
                    title = link.get_text(strip=True)
                    if not title or len(title) < 5:
                        continue
                    
                    # ソースを抽出（リンクの近くにあるドメイン情報）
                    source = "Unknown"
                    try:
                        source = urlparse(actual_url).netloc
                    except:
                        pass
                    
                    # スニペットを抽出（リンクの後にある説明文）
                    snippet = ""
                    parent = link.parent
                    if parent:
                        # 親要素のテキストからスニペットを抽出
                        parent_text = parent.get_text(strip=True)
                        # タイトルより後の部分をスニペットとして使用
                        if title in parent_text:
                            snippet_parts = parent_text.split(title, 1)
                            if len(snippet_parts) > 1:
                                snippet = snippet_parts[1].strip()[:200]
                    
                    alert = Alert(
                        title=title,
                        url=actual_url,
                        source=source,
                        snippet=snippet,
                        date_processed=""  # メール配信日時は後で設定
                    )
                    alerts.append(alert)
                    
            except Exception as e:
                logger.error(f"URL解析エラー: {e}")
                continue
        
        return alerts
    
    def fetch_article_content(self, alert: Alert) -> str:
        """アラートURLから記事の内容を取得"""
        try:
            # User-Agentを設定してブロックを回避
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            
            response = requests.get(alert.url, headers=headers, timeout=30)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 記事本文を抽出する複数のパターンを試す
            content_selectors = [
                'article',
                '.post-content',
                '.entry-content',
                '.content',
                '.article-body',
                '.story-body',
                '.article-content',
                'main',
                '.main-content',
                '[role="main"]'
            ]
            
            article_text = ""
            for selector in content_selectors:
                content_element = soup.select_one(selector)
                if content_element:
                    # スクリプトとスタイルタグを除去
                    for script in content_element(['script', 'style']):
                        script.decompose()
                    
                    article_text = content_element.get_text(separator=' ', strip=True)
                    break
            
            # 記事が見つからない場合は全体のテキストを取得
            if not article_text:
                # スクリプトとスタイルタグを除去
                for script in soup(['script', 'style']):
                    script.decompose()
                article_text = soup.get_text(separator=' ', strip=True)
            
            # 長すぎる場合は最初の3000文字に制限
            return article_text[:3000] if article_text else ""
            
        except Exception as e:
            logger.error(f"記事取得エラー ({alert.url}): {e}")
            return ""
    
    def fetch_articles_parallel(self, alerts: List[Alert], max_workers: int = 5) -> None:
        """複数のアラートの記事コンテンツを並列で取得"""
        logger.info(f"記事コンテンツ並列取得開始: {len(alerts)}件のアラートを{max_workers}並列で処理")
        
        def fetch_single_article(alert: Alert) -> None:
            """単一の記事コンテンツを取得してアラートに設定"""
            try:
                content = self.fetch_article_content(alert)
                # 記事コンテンツをアラートオブジェクトに保存（新しい属性を追加）
                if not hasattr(alert, 'article_content'):
                    alert.article_content = content
                else:
                    alert.article_content = content
                self.safe_print(f"  -> 記事取得完了: {alert.url[:50]}...")
            except Exception as e:
                self.safe_print(f"  -> 記事取得エラー: {alert.url}: {e}")
                alert.article_content = ""
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # 各アラートの記事取得を並列で実行
            futures = [executor.submit(fetch_single_article, alert) for alert in alerts]
            
            # 全ての処理が完了するまで待機
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    logger.error(f"記事取得で予期しないエラー: {e}")
    
    def generate_japanese_translation_and_summary(self, alert: Alert):
        """アラートの日本語タイトル翻訳と要約を生成"""
        try:
            # 記事のコンテンツを取得（並列処理で既に取得済みの場合はそれを使用）
            if hasattr(alert, 'article_content'):
                article_content = alert.article_content
            else:
                article_content = self.fetch_article_content(alert)
            
            if not article_content:
                # コンテンツが取得できない場合はスニペットを使用
                article_content = alert.snippet
            
            # Ollama APIでタイトル翻訳と要約生成
            prompt = f"""You are a professional translator and summarizer. Respond in JSON format.

Translate the following article title to Japanese and summarize the article content in Japanese (around 200 characters).

Original Title: {alert.title}
Source: {alert.source}
Original snippet: {alert.snippet}

Article Content:
{article_content}

---

Respond with a JSON object with two keys: 'japanese_title' and 'japanese_summary'.
Example:
{{
  "japanese_title": "ここに日本語のタイトル",
  "japanese_summary": "ここに日本語の要約"
}}
"""

            response = self.ollama_client.chat(
                model="gemma3:27b",
                messages=[{"role": "user", "content": prompt}],
                format="json"  # JSONモードを有効化
            )

            # JSONレスポンスをパース
            result = json.loads(response.message.content)
            alert.japanese_title = result.get('japanese_title', "翻訳失敗")
            alert.japanese_summary = result.get('japanese_summary', "要約失敗")

        except Exception as e:
            logger.error(f"翻訳・要約生成エラー ({alert.title}): {e}")
            alert.japanese_title = "翻訳失敗"
            alert.japanese_summary = "要約の生成に失敗しました"
    
    def process_translations_parallel(self, alerts: List[Alert], max_workers: int = 2) -> None:
        """複数のアラートの翻訳・要約を並列で処理"""
        logger.info(f"翻訳・要約並列処理開始: {len(alerts)}件のアラートを{max_workers}並列で処理")
        
        def process_single_translation(alert: Alert) -> None:
            """単一のアラートの翻訳・要約を処理"""
            try:
                self.safe_print(f"  -> 翻訳・要約処理中: {alert.title[:50]}...")
                self.generate_japanese_translation_and_summary(alert)
                self.safe_print(f"  -> 翻訳・要約完了: {alert.japanese_title[:30]}...")
            except Exception as e:
                self.safe_print(f"  -> 翻訳・要約エラー: {alert.title}: {e}")
                alert.japanese_title = "翻訳失敗"
                alert.japanese_summary = "要約の生成に失敗しました"
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # 各アラートの翻訳・要約を並列で実行
            futures = [executor.submit(process_single_translation, alert) for alert in alerts]
            
            # 全ての処理が完了するまで待機
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    logger.error(f"翻訳・要約で予期しないエラー: {e}")
    
    def save_to_notion(self, alert: Alert):
        """アラート情報をNotionデータベースに保存"""
        database_id = os.getenv('NOTION_DB_ID_GOOGLE_ALERTS')
        if not database_id:
            raise ValueError("NOTION_DB_ID_GOOGLE_ALERTS環境変数が設定されていません")
        
        try:
            # 既存のエントリをチェック
            existing = self.notion_client.databases.query(
                database_id=database_id,
                filter={
                    "property": "URL",
                    "url": {
                        "equals": alert.url
                    }
                }
            )

            if existing['results']:
                logger.info(f"  -> 既に存在するためスキップ: {alert.title}")
                return

            # 新規ページ作成
            logger.info(f"  -> Notionに保存する日時: {alert.date_processed}")
            self.notion_client.pages.create(
                parent={"database_id": database_id},
                properties={
                    "Title": {
                        "title": [
                            {
                                "text": {
                                    "content": alert.japanese_title
                                }
                            }
                        ]
                    },
                    "Original Title": { 
                        "rich_text": [
                            {
                                "text": {
                                    "content": alert.title
                                }
                            }
                        ]
                    },
                    "URL": {
                        "url": alert.url
                    },
                    "Source": {
                        "rich_text": [
                            {
                                "text": {
                                    "content": alert.source
                                }
                            }
                        ]
                    },
                    "Summary": {
                        "rich_text": [
                            {
                                "text": {
                                    "content": alert.japanese_summary
                                }
                            }
                        ]
                    },
                    "Snippet": {
                        "rich_text": [
                            {
                                "text": {
                                    "content": alert.snippet
                                }
                            }
                        ]
                    },
                    "Date": {
                        "date": {
                            "start": alert.date_processed,
                            "time_zone": "Asia/Tokyo"
                        }
                    }
                }
            )

            logger.info(f"  -> 保存完了: {alert.title}")

        except Exception as e:
            logger.error(f"  -> Notion保存エラー ({alert.title}): {e}")
    
    def save_to_notion_parallel(self, alerts: List[Alert], max_workers: int = 3) -> List[Alert]:
        """複数のアラートをNotionに並列で保存"""
        logger.info(f"Notion並列保存開始: {len(alerts)}件のアラートを{max_workers}並列で処理")
        
        saved_alerts = []
        
        def save_single_alert(alert: Alert) -> Alert:
            """単一のアラートをNotionに保存"""
            try:
                self.safe_print(f"  -> Notion保存中: {alert.title[:50]}...")
                self.save_to_notion(alert)
                self.safe_print(f"  -> Notion保存完了: {alert.title[:30]}...")
                return alert
            except Exception as e:
                self.safe_print(f"  -> Notion保存エラー: {alert.title}: {e}")
                return alert  # エラーがあってもアラートは返す
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # 各アラートのNotion保存を並列で実行
            future_to_alert = {
                executor.submit(save_single_alert, alert): alert 
                for alert in alerts
            }
            
            # 完了した処理から結果を取得
            for future in as_completed(future_to_alert):
                try:
                    alert = future.result()
                    saved_alerts.append(alert)
                except Exception as e:
                    original_alert = future_to_alert[future]
                    logger.error(f"Notion保存で予期しないエラー ({original_alert.title}): {e}")
                    saved_alerts.append(original_alert)  # エラーがあってもアラートは返す
        
        return saved_alerts
    
    def format_slack_message(self, alerts: List[Alert], date: str) -> str:
        """アラートデータをSlack投稿用にフォーマット"""
        if not alerts:
            return f"*{date}のGoogle Alerts*\n本日はアラートがありませんでした。"
        
        message = f"*{date}のGoogle Alerts ({len(alerts)}件)*\n\n"
        
        for i, alert in enumerate(alerts, 1):
            message += f"{i}. *{alert.japanese_title or alert.title}*\n"
            message += f"   🌐 {alert.source}\n"
            message += f"   📄 {alert.japanese_summary}\n"
            message += f"   🔗 <{alert.url}|記事を読む>\n\n"
        
        return message
    
    def send_to_slack(self, message: str) -> bool:
        """Slackに投稿"""
        if not SLACK_WEBHOOK_URL:
            logger.error("SLACK_WEBHOOK_URL_GOOGLE_ALERTS環境変数が設定されていません")
            return False
        
        payload = {"text": message}
        
        try:
            response = requests.post(SLACK_WEBHOOK_URL, json=payload)
            if response.status_code == 200:
                logger.info("Slackへの送信が完了しました")
                return True
            else:
                logger.error(f"Slackへの送信に失敗しました。ステータスコード: {response.status_code}")
                return False
        except Exception as e:
            logger.error(f"Slackへの送信エラー: {e}")
            return False
    
    def process_google_alerts(self, target_date: datetime, save_notion: bool = True, send_slack: bool = True, date_specified: bool = False, hours: int = 6):
        """Google Alertsの処理メイン関数"""
        date_str = target_date.strftime('%Y-%m-%d')
        if date_specified:
            logger.info(f"Google Alerts ({date_str}) の処理を開始します...")
        else:
            logger.info(f"Google Alerts (過去{hours}時間) の処理を開始します...")

        # Slack送信が有効な場合、環境変数をチェック
        if send_slack and not SLACK_WEBHOOK_URL:
            raise ValueError("SLACK_WEBHOOK_URL_GOOGLE_ALERTS環境変数が設定されていません。Slack送信を行う場合は設定してください。")

        # 指定された日付のメールを取得
        messages = self.get_google_alerts_emails(target_date, date_specified, hours)

        if not messages:
            if date_specified:
                logger.warning(f"{date_str} のGoogle Alertsメールが見つかりません")
            else:
                logger.warning(f"過去{hours}時間のGoogle Alertsメールが見つかりません")
            return

        # 全てのメールから全てのアラートを並列で抽出
        all_alerts = self.process_messages_parallel(messages)

        logger.info(f"{len(all_alerts)}件のアラートを検出しました")

        if not all_alerts:
            logger.warning("アラートが見つかりませんでした")
            return

        # 記事コンテンツを並列で取得
        self.fetch_articles_parallel(all_alerts)

        # 翻訳・要約を並列で処理
        self.process_translations_parallel(all_alerts)

        # Notionに並列で保存
        if save_notion:
            processed_alerts = self.save_to_notion_parallel(all_alerts)
        else:
            processed_alerts = all_alerts

        # Slackに送信
        if send_slack and processed_alerts:
            if date_specified:
                slack_message = self.format_slack_message(processed_alerts, date_str)
            else:
                slack_message = self.format_slack_message(processed_alerts, f"過去{hours}時間")
            self.send_to_slack(slack_message)

        logger.info("処理が完了しました")


def main():
    """メイン実行関数"""
    parser = argparse.ArgumentParser(description='Google Alertsメールを取得してNotionに保存およびSlackに送信（デフォルトは両方実行）')
    
    # 日付/時間指定の相互排他的グループ
    time_group = parser.add_mutually_exclusive_group()
    time_group.add_argument(
        '--date',
        type=str,
        help='取得する日付 (YYYY-MM-DD形式)。指定した場合はその日の全メールを取得',
        default=None
    )
    time_group.add_argument(
        '--hours',
        type=int,
        help='過去何時間のメールを取得するかを指定（デフォルト: 6時間）',
        default=6
    )
    
    # 送信先の相互排他的グループ
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
    date_specified = False
    hours = 6  # デフォルト値
    
    if args.date:
        try:
            target_date = datetime.strptime(args.date, '%Y-%m-%d')
            date_specified = True
        except ValueError:
            logger.error("エラー: 日付は YYYY-MM-DD 形式で指定してください (例: 2024-01-15)")
            return
    else:
        target_date = datetime.now()
        hours = args.hours  # --hoursオプションが指定された場合はその値を使用
    
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
        processor = GoogleAlertsProcessor()
        processor.process_google_alerts(target_date, save_notion=save_notion, send_slack=send_slack, date_specified=date_specified, hours=hours)
    except Exception as e:
        logger.error(f"エラーが発生しました: {e}")
        raise


if __name__ == "__main__":
    main()