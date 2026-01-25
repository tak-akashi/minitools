# ArXiv週次ダイジェスト機能

> 作成日: 2025-01-25
> ステータス: draft

## 概要

過去1週間のArXiv論文（Notion DBに保存済み）から重要な10件を選出し、Slackに出力する機能。論文が多すぎて追いきれない問題を解決し、読むべき論文のキュレーションを行う。

## 背景

### 現状の課題

- ArXivから収集した論文がNotion DBに大量に蓄積される
- 全ての論文を確認する時間がない
- 重要な論文を見逃すリスクがある

### 解決したいこと

- 週次で重要な論文10件をピックアップ
- 選出理由と重要ポイントを提示
- ユーザーは選出された論文のみ詳細確認（NotebookLM等でPDF全文分析）

## 解決策

### アプローチ

既存のweekly-digest（Google Alerts用）の仕組みを流用し、ArXiv論文専用の週次ダイジェストを作成する。

1. **データソース**: Notion DB（ArXiv論文）
2. **重要度判定**: 日本語訳フィールドを使用してLLMが評価
3. **評価基準**: 技術的新規性・業界インパクト・実用性の総合スコア
4. **出力先**: Slackのみ

### 代替案と比較

| アプローチ | メリット | デメリット | 採否 |
|-----------|---------|-----------|------|
| Notion DBから取得 + 日本語訳で判定 | 既存データ活用、高速 | 概要のみで判定 | ✓ 採用 |
| PDF全文を読んで判定 | 詳細な分析可能 | 処理時間・コスト大 | ✗ |
| 直接ArXiv APIから取得 | 最新データ | 翻訳処理が必要 | ✗ |

## データフロー

```
Notion DB (ArXiv論文)
    ↓ NotionReader.get_arxiv_articles_by_date_range()
    ↓ 過去7日分取得（公開日でフィルタ）
論文リスト (数十〜数百件)
    ↓ ArxivWeeklyProcessor.rank_papers_by_importance()
    ↓ 「日本語訳」フィールドを使用
    ↓ LLMが総合スコア(1-10)を付与
上位10件
    ↓ generate_paper_highlights()
    ↓ 選出理由・重要ポイント生成
SlackPublisher.format_arxiv_weekly()
    ↓
Slack出力
```

## 実装する機能

### 機能1: NotionReader拡張

- ArXiv論文用の日付フィルタ取得メソッド追加
- 既存のNotionReaderを拡張

### 機能2: ArxivWeeklyProcessor

- `rank_papers_by_importance()` - 重要度スコア付与
  - 評価基準: 技術的新規性、業界インパクト、実用性
  - 総合スコア(1-10)を算出
- `generate_paper_highlights()` - 選出理由・重要ポイント生成

### 機能3: SlackPublisher拡張

- `format_arxiv_weekly()` - ArXiv週次ダイジェスト用フォーマット

### 機能4: CLIコマンド

- `arxiv-weekly` コマンドとして独立

## Notion DBプロパティ（参照）

| プロパティ名 | 型 | 内容 |
|-------------|-----|------|
| タイトル | Title | 英語の論文タイトル |
| 公開日 | Date | ArXiv投稿日 |
| 更新日 | Date | 論文更新日 |
| 概要 | Rich Text | 英語の要約（最大2000文字） |
| 日本語訳 | Rich Text | 翻訳済み要約（最大2000文字） |
| URL | URL | ArXivリンク |

## Slack出力フォーマット

```
📚 ArXiv週次ダイジェスト
_2025/01/19 - 2025/01/25_

🏆 今週の注目論文 TOP 10

🥇 1. [論文タイトル]
⭐ 総合スコア: 9.2/10
📌 選出理由: 〜という点で技術的に画期的...
💡 重要ポイント:
  - ポイント1
  - ポイント2
  - ポイント3
🔗 <ArXiv URL|ArXiv> | <PDF URL|PDF>

🥈 2. [論文タイトル]
⭐ 総合スコア: 8.8/10
📌 選出理由: ...
💡 重要ポイント: ...
🔗 ...

... (10件まで)
```

## CLIコマンド

```bash
# 基本実行
uv run arxiv-weekly

# オプション
uv run arxiv-weekly --days 7 --top 10
uv run arxiv-weekly --dry-run          # Slack送信せず表示
uv run arxiv-weekly --provider openai  # OpenAI使用
```

## 受け入れ条件

### NotionReader拡張
- [ ] ArXiv論文を公開日でフィルタして取得できる
- [ ] 日本語訳フィールドを含むデータが取得できる

### ArxivWeeklyProcessor
- [ ] 論文リストに対して総合スコア(1-10)を付与できる
- [ ] 上位10件を選出できる
- [ ] 各論文に選出理由と重要ポイントを生成できる

### SlackPublisher
- [ ] 指定フォーマットでSlackに出力できる
- [ ] ArXivリンクとPDFリンクが正しく表示される

### CLI
- [ ] `uv run arxiv-weekly` で実行できる
- [ ] `--dry-run` でSlack送信せずに結果確認できる
- [ ] `--days` と `--top` オプションが機能する

## スコープ外

- PDF全文の分析（NotebookLM等の外部ツールに委譲）
- Notionへの出力（Slackのみ）
- 既存weekly-digestとの統合（独立コマンドとして実装）
- 著者情報の表示（現在Notion DBに未保存）

## 技術的考慮事項

### 影響範囲

- `minitools/readers/notion.py` - メソッド追加
- `minitools/processors/` - 新規Processor追加
- `minitools/publishers/slack.py` - メソッド追加
- `scripts/arxiv_weekly.py` - 新規スクリプト
- `pyproject.toml` - コマンド追加
- `settings.yaml` - 設定追加

### 既存コンポーネントの再利用

- `NotionReader` - 既存の日付フィルタロジックを拡張
- `get_llm_client()` - 既存のLLM抽象化レイヤーを使用
- `SlackPublisher` - 既存のWebhook送信ロジックを使用

### リスクと対策

- **リスク1**: 論文数が多すぎてLLMのトークン制限を超える
  → **対策**: バッチ処理で分割評価、または概要のみで一次スクリーニング

- **リスク2**: スコアリングの一貫性が低い
  → **対策**: プロンプトで評価基準を明確化、Few-shot例を追加

## 実装順序

1. **NotionReader拡張** - ArXiv論文取得メソッド
2. **ArxivWeeklyProcessor** - 重要度判定・ハイライト生成
3. **SlackPublisher拡張** - 出力フォーマット
4. **設定ファイル** - settings.yaml
5. **CLIスクリプト** - scripts/arxiv_weekly.py
6. **pyproject.toml** - コマンド登録
