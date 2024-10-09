import os
import requests
import feedparser
import ollama
from typing import List
from datetime import datetime, timedelta
import pandas as pd
import pytz
import argparse
import logging


logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
# h = logging.FileHandler("outputs/get_arxiv_abs_in_ja.log")
# logger.addHandler(h)
# コンソールハンドラの作成
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.DEBUG)  # DEBUGレベル以上のすべてのログを出力

# フォーマッタの作成とハンドラへの設定
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
console_handler.setFormatter(formatter)

# ロガーにハンドラを追加
logger.addHandler(console_handler)


def search_arxiv(queries: List[str], start_date: str, end_date: str, max_results: int):
    """
    arXiv APIを使用して、指定されたクエリ、日付範囲、最大結果数に基づいて論文を検索する関数。

    Arguments:
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
    search_query = ' AND '.join(queries)

    # パラメータの設定
    params = {
        "search_query": f"all:{search_query} AND submittedDate:[{start_date}000000 TO {end_date}235959]",
        "start": 0,
        "max_results": max_results,
        "sortBy": "submittedDate",
        "sortOrder": "descending",
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


def tranlate_to_japanese_with_ollama(text: str, model="gemma2"):
    """
    ollamaを使用して日本語に翻訳する関数

    :param text: 翻訳する英語のテキスト
    :param model: 使用するollamaモデル（デフォルトは"gemma2"）
    :return: 日本語に翻訳されたテキスト
    """
    abs = ollama.chat(model=model, messages=[
        {
            "role": "user", 
            "content": f"以下を日本語に翻訳して。\n\n{text}"
        }
    ])
    return abs["message"]["content"]


def main(queries: List[str], start_date: str, end_date: str, max_results: int):

    logger.info(f"Searching papers from {start_date} to {end_date} with queries: {queries}")
    # 論文を検索
    papers = search_arxiv(queries, start_date.replace("-", ""), end_date.replace("-", ""), max_results)
    logger.info(f"Found {len(papers)} papers")

    all_summaries = []
    for i, paper in enumerate(papers):
        logger.info(f"Translating summary of {paper['title']} ({i+1}/{len(papers)})")
        translated_summary = tranlate_to_japanese_with_ollama(paper["summary"])
        all_summaries.append(
            [paper['title'], paper["updated_date"], paper["published_date"],
             paper["summary"], translated_summary, paper['pdf_url']])
    logger.info(f"Translated {len(papers)} papers, and start to save to csv")

    df = pd.DataFrame(all_summaries, columns=[
        "Title", "Updated Date", "Published Date", "Summary", "Translated Summary", "PDF URL"])
    output_path = os.path.join(os.path.dirname(__file__), "outputs",
            "arxiv_summary_" + start_date.replace("/", "") + "_" + end_date.replace("/", "") + "_" + str(max_results) + "results.csv")
    df.to_csv(output_path, index=False, encoding="utf-8-sig")
    logger.info(f"Saved to {output_path}")


if __name__ == "__main__":

    parser = argparse.ArgumentParser()

    jst = pytz.timezone('Asia/Tokyo')
    a_week_ago = (datetime.now(jst) - timedelta(days=7)).strftime("%Y-%m-%d")
    today = datetime.today().strftime("%Y-%m-%d")

    parser.add_argument('-q', '--queries', type=List[str], default=["LLM", "RAG"])
    parser.add_argument('-s', '--start_date', type=str, default=a_week_ago)
    parser.add_argument('-e', '--end_date', type=str, default=today)
    parser.add_argument('-r', '--max_results', type=int, default=50)

    args = parser.parse_args()

    main(args.queries, args.start_date, args.end_date, args.max_results)
