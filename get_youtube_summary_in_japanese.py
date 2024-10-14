import yt_dlp
import mlx_whisper
import os
import ollama
import argparse
import logging


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
file_handler = logging.FileHandler("outputs/logs/youtube.log", mode="a")
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)


# YouTubeから音声データを取得し、特定のフォルダにダウンロード
def download_youtube_audio(url, output_path):
    """
    YouTubeから音声データを取得し、特定のフォルダにダウンロードする関数
    """
    temp_dir = os.path.join(output_path, "temp")
    if not(os.path.exists(temp_dir)):
        os.makedirs(temp_dir, exist_ok=True)

    ydl_opts = {
        'format': 'bestaudio/best',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
        'outtmpl': os.path.join(temp_dir, 'audio'),
        'ffmpeg_location': '/opt/homebrew/bin/ffmpeg',
    }
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            logger.info(f"Downloading audio from {url}...")
            ydl.download([url])
            logger.info(f"Downloaded audio from {url}")
        except Exception as e:
            logger.error(f"Error downloading audio from {url}: {e}")


# 音声を文字起こし
def transcribe_audio(audio_file, model_path):
    """
    音声を文字起こしする関数
    """
    try:
        logger.info(f"Transcribing audio from {audio_file}...")
        return mlx_whisper.transcribe(audio_file, path_or_hf_repo=model_path)
    except Exception as e:
        logger.error(f"Error transcribing audio: {e}")
        return None


def get_summary_and_translate(text: str):
    """
    英語の文章を要約して、翻訳する関数
    """
    try:
        response = ollama.chat(
            model="gemma2",
            messages=[
            {
                "role": "user", 
                "content": f"以下の文章を要約して。\n\n#####\n{text}",
            }
            ]
        )
    except Exception as e:
        logger.error(f"Error summarizing audio: {e}")
        return None

    try:
        translated_text = ollama.chat(
        model="gemma2",
        messages=[
                {
                    "role": "user", 
                    "content": f"以下の文章を日本語に翻訳して。日本語の文章の場合はそのまま返して。" \
                               f"\n\n#####\n{response['message']['content']}",
                }
            ]
        ) 
        return translated_text['message']['content']
    except Exception as e:
        logger.error(f"Error translating audio: {e}")
        return None



def save_to_file(text, file_path):
    """
    要約した文章をファイルに保存する関数
    """
    with open(file_path, "w") as f:
        f.write(text)



def main(youtube_url, output_path, model_path):
    """
    メイン処理
    """
    # YouTubeから音声をダウンロード
    download_youtube_audio(youtube_url, output_path)

    audio_file = os.path.join(output_path, "temp", "audio.mp3")

    # 音声を文字起こし
    if os.path.exists(audio_file):
        text = transcribe_audio(audio_file, model_path)
        if text:
            save_to_file(text["text"], os.path.join(output_path, "audio_transcript.txt"))
            logger.info(f"Transcribed audio and saved to {os.path.join(output_path, "audio_transcript.txt")}") 
            logger.info(f"Summarizing and translating audio...")
            summary_and_translate = get_summary_and_translate(text['text'])  # text['text'] を渡す
            if summary_and_translate:
                save_to_file(summary_and_translate, os.path.join(output_path, "youtube_summary.txt"))
                logger.info("Successfully processed YouTube video.")
            else:
                logger.error("Failed to summarize and translate the text.")
        else:
            logger.error("Failed to transcribe audio.")
    else:
        logger.error("Failed to download audio file.")

    # 一時ファイルの削除
    if os.path.exists(audio_file):
        os.remove(audio_file)
        logger.info(f"Deletedtemporary audio file: {audio_file}")


if __name__ == "__main__":

    youtube_url = "https://www.youtube.com/watch?v=B4oHJpEJBAA"  # 例としてのURL
    output_path = "outputs"
    model_path = "mlx-community/whisper-large-v3-turbo"


    parser = argparse.ArgumentParser()
    parser.add_argument('-u', '--youtube_url', type=str, default=youtube_url)
    parser.add_argument('-o', '--output_dir', type=str, default=output_path)
    parser.add_argument('-m', '--model_path', type=str, default=model_path)
    args = parser.parse_args()

    main(args.youtube_url, args.output_dir, args.model_path)
