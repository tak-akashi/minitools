"""
Slack publisher module for sending messages to Slack channels.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

import aiohttp

from minitools.utils.logger import get_logger

logger = get_logger(__name__)


class SlackPublisher:
    """Slackにメッセージを送信するクラス"""
    
    def __init__(self, webhook_url: Optional[str] = None):
        """
        Args:
            webhook_url: Slack Webhook URL（指定しない場合は環境変数から取得）
        """
        self.webhook_url = webhook_url
        self.http_session = None
    
    async def __aenter__(self):
        """非同期コンテキストマネージャーのエントリー"""
        self.http_session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """非同期コンテキストマネージャーのクリーンアップ"""
        if self.http_session:
            await self.http_session.close()
    
    def set_webhook_url(self, webhook_url: str):
        """Webhook URLを設定"""
        self.webhook_url = webhook_url
    
    async def send_message(self, message: str, webhook_url: Optional[str] = None) -> bool:
        """
        Slackにメッセージを送信
        
        Args:
            message: 送信するメッセージ
            webhook_url: 使用するWebhook URL（オプション）
            
        Returns:
            送信成功の場合True
        """
        url = webhook_url or self.webhook_url
        if not url:
            logger.error("No Slack webhook URL provided")
            return False
        
        if not self.http_session:
            logger.error("HTTP session not initialized. Use async context manager.")
            return False
        
        payload = {"text": message}
        
        try:
            async with self.http_session.post(url, json=payload) as response:
                if response.status == 200:
                    logger.info("Message sent to Slack successfully")
                    return True
                else:
                    logger.error(f"Failed to send message to Slack. Status: {response.status}")
                    return False
                    
        except Exception as e:
            logger.error(f"Error sending message to Slack: {e}")
            return False
    
    def format_articles_message(self, articles: List[Dict[str, Any]], 
                               date: Optional[str] = None,
                               title: str = "Daily Digest") -> str:
        """
        記事リストをSlackメッセージ形式にフォーマット
        
        Args:
            articles: 記事データのリスト
            date: 日付文字列
            title: メッセージタイトル
            
        Returns:
            フォーマットされたメッセージ
        """
        if not articles:
            return f"*{title} : {date or datetime.now().strftime('%Y-%m-%d')}*\n対象となる記事や論文等がありませんでした。"
        
        date_str = date or datetime.now().strftime('%Y-%m-%d')
        message = f"*{title} {date_str} ({len(articles)}件)*\n\n"
        
        for i, article in enumerate(articles, 1):
            # タイトル（日本語優先）
            display_title = article.get('japanese_title') or article.get('title', 'タイトルなし')
            message += f"{i}. *{display_title}*\n"
            
            # 著者
            if 'author' in article:
                message += f"   👤 {article['author']}\n"
            
            # 要約（日本語優先）
            summary = article.get('japanese_summary') or article.get('summary', '')
            if summary:
                message += f"   📄 {summary}\n"
            
            # URL
            if 'url' in article:
                message += f"   🔗 <{article['url']}|記事を読む>\n"
            
            message += "\n"
        
        return message
    
    def format_simple_list(self, items: List[str], title: str = "通知") -> str:
        """
        シンプルなリストをSlackメッセージ形式にフォーマット
        
        Args:
            items: アイテムのリスト
            title: メッセージタイトル
            
        Returns:
            フォーマットされたメッセージ
        """
        if not items:
            return f"*{title}*\n項目がありません。"
        
        message = f"*{title} ({len(items)}件)*\n\n"
        for i, item in enumerate(items, 1):
            message += f"{i}. {item}\n"
        
        return message
    
    async def send_articles(self, articles: List[Dict[str, Any]],
                           webhook_url: Optional[str] = None,
                           date: Optional[str] = None,
                           title: str = "Daily Digest") -> bool:
        """
        記事リストをフォーマットしてSlackに送信

        Args:
            articles: 記事データのリスト
            webhook_url: 使用するWebhook URL（オプション）
            date: 日付文字列
            title: メッセージタイトル

        Returns:
            送信成功の場合True
        """
        message = self.format_articles_message(articles, date, title)
        return await self.send_message(message, webhook_url)

    def format_weekly_digest(
        self,
        start_date: str,
        end_date: str,
        trend_summary: str,
        articles: List[Dict[str, Any]],
    ) -> str:
        """
        週次ダイジェストをSlackメッセージ形式にフォーマット

        Args:
            start_date: 期間開始日（YYYY-MM-DD形式）
            end_date: 期間終了日（YYYY-MM-DD形式）
            trend_summary: 週のトレンド総括
            articles: 上位記事リスト（digest_summary付き）

        Returns:
            フォーマットされたメッセージ
        """
        # ランキング用絵文字
        rank_emoji = {1: "1", 2: "2", 3: "3"}

        # ヘッダー
        message = f"*Weekly AI Digest ({start_date} - {end_date})*\n"
        message += f"📊 {len(articles)}件の記事を分析しました\n\n"

        # トレンド総括セクション
        message += "*📈 今週のトレンド*\n"
        message += "─" * 30 + "\n"
        message += f"{trend_summary}\n\n"

        # 上位記事リスト
        message += "*🏆 注目記事 TOP " + str(len(articles)) + "*\n"
        message += "─" * 30 + "\n\n"

        for i, article in enumerate(articles, 1):
            # ランキング表示
            if i <= 3:
                rank_display = rank_emoji.get(i, str(i))
            else:
                rank_display = str(i)

            # タイトル（日本語優先）
            title = article.get("title", article.get("original_title", "タイトルなし"))

            # スコア
            score = article.get("importance_score", 0)

            message += f"*{rank_display}. {title}*\n"

            # ソース情報
            source = article.get("source", "")
            if source:
                message += f"   📰 {source}\n"

            # 重要度スコア
            message += f"   ⭐ スコア: {score:.1f}/10\n"

            # 要約
            summary = article.get("digest_summary", article.get("summary", ""))
            if summary:
                # 長すぎる場合は切り詰め
                if len(summary) > 200:
                    summary = summary[:197] + "..."
                message += f"   📄 {summary}\n"

            # URL
            url = article.get("url", "")
            if url:
                message += f"   🔗 <{url}|記事を読む>\n"

            message += "\n"

        return message

    async def send_weekly_digest(
        self,
        start_date: str,
        end_date: str,
        trend_summary: str,
        articles: List[Dict[str, Any]],
        webhook_url: Optional[str] = None,
    ) -> bool:
        """
        週次ダイジェストをフォーマットしてSlackに送信

        Args:
            start_date: 期間開始日
            end_date: 期間終了日
            trend_summary: トレンド総括
            articles: 上位記事リスト
            webhook_url: 使用するWebhook URL（オプション）

        Returns:
            送信成功の場合True
        """
        message = self.format_weekly_digest(
            start_date, end_date, trend_summary, articles
        )
        return await self.send_message(message, webhook_url)