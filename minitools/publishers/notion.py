"""
Notion publisher module for saving content to Notion databases.
"""

import os
import asyncio
from typing import Dict, Any, List, Optional
from datetime import datetime
from notion_client import Client

from minitools.utils.logger import get_logger

logger = get_logger(__name__)


class NotionPublisher:
    """Notionデータベースにコンテンツを保存するクラス"""
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Args:
            api_key: Notion APIキー（指定しない場合は環境変数から取得）
        """
        self.api_key = api_key or os.getenv('NOTION_API_KEY')
        if not self.api_key:
            raise ValueError("NOTION_API_KEY is required")
        
        self.client = Client(auth=self.api_key)
        logger.info("Notion client initialized")
    
    async def check_existing(self, database_id: str, url: str) -> bool:
        """
        URLが既にデータベースに存在するかチェック
        
        Args:
            database_id: NotionデータベースID
            url: チェックするURL
            
        Returns:
            存在する場合True
        """
        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: self.client.databases.query(
                    database_id=database_id,
                    filter={
                        "property": "URL",
                        "url": {"equals": url}
                    }
                )
            )
            
            exists = len(result.get('results', [])) > 0
            if exists:
                logger.info(f"既に存在するためスキップ: {url}")
            else:
                logger.debug(f"新規記事として処理: {url}")
            return exists
            
        except Exception as e:
            logger.error(f"重複チェックエラー: {e}")
            return False
    
    async def create_page(self, database_id: str, properties: Dict[str, Any]) -> Optional[str]:
        """
        Notionページを作成
        
        Args:
            database_id: NotionデータベースID
            properties: ページプロパティ
            
        Returns:
            作成されたページのID
        """
        try:
            loop = asyncio.get_event_loop()
            page = await loop.run_in_executor(
                None,
                lambda: self.client.pages.create(
                    parent={"database_id": database_id},
                    properties=properties
                )
            )
            
            page_id = page.get('id')
            logger.debug(f"Notionページ作成完了: {page_id}")
            return page_id
            
        except Exception as e:
            logger.error(f"Notionページ作成エラー: {e}")
            return None
    
    async def save_article(self, database_id: str, article_data: Dict[str, Any]) -> bool:
        """
        記事をNotionデータベースに保存
        
        Args:
            database_id: NotionデータベースID
            article_data: 記事データ（title, url, author, summary等を含む辞書）
            
        Returns:
            保存成功の場合True
        """
        # URLの重複チェック
        url = article_data.get('url')
        title = article_data.get('title', 'Unknown')
        author = article_data.get('author', 'Unknown')
        
        if url and await self.check_existing(database_id, url):
            logger.info(f"  -> 既に存在するためスキップ: {title[:50]}..." if len(title) > 50 else f"  -> 既に存在するためスキップ: {title}")
            return False
        
        logger.info(f"  -> Notionに保存中: {title[:50]}..." if len(title) > 50 else f"  -> Notionに保存中: {title}")
        
        # Notionプロパティの構築
        properties = self._build_article_properties(article_data)
        
        # ページ作成
        page_id = await self.create_page(database_id, properties)
        
        if page_id:
            logger.info(f"  -> 保存完了: {title[:50]}... by {author}" if len(title) > 50 else f"  -> 保存完了: {title} by {author}")
        else:
            logger.error(f"  -> 保存失敗: {title[:50]}..." if len(title) > 50 else f"  -> 保存失敗: {title}")
        
        return page_id is not None
    
    def _build_article_properties(self, article_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        記事データからNotionプロパティを構築
        
        Args:
            article_data: 記事データ
            
        Returns:
            Notionプロパティ辞書
        """
        properties = {}
        
        # タイトル (元の英語タイトルをメインのTitleに)
        if 'title' in article_data:
            properties['Title'] = {
                "title": [{"text": {"content": article_data['title']}}]
            }
        
        # 日本語タイトルをJapanese Titleに
        if 'japanese_title' in article_data:
            properties['Japanese Title'] = {
                "rich_text": [{"text": {"content": article_data['japanese_title']}}]
            }
        
        # URL
        if 'url' in article_data:
            properties['URL'] = {"url": article_data['url']}
        
        # 著者情報をAuthorプロパティに
        if 'author' in article_data:
            properties['Author'] = {
                "rich_text": [{"text": {"content": article_data['author']}}]
            }
        elif 'source' in article_data:  # sourceがある場合はそれを使用
            properties['Author'] = {
                "rich_text": [{"text": {"content": article_data['source']}}]
            }
        
        # 要約
        if 'japanese_summary' in article_data:
            properties['Summary'] = {
                "rich_text": [{"text": {"content": article_data['japanese_summary']}}]
            }
        elif 'summary' in article_data:
            properties['Summary'] = {
                "rich_text": [{"text": {"content": article_data['summary']}}]
            }
        
        # スニペット
        if 'snippet' in article_data:
            properties['Snippet'] = {
                "rich_text": [{"text": {"content": article_data['snippet']}}]
            }
        
        # 日付
        if 'date' in article_data:
            properties['Date'] = {
                "date": {"start": article_data['date']}
            }
        else:
            properties['Date'] = {
                "date": {"start": datetime.now().strftime("%Y-%m-%d")}
            }
        
        # タグ
        if 'tags' in article_data and isinstance(article_data['tags'], list):
            properties['Tags'] = {
                "multi_select": [{"name": tag} for tag in article_data['tags']]
            }
        
        return properties
    
    async def batch_save_articles(self, database_id: str, articles: List[Dict[str, Any]], 
                                 max_concurrent: int = 3) -> Dict[str, int]:
        """
        複数の記事を並列でNotionに保存
        
        Args:
            database_id: NotionデータベースID
            articles: 記事データのリスト
            max_concurrent: 最大同時実行数
            
        Returns:
            処理結果の統計（成功数、スキップ数、失敗数）
        """
        semaphore = asyncio.Semaphore(max_concurrent)
        stats = {"success": 0, "skipped": 0, "failed": 0}
        
        async def save_with_semaphore(article):
            async with semaphore:
                try:
                    result = await self.save_article(database_id, article)
                    if result:
                        stats["success"] += 1
                    else:
                        stats["skipped"] += 1
                except Exception as e:
                    title = article.get('title', 'Unknown')
                    error_title = f"{title[:50]}..." if len(title) > 50 else title
                    logger.error(f"記事の保存エラー '{error_title}': {e}")
                    stats["failed"] += 1
        
        # 全記事を並列処理
        tasks = [save_with_semaphore(article) for article in articles]
        await asyncio.gather(*tasks)
        
        logger.info(f"バッチ保存完了: 成功={stats['success']}, スキップ={stats['skipped']}, 失敗={stats['failed']}")
        return stats