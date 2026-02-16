#!/usr/bin/env python3
"""
X (Twitter) フォロー中アカウント一覧を取得するスクリプト。

Usage:
    uv run x-followings --user YOUR_USERNAME
    uv run x-followings --user YOUR_USERNAME --limit 50
"""

import argparse
import asyncio
import sys

from minitools.collectors.x_trend import XTrendCollector
from minitools.utils.config import get_config
from minitools.utils.logger import setup_logger

logger = setup_logger(name="scripts.x_followings", log_file="x_followings.log")


async def fetch_followings(username: str, limit: int = 0) -> list[dict]:
    """
    指定ユーザーのフォロー中アカウント一覧を取得

    Args:
        username: Twitterユーザー名（@なし）
        limit: 取得上限（0=全件）

    Returns:
        フォロー中アカウントのリスト
    """
    all_followings: list[dict] = []
    cursor = ""

    async with XTrendCollector() as collector:
        while True:
            params = {"userName": username, "cursor": cursor}
            data = await collector._request_with_retry(
                f"{collector.BASE_URL}/twitter/user/followings",
                params=params,
            )

            if not data:
                logger.error("API request failed")
                break

            followings = data.get("followings", [])
            if not followings:
                break

            all_followings.extend(followings)
            logger.info(f"Fetched {len(all_followings)} followings so far...")

            if limit and len(all_followings) >= limit:
                all_followings = all_followings[:limit]
                break

            if not data.get("has_next_page"):
                break

            cursor = data.get("next_cursor", "")
            if not cursor:
                break

    return all_followings


def main():
    parser = argparse.ArgumentParser(
        description="X (Twitter) フォロー中アカウント一覧を取得",
    )
    parser.add_argument(
        "--user",
        required=True,
        help="Twitterユーザー名（@なし）",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="取得上限（デフォルト: 全件）",
    )
    parser.add_argument(
        "--format",
        choices=["list", "yaml"],
        default="list",
        help="出力フォーマット（デフォルト: list）",
    )

    args = parser.parse_args()

    get_config()  # .envファイルを読み込み
    logger.info(f"Fetching followings for @{args.user}")
    followings = asyncio.run(fetch_followings(args.user, args.limit))

    if not followings:
        print("フォロー中のアカウントが見つかりませんでした。")
        sys.exit(1)

    print(f"\n@{args.user} のフォロー中アカウント（{len(followings)}件）:\n")

    if args.format == "yaml":
        print("watch_accounts:")
        for f in followings:
            name = f.get("userName", "")
            display = f.get("name", "")
            print(f'  - "{name}"  # {display}')
    else:
        for i, f in enumerate(followings, 1):
            name = f.get("userName", "")
            display = f.get("name", "")
            followers = f.get("followers", 0)
            print(f"  {i:3d}. @{name} ({display}) - {followers:,} followers")


if __name__ == "__main__":
    main()
