import os
import requests
import json
import feedparser
import ollama
from typing import List
from datetime import datetime, timedelta
import pandas as pd
import pytz
import argparse
import logging
from dotenv import load_dotenv

load_dotenv()

print(os.path.dirname(__file__))

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# コンソールハンドラの作成
console_handler = logging.StreamHandler()

# フォーマッタの作成とハンドラへの設定
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
console_handler.setFormatter(formatter)
# ロガーにハンドラを追加
logger.addHandler(console_handler)

# ファイルハンドラの作成
file_handler = logging.FileHandler("outputs/logs/arxiv.log", mode="a")
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)



NOTION_API_KEY = os.getenv("NOTION_API_KEY")
DATABASE_ID = os.getenv("NOTION_DB_ID")


def search_arxiv(queries: List[str], start_date: str, end_date: str, max_results: int):
    """
    arXiv APIを使用して、指定されたクエリ、日付範囲、最大結果数に基づいて論文を検索する関数。

    Args:
    queries (List[str]): 検索語のリスト
    start_date (str): 検索開始日（YYYYMMDD形式）
    end_date (str): 検索終了日（YYYYMMDD形式）
    max_results (int): 取得する最大結果数

    Returns:
    List[Dict]: 検索結果の論文情報のリスト
    """
    # arXiv APIのエンドポイント
    url = "http://export.arxiv.org/api/query"

    # 複数の語句を " AND " で結合してクエリを作成
    search_query = " AND ".join(queries)

    # パラメータの設定
    params = {
        "search_query": f"all:{search_query} AND submittedDate:[{start_date}000000 TO {end_date}235959]",
        "start": 0,
        "max_results": max_results,
        "sortBy": "submittedDate",
        "sortOrder": "ascending",
    }

    # APIリクエスト
    response = requests.get(url, params=params)
    feed = feedparser.parse(response.content)

    # タイトル、日付、サマリー、PDFリンクの抽出
    papers = []
    for entry in feed.entries:
        title = entry.title.replace("\n", "")
        summary = entry.summary
        updated = entry.updated
        published = entry.published
        for link in entry.links:
            try:
                if link.title == 'pdf':
                    papers.append(
                        {"title": title, "updated_date": updated, "published_date": published,
                         "summary": summary, "pdf_url": link.href})
            except Exception as e:
                pass

    return papers


def tranlate_to_japanese_with_ollama(text: str, model="gemma3:27b"):
    """
    ollamaを使用して日本語に翻訳する関数

    Args:
    text (str): 翻訳する英語のテキスト
    model (str): 使用するollamaモデル（デフォルトは"gemma2"）

    Returns:
    str: 日本語に翻訳されたテキスト
    """
    abs = ollama.chat(model=model, messages=[
        {
            "role": "user", 
            "content": f"以下を日本語に翻訳して。\n\n{text}"
        }
    ])
    return abs["message"]["content"].strip()


# Notion APIにデータを送信する関数
def add_to_notion(title, published_date, updated_date, summary, translated_summary, url, error_flag=False):
    api_url = "https://api.notion.com/v1/pages"
    headers = {
        "Authorization": f"Bearer {NOTION_API_KEY}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28"
    }

    # Notionに送るデータ（データベースに合わせて調整が必要）
    data = {
        "parent": { "database_id": DATABASE_ID },
        "properties": {
            "タイトル": {
                "title": [
                    {
                        "text": {
                            "content": title
                        }
                    }
                ]
            },
            "公開日": {
                "date": {
                    "start": published_date,
                    "end": None
                }
            },
            "更新日": {
                "date": {
                    "start": updated_date,
                    "end": None
                }
            },
            "概要": {
                "rich_text": [
                    {
                        "text": {
                            "content": summary
                        }
                    }
                ]
            },
            "日本語訳": {
                "rich_text": [
                    {
                        "text": {
                            "content": translated_summary
                        }
                    }
                ]
            },
            "URL": {
                "url": url
            }
        }
    }

    # POSTリクエストでデータをNotionに送信
    response = requests.post(api_url, headers=headers, data=json.dumps(data))
    
    if response.status_code == 200:
        logger.info(f"Added '{title}' to Notion.")
    else:
        logger.error(f"Failed to add data to Notion. Status code: {response.status_code}, Response: {response.text}")
        error_flag = True

    return error_flag



def main(queries: List[str], start_date: str, end_date: str, max_results: int, save_to_csv: bool=False):

    logger.info(f"Searching max {max_results} papers from {start_date} 00:00:00 to {end_date} 23:59:59 with queries: {queries}")
    # 論文を検索
    papers = search_arxiv(queries, start_date.replace("-", ""), end_date.replace("-", ""), max_results)
    logger.info(f"Found {len(papers)} papers")

    all_summaries = []
    error_counts = 0
    for i, paper in enumerate(papers):
        logger.info(f"Translating summary of {paper['title']} ({i+1}/{len(papers)})")
        translated_summary = tranlate_to_japanese_with_ollama(paper["summary"])
        error_flag = add_to_notion(paper['title'], paper["updated_date"], paper["published_date"],
                          paper["summary"], translated_summary, paper['pdf_url'])
        if error_flag:
            error_counts += 1
        if save_to_csv:
            all_summaries.append(
                [paper['title'], paper["updated_date"], paper["published_date"],
             paper["summary"], translated_summary, paper['pdf_url']])

    logger.info(f"Translated and saved to Notion {len(papers) - error_counts} papers. {error_counts} papers were not saved.")

    if save_to_csv:
        logger.info(f"Saving to csv")
        # 出力ディレクトリがなければ作成
        output_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "outputs")
        if not os.path.exists(output_dir):
            os.makedirs(output_dir, exist_ok=True)
        df = pd.DataFrame(all_summaries, columns=[
            "Title", "Updated Date", "Published Date", "Summary", "Translated Summary", "PDF URL"])
        output_path = os.path.join(os.path.dirname(__file__), "outputs",
            "arxiv_summary_" + start_date.replace("/", "") + "_" + end_date.replace("/", "") + "_" + str(max_results) + "results.csv")
        df.to_csv(output_path, index=False, encoding="utf-8-sig")
        logger.info(f"Saved to {output_path}")


if __name__ == "__main__":

    parser = argparse.ArgumentParser()

    jst = pytz.timezone('Asia/Tokyo')
    # today = datetime.now(jst).strftime("%Y-%m-%d")
    yesterday = (datetime.now(jst) - timedelta(days=1)).strftime("%Y-%m-%d")

    parser.add_argument('-q', '--queries', type=List[str], default=["LLM", "(RAG OR FINETUNING)"])
    parser.add_argument('-d', '--days_before', type=int, default=1)
    parser.add_argument('-b', '--base_date', type=str, default=yesterday)
    parser.add_argument('-r', '--max_results', type=int, default=50)
    parser.add_argument('-c', '--save_to_csv', action='store_true', default=False)
    args = parser.parse_args()
    
    start_date = (datetime.strptime(args.base_date, "%Y-%m-%d") - timedelta(days=args.days_before - 1)).strftime("%Y-%m-%d")
        
    main(args.queries, start_date, args.base_date, args.max_results, args.save_to_csv)
