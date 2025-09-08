# Docker環境でのGmail認証ガイド

## 概要
MinitoolsのMedium Daily DigestとGoogle Alertsコレクターは、Gmail APIを使用してメールを取得します。
Docker環境では、OAuth 2.0認証フローがブラウザアクセスを必要とするため、特別な手順が必要です。

## 認証方法

### 方法1: ホストマシンでの事前認証（推奨）

最も簡単で確実な方法です。

1. **ホストマシンにminitoolsをインストール**
   ```bash
   # プロジェクトディレクトリで
   pip install -e .
   # または
   uv sync
   ```

2. **ホストマシンで一度ツールを実行**
   ```bash
   # Google Alertsの場合
   minitools-google-alerts --hours 1
   
   # Medium Daily Digestの場合
   minitools-medium --test
   ```

3. **ブラウザでOAuth認証を完了**
   - 自動的にブラウザが開きます
   - Googleアカウントでログイン
   - 権限を許可

4. **生成されたtoken.pickleをDockerで使用**
   - 認証が成功すると、プロジェクトディレクトリに`token.pickle`が生成されます
   - このファイルは自動的にDockerコンテナにマウントされます
   - 以降、Docker環境でも認証なしで実行可能になります

### 方法2: 新規にOAuth認証を設定

Google Cloud Consoleから認証情報を取得する方法です。

1. **Google Cloud Consoleでプロジェクトを作成**
   - https://console.cloud.google.com にアクセス
   - 新しいプロジェクトを作成

2. **Gmail APIを有効化**
   - APIとサービス → ライブラリ
   - Gmail APIを検索して有効化

3. **OAuth 2.0認証情報を作成**
   - APIとサービス → 認証情報
   - 「認証情報を作成」→「OAuth クライアント ID」
   - アプリケーションの種類：デスクトップアプリ
   - 名前を設定して作成

4. **credentials.jsonをダウンロード**
   - 作成した認証情報の「ダウンロード」ボタンをクリック
   - ダウンロードしたファイルを`credentials.json`にリネーム
   - プロジェクトディレクトリに配置

5. **ホストマシンで初回認証を実行**
   - 方法1の手順2-4を実行

### 方法3: サービスアカウント認証（ヘッドレス環境向け）

完全自動化が必要な場合の方法です。

1. **サービスアカウントを作成**
   - Google Cloud Console → IAMと管理 → サービスアカウント
   - 新しいサービスアカウントを作成

2. **キーを生成**
   - サービスアカウント → キー → キーを追加
   - JSON形式でダウンロード

3. **Gmail APIへのアクセスを設定**
   - Google Workspace管理コンソールでドメイン全体の委任を設定
   - または、個人Gmailの場合は共有設定を使用

**注意**: この方法は実装にコード変更が必要です。

## トラブルシューティング

### token.pickleが期限切れの場合
```bash
# token.pickleを削除して再認証
rm token.pickle
# ホストマシンで再度実行
minitools-google-alerts --hours 1
```

### 権限エラーが発生する場合
```bash
# ファイルの権限を確認
ls -la credentials.json token.pickle
# 必要に応じて権限を修正
chmod 644 credentials.json token.pickle
```

### Docker環境でブラウザが開かない場合
Docker環境では直接ブラウザを開けないため、必ずホストマシンで初回認証を行ってください。

## 環境変数の設定

`.env`ファイルに以下を設定してください：

```bash
# Notion API設定（必須）
NOTION_API_KEY=your_notion_api_key_here
NOTION_GOOGLE_ALERTS_DATABASE_ID=your_database_id_here
NOTION_MEDIUM_DATABASE_ID=your_database_id_here

# Slack Webhook設定（オプション）
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL
SLACK_GOOGLE_ALERTS_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/ALERTS/WEBHOOK
SLACK_MEDIUM_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/MEDIUM/WEBHOOK
```

## Docker環境のメモリ設定

Minitools では大型言語モデル（gemma3:27b）を使用するため、十分なメモリが必要です。

### macOS Docker Desktop の設定

1. **Docker Desktop を開く**
2. **設定画面にアクセス**: ⚙️ → Settings → Resources → Memory
3. **メモリ制限を増加**: デフォルト8GBから32GB以上に変更
4. **Apply & Restart**: 設定を適用してDockerを再起動

### メモリ要件
- **gemma3:27b モデル**: 20-32GB RAM推奨
- **docker-compose.yml設定**: 32GB制限に更新済み
- **ホストマシン**: 32GB以上のRAM推奨

### 確認方法
```bash
# Dockerのメモリ制限確認
docker system info | grep "Total Memory"

# システム全体のメモリ確認（macOS）
system_profiler SPHardwareDataType | grep "Memory:"
```

### トラブルシューティング
- メモリ不足エラーが発生する場合は、Docker Desktop のメモリ設定を確認
- ホストマシンに十分なRAMがあることを確認
- 必要に応じて他のDockerコンテナを停止してメモリを確保

## セキュリティに関する注意

- `credentials.json`と`token.pickle`には機密情報が含まれます
- これらのファイルをGitにコミットしないでください（`.gitignore`に追加済み）
- 定期的にトークンを更新することを推奨します
- 不要になった認証情報は Google Cloud Console から削除してください