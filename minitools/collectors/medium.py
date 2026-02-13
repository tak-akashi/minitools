"""
Medium Daily Digest collector module.
"""

import os
import pickle
import base64
import re
import asyncio
import random
import aiohttp
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from dataclasses import dataclass
import pytz
from bs4 import BeautifulSoup

from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from minitools.utils.logger import get_logger

logger = get_logger(__name__)

# Gmail API スコープ
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

# User-Agent ローテーション用リスト
USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.2 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:134.0) Gecko/20100101 Firefox/134.0",
]


@dataclass
class Article:
    """記事情報を格納するデータクラス"""

    title: str
    url: str
    author: str
    preview: str = ""  # メールから抽出したプレビューテキスト
    claps: int = 0  # 拍手数
    japanese_title: str = ""
    summary: str = ""
    japanese_summary: str = ""
    date_processed: str = ""


class MediumCollector:
    """Medium Daily Digestメールを収集するクラス"""

    def __init__(self, credentials_path: Optional[str] = None):
        self.gmail_service = None
        self.http_session = None
        self.credentials_path = credentials_path or os.getenv(
            "GMAIL_CREDENTIALS_PATH", "credentials.json"
        )
        self._authenticate_gmail()

    async def __aenter__(self):
        """非同期コンテキストマネージャーのエントリー"""
        connector = aiohttp.TCPConnector(limit=5)  # 並列数を削減（bot検出回避）
        timeout = aiohttp.ClientTimeout(
            total=60, connect=30, sock_connect=30, sock_read=30
        )

        # ブラウザを模倣したヘッダー
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9,ja;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "DNT": "1",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Cache-Control": "max-age=0",
        }

        self.http_session = aiohttp.ClientSession(
            connector=connector, timeout=timeout, headers=headers
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """非同期コンテキストマネージャーのクリーンアップ"""
        if self.http_session:
            await self.http_session.close()

    def _authenticate_gmail(self):
        """Gmail APIの認証"""
        try:
            creds = None
            token_path = "token.pickle"

            if os.path.exists(token_path):
                with open(token_path, "rb") as token:
                    creds = pickle.load(token)

            if not creds or not creds.valid:
                if creds and creds.expired and creds.refresh_token:
                    creds.refresh(Request())
                else:
                    if not os.path.exists(self.credentials_path):
                        raise FileNotFoundError(
                            f"認証ファイル {self.credentials_path} が見つかりません"
                        )

                    flow = InstalledAppFlow.from_client_secrets_file(
                        self.credentials_path, SCOPES
                    )
                    creds = flow.run_local_server(port=0)

                with open(token_path, "wb") as token:
                    pickle.dump(creds, token)

            self.gmail_service = build("gmail", "v1", credentials=creds)
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
        jst = pytz.timezone("Asia/Tokyo")

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
        query = (
            f"from:noreply@medium.com after:{start_timestamp} before:{end_timestamp}"
        )
        logger.info(f"Searching Gmail with query: {query}")

        try:
            loop = asyncio.get_event_loop()
            if self.gmail_service is None:
                logger.error("Gmail service is not initialized")
                return []

            service = self.gmail_service
            response = await loop.run_in_executor(
                None,
                lambda: service.users()
                .threads()
                .list(userId="me", q=query, maxResults=1)
                .execute(),
            )

            threads = response.get("threads", [])
            if not threads:
                logger.info("No Medium Daily Digest emails found")
                return []

            thread_id = threads[0]["id"]
            thread = await loop.run_in_executor(
                None,
                lambda: service.users()
                .threads()
                .get(userId="me", id=thread_id)
                .execute(),
            )

            messages = thread.get("messages", [])
            if messages:
                logger.info(f"Found {len(messages)} messages in thread")
                return [messages[-1]]  # 最新のメッセージのみを返す

            return []

        except HttpError as error:
            logger.error(f"Gmail APIエラー: {error}")
            return []

    def parse_articles(self, html_content: str) -> List[Article]:
        """
        メールHTMLから記事情報を抽出

        Args:
            html_content: メールのHTML内容

        Returns:
            記事情報のリスト
        """
        soup = BeautifulSoup(html_content, "html.parser")
        articles = []

        # Medium Daily Digestの記事リンクパターンを探す
        article_links = soup.find_all(
            "a", class_="ag", href=re.compile(r"https://medium\.com/.*\?source=email")
        )

        seen_urls = set()

        for link in article_links:
            url = str(link.get("href", ""))
            if not url or url in seen_urls:
                continue

            # URLクリーンアップ（改善版）
            clean_url = self._clean_url(url)
            if clean_url in seen_urls:
                logger.debug(f"重複URLをスキップ: {clean_url}")
                continue
            seen_urls.add(clean_url)

            # タイトルの抽出（h2タグから）
            h2_tag = link.find("h2")
            if h2_tag:
                title = h2_tag.get_text(strip=True)
            else:
                title = link.get_text(strip=True)

            if not title or len(title) < 10:
                logger.debug(f"短いタイトルをスキップ: {title}")
                continue

            # プレビューテキストの抽出（h3タグから）
            preview = ""
            h3_tag = link.find("h3")
            if h3_tag:
                preview = h3_tag.get_text(strip=True)
                if preview and len(preview) > 20:
                    preview = preview[:500]  # 500文字に制限
                else:
                    preview = ""

            # 著者情報の抽出（great-grandparentから著者リンクを探す）
            author = "Unknown"
            parent = link.parent
            grandparent = parent.parent if parent else None
            great_grandparent = grandparent.parent if grandparent else None

            if great_grandparent:
                # 著者リンクを探す（medium.com/@username パターン、テキストを持つもの）
                author_links = great_grandparent.find_all(
                    "a", href=re.compile(r"medium\.com/@[^/]+\?")
                )
                for author_link in author_links:
                    if author_link == link:
                        continue
                    author_text = author_link.get_text(strip=True)
                    # 有効な著者名: 空でなく、特定のパターンでない
                    if (
                        author_text
                        and len(author_text) > 1
                        and not author_text.startswith("@")
                        and author_text != "Member"
                    ):
                        author = author_text
                        break

            # 拍手数の抽出（great_grandparent コンテナから）
            claps = self._extract_claps(great_grandparent)

            article = Article(
                title=title,
                url=clean_url,
                author=author,
                preview=preview,
                claps=claps,
                date_processed=datetime.now().isoformat(),
            )
            articles.append(article)
            logger.debug(
                f"記事を検出: {title[:50]}... by {author}, claps: {claps}, preview: {len(preview)} chars"
            )

        logger.info(f"Parsed {len(articles)} articles from email")
        return articles

    @staticmethod
    def _parse_count(count_str: str) -> int:
        """
        "1.2K" → 1200、"320" → 320 のようにカウント文字列を整数に変換

        Args:
            count_str: カウント文字列

        Returns:
            整数値（パース失敗時は0）
        """
        if not count_str:
            return 0
        count_str = count_str.strip().upper()
        try:
            if count_str.endswith("K"):
                return int(float(count_str[:-1]) * 1000)
            elif count_str.endswith("M"):
                return int(float(count_str[:-1]) * 1000000)
            else:
                return int(count_str)
        except (ValueError, IndexError):
            return 0

    def _extract_claps(self, container) -> int:
        """
        記事コンテナ要素から拍手数を抽出

        Args:
            container: BeautifulSoupの記事コンテナ要素

        Returns:
            拍手数（見つからない場合は0）
        """
        if not container:
            return 0

        text = container.get_text(separator=" ", strip=True)

        # パターン1: "Claps" の後に数値 (例: "Claps 320", "Claps320", "Claps 1.2K")
        match = re.search(r"Claps\s*([0-9][0-9.,]*[KkMm]?)", text)
        if match:
            return self._parse_count(match.group(1))

        # パターン2: 拍手アイコン(👏)の後に数値
        match = re.search(r"👏\s*([0-9][0-9.,]*[KkMm]?)", text)
        if match:
            return self._parse_count(match.group(1))

        # パターン3: "min read" の後の数値列（min read → claps → responses）
        match = re.search(r"min read\s+([0-9][0-9.,]*[KkMm]?)", text)
        if match:
            return self._parse_count(match.group(1))

        return 0

    def _clean_url(self, url: str) -> str:
        """
        URLをクリーンアップ（トラッキングパラメータ除去）

        Args:
            url: クリーンアップするURL

        Returns:
            クリーンアップされたURL
        """
        # URLからクエリパラメータを除去
        clean_url = url.split("?")[0]
        # 末尾のスラッシュを除去
        clean_url = clean_url.rstrip("/")
        # Mediumの特殊なパラメータを除去
        if "#" in clean_url:
            clean_url = clean_url.split("#")[0]
        return clean_url

    def _extract_author_from_jina(self, content: str) -> Optional[str]:
        """
        Jina Readerの出力から著者名を抽出

        Args:
            content: Jina Readerから取得したテキスト

        Returns:
            著者名（見つからない場合はNone）
        """
        # 無効な著者名パターン
        invalid_names = {
            "sitemap",
            "follow",
            "share",
            "menu",
            "home",
            "about",
            "contact",
            "sign in",
            "sign up",
            "login",
            "register",
            "subscribe",
            "newsletter",
            "privacy",
            "terms",
            "help",
            "search",
            "more",
            "read more",
            "continue",
            "medium",
            "member",
            "membership",
            "upgrade",
            "get started",
            "open in app",
            "open app",
            "get the app",
            "download",
            "install",
            "write",
            "read",
            "listen",
            "watch",
            "see more",
            "view more",
            "responses",
            "clap",
            "claps",
            "save",
            "bookmark",
            "copy link",
            "published",
            "edited",
            "updated",
            "posted",
            "featured",
        }

        def clean_author_name(name: str) -> str:
            """著者名からMarkdown構文などを除去"""
            if not name:
                return ""
            # Markdown画像構文を除去: ![Image N: Author Name -> Author Name
            name = re.sub(r"!\[Image\s*\d*:\s*", "", name)
            # 閉じ括弧も除去
            name = name.rstrip("]")
            return name.strip()

        def is_valid_author(name: str) -> bool:
            if not name or len(name) < 3 or len(name) > 50:
                return False
            if name.lower() in invalid_names:
                return False
            # 著者名は通常大文字で始まる単語を含む
            if not any(word[0].isupper() for word in name.split() if word):
                return False
            return True

        lines = content.split("\n")

        for i, line in enumerate(lines[:50]):  # 最初の50行を検索
            line_stripped = line.strip()

            # パターン1: "By Author Name" or "by Author Name"
            if line_stripped.lower().startswith("by ") and len(line_stripped) > 3:
                author = line_stripped[3:].strip()
                # "By Author Name in Publication" のパターン
                if " in " in author:
                    author = author.split(" in ")[0].strip()
                author = clean_author_name(author)
                if is_valid_author(author):
                    return author

            # パターン2: "Author Name" の後に "Follow" がある行
            if i + 1 < len(lines) and "follow" in lines[i + 1].lower():
                if line_stripped and not line_stripped.startswith("#"):
                    author = clean_author_name(line_stripped)
                    if is_valid_author(author):
                        return author

            # パターン3: Markdown リンク形式 [Author Name](url)
            if (
                line_stripped.startswith("[")
                and "](https://medium.com/@" in line_stripped
            ):
                match = re.match(r"\[([^\]]+)\]", line_stripped)
                if match:
                    author = clean_author_name(match.group(1))
                    if is_valid_author(author):
                        return author

            # パターン4: "Written by Author" 形式
            if "written by " in line_stripped.lower():
                idx = line_stripped.lower().find("written by ")
                author = clean_author_name(line_stripped[idx + 11 :].strip())
                if is_valid_author(author):
                    return author

            # パターン5: "Author Name · X min read" 形式
            if " min read" in line_stripped.lower():
                match = re.match(r"^([A-Z][a-zA-Z\s\.]+?)(?:\s*·|\s+\d)", line_stripped)
                if match:
                    author = clean_author_name(match.group(1).strip())
                    if is_valid_author(author):
                        return author

            # パターン6: Markdown リンク形式（一般的なURLパターン）
            match = re.match(
                r"^\[([A-Z][a-zA-Z\s\.]+?)\]\(https?://[^\)]+\)$", line_stripped
            )
            if match:
                author = clean_author_name(match.group(1).strip())
                if is_valid_author(author):
                    return author

        return None

    def _extract_author_from_url(self, url: str) -> Optional[str]:
        """
        URLから著者名（ユーザー名）を抽出

        Args:
            url: Medium記事のURL

        Returns:
            著者のユーザー名（見つからない場合はNone）
        """
        # medium.com/@username/... のパターン
        match = re.search(r"medium\.com/@([^/]+)", url)
        if match:
            username = match.group(1)
            # アンダースコアやハイフンをスペースに置換して読みやすく
            return f"@{username}"
        return None

    async def fetch_article_content(
        self, url: str, max_retries: int = 3
    ) -> tuple[str, Optional[str]]:
        """
        記事のコンテンツをJina AI Readerで取得（ボット検出回避）

        Args:
            url: 記事のURL
            max_retries: 最大リトライ回数

        Returns:
            (記事内容, 著者名) のタプル
        """
        # リクエスト間のランダム遅延
        delay = random.uniform(1, 3)
        await asyncio.sleep(delay)

        # Jina AI Reader URL
        jina_url = f"https://r.jina.ai/{url}"

        for attempt in range(max_retries):
            try:
                user_agent = random.choice(USER_AGENTS)
                headers = {
                    "User-Agent": user_agent,
                    "Accept": "text/plain",
                }

                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        jina_url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)
                    ) as response:
                        if response.status == 200:
                            text_content = await response.text()

                            # Jinaがブロックされた場合を検出
                            if (
                                "error 403" in text_content.lower()
                                or "just a moment" in text_content.lower()
                            ):
                                logger.warning(
                                    f"Jina Reader blocked by Medium for {url}"
                                )
                                return "", None

                            # 著者名を抽出（複数パターン対応）
                            author = self._extract_author_from_jina(text_content)
                            # 注: URLフォールバックは使わない（メールから抽出した著者名を優先）

                            # コンテンツを3000文字に制限
                            text_content = text_content.strip()[:3000]

                            if len(text_content) > 100:
                                logger.debug(
                                    f"Jina Reader: {len(text_content)} chars, author: {author}"
                                )
                                return text_content, author
                            else:
                                raise Exception("Content too short")

                        else:
                            raise Exception(f"HTTP {response.status}")

            except Exception as e:
                wait_time = 2**attempt

                if attempt < max_retries - 1:
                    logger.warning(
                        f"Error fetching {url}, retrying in {wait_time}s... (attempt {attempt + 1}/{max_retries}): {e}"
                    )
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"Error fetching article from {url}: {e}")
                    return "", None

        return "", None

    def extract_email_body(self, message: Dict) -> str:
        """
        メールメッセージから本文を抽出

        Args:
            message: Gmail APIのメッセージオブジェクト

        Returns:
            メール本文のHTML
        """
        payload = message.get("payload", {})
        body = self._extract_body_from_payload(payload)
        return body

    def _extract_body_from_payload(self, payload: Dict) -> str:
        """ペイロードからメール本文を抽出（内部メソッド）"""
        body = ""

        if "parts" in payload:
            for part in payload["parts"]:
                if part["mimeType"] == "text/html":
                    data = part["body"]["data"]
                    body = base64.urlsafe_b64decode(data).decode("utf-8")
                    break
                elif "parts" in part:
                    body = self._extract_body_from_payload(part)
                    if body:
                        break
        elif payload.get("body", {}).get("data"):
            body = base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8")

        return body
