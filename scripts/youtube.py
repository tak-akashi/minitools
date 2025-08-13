#!/usr/bin/env python3
"""
YouTube video summarization script - backward compatibility wrapper.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
import argparse
import logging
from pathlib import Path
from dotenv import load_dotenv

from minitools.collectors.youtube import YouTubeCollector
from minitools.processors.summarizer import Summarizer
from minitools.processors.translator import Translator
from minitools.utils.logger import setup_logger
from minitools.utils.config import get_config

load_dotenv()

# ロガーは後で初期化（argparseの前には基本設定のみ）
logger = None


def main():
    """エントリーポイント（同期版）"""
    asyncio.run(main_async())

async def main_async():
    parser = argparse.ArgumentParser(description='YouTube動画を要約して日本語で出力')
    parser.add_argument('-u', '--youtube_url', '--url', required=True,
                       help='YouTube動画のURL')
    parser.add_argument('-o', '--output_dir', default='outputs',
                       help='出力ディレクトリ')
    parser.add_argument('-m', '--model_path', default='mlx-community/whisper-large-v3-turbo',
                       help='使用する音声認識モデルのパス')
    parser.add_argument('--no-save', action='store_true',
                       help='ファイル保存をスキップ')
    parser.add_argument('--debug', action='store_true',
                       help='デバッグモードで実行')
    
    args = parser.parse_args()
    
    # 設定ファイルからデフォルトログレベルを取得
    config = get_config()
    default_log_level = config.get('logging.level', 'INFO').upper()
    
    # デバッグオプションが指定されている場合は上書き
    if args.debug:
        log_level = logging.DEBUG
    else:
        log_level = getattr(logging, default_log_level, logging.INFO)
    
    # ロガーの初期化
    global logger
    logger = setup_logger("scripts.youtube", log_file="youtube.log", level=log_level)
    
    # 出力ディレクトリの作成
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # コレクターの初期化
    collector = YouTubeCollector(
        output_dir=str(output_dir),
        whisper_model=args.model_path
    )
    
    # 動画を処理
    logger.info(f"Processing YouTube video: {args.youtube_url}")
    
    result = collector.process_video(args.youtube_url)
    
    if not result:
        logger.error("Failed to process video")
        return
    
    logger.info(f"Video title: {result['title']}")
    logger.info(f"Video author: {result['author']}")
    logger.info(f"Transcript length: {len(result['transcript'])} characters")
    
    # 要約と翻訳（YouTube用の軽量モデルを使用）
    config = get_config()
    youtube_model = config.get('models.youtube_summary', 'gemma2')
    summarizer = Summarizer(model=youtube_model)
    translator = Translator(model=youtube_model)
    
    # 英語で要約
    summary = await summarizer.summarize(
        result['transcript'],
        max_length=500,
        language="english"
    )
    
    # 日本語に翻訳
    japanese_summary = await translator.translate_to_japanese(summary)
    
    # 結果を表示
    print("\n" + "="*50)
    print(f"動画タイトル: {result['title']}")
    print(f"チャンネル: {result['author']}")
    print(f"動画時間: {result['duration']}秒")
    print("="*50)
    print("\n要約（日本語）:")
    print(japanese_summary)
    print("="*50)
    
    # ファイルに保存
    if not args.no_save:
        # 文字起こしを保存
        transcript_file = output_dir / "audio_transcript.txt"
        with open(transcript_file, 'w', encoding='utf-8') as f:
            f.write(f"Title: {result['title']}\n")
            f.write(f"Author: {result['author']}\n")
            f.write(f"URL: {result['url']}\n")
            f.write(f"\nTranscript:\n{result['transcript']}\n")
        logger.info(f"Transcript saved to: {transcript_file}")
        
        # 要約を保存
        summary_file = output_dir / "youtube_summary.txt"
        with open(summary_file, 'w', encoding='utf-8') as f:
            f.write(f"動画タイトル: {result['title']}\n")
            f.write(f"チャンネル: {result['author']}\n")
            f.write(f"URL: {result['url']}\n")
            f.write(f"\n要約（日本語）:\n{japanese_summary}\n")
        logger.info(f"Summary saved to: {summary_file}")
    
    logger.info("Processing completed")


if __name__ == "__main__":
    main()