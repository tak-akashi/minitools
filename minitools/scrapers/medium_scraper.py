"""
Medium article scraper using Playwright.

Two modes:
    1. CDP mode (recommended): Connects to user's real Chrome browser.
       Bypasses Cloudflare bot detection and uses existing Medium login.
    2. Standalone mode: Uses Playwright's built-in Chromium.
       May be blocked by Cloudflare.

CDP mode usage:
    # First run: Chrome opens automatically, log in to Medium
    uv run medium-translate --url "..." --cdp --dry-run

    # Subsequent runs: Chrome opens with saved cookies, no login needed
    uv run medium-translate --url "..." --cdp --dry-run --provider gemini
"""

import asyncio
import random
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional

from minitools.utils.logger import get_logger

logger = get_logger(__name__)

# CDP用Chromeプロファイルのデフォルトパス
DEFAULT_CHROME_PROFILE = Path.home() / ".minitools" / "chrome-profile"
CDP_PORT = 9222


def _find_chrome_path() -> Optional[str]:
    """システムのChromeブラウザのパスを検出する"""
    if sys.platform == "darwin":
        chrome_path = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
        if Path(chrome_path).exists():
            return chrome_path
    elif sys.platform == "linux":
        for name in ["google-chrome", "google-chrome-stable", "chromium-browser"]:
            path = shutil.which(name)
            if path:
                return path
    elif sys.platform == "win32":
        import winreg

        try:
            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe",
            )
            return winreg.QueryValue(key, None)
        except WindowsError:
            pass
    return None


class MediumScraper:
    """Playwrightを使用してMedium記事の全文HTMLを取得するクラス"""

    def __init__(
        self,
        headless: bool = True,
        cdp_mode: bool = False,
    ):
        """
        Args:
            headless: ヘッドレスモードで実行するか（CDPモードでは無視）
            cdp_mode: Trueの場合、実際のChromeにCDP接続する
        """
        self.headless = headless
        self.cdp_mode = cdp_mode
        self._playwright: Any = None
        self._browser: Any = None
        self._context: Any = None
        self._page: Any = None
        self._chrome_process: Any = None

    async def __aenter__(self) -> "MediumScraper":
        """ブラウザを起動/接続する"""
        try:
            from playwright.async_api import async_playwright

            self._playwright = await async_playwright().start()

            if self.cdp_mode:
                await self._connect_cdp()
            else:
                await self._launch_standalone()

            return self
        except ImportError:
            raise ImportError(
                "playwright is required. Install with: "
                "uv sync && playwright install chromium"
            )

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """ブラウザを切断/閉じる"""
        if self.cdp_mode:
            # CDP: ブラウザ自体は閉じない（セッション維持のため）
            if self._browser:
                await self._browser.close()  # 接続を切断するだけ
        else:
            if self._browser:
                await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        self._browser = None
        self._context = None
        self._page = None

    async def _connect_cdp(self) -> None:
        """実際のChromeにCDP経由で接続する"""
        # Chromeが起動しているか確認、起動していなければ起動する
        if not await self._is_chrome_running():
            await self._launch_chrome()

        # CDP接続
        logger.info(f"Connecting to Chrome via CDP (port {CDP_PORT})...")
        try:
            self._browser = await self._playwright.chromium.connect_over_cdp(
                f"http://localhost:{CDP_PORT}"
            )
        except Exception as e:
            raise RuntimeError(
                f"Failed to connect to Chrome via CDP: {e}\n"
                f"Ensure Chrome is running with --remote-debugging-port={CDP_PORT}"
            )

        # 既存のコンテキストを取得（Chromeの既存タブ/セッション）
        contexts = self._browser.contexts
        if contexts:
            self._context = contexts[0]
        else:
            self._context = await self._browser.new_context()

        # 新しいタブで作業する
        self._page = await self._context.new_page()
        logger.info("Connected to Chrome via CDP")

    async def _is_chrome_running(self) -> bool:
        """CDP対応のChromeが起動しているか確認"""
        import httpx

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"http://localhost:{CDP_PORT}/json/version",
                    timeout=2,
                )
                return resp.status_code == 200
        except Exception:
            return False

    async def _launch_chrome(self) -> None:
        """Chromeをデバッグポート付きで起動する"""
        chrome_path = _find_chrome_path()
        if not chrome_path:
            raise RuntimeError(
                "Chrome not found. Please install Google Chrome or "
                "start it manually with: "
                f"google-chrome --remote-debugging-port={CDP_PORT} "
                f"--user-data-dir={DEFAULT_CHROME_PROFILE}"
            )

        # プロファイルディレクトリ作成
        DEFAULT_CHROME_PROFILE.mkdir(parents=True, exist_ok=True)

        logger.info("Launching Chrome with debug port...")
        self._chrome_process = subprocess.Popen(
            [
                chrome_path,
                f"--remote-debugging-port={CDP_PORT}",
                f"--user-data-dir={DEFAULT_CHROME_PROFILE}",
                "--no-first-run",
                "--no-default-browser-check",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        # Chromeの起動を待機
        for _ in range(30):
            if await self._is_chrome_running():
                logger.info("Chrome started successfully")
                return
            await asyncio.sleep(0.5)

        raise RuntimeError("Chrome failed to start within 15 seconds")

    async def _launch_standalone(self) -> None:
        """Playwrightの内蔵Chromiumで起動する（Cloudflareにブロックされる可能性あり）"""
        self._browser = await self._playwright.chromium.launch(
            headless=self.headless,
        )
        self._context = await self._browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1920, "height": 1080},
        )
        self._page = await self._context.new_page()
        logger.warning(
            "Using standalone Chromium. "
            "May be blocked by Cloudflare. Use --cdp for reliable access."
        )

    async def scrape_article(self, url: str) -> str:
        """
        記事URLから全文HTMLを取得する

        Args:
            url: Medium記事のURL

        Returns:
            記事のHTML文字列（取得失敗時は空文字列）
        """
        if not self._page:
            raise RuntimeError("Browser not initialized. Use 'async with' context.")

        try:
            logger.info(f"Scraping article: {url}")

            await self._page.goto(url, wait_until="domcontentloaded", timeout=60000)
            await asyncio.sleep(random.uniform(2, 4))

            # Cloudflareチャレンジの検出
            if await self._is_cloudflare_challenge():
                logger.warning(
                    "Cloudflare challenge detected, waiting for resolution..."
                )
                for _ in range(24):
                    await asyncio.sleep(5)
                    if not await self._is_cloudflare_challenge():
                        logger.info("Cloudflare challenge resolved")
                        await asyncio.sleep(2)
                        break
                else:
                    logger.error("Cloudflare challenge not resolved within 2 minutes")
                    return ""

            # エラーページの検出（404等）
            if await self._is_error_page():
                logger.error(f"Error page detected for: {url}")
                return ""

            # 記事本文のHTMLを取得
            article_element = await self._page.query_selector("article")

            if article_element:
                html = await article_element.evaluate("el => el.outerHTML")
                logger.info(f"Article HTML extracted: {len(html)} chars")
                return html

            logger.error(f"No <article> tag found for: {url}")
            return ""

        except Exception as e:
            logger.error(f"Article scraping failed for {url}: {e}")
            return ""

    async def _is_cloudflare_challenge(self) -> bool:
        """現在のページがCloudflareチャレンジかどうかを判定"""
        try:
            title = await self._page.title()
            if "just a moment" in title.lower():
                return True
            cf_element = await self._page.query_selector("#cf-challenge-running")
            return cf_element is not None
        except Exception:
            return False

    async def _is_error_page(self) -> bool:
        """現在のページがエラーページ（404等）かどうかを判定"""
        try:
            # Medium固有の404ページ検出
            title = await self._page.title()
            error_titles = [
                "page not found",
                "404",
                "error",
                "out of the loop",  # Mediumの404ページタイトル
            ]
            title_lower = title.lower()
            if any(t in title_lower for t in error_titles):
                return True

            # HTTP status codeベースの検出（h1に"404"等がある場合）
            h1 = await self._page.query_selector("h1")
            if h1:
                h1_text = await h1.inner_text()
                if "404" in h1_text or "not found" in h1_text.lower():
                    return True

            return False
        except Exception:
            return False
