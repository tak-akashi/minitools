# リポジトリ構造定義書

このドキュメントは、minitoolsプロジェクトのディレクトリ構造とモジュールの役割を説明します。

## ディレクトリ構造

```
minitools/
├── minitools/                      # コアパッケージ
│   ├── __init__.py                 # パッケージエクスポート
│   ├── collectors/                 # データ収集レイヤー
│   │   ├── __init__.py
│   │   ├── arxiv.py               # ArXiv論文検索
│   │   ├── medium.py              # Medium Daily Digest収集
│   │   ├── google_alerts.py       # Google Alerts収集
│   │   └── youtube.py             # YouTube文字起こし
│   ├── llm/                        # LLM抽象化レイヤー
│   │   ├── __init__.py            # get_llm_client()ファクトリ
│   │   ├── base.py                # BaseLLMClient抽象基底クラス
│   │   ├── embeddings.py          # Embedding抽象化レイヤー
│   │   ├── ollama_client.py       # Ollama APIクライアント（ネイティブ）
│   │   ├── openai_client.py       # OpenAI APIクライアント（ネイティブ）
│   │   ├── langchain_ollama.py    # LangChain Ollamaクライアント
│   │   └── langchain_openai.py    # LangChain OpenAIクライアント
│   ├── readers/                    # 読み取りレイヤー
│   │   ├── __init__.py
│   │   └── notion.py              # Notionデータベース読み取り
│   ├── researchers/                # リサーチレイヤー
│   │   ├── __init__.py
│   │   └── trend.py               # Tavily APIでトレンド調査
│   ├── processors/                 # コンテンツ処理レイヤー
│   │   ├── __init__.py
│   │   ├── translator.py          # Ollama翻訳
│   │   ├── summarizer.py          # Ollama要約
│   │   ├── weekly_digest.py       # 週次ダイジェスト生成
│   │   ├── arxiv_weekly.py        # ArXiv週次ダイジェスト生成
│   │   └── duplicate_detector.py  # 類似記事検出
│   ├── publishers/                 # 出力レイヤー
│   │   ├── __init__.py
│   │   ├── notion.py              # Notionデータベース連携
│   │   └── slack.py               # Slack通知
│   └── utils/                      # ユーティリティ
│       ├── __init__.py
│       ├── config.py              # 設定管理（シングルトン）
│       └── logger.py              # カラーログ出力
│
├── scripts/                        # CLIエントリーポイント
│   ├── arxiv.py                   # arxiv コマンド
│   ├── medium.py                  # medium コマンド
│   ├── google_alerts.py           # google-alerts コマンド
│   ├── youtube.py                 # youtube コマンド
│   ├── weekly_digest.py           # weekly-digest コマンド
│   └── arxiv_weekly.py            # arxiv-weekly コマンド
│
├── docs/                           # ドキュメント
│   ├── generated/                 # 生成ドキュメント
│   └── ideas/                     # アイデア・ブレインストーム
│
├── outputs/                        # 実行時出力
│   ├── logs/                      # ログファイル
│   └── temp/                      # 一時ファイル
│
├── pyproject.toml                 # プロジェクト設定・依存関係
├── settings.yaml.example          # 設定ファイルテンプレート
├── .env.docker.example            # 環境変数テンプレート
├── Dockerfile                     # Dockerイメージ定義
├── docker-compose.yml             # Docker Compose設定
├── docker-compose.mac.yml         # macOS向けDocker設定
├── docker-compose.windows.yml     # Windows向けDocker設定
├── docker-entrypoint.sh           # Dockerエントリーポイント
├── Makefile                       # ビルド自動化
├── README.md                      # プロジェクト説明
├── CLAUDE.md                      # 開発ガイダンス
├── .python-version                # Pythonバージョン固定
├── uv.lock                        # 依存関係ロック
└── .gitignore                     # Git除外設定
```

## 各ディレクトリ/モジュールの役割

### minitools/ (コアパッケージ)

プロジェクトのメインライブラリ。4つのサブパッケージで構成されています。

#### collectors/ (データ収集)

外部ソースからコンテンツを収集するモジュール群。

| モジュール | 役割 | 外部サービス |
|-----------|------|------------|
| `arxiv.py` | ArXiv APIから論文を検索・取得 | ArXiv API, feedparser |
| `medium.py` | Gmail経由でMedium Daily Digestを取得 | Gmail API, Jina AI Reader |
| `google_alerts.py` | Gmail経由でGoogle Alertsを取得 | Gmail API |
| `youtube.py` | YouTube動画の音声ダウンロード・文字起こし | yt-dlp, MLX Whisper |

#### llm/ (LLM抽象化レイヤー)

Ollama/OpenAIを統一的に扱うための抽象化レイヤー。

| モジュール | 役割 | 備考 |
|-----------|------|------|
| `base.py` | BaseLLMClient抽象基底クラス | chat(), generate()の共通インターフェース |
| `embeddings.py` | Embedding抽象化レイヤー | BaseEmbeddingClient, get_embedding_client() |
| `ollama_client.py` | Ollamaクライアント実装（ネイティブ） | 同期APIをrun_in_executorで非同期化 |
| `openai_client.py` | OpenAIクライアント実装（ネイティブ） | AsyncOpenAIを使用 |
| `langchain_ollama.py` | LangChain Ollamaクライアント | LangChain経由でOllamaを使用（推奨） |
| `langchain_openai.py` | LangChain OpenAIクライアント | LangChain経由でOpenAIを使用（推奨） |
| `__init__.py` | get_llm_client()ファクトリ | LangChain優先、ネイティブにフォールバック |

#### readers/ (データ読み取り)

外部データベースからデータを読み取るモジュール群。

| モジュール | 役割 | 外部サービス |
|-----------|------|------------|
| `notion.py` | Notionデータベースからの記事取得 | Notion API |

#### researchers/ (リサーチ)

外部APIを使用してリサーチを行うモジュール群。

| モジュール | 役割 | 外部サービス |
|-----------|------|------------|
| `trend.py` | AI/機械学習分野のトレンド調査 | Tavily API |

#### processors/ (コンテンツ処理)

LLMを使用してコンテンツを処理するモジュール群。

| モジュール | 役割 | 使用モデル |
|-----------|------|----------|
| `translator.py` | テキストの日本語翻訳 | gemma3:27b (Ollama) |
| `summarizer.py` | テキストの要約・キーポイント抽出 | gemma3:27b (Ollama) |
| `weekly_digest.py` | 週次ダイジェスト生成 | LLM抽象化レイヤー経由 |
| `arxiv_weekly.py` | ArXiv週次ダイジェスト生成 | LLM抽象化レイヤー経由 |
| `duplicate_detector.py` | 類似記事検出・重複除去 | Embedding抽象化レイヤー経由 |

#### publishers/ (出力)

処理結果を外部サービスに出力するモジュール群。

| モジュール | 役割 | 外部サービス |
|-----------|------|------------|
| `notion.py` | Notionデータベースへの保存 | Notion API |
| `slack.py` | Slackチャンネルへの通知 | Slack Webhook |

#### utils/ (ユーティリティ)

共通機能を提供するモジュール群。

| モジュール | 役割 | パターン |
|-----------|------|---------|
| `config.py` | 設定ファイル管理 | シングルトン |
| `logger.py` | カラー対応ログ出力 | ColoredFormatter |

### scripts/ (CLIエントリーポイント)

各ツールのコマンドラインインターフェース。`pyproject.toml`で定義されたエントリーポイント。

| スクリプト | コマンド | 用途 |
|-----------|---------|-----|
| `arxiv.py` | `arxiv` | ArXiv論文の検索・翻訳・保存 |
| `medium.py` | `medium` | Medium記事の収集・翻訳・保存 |
| `google_alerts.py` | `google-alerts` | Google Alertsの収集・翻訳・保存 |
| `youtube.py` | `youtube` | YouTube動画の文字起こし・要約 |
| `weekly_digest.py` | `weekly-digest` | 週次ダイジェストの生成・Slack通知 |
| `arxiv_weekly.py` | `arxiv-weekly` | ArXiv週次ダイジェストの生成・Slack通知 |

## 新規コンポーネント追加手順

### 新しいCollectorの追加

1. `minitools/collectors/` に新しいモジュールを作成
2. クラスを実装（async context manager対応推奨）
3. `minitools/collectors/__init__.py` にエクスポート追加
4. 対応するCLIスクリプトを `scripts/` に作成
5. `pyproject.toml` にエントリーポイント追加

```python
# minitools/collectors/new_source.py
class NewSourceCollector:
    """新しいソースのCollector"""

    def __init__(self, config_param: str = None):
        self.http_session = None

    async def __aenter__(self):
        """非同期コンテキストマネージャーのエントリー"""
        self.http_session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """非同期コンテキストマネージャーのクリーンアップ"""
        if self.http_session:
            await self.http_session.close()

    async def collect(self) -> List[Dict]:
        """データを収集"""
        pass
```

### 新しいProcessorの追加

1. `minitools/processors/` に新しいモジュールを作成
2. Ollamaクライアントを使用するクラスを実装
3. `minitools/processors/__init__.py` にエクスポート追加

```python
# minitools/processors/new_processor.py
import ollama

class NewProcessor:
    """新しい処理クラス"""

    def __init__(self, model: Optional[str] = None):
        self.model = model or "gemma3:27b"
        self.client = ollama.Client()

    async def process(self, text: str) -> str:
        """テキストを処理"""
        prompt = f"Process this text: {text}"
        response = self.client.chat(
            model=self.model,
            messages=[{"role": "user", "content": prompt}]
        )
        return response['message']['content']
```

### 新しいPublisherの追加

1. `minitools/publishers/` に新しいモジュールを作成
2. 非同期メソッドを持つクラスを実装
3. `minitools/publishers/__init__.py` にエクスポート追加

```python
# minitools/publishers/new_publisher.py
class NewPublisher:
    """新しい出力先のパブリッシャー"""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv('NEW_SERVICE_API_KEY')
        self.http_session = None

    async def __aenter__(self):
        self.http_session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.http_session:
            await self.http_session.close()

    async def publish(self, data: Dict[str, Any]) -> bool:
        """データを出力"""
        pass
```

## 設定追加ガイド

### .env (セキュリティ関連)

新しい外部サービスのAPIキーやWebhook URLを追加する場合:

```bash
# .env

# 既存の設定
NOTION_API_KEY=your_key
SLACK_WEBHOOK_URL=https://hooks.slack.com/...

# 新規追加
NEW_SERVICE_API_KEY=your_new_key
NEW_SERVICE_WEBHOOK_URL=https://example.com/webhook
```

### settings.yaml (アプリケーション設定)

新しいモデルやパラメータを追加する場合:

```yaml
# settings.yaml

# 既存の設定
models:
  translation: "gemma3:27b"
  summarization: "gemma3:27b"
  # 新規追加
  new_processor: "new-model:latest"

# 新しいツールのデフォルト設定
defaults:
  new_source:
    param1: "default_value"
    param2: 100
```

### config.py でのアクセス

```python
from minitools.utils.config import get_config, Config

config = get_config()

# 設定値の取得
model = config.get('models.new_processor', 'fallback-model')
param = config.get('defaults.new_source.param1', 'default')

# APIキーの取得
api_key = Config.get_api_key('new_service')  # NEW_SERVICE_API_KEY を検索
```

### pyproject.toml エントリーポイント追加

```toml
[project.scripts]
arxiv = "scripts.arxiv:main"
medium = "scripts.medium:main"
google-alerts = "scripts.google_alerts:main"
youtube = "scripts.youtube:main"
weekly-digest = "scripts.weekly_digest:main"
# 新規追加
new-source = "scripts.new_source:main"
```

## ファイル命名規則

| 種類 | 規則 | 例 |
|-----|------|---|
| モジュール | スネークケース | `google_alerts.py` |
| クラス | パスカルケース | `GoogleAlertsCollector` |
| 関数/メソッド | スネークケース | `get_alerts_emails` |
| 定数 | 大文字スネークケース | `SCOPES`, `USER_AGENTS` |
| 設定キー | ドット区切り小文字 | `models.translation` |
| 環境変数 | 大文字スネークケース | `NOTION_API_KEY` |
