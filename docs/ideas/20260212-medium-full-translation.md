# Medium記事全文翻訳

> 作成日: 2026-02-12
> ステータス: implemented
> 実装日: 2026-02-12
> ステアリングディレクトリ: .steering/20260212-medium-full-translation/
> 優先度: P1

## 概要

Medium記事の全文を自動取得・日本語翻訳し、Notionの既存ページに体裁付きで追記する機能。手動でのコピペ→翻訳→Notion貼り付け→体裁整えのワークフローを自動化する。

## 背景

### 現状の課題

- `uv run medium` で記事概要を取得しSlackに通知しているが、全文翻訳は手動作業
- 手動ワークフロー（記事コピペ → Google AI Studio/Gemini 2.5 Pro翻訳 → Notion貼り付け → 体裁整え）に時間がかかる
- MediumがCloudflare等のボット対策をしており、Jina AI Readerでのアクセスが拒否される
- Notionへの貼り付け時に見出しレベル、画像、コードブロックの体裁調整が必要

### 解決したいこと

- 記事URL指定または拍手数閾値による自動翻訳で手作業を排除
- ボット対策を突破してMedium全文を取得
- 翻訳結果をNotionの既存ページに体裁付きで自動追記

## 解決策

### アプローチ

Playwright（ヘッドレスブラウザ）でMedium有料アカウントにログインし、ボット対策を突破して全文を取得。既存のLLM抽象レイヤーで翻訳し、Notion APIで既存ページに追記する。

```bash
# モード1: 個別記事を翻訳
uv run medium-translate --url "https://medium.com/..." --provider ollama

# モード2: 複数記事を一括翻訳
uv run medium-translate --url "https://..." --url "https://..."

# モード3: medium実行時に拍手閾値以上を自動翻訳
uv run medium --translate --notion
```

### 設計方針

1. **Playwrightでボット対策突破**: Google OAuthでMediumにログインし、ペイウォール記事も含めて全文取得
2. **LLMプロバイダー選択可能**: 既存の`minitools/llm/`を活用し、Ollama/OpenAI/（将来）Geminiから選択
3. **Notion既存ページへの追記**: 区切り線（divider）の下に翻訳全文をブロック形式で追記
4. **体裁の維持**: HTML → 構造化Markdown → 翻訳 → Notionブロック変換で見出し・画像・コードブロックを保持

### 代替案と比較

| 案 | メリット | デメリット | 採否 |
|----|---------|-----------|------|
| Playwright + ログイン | ペイウォール記事も取得可能、安定 | セットアップがやや複雑 | 採用 |
| Jina AI Reader | 実装が簡単 | Mediumのボット対策でアクセス拒否 | 不採用 |
| Freedium等のプロキシ | 実装が簡単 | サービス安定性に依存、ペイウォール非対応 | 不採用 |
| Medium RSS | 公式手段 | 全文が取得できない場合あり | 不採用 |

## 実装する機能

### ロードマップ

| Phase | 機能 | 概要 |
|-------|------|------|
| 1 | Medium全文取得 + Ollama翻訳 + Notion追記 | コア機能（今回のスコープ） |
| 2 | Gemini APIプロバイダー追加 | LLM抽象レイヤーにGeminiを追加 |
| 3 | 翻訳品質比較・最適化 | Ollama/OpenAI/Geminiの翻訳品質を検証し最適設定を決定 |

### 機能1: Medium全文取得（MediumScraper）

Playwrightを使用してMediumにログインし、記事の全文をHTML→構造化Markdownとして取得する。

**パラメータ/オプション:**
- `url`: 対象記事のURL
- Google認証情報: `.env` の `GOOGLE_EMAIL` / `GOOGLE_PASSWORD`（Google OAuth経由でMediumにログイン）

### 機能2: 全文翻訳コマンド（medium-translate）

個別URLを指定して記事を翻訳し、Notionに保存する独立コマンド。

```bash
uv run medium-translate --url "https://medium.com/..." [--provider ollama|openai]
```

**パラメータ/オプション:**
- `--url`: 翻訳対象のMedium記事URL（複数指定可）
- `--provider`: LLMプロバイダー（デフォルト: settings.yamlの設定値）
- `--dry-run`: 翻訳結果を表示するのみ（Notion保存しない）

### 機能3: medium コマンドへの --translate オプション追加

`uv run medium` 実行時に、**拍手数（claps）が閾値以上の記事のみ**を自動で全文翻訳する。閾値未満の記事は翻訳をスキップする。

```bash
uv run medium --translate --notion
```

**動作仕様:**
1. Medium Daily Digestメールから記事一覧を取得（通常のmediumコマンドと同じ）
2. 各記事の拍手数をメールHTMLから抽出
3. 拍手数 >= 閾値（デフォルト: 100）の記事のみを全文翻訳対象として選定
4. 対象記事をPlaywrightで全文取得 → 翻訳 → Notionの既存ページに追記

**パラメータ/オプション:**
- `--translate`: 翻訳モードを有効化（拍手数による自動フィルタリング付き）
- 拍手数閾値: `settings.yaml` の `defaults.medium.translate_clap_threshold`（デフォルト: 100）

### 機能4: Notion既存ページへの翻訳追記

既存のNotionページ末尾に区切り線 + 翻訳全文をブロック形式で追記する。

**対象ブロック:**

| ブロックタイプ | 内容 |
|--------------|------|
| divider | 区切り線 |
| heading_1/2/3 | 見出し（レベル維持） |
| paragraph | 本文テキスト |
| code | コードブロック（言語指定付き） |
| image | 画像（元URLを参照） |
| bulleted_list_item | 箇条書き |
| numbered_list_item | 番号付きリスト |
| quote | 引用 |

## 受け入れ条件

### Medium全文取得
- [ ] Playwrightで有料アカウントにログインできる
- [ ] ペイウォール記事の全文が取得できる
- [ ] 記事のHTML構造から見出し・画像・コードブロックを正しく抽出できる

### 翻訳
- [ ] Ollamaで記事全文を日本語に翻訳できる
- [ ] OpenAIプロバイダーでも翻訳できる
- [ ] 見出し・コードブロック等の構造が翻訳後も維持される
- [ ] コードブロック内のコードは翻訳されない（コメントのみ翻訳）

### Notion保存
- [ ] 既存ページの末尾に区切り線 + 翻訳全文が追記される
- [ ] 見出しレベルが正しく反映される
- [ ] 画像が表示される
- [ ] コードブロックが言語指定付きで正しく表示される

### 拍手数フィルタリング（`--translate` モード）
- [ ] Medium Daily Digestメールから各記事の拍手数（claps）を正しく抽出できる
- [ ] 拍手数 >= 閾値（デフォルト: 100）の記事のみが全文翻訳対象となる
- [ ] 閾値未満の記事はスキップされ、ログに通知される
- [ ] 閾値は `settings.yaml` の `defaults.medium.translate_clap_threshold` で変更可能

### コマンド
- [ ] `uv run medium-translate --url` で個別翻訳が実行できる
- [ ] `uv run medium --translate` で拍手閾値以上の記事が自動翻訳される
- [ ] `--dry-run` で翻訳結果のプレビューができる
- [ ] `--provider` でLLMプロバイダーを切り替えられる

### エラーハンドリング
- [ ] Mediumログイン失敗時にエラーメッセージが表示される
- [ ] 記事取得失敗時にスキップして次の記事に進む
- [ ] 翻訳失敗時にリトライされる（既存のリトライロジック活用）

## スコープ外

### 今回対象外
- Gemini APIプロバイダーの実装（Phase 2で対応）
- Medium以外のサイト（Substack等）の翻訳対応
- 翻訳のキャッシュ・差分更新
- 翻訳済み記事の再翻訳防止（Notionプロパティでの管理）

### 将来対応予定
- Gemini APIプロバイダー追加（`minitools/llm/`）
- 翻訳品質の自動評価
- 翻訳済みフラグによる重複翻訳防止

## 技術的考慮事項

### ディレクトリ構成

```
minitools/
├── scrapers/               # 新規追加
│   ├── __init__.py
│   └── medium_scraper.py   # Playwrightによる全文取得
├── processors/
│   └── translator.py       # 既存を拡張（全文翻訳対応）
├── publishers/
│   └── notion_publisher.py # 既存を拡張（ページ追記対応）
scripts/
├── medium_translate.py     # 新規: medium-translateコマンド
└── medium_daily_digest.py  # 既存: --translateオプション追加
```

### 既存コードとの関係

- `minitools/llm/`: LLMプロバイダー抽象レイヤーをそのまま利用
- `minitools/processors/translator.py`: 要約翻訳の既存ロジックを拡張
- `minitools/publishers/notion_publisher.py`: ページ追記機能を追加
- `settings.yaml`: 翻訳設定（閾値、プロバイダー等）を追加

### 依存コンポーネント

| コンポーネント | 用途 |
|--------------|------|
| playwright | Medium記事の全文取得（ヘッドレスブラウザ） |
| beautifulsoup4 | HTML解析・構造化 |
| notion-client | 既存ページへのブロック追記 |
| minitools/llm | 翻訳LLM呼び出し |

### パフォーマンス考慮

- Playwright起動に数秒かかるため、複数記事は1セッションで処理
- 長文記事の翻訳はチャンク分割が必要な場合あり（LLMのコンテキスト長制限）
- 非同期処理で複数記事の翻訳を並列化

### リスクと対策

| リスク | 影響度 | 対策 |
|-------|--------|------|
| MediumがPlaywrightを検知・ブロック | 高 | ユーザーエージェント偽装、適切な待機時間、persistent contextの活用 |
| 記事HTML構造の変更 | 中 | 主要要素のセレクタを設定可能にし、変更時に対応しやすくする |
| 長文記事でLLMコンテキスト長超過 | 中 | セクション単位でチャンク分割して翻訳 |
| Notion APIのブロック追記制限 | 低 | バッチ処理で100ブロック単位に分割 |

## 設定項目（settings.yaml）

```yaml
defaults:
  medium:
    translate_clap_threshold: 100    # 自動翻訳の拍手数閾値
    translate_provider: ollama       # 翻訳LLMプロバイダー
    translate_model: gemma3:27b      # 翻訳モデル
```

```env
# .env に追加（Google OAuthでMediumにログイン）
GOOGLE_EMAIL=your-google-email@gmail.com
GOOGLE_PASSWORD=your-google-password
```

## 更新履歴

- 2026-02-12: 初版作成（ブレインストーミングセッション）
