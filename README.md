# Minitools

コンテンツ収集・処理・配信を自動化するPythonパッケージです。ArXiv論文、Medium記事、Google Alerts、YouTube動画などから情報を収集し、日本語に翻訳・要約してNotionやSlackに配信します。

## 特徴

- 📚 **複数のソースに対応**: ArXiv、Medium Daily Digest、Google Alerts、YouTube
- 🌐 **日本語対応**: Ollamaを使用した高品質な翻訳・要約
- ⚡ **高速パッケージ管理**: uvによる10-100倍高速な依存関係管理
- 🚀 **高速並列処理**: 非同期処理により3-5倍の高速化
- 📝 **Notion連携**: 自動的にデータベースに保存
- 💬 **Slack通知**: 処理結果をSlackに送信
- 🎨 **カラフルなログ**: ログレベルに応じた色分け表示

## プロジェクト構造

```
minitools/
├── minitools/              # メインパッケージ
│   ├── collectors/         # データ収集モジュール
│   │   ├── arxiv.py       # ArXiv論文収集
│   │   ├── medium.py      # Medium Daily Digest収集
│   │   ├── google_alerts.py  # Google Alerts収集
│   │   └── youtube.py     # YouTube動画処理
│   ├── processors/        # データ処理モジュール
│   │   ├── translator.py  # 翻訳処理
│   │   └── summarizer.py  # 要約処理
│   ├── publishers/        # 出力先モジュール
│   │   ├── notion.py      # Notion連携
│   │   └── slack.py       # Slack連携
│   └── utils/             # ユーティリティ
│       └── logger.py      # カラー対応ロギング
├── scripts/               # 実行可能スクリプト
├── docs/                  # ドキュメント
└── outputs/               # 出力ファイル
```

## インストール

### 方法1: Docker を使用（推奨: Windows/Linux/Mac対応）

Dockerを使用することで、すべてのプラットフォームで統一された環境で実行できます。

> **📍 GPU対応について**: プラットフォームによってGPU設定が異なります。詳細は[GPU_SETUP.md](GPU_SETUP.md)を参照してください。

#### 前提条件
- Docker Desktop のインストール
  - [Windows](https://docs.docker.com/desktop/install/windows-install/)
  - [Mac](https://docs.docker.com/desktop/install/mac-install/)
  - [Linux](https://docs.docker.com/desktop/install/linux-install/)

#### クイックセットアップ（推奨）

プラットフォーム別の自動セットアップスクリプトを用意しています：

**macOS (Apple Silicon)**
```bash
# GPU（Metal/MPS）を使用するハイブリッド構成
chmod +x setup-mac.sh
./setup-mac.sh
```

**Windows (NVIDIA GPU)**
```powershell
# PowerShellを管理者として実行
Set-ExecutionPolicy Bypass -Scope Process -Force
.\setup-windows.ps1
```

**または手動セットアップ**
```bash
# リポジトリのクローン
git clone https://github.com/yourusername/minitools.git
cd minitools

# 環境変数の設定
cp .env.docker.example .env
# .env ファイルを編集してAPIキーを設定

# Gmail認証ファイルをコピー（Medium/Google Alerts使用時）
# credentials.json と token.pickle を配置

# プラットフォーム別のビルド
make setup  # 自動的にOSを検出して適切な設定を使用
```

#### 使用方法

**Makefileを使った実行（推奨）:**

```bash
# ArXiv論文の検索・翻訳
make arxiv
make -- arxiv --keywords "LLM" "RAG" --days 7
make -- arxiv --date 2025-09-04 --max-results 100

# Medium Daily Digestの処理
make medium
make -- medium --date 2024-01-15 --notion

# Google Alertsの処理
make google
make -- google --hours 24

# YouTube動画の要約
make -- youtube --url https://youtube.com/watch?v=...

# テストモード（1記事のみ処理）
make arxiv-test
make medium-test

# 注意: ダッシュで始まるオプションを使う場合は -- (ダブルダッシュ) を使用

# その他の便利なコマンド
make build        # Dockerイメージのビルド
make shell        # インタラクティブシェル
make jupyter      # Jupyter Notebook（開発用）
make help         # 利用可能なコマンドの表示
```

**従来のdocker-composeコマンド:**

```bash
# ArXiv論文の検索・翻訳
docker-compose run minitools minitools-arxiv --keywords "LLM" "RAG"

# Medium Daily Digestの処理
docker-compose run minitools minitools-medium --date 2024-01-15

# Google Alertsの処理
docker-compose run minitools minitools-google-alerts --hours 12

# YouTube動画の要約（whisper機能付きビルドが必要）
BUILD_TARGET=development docker-compose build
docker-compose run minitools minitools-youtube --url "https://youtube.com/watch?v=..."

# インタラクティブシェル
docker-compose run minitools bash

# Jupyter Notebook（開発用）
docker-compose --profile development up jupyter
# http://localhost:8888 でアクセス
```

### 方法2: ローカルインストール

このプロジェクトは[uv](https://github.com/astral-sh/uv)を使用してPython環境と依存関係を管理しています。uvはRustで実装された高速なPythonパッケージマネージャーです。

**uvのインストール:**
```bash
# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# または Homebrew (macOS)
brew install uv

# Windows
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

### 1. リポジトリのクローン

```bash
git clone https://github.com/yourusername/minitools.git
cd minitools
```

### 2. 依存関係のインストール

```bash
# 基本機能のインストール（ArXiv、Medium、Google Alerts）
uv sync

# YouTube要約機能も含める場合
uv sync --extra whisper

# 仮想環境を有効化（必要に応じて）
source .venv/bin/activate  # macOS/Linux
# または
.venv\Scripts\activate  # Windows
```

**注意**: Apple Silicon Macユーザーへ
- YouTube要約機能（mlx-whisper）はオプションです
- scipyのインストールでエラーが出る場合は、基本機能のみインストールしてください

従来のpipを使用する場合:
```bash
# pipでもインストール可能（uvを使いたくない場合）
pip install -e .
# YouTube要約機能を含める場合
pip install -e ".[whisper]"
```

### 3. 設定ファイルの準備

#### 環境変数の設定（セキュリティ関連）

`.env`ファイルを作成し、APIキーなどのセキュリティ関連の環境変数を設定：

```bash
# Notion API
NOTION_API_KEY="your_notion_api_key"
NOTION_DB_ID="your_arxiv_database_id"
NOTION_DB_ID_DAILY_DIGEST="your_medium_database_id"
NOTION_DB_ID_GOOGLE_ALERTS="your_google_alerts_database_id"

# Slack Webhooks（オプション）
SLACK_WEBHOOK_URL="your_arxiv_slack_webhook"
SLACK_WEBHOOK_URL_MEDIUM_DAILY_DIGEST="your_medium_slack_webhook"
SLACK_WEBHOOK_URL_GOOGLE_ALERTS="your_google_alerts_slack_webhook"

# Gmail API（Medium/Google Alerts用）
GMAIL_CREDENTIALS_PATH="credentials.json"
```

#### アプリケーション設定（モデル、パラメータ等）

`settings.yaml.example`を`settings.yaml`にコピーして、必要に応じて設定を変更：

```bash
cp settings.yaml.example settings.yaml
```

主な設定項目：
- **models**: Ollamaモデルの設定（翻訳・要約用）
- **processing**: 並列処理やリトライの設定
- **defaults**: 各ツールのデフォルト値
- **logging**: ログレベルや出力先の設定

詳細は`settings.yaml.example`のコメントを参照してください。

### 4. 必要なセットアップ

- **Ollama**: ローカルLLMの実行環境
  ```bash
  # Ollamaのインストールと起動
  brew install ollama
  ollama serve
  ollama pull gemma2  # Medium/YouTubeの要約用
  ollama pull gemma3:27b  # ArXiv/Google Alertsの翻訳・要約用
  ```

- **Gmail API**: Google Cloud Platformで有効化し、`credentials.json`を取得

- **FFmpeg**: YouTube処理用（macOS）
  ```bash
  brew install ffmpeg
  ```

### 5. uvを使った開発

```bash
# パッケージの追加
uv add package-name

# 開発用パッケージの追加
uv add --dev pytest black ruff

# 依存関係の更新
uv sync

# スクリプトの実行（仮想環境を自動的に使用）
uv run minitools-arxiv --keywords "machine learning"

# Pythonインタープリターの実行
uv run python

# 依存関係の確認
uv pip list
```

## 使い方

### コマンドラインツール

インストール後、以下のコマンドが利用可能になります。
仮想環境を有効化している場合は直接実行、uvを使う場合は`uv run`を付けて実行：

#### ArXiv論文検索
```bash
# 基本的な使い方（仮想環境有効化済み）
minitools-arxiv --keywords "LLM" "RAG" --days 7

# uvを使った実行（仮想環境の有効化不要）
uv run minitools-arxiv --keywords "LLM" "(RAG OR FINETUNING OR AGENT)" --days 30 --max-results 100

# 特定の日付を基準に検索
uv run minitools-arxiv --date 2024-01-15 --days 7  # 1/9〜1/15の論文を検索

# 月曜日実行：自動的に土日分もカバー（3日検索）
uv run minitools-arxiv --keywords "LLM"

# 月曜日でも手動指定は優先
uv run minitools-arxiv --keywords "LLM" --days 5

# Notionのみに保存
uv run minitools-arxiv --notion

# Slackのみに送信
uv run minitools-arxiv --slack
```

#### Medium Daily Digest
```bash
# 今日のダイジェストを処理
minitools-medium
# または
uv run minitools-medium

# 特定の日付を処理
uv run minitools-medium --date 2024-01-15

# Notionのみに保存
uv run minitools-medium --notion
```

#### Google Alerts
```bash
# 過去6時間のアラートを処理（デフォルト）
minitools-google-alerts
# または
uv run minitools-google-alerts

# 過去12時間のアラートを処理
uv run minitools-google-alerts --hours 12

# 特定の日付のアラートを処理
uv run minitools-google-alerts --date 2024-01-15
```

#### YouTube要約
```bash
# YouTube動画を要約（whisperオプションのインストールが必要）
minitools-youtube --url "https://www.youtube.com/watch?v=..."
# または
uv run minitools-youtube --url "https://www.youtube.com/watch?v=..."

# 出力ディレクトリとモデルを指定
uv run minitools-youtube --url "URL" --output_dir outputs --model_path mlx-community/whisper-large-v3-turbo
```

### Pythonモジュールとして使用

```python
import asyncio
from minitools.collectors import ArxivCollector
from minitools.processors import Translator
from minitools.publishers import NotionPublisher

async def main():
    # ArXiv論文を収集
    collector = ArxivCollector()
    papers = collector.search(
        queries=["machine learning"],
        start_date="20240101",
        end_date="20240131"
    )
    
    # 翻訳処理
    translator = Translator()
    for paper in papers:
        result = await translator.translate_with_summary(
            title=paper['title'],
            content=paper['abstract']
        )
        paper.update(result)
    
    # Notionに保存
    publisher = NotionPublisher()
    await publisher.batch_save_articles(
        database_id="your_database_id",
        articles=papers
    )

asyncio.run(main())
```

### 既存スクリプトとの互換性

従来のスクリプトも引き続き使用可能です：

```bash
# 従来の方法（後方互換性のため維持）
python scripts/arxiv.py --keywords "LLM" --days 7
python scripts/medium.py --date 2024-01-15
python scripts/google_alerts.py --hours 12
python scripts/youtube.py --url "https://www.youtube.com/watch?v=..."

# uvを使った実行
uv run python scripts/arxiv.py --keywords "LLM" --date 2024-01-15
uv run python scripts/medium.py --date 2024-01-15
uv run python scripts/google_alerts.py --date 2024-01-15
uv run python scripts/youtube.py --url "URL"
```

## 各ツールの詳細

### ArXiv論文要約ツール

arXivから指定キーワードで論文を検索し、要約を日本語に翻訳してNotionに保存、Slackに通知します。

**特徴**:
- 並列処理により50論文を約60秒で処理（4倍高速化）
- 最大10論文を同時処理
- 適切なレート制限でAPIを保護

**オプション**:
- `--keywords`: 検索キーワード（複数指定可、デフォルト: "LLM" "(RAG OR FINETUNING OR AGENT)"）
- `--days`: 何日前から検索するか（デフォルト: 1、月曜日は自動的に3日に拡張）
- `--date`: 基準日（YYYY-MM-DD形式、デフォルト: 昨日）
- `--max-results`: 最大検索結果数（デフォルト: 50）
- `--notion`: Notionへの保存のみ実行
- `--slack`: Slackへの送信のみ実行

**月曜日自動検索機能**:
- 月曜日実行時は自動的に過去3日間を検索（土日提出分をカバー）
- 手動で`--days`指定時はユーザー指定を優先
- 火〜金曜日は従来通り1日検索で効率性を保持

詳細: [docs/arxiv_async_usage.md](docs/arxiv_async_usage.md)

### Medium Daily Digest

Gmail経由で受信したMedium Daily Digestメールから記事を抽出し、日本語要約を付けてNotionに保存、Slackに通知します。

**特徴**:
- 10記事を約12秒で処理（4倍高速化）
- Gmail API連携で自動取得
- 重複チェック機能

**オプション**:
- `--date`: 処理する日付（YYYY-MM-DD形式）
- `--notion`: Notion保存のみ
- `--slack`: Slack送信のみ

詳細: [docs/medium_daily_digest_async_usage.md](docs/medium_daily_digest_async_usage.md)

### Google Alerts

Google Alertsメールから各アラートを抽出し、日本語要約を付けてNotionに保存、Slackに通知します。

**特徴**:
- デフォルトで過去6時間のメールを処理
- 並列処理で高速化
- 定期実行に最適

**オプション**:
- `--hours`: 過去何時間分を処理するか
- `--date`: 特定日付の全メールを処理
- `--notion`: Notion保存のみ
- `--slack`: Slack送信のみ

**定期実行の設定例（cron）**:
```bash
# 6時間ごとに実行（uvを使用）
0 */6 * * * cd /path/to/minitools && /path/to/uv run minitools-google-alerts

# または仮想環境を直接指定
0 */6 * * * cd /path/to/minitools && .venv/bin/minitools-google-alerts
```

### YouTube要約ツール

YouTube動画の音声を文字起こしし、要約を日本語で出力します。

**特徴**:
- MLX Whisperによる高速文字起こし
- Ollamaによる要約と翻訳
- Apple Silicon Mac最適化

**必要な環境**:
- Apple Silicon搭載Mac（MLX使用）
- FFmpeg
- 十分なストレージ（一時ファイル用）
- `uv sync --extra whisper`でインストール

**オプション**:
- `--url`, `-u`: YouTube動画のURL（必須）
- `--output_dir`, `-o`: 出力ディレクトリ（デフォルト: outputs）
- `--model_path`, `-m`: Whisperモデル（デフォルト: mlx-community/whisper-large-v3-turbo）
- `--no-save`: ファイル保存をスキップ

## Notionデータベースの設定

各ツール用のNotionデータベースには以下のプロパティが必要です：

### ArXiv / Medium / Google Alerts共通
- `Title` (Title): 記事タイトル
- `Japanese Title` (Rich Text): 日本語タイトル
- `URL` (URL): 元記事のURL
- `Author` (Rich Text): 著者名
- `Summary` (Rich Text): 日本語要約
- `Date` (Date): 処理日付

### Google Alerts追加
- `Source` (Rich Text): ソース情報

## Docker トラブルシューティング

### Ollama接続エラー
```bash
# Ollamaサービスの状態確認
docker-compose ps ollama

# Ollamaログの確認
docker-compose logs ollama

# 接続テスト
docker-compose run minitools test
```

### メモリ不足エラー
```yaml
# docker-compose.yml でメモリ制限を調整
deploy:
  resources:
    limits:
      memory: 32G  # 環境に応じて調整
```

### Gmail認証エラー
```bash
# ホストマシンで先に認証
uv run minitools-medium --test

# 生成された token.pickle をコンテナで使用
docker-compose run minitools minitools-medium
```

### Windows固有の問題
- WSL2を有効化してDocker Desktopを使用推奨
- ファイルパス区切り文字の違いはDockerが自動処理

## トラブルシューティング

### Gmail API認証エラー
1. Google Cloud PlatformでGmail APIが有効になっているか確認
2. `credentials.json`が正しい場所にあるか確認
3. `token.pickle`を削除して再認証

### Ollama接続エラー
```bash
# Ollamaが起動しているか確認
ollama list

# 起動していない場合
ollama serve
```

### Notion保存エラー
- APIキーが正しいか確認
- データベースIDが正しいか確認
- 必要なプロパティが設定されているか確認

## 開発

### 開発環境のセットアップ
```bash
# 開発用依存関係のインストール
uv add --dev pytest black ruff mypy

# コードフォーマット
uv run black minitools/
uv run ruff check minitools/

# 型チェック
uv run mypy minitools/
```

### テストの実行
```bash
# テストの実行
uv run pytest tests/

# カバレッジ付きテスト
uv run pytest tests/ --cov=minitools
```

### ログの確認
```bash
# ログファイルの場所
tail -f outputs/logs/arxiv.log
tail -f outputs/logs/medium_daily_digest.log
tail -f outputs/logs/google_alerts.log
tail -f outputs/logs/youtube.log
```

### カスタムモジュールの作成
```python
from minitools.collectors import BaseCollector
from minitools.utils import setup_logger

class MyCollector(BaseCollector):
    def __init__(self):
        self.logger = setup_logger(__name__)
    
    def collect(self):
        # カスタム収集ロジック
        pass
```

### uvの便利なコマンド

```bash
# 依存関係のツリー表示
uv pip tree

# 古い依存関係の確認
uv pip list --outdated

# 仮想環境の場所を確認
uv venv --python 3.11

# キャッシュのクリア（scipyエラー時などに有効）
uv cache clean
rm -rf /Users/$USER/.cache/uv  # 完全クリア

# プロジェクトの依存関係をロック
uv lock

# オプション機能の確認
uv sync --extra whisper  # YouTube要約機能
```

## ライセンス

MIT License