"""
YouTube video collector and transcriber module.
"""

import os
from pathlib import Path
from typing import Optional, Dict, Any

import yt_dlp

try:
    import mlx_whisper

    MLX_WHISPER_AVAILABLE = True
except ImportError:
    MLX_WHISPER_AVAILABLE = False

from minitools.utils.logger import get_logger

logger = get_logger(__name__)


class YouTubeCollector:
    """YouTube動画を収集して文字起こしするクラス"""

    def __init__(
        self,
        output_dir: str = "outputs/temp",
        whisper_model: str = "mlx-community/whisper-base",
    ):
        """
        Args:
            output_dir: 一時ファイルの出力ディレクトリ
            whisper_model: 使用するWhisperモデル
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.whisper_model = whisper_model

        if not MLX_WHISPER_AVAILABLE:
            logger.warning(
                "mlx_whisper is not installed. YouTube transcription will not be available."
            )
            logger.warning("To enable it, run: uv sync --extra whisper")

        # yt-dlpの設定
        self.ydl_opts = {
            "format": "bestaudio/best",
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }
            ],
            "outtmpl": str(self.output_dir / "%(id)s.%(ext)s"),
            "quiet": True,
            "no_warnings": True,
        }

        # FFmpegのパスを設定（Homebrewでインストールした場合）
        ffmpeg_path = "/opt/homebrew/bin/ffmpeg"
        if os.path.exists(ffmpeg_path):
            self.ydl_opts["ffmpeg_location"] = ffmpeg_path

    def download_audio(self, url: str) -> Optional[str]:
        """
        YouTubeから音声をダウンロード

        Args:
            url: YouTube動画のURL

        Returns:
            ダウンロードしたファイルのパス
        """
        with yt_dlp.YoutubeDL(self.ydl_opts) as ydl:
            try:
                logger.info(f"Downloading audio from {url}...")
                info = ydl.extract_info(url, download=True)
                video_id = info["id"]
                audio_file = self.output_dir / f"{video_id}.mp3"

                if audio_file.exists():
                    logger.info(f"Downloaded audio to {audio_file}")
                    return str(audio_file)
                else:
                    logger.error(f"Audio file not found: {audio_file}")
                    return None

            except Exception as e:
                logger.error(f"Error downloading audio from {url}: {e}")
                return None

    def transcribe_audio(self, audio_file: str) -> Optional[Dict[str, Any]]:
        """
        音声ファイルを文字起こし

        Args:
            audio_file: 音声ファイルのパス

        Returns:
            文字起こし結果（textキーを含む辞書）
        """
        if not MLX_WHISPER_AVAILABLE:
            logger.error("mlx_whisper is not installed. Cannot transcribe audio.")
            logger.error("To enable transcription, run: uv sync --extra whisper")
            return None

        try:
            logger.info(f"Transcribing audio from {audio_file}...")
            result = mlx_whisper.transcribe(
                audio_file, path_or_hf_repo=self.whisper_model
            )

            if result and "text" in result:
                logger.info(
                    f"Transcription completed: {len(result['text'])} characters"
                )
                return result
            else:
                logger.error("Transcription returned no text")
                return None

        except Exception as e:
            logger.error(f"Error transcribing audio: {e}")
            return None

    def process_video(self, url: str) -> Optional[Dict[str, str]]:
        """
        YouTube動画をダウンロードして文字起こし

        Args:
            url: YouTube動画のURL

        Returns:
            動画情報と文字起こしテキストを含む辞書
        """
        # 動画情報を取得
        video_info = self.get_video_info(url)
        if not video_info:
            return None

        # 音声をダウンロード
        audio_file = self.download_audio(url)
        if not audio_file:
            return None

        # 文字起こし
        transcription = self.transcribe_audio(audio_file)
        if not transcription:
            return None

        # 結果をまとめる
        result = {
            "url": url,
            "title": video_info.get("title", "Unknown"),
            "author": video_info.get("uploader", "Unknown"),
            "duration": video_info.get("duration", 0),
            "transcript": transcription.get("text", ""),
            "audio_file": audio_file,
        }

        # 一時ファイルを削除（オプション）
        try:
            os.remove(audio_file)
            logger.debug(f"Removed temporary file: {audio_file}")
        except Exception as e:
            logger.warning(f"Could not remove temporary file {audio_file}: {e}")

        return result

    def get_video_info(self, url: str) -> Optional[Dict[str, Any]]:
        """
        YouTube動画の情報を取得

        Args:
            url: YouTube動画のURL

        Returns:
            動画情報の辞書
        """
        with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True}) as ydl:
            try:
                info = ydl.extract_info(url, download=False)
                return {
                    "id": info.get("id"),
                    "title": info.get("title"),
                    "uploader": info.get("uploader"),
                    "duration": info.get("duration"),
                    "description": info.get("description"),
                    "upload_date": info.get("upload_date"),
                    "view_count": info.get("view_count"),
                    "like_count": info.get("like_count"),
                }
            except Exception as e:
                logger.error(f"Error getting video info for {url}: {e}")
                return None
