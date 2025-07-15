import os
import requests
import json
import feedparser
import ollama
from typing import List, Dict, Tuple
from datetime import datetime, timedelta
import pytz
import argparse
import logging
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

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


def search_arxiv(queries: List[str], start_date: str, end_date: str, max_results: int) -> List[Dict[str, str]]:
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


def summarize_paper_briefly(title: str, summary: str, model="gemma3:27b") -> str:
    """
    論文のタイトルと要約から簡潔な要約を生成
    """
    prompt = f"""以下の論文のタイトルと要約を1〜2文で簡潔に要約してください。
    
タイトル: {title}
要約: {summary}

簡潔な要約:"""
    
    response = ollama.chat(model=model, messages=[
        {"role": "user", "content": prompt}
    ])
    return response["message"]["content"].strip()


def translate_to_japanese_with_ollama(text: str, model: str = "gemma3:27b") -> str:
    """
    ollamaを使用して日本語に翻訳
    
    Args:
        text: 翻訳する英語のテキスト
        model: 使用するollamaモデル
    
    Returns:
        日本語に翻訳されたテキスト
    """
    response = ollama.chat(
        model=model,
        messages=[{
            "role": "user",
            "content": f"以下を日本語に翻訳して。\n\n{text}"
        }]
    )
    return response["message"]["content"].strip()


def add_to_notion(
    title: str,
    published_date: str,
    updated_date: str,
    summary: str,
    translated_summary: str,
    url: str
) -> bool:
    """
    Notion APIにデータを送信
    
    Returns:
        エラーが発生した場合True
    """
    if not NOTION_API_KEY or not DATABASE_ID:
        logger.error("Notion API key or Database ID not set")
        return True
    
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
    
    try:
        response = requests.post(api_url, headers=headers, data=json.dumps(data))
        if response.status_code == 200:
            logger.info(f"Added '{title}' to Notion.")
            return False
        else:
            logger.error(f"Failed to add to Notion. Status: {response.status_code}, Response: {response.text}")
            return True
    except Exception as e:
        logger.error(f"Error adding to Notion: {e}")
        return True


def format_slack_message(papers: List[dict], date: str) -> str:
    """
    論文データをSlack投稿用にフォーマット
    """
    if not papers:
        return f"*{date}のarXiv論文*\n本日は対象論文がありませんでした。"
    
    message = f"*{date}のarXiv論文 ({len(papers)}件)*\n\n"
    
    for i, paper in enumerate(papers, 1):
        brief_summary = summarize_paper_briefly(paper['title'], paper['summary'])
        message += f"{i}. *{paper['title']}*\n"
        message += f"   📄 {brief_summary}\n"
        message += f"   🔗 <{paper['pdf_url']}|PDF>\n\n"
    
    return message


def send_to_slack(message: str) -> bool:
    """
    Slackに投稿
    """
    if not SLACK_WEBHOOK_URL:
        logger.error("SLACK_WEBHOOK_URL environment variable not set")
        return False
    
    payload = {"text": message}
    
    try:
        response = requests.post(SLACK_WEBHOOK_URL, json=payload)
        if response.status_code == 200:
            logger.info("Successfully sent message to Slack")
            return True
        else:
            logger.error(f"Failed to send to Slack. Status code: {response.status_code}")
            return False
    except Exception as e:
        logger.error(f"Error sending to Slack: {e}")
        return False



def process_papers(
    papers: List[Dict[str, str]]
) -> Tuple[int, List[Dict[str, str]]]:
    """
    論文を処理してNotionに保存
    
    Returns:
        (エラー数, 処理済み論文リスト)
    """
    error_count = 0
    processed_papers = []
    
    for i, paper in enumerate(papers, 1):
        logger.info(f"Processing {paper['title']} ({i}/{len(papers)})")
        
        # 日本語に翻訳
        translated_summary = translate_to_japanese_with_ollama(paper["summary"])
        
        # Notionに追加
        error = add_to_notion(
            paper['title'],
            paper["published_date"],
            paper["updated_date"],
            paper["summary"],
            translated_summary,
            paper['pdf_url']
        )
        
        if error:
            error_count += 1
        
        # 処理済みデータを保存
        processed_paper = paper.copy()
        processed_paper['translated_summary'] = translated_summary
        processed_papers.append(processed_paper)
    
    return error_count, processed_papers


def main(
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
    papers = search_arxiv(
        queries,
        start_date.replace("-", ""),
        end_date.replace("-", ""),
        max_results
    )
    logger.info(f"Found {len(papers)} papers")
    
    if not papers:
        logger.info("No papers found")
        if send_slack:
            slack_message = format_slack_message([], end_date)
            send_to_slack(slack_message)
        return
    
    # 論文を処理
    error_count, processed_papers = process_papers(papers)
    
    logger.info(
        f"Processed {len(papers) - error_count} papers successfully. "
        f"{error_count} papers failed."
    )
    
    # Slackに投稿
    if send_slack:
        slack_message = format_slack_message(processed_papers, end_date)
        send_to_slack(slack_message)


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


if __name__ == "__main__":
    args = parse_args()
    
    start_date = (
        datetime.strptime(args.base_date, "%Y-%m-%d") - 
        timedelta(days=args.days_before - 1)
    ).strftime("%Y-%m-%d")
    
    main(
        queries=args.queries,
        start_date=start_date,
        end_date=args.base_date,
        max_results=args.max_results,
        send_slack=not args.no_slack
    )
