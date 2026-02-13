# 変更履歴 (CHANGELOG)

このドキュメントは、minitoolsプロジェクトの変更履歴をまとめたものです。

## [Unreleased]

### Changed
- **週次ダイジェストスクリプトのリネーム**: `scripts/weekly_digest.py` → `scripts/google_alert_weekly_digest.py`
  - CLIコマンド: `weekly-digest` → `google-alert-weekly-digest`
  - 目的: Google Alerts専用であることを明確化

### Added
- **Medium Claps数の出力**: NotionデータベースとSlack通知にClaps（拍手数）を追加
  - Notion: `Claps` (Number型) プロパティとして保存、フィルタ・ソート可能
  - Slack: 著者名の下に👏アイコン付きでカンマ区切り表示（0の場合は非表示）
  - Article dataclass: `claps: int = 0` フィールド追加
- **全文翻訳済みチェックボックス**: 全文翻訳成功時にNotionページの`Translated` (Checkbox型) を自動チェック
  - `scripts/medium.py --translate` 経由の翻訳に対応
  - `scripts/medium_translate.py` 経由の翻訳に対応
  - NotionPublisher拡張: `update_page_properties()` メソッド追加
- **Mediumコマンドオプション拡張**: `--translate`（claps閾値以上の記事を全文翻訳）、`--cdp`（CDP接続でCloudflare回避）オプション追加
  - 設定項目: `defaults.medium.translate_clap_threshold`, `defaults.medium.translate_provider`, `defaults.medium.translate_model`

- **Medium全文翻訳機能**: Medium記事の全文をPlaywrightで取得し、LLMで日本語翻訳してNotionに追記する機能
  - 新規コンポーネント:
    - `minitools/scrapers/medium_scraper.py` - MediumScraper（CDP/スタンドアロン、Cloudflare回避）
    - `minitools/scrapers/markdown_converter.py` - MarkdownConverter（HTML→構造化Markdown変換）
    - `minitools/processors/full_text_translator.py` - FullTextTranslator（チャンク分割翻訳・構造維持）
    - `minitools/publishers/notion_block_builder.py` - NotionBlockBuilder（Markdown→Notionブロック変換）
    - `minitools/llm/langchain_gemini.py` - LangChainGeminiClient（Gemini APIプロバイダー）
    - `scripts/medium_translate.py` - CLIスクリプト
  - NotionPublisher拡張: `find_page_by_url()`, `append_blocks()` メソッド（100ブロックバッチ対応）
  - LLMファクトリ拡張: `get_llm_client(provider="gemini")` サポート
  - `medium` コマンドに `--translate`, `--cdp` オプション追加
  - 新規CLIコマンド: `medium-translate`
  - 新規環境変数: `GEMINI_API_KEY`
  - 設定項目: `defaults.medium.translate_clap_threshold`, `defaults.medium.translate_provider`, `defaults.medium.translate_model`

- **バッチスコアリング機能**: `WeeklyDigestProcessor` と `ArxivWeeklyProcessor` にバッチ処理を導入し、スコアリング処理を高速化
  - 20件を1回のLLM呼び出しでまとめてスコアリング（約8倍の速度向上）
  - デフォルトプロバイダーをOpenAIに変更（`defaults.weekly_digest.provider`, `defaults.arxiv_weekly.provider`）
  - バッチ処理失敗時は自動的に個別処理にフォールバック
  - 新規設定項目: `defaults.weekly_digest.batch_size`, `defaults.arxiv_weekly.batch_size`
  - 500件以上の記事を40分以上 → 数分で処理可能に

- **ArXiv週次ダイジェスト機能**: Notion DBから過去1週間分のArXiv論文を取得し、AIが重要度を判定して上位論文を選出。週のトレンド総括と各論文のハイライトをSlackに出力する
  - 新規コンポーネント:
    - `minitools/researchers/trend.py` - TrendResearcher（Tavily APIでトレンド調査）
    - `minitools/processors/arxiv_weekly.py` - ArxivWeeklyProcessor（重要度スコアリング・ハイライト生成）
    - `scripts/arxiv_weekly.py` - CLIスクリプト
  - NotionReader拡張: `get_arxiv_papers_by_date_range()` メソッド
  - SlackPublisher拡張: `format_arxiv_weekly()`, `send_arxiv_weekly()` メソッド
  - 新規CLIコマンド: `arxiv-weekly`
  - 新規環境変数: `TAVILY_API_KEY`, `NOTION_ARXIV_DATABASE_ID`, `SLACK_ARXIV_WEEKLY_WEBHOOK_URL`
  - 設定項目: `defaults.arxiv_weekly.days_back`, `defaults.arxiv_weekly.top_papers`

- **ドキュメント自動生成**: `docs/core/` に以下のドキュメントを追加
  - `architecture.md` - システムアーキテクチャ設計書
  - `repo-structure.md` - リポジトリ構造定義書
  - `api-reference.md` - APIリファレンス
  - `diagrams.md` - Mermaid図（シーケンス図、クラス図等）
  - `dev-guidelines.md` - 開発ガイドライン
  - `CHANGELOG.md` - 変更履歴

- **Google Alerts週次AIダイジェスト機能**: Google AlertsのNotion DBから過去1週間分の記事を取得し、AIが重要度を判定して上位20件を選出。週のトレンド総括と各記事の要約をSlackに出力する
  - 新規コンポーネント:
    - `minitools/llm/` - LLM抽象化レイヤー（Ollama/OpenAI切り替え、LangChain統合）
    - `minitools/llm/embeddings.py` - Embedding抽象化レイヤー（類似記事検出用）
    - `minitools/llm/langchain_ollama.py` - LangChain Ollamaクライアント
    - `minitools/llm/langchain_openai.py` - LangChain OpenAIクライアント
    - `minitools/readers/notion.py` - NotionReader（日付フィルタでデータ取得）
    - `minitools/processors/weekly_digest.py` - 週次ダイジェスト処理
    - `minitools/processors/duplicate_detector.py` - 類似記事検出・重複除去
    - `scripts/google_alert_weekly_digest.py` - CLIスクリプト
  - 新規CLIコマンド: `google-alert-weekly-digest`
  - 新規設定項目: `llm.provider`, `llm.ollama.default_model`, `llm.openai.default_model`
  - 新規環境変数: `NOTION_GOOGLE_ALERTS_DATABASE_ID`, `SLACK_WEEKLY_DIGEST_WEBHOOK_URL`

### Changed
- ruff による静的解析チェックを追加 (bf4f777)

### Removed
- **レガシードキュメントの削除**: 以下のドキュメントを削除し、`docs/core/` に統合
  - `docs/arxiv_async_usage.md` → `docs/core/architecture.md` に統合
  - `docs/docker-gmail-auth.md` → README.md に統合
  - `docs/gmail_alerts_parallel_processing.md` → `docs/core/architecture.md` に統合
  - `docs/medium_daily_digest_async_usage.md` → `docs/core/architecture.md` に統合
  - `docs/medium_daily_digest_error_fixes.md` → `docs/core/dev-guidelines.md` に統合
  - `GPU_SETUP.md` → 削除（未使用）

## [0.1.0] - 2024

### Added

#### 機能追加
- **Makefileの導入** (035e8aa)
  - Docker実行を簡略化する `make arxiv`, `make medium` 等のコマンド
  - `make build`, `make shell`, `make help` コマンド

- **Docker対応** (374a737, 6c833a7)
  - マルチステージビルドによるDockerイメージ
  - docker-compose.yml によるサービス定義
  - macOS向け、Windows向けの個別Compose設定
  - ollama-setup サービスによるモデル自動ダウンロード

- **並列処理機能** (6b429a8)
  - asyncio.Semaphore による並列数制限
  - バッチ処理によるパフォーマンス改善
  - 3-5倍の処理速度向上

- **ログ機能** (1bcf19f)
  - ColoredFormatter によるカラー出力
  - ファイルとコンソールへの二重出力
  - ログレベルに応じた色分け

- **タグ付け機能** (2911dc9)
  - Google Alertsのタグ自動付与
  - settings.yaml でのタグマッピング設定

- **Medium Daily Digest機能** (2027df0)
  - Gmail APIからのメール取得
  - メールHTML解析による記事抽出
  - Jina AI Readerによるコンテンツ取得

- **Slack通知機能** (3147620)
  - Webhook URLによる通知送信
  - 記事リストのフォーマット機能

- **YouTube要約機能** (01cfe20)
  - yt-dlp による音声ダウンロード
  - MLX Whisper による文字起こし
  - 要約と日本語翻訳

- **ArXiv論文検索機能** (aa51c1f)
  - ArXiv API連携
  - feedparser による結果解析
  - Notion保存機能

- **Notion保存機能** (c5c9634)
  - Notion API連携
  - 重複検出機能
  - バッチ保存機能

### Changed

#### 改善・変更
- **Medium記事取得ロジックの更新** (0091741, e692971)
  - bot検出回避のためのUser-Agentローテーション
  - 並列数の削減（5接続に制限）
  - ブラウザを模倣したヘッダー追加
  - リクエスト間のランダム遅延

- **コマンド名の簡略化** (a58e225)
  - `minitools-arxiv` → `arxiv`
  - `minitools-medium` → `medium`
  - `minitools-google-alerts` → `google-alerts`
  - `minitools-youtube` → `youtube`

- **パッケージマネージャー変更** (002e885)
  - Poetry から uv への移行
  - 高速な依存関係解決

- **モデル更新** (e5d293a, 1489ff1)
  - デフォルトモデルを `gemma3:27b` に変更
  - YouTube用に軽量モデル `gemma2` を設定

- **プロジェクト構造のリファクタリング** (5ffb4b0, f7beede, da0ccda)
  - 共通ロギング関数の外部化
  - ソースコードを `minitools/` パッケージに整理
  - Collectors, Processors, Publishers の分離

#### バグ修正
- 各種バグ修正 (820c578, b91aefc, b173cb0, 68d4d58, 1afb4fb, 0383d83, b4c8d82, 6ea8347)
  - Gmail API認証フローの修正
  - URL正規化の改善
  - エラーハンドリングの強化
  - 重複検出ロジックの修正

### Removed
- **CSV保存機能の削除** (3147620)
  - Notion保存に一本化

- **レガシーコードの削除** (0091741)
  - 古いMedium取得ロジック

## マイグレーションノート

### Poetry から uv への移行

```bash
# 既存の Poetry 環境を削除
rm -rf .venv poetry.lock

# uv をインストール
curl -LsSf https://astral.sh/uv/install.sh | sh

# 依存関係をインストール
uv sync
```

### コマンド名の変更

| 旧コマンド | 新コマンド |
|-----------|-----------|
| `minitools-arxiv` | `arxiv` |
| `minitools-medium` | `medium` |
| `minitools-google-alerts` | `google-alerts` |
| `minitools-youtube` | `youtube` |

### 環境変数の統一

新しい環境変数名を推奨。旧名は引き続きサポート（フォールバック）。

| 旧環境変数 | 新環境変数 |
|-----------|-----------|
| `NOTION_DB_ID` | `NOTION_ARXIV_DATABASE_ID` |
| `NOTION_DB_ID_DAILY_DIGEST` | `NOTION_MEDIUM_DATABASE_ID` |
| `NOTION_DB_ID_GOOGLE_ALERTS` | `NOTION_GOOGLE_ALERTS_DATABASE_ID` |
| `SLACK_WEBHOOK_URL` | `SLACK_ARXIV_WEBHOOK_URL` |
| `SLACK_WEBHOOK_URL_MEDIUM_DAILY_DIGEST` | `SLACK_MEDIUM_WEBHOOK_URL` |
| `SLACK_WEBHOOK_URL_GOOGLE_ALERTS` | `SLACK_GOOGLE_ALERTS_WEBHOOK_URL` |

### Docker への移行

```bash
# .env.docker.example をコピー
cp .env.docker.example .env

# 環境変数を設定
vim .env

# Docker イメージをビルド
make build

# 実行
make arxiv
make medium
```

## コミット履歴

| コミット | 説明 |
|---------|------|
| bf4f777 | ruff checks |
| 0091741 | updated medium fetch logic and deleted legacy codes |
| e692971 | updated mcollectors/medium.py |
| a58e225 | simplified from minitools-tool to tool |
| 6c833a7 | bugfixes for docker use |
| 035e8aa | introduced makefile |
| 820c578 | bugfixes |
| 374a737 | introduced docker-feature |
| b91aefc | bugfixes |
| b173cb0 | bugfixes |
| 68d4d58 | bugfixes |
| 1afb4fb | bugfixes |
| e8da6f7 | miscellaneous updates |
| 5c8aabf | miscellaneous updates |
| f7beede | executed refactoring |
| 5ffb4b0 | externized common loggin function |
| f1cf4bc | add error handling |
| 8781eee | modified not to save the same papers |
| 7ae39c1 | miscellaneous updates |
| 2911dc9 | include addition of tags and article fetching improvements |
| 1bcf19f | added logging feature |
| 6b429a8 | added parallel processing feature |
| 0383d83 | bugfixes |
| 2027df0 | added medium_daily_digest_to_notion.py |
| 3147620 | added slack notification feature and deleted save to csv feature |
| 002e885 | changed package manager poetry to uv |
| e5d293a | updated model and miscellaneous stuff |
| 1489ff1 | changed default model to gemma3:27b |
| b4c8d82 | Bug fixes |
| d1bdf35 | miscellaneous fixes |
| cbd9f61 | miscellaneous fixes |
| da0ccda | Transferred program files under src folder |
| 01cfe20 | Add get_youtube_sumary_in_japanese.py |
| 6ea8347 | bug fixes |
| 1a1c699 | Modify miscellaneouses |
| cf94841 | Add README.md and modify miscellaneouses |
| 2251c64 | miscellaneous stuff |
| 64f9f19 | modified logging information |
| c5c9634 | Modified to save results to Notion |
| aa51c1f | add get_arxiv_summary_in_japanese.py |
| f13b29b | Initial commit |
