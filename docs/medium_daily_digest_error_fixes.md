# Medium Daily Digest スクリプトのエラー修正ドキュメント

## 概要
`medium_daily_digest_to_notion_and_slack.py` スクリプトで発生していたエラーの調査と修正内容を記録します。

## 発生していたエラー

### 1. KeyboardInterrupt時の不適切な終了
```
^C^Cobject address  : 0x10ec42620
object refcount : 2
object type     : 0x103014238
object type name: KeyboardInterrupt
object repr     : KeyboardInterrupt()
lost sys.stderr
^CException ignored in: <module 'threading' from '/Users/tak/.local/share/uv/python/cpython-3.11.11-macos-aarch64-none/lib/python3.11/threading.py'>
```

**原因**: 非同期処理（asyncio）とThreadPoolExecutorの組み合わせで、Ctrl+C時に適切にクリーンアップされていない。

### 2. DNS解決エラー
```
socket.gaierror: [Errno 8] nodename nor servname provided, or not known
httplib2.error.ServerNotFoundError: Unable to find the server at gmail.googleapis.com
```

**原因**: 
- ネットワーク接続の問題
- DNS設定の問題
- Gmail APIの同期的な呼び出しがエラーハンドリングされていない

## 実施した修正

### 1. シグナルハンドラーの実装

```python
import signal

# グローバル変数でタスクを管理
_running_tasks = set()

def signal_handler(signum, frame):
    """シグナルハンドラー（Ctrl+C対応）"""
    logger.info("\n処理を中断しています...")
    # 実行中のタスクをキャンセル
    for task in _running_tasks:
        task.cancel()
    # イベントループを停止
    loop = asyncio.get_event_loop()
    loop.stop()
```

### 2. Gmail API呼び出しの非同期化

#### 修正前
```python
def get_medium_digest_emails(self, date: Optional[datetime] = None) -> List[Dict]:
    response = self.gmail_service.users().threads().list(
        userId='me',
        q=query,
        maxResults=1
    ).execute()
```

#### 修正後
```python
async def get_medium_digest_emails_async(self, date: Optional[datetime] = None) -> List[Dict]:
    loop = asyncio.get_event_loop()
    
    try:
        response = await loop.run_in_executor(
            None,
            lambda: self.gmail_service.users().threads().list(
                userId='me',
                q=query,
                maxResults=1
            ).execute()
        )
    except socket.gaierror as e:
        logger.error(f"DNS解決エラー: {e}")
        logger.error("ネットワーク接続を確認してください。")
        raise
```

### 3. エラーハンドリングの強化

```python
try:
    async with MediumDigestProcessorAsync() as processor:
        await processor.process_daily_digest_async(target_date, save_notion=save_notion, send_slack=send_slack)
except asyncio.CancelledError:
    logger.info("処理がキャンセルされました")
    raise
except socket.gaierror as e:
    logger.error(f"ネットワーク接続エラー: {e}")
    logger.error("ネットワーク接続を確認して、再度実行してください。")
    logger.error("DNS設定に問題がある可能性があります。")
    raise
except Exception as e:
    logger.error(f"エラーが発生しました: {e}")
    logger.error(f"エラーの詳細: {type(e).__name__}")
    import traceback
    logger.error(f"スタックトレース: {traceback.format_exc()}")
    raise
```

### 4. タスク管理の改善

```python
# タスクを追跡
for task in tasks:
    _running_tasks.add(task)

try:
    batch_results = await asyncio.gather(*tasks, return_exceptions=True)
finally:
    # 完了したタスクを削除
    for task in tasks:
        _running_tasks.discard(task)
```

### 5. HTTPセッションのタイムアウト設定

```python
timeout = aiohttp.ClientTimeout(
    total=60,        # 全体のタイムアウト
    connect=30,      # 接続タイムアウト
    sock_connect=30, # ソケット接続タイムアウト
    sock_read=30     # ソケット読み取りタイムアウト
)
self.http_session = aiohttp.ClientSession(connector=connector, timeout=timeout)
```

### 6. メイン関数のエラーハンドリング

```python
def main():
    """同期的なエントリーポイント"""
    # シグナルハンドラーを設定
    signal.signal(signal.SIGINT, signal_handler)
    
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        logger.info("\n処理が中断されました")
    except Exception as e:
        logger.error(f"予期しないエラー: {e}")
        raise
```

## 修正の効果

1. **Ctrl+Cでの適切な終了**: シグナルハンドラーにより、実行中のタスクが適切にキャンセルされ、クリーンに終了
2. **詳細なエラー情報**: DNS解決エラーやネットワークエラーの詳細が表示され、原因特定が容易に
3. **非同期処理の改善**: Gmail APIの呼び出しが非同期化され、全体的なパフォーマンスが向上
4. **タイムアウト設定**: 各種タイムアウトの設定により、ネットワーク問題時のハングを防止

## トラブルシューティング

### DNS解決エラーが継続する場合

1. **ネットワーク接続を確認**
   ```bash
   ping gmail.googleapis.com
   nslookup gmail.googleapis.com
   ```

2. **DNS設定を確認**
   ```bash
   cat /etc/resolv.conf
   ```

3. **プロキシ設定を確認**
   - 企業ネットワークの場合、プロキシ設定が必要な可能性

4. **一時的な回避策**
   - DNS設定を Google DNS (8.8.8.8) に変更
   - VPNを使用している場合は一時的に切断

### 非同期処理のデバッグ

デバッグモードを有効にする場合：
```python
import logging
logging.basicConfig(level=logging.DEBUG)
logging.getLogger("asyncio").setLevel(logging.DEBUG)
```

## まとめ

これらの修正により、スクリプトの安定性が大幅に向上しました。特に：
- 非同期処理の適切な管理
- エラー時の詳細な情報提供
- ネットワーク問題への耐性向上

が実現されています。