# Weekly Digest パフォーマンス改善

> 作成日: 2026-02-02
> ステータス: draft

## 概要

`google-alert-weekly-digest` と `arxiv-weekly` のスコアリング処理を高速化する。OpenAI APIをデフォルトプロバイダーとし、バッチ処理を導入することで、処理時間を40分以上から数分に短縮する。

## 背景

### 現状の課題

- `google-alert-weekly-digest` で500件以上の記事を処理すると40分以上かかる
- 全記事に対してOllama (gemma3:27b) で個別にスコアリングしている
- MacでCPUのみの環境では1件あたり10-20秒かかる
- 並列処理（max_concurrent: 3）でも500件 ÷ 3 × 15秒 ≈ 40分以上

### 解決したいこと

- 処理時間を40分以上から数分に短縮
- 通常の要約処理（medium/arxiv/google-alerts）はollamaを継続使用
- 週次ダイジェストのみOpenAI APIを使用してコストと速度のバランスを取る

## 解決策

### アプローチ

2つの改善を組み合わせる：

1. **OpenAI APIをデフォルト化**: 週次ダイジェスト専用のプロバイダー設定を追加
2. **バッチ処理の導入**: 20件を1回のLLM呼び出しでまとめてスコアリング

### 代替案と比較

| アプローチ | メリット | デメリット | 採否 |
|-----------|---------|-----------|------|
| OpenAI API + バッチ処理 | 高速（数分）、コスト低（gpt-4o-mini） | API料金発生 | ✓ 採用 |
| 2段階スクリーニング | コスト最小 | 実装複雑、精度低下リスク | ✗ |
| キャッシュ機構 | 再実行時は高速 | 初回は遅いまま | ✗ |
| 軽量モデル (gemma3:4b) | コスト0 | 精度低下、依然として遅い | ✗ |

## データフロー

```
500件以上の記事
    ↓ バッチ分割（20件ずつ）
25バッチ
    ↓ OpenAI API 並列呼び出し（max_concurrent: 3）
スコア付き記事
    ↓ 上位20件選出 + 重複除去
最終ダイジェスト
```

## 実装する機能

### 機能1: settings.yaml に週次ダイジェスト専用プロバイダー設定を追加

- `defaults.weekly_digest.provider: "openai"` を追加
- `defaults.arxiv_weekly.provider: "openai"` を追加
- プロバイダー優先順位: コマンドライン引数 > weekly_digest.provider > llm.provider

### 機能2: バッチスコアリング処理

- `WeeklyDigestProcessor.rank_articles_by_importance()` にバッチ処理を導入
- バッチサイズ: 20件（設定可能）
- 複数記事を1つのプロンプトでまとめてスコアリング
- JSON配列形式でスコアを返却

### 機能3: エラーハンドリング（リトライ + フォールバック）

- バッチ処理が失敗した場合、1件ずつ個別にリトライ
- 個別処理も失敗した場合はデフォルトスコア（5）を付与
- 部分的な失敗でも処理を継続

### 機能4: arxiv-weekly への同様の適用

- `ArxivWeeklyProcessor` にも同じバッチ処理を導入
- デフォルトプロバイダーを `openai` に設定

## CLIコマンド

```bash
# 基本実行（デフォルトでOpenAI使用）
uv run google-alert-weekly-digest
uv run arxiv-weekly

# 明示的にollamaを使用
uv run google-alert-weekly-digest --provider ollama
uv run arxiv-weekly --provider ollama

# dry-run（Slack送信なし）
uv run google-alert-weekly-digest --dry-run
```

## 受け入れ条件

### 機能1: プロバイダー設定
- [ ] settings.yaml に `defaults.weekly_digest.provider` が追加されている
- [ ] settings.yaml に `defaults.arxiv_weekly.provider` が追加されている
- [ ] `--provider` オプションが設定ファイルの値を上書きできる
- [ ] プロバイダー未指定時は `llm.provider` にフォールバックする

### 機能2: バッチ処理
- [ ] 20件を1回のLLM呼び出しでスコアリングできる
- [ ] バッチサイズが settings.yaml で設定可能
- [ ] 500件の処理が5分以内に完了する

### 機能3: エラーハンドリング
- [ ] バッチ失敗時に個別処理へフォールバックする
- [ ] 個別処理失敗時にデフォルトスコアが付与される
- [ ] 部分的な失敗でも処理が継続する
- [ ] エラーがログに記録される

### 機能4: arxiv-weekly
- [ ] arxiv-weekly でも同じバッチ処理が動作する
- [ ] デフォルトプロバイダーが openai になっている

## スコープ外

- medium/arxiv/google-alerts の通常処理: 引き続きollamaを使用
- Embedding処理の変更: 既にOpenAIを使用しており高速
- キャッシュ機構: 将来の改善として検討

## 技術的考慮事項

### 影響範囲

- `settings.yaml` - プロバイダー設定の追加
- `minitools/processors/weekly_digest.py` - バッチ処理の実装
- `minitools/processors/arxiv_weekly.py` - バッチ処理の実装
- `scripts/google_alert_weekly_digest.py` - デフォルトプロバイダーの変更
- `scripts/arxiv_weekly_digest.py` - デフォルトプロバイダーの変更

### 既存コンポーネントの再利用

- `get_llm_client()` - プロバイダー切り替えに使用
- `IMPORTANCE_PROMPT_TEMPLATE` - バッチ用に拡張

### リスクと対策

- **リスク1**: バッチ処理でJSON解析エラーが発生しやすくなる
  → **対策**: リトライ + 個別処理へのフォールバック

- **リスク2**: OpenAI API料金の増加
  → **対策**: gpt-4o-miniを使用（500件で約$0.05程度）、バッチ処理で呼び出し回数削減

- **リスク3**: バッチサイズが大きすぎるとトークン制限に達する
  → **対策**: バッチサイズ20件でテスト、必要に応じて調整可能に

## 実装順序

1. **settings.yaml の更新** - プロバイダー設定を追加
2. **バッチスコアリングの実装** - WeeklyDigestProcessor を修正
3. **エラーハンドリングの実装** - リトライ + フォールバック
4. **スクリプトの更新** - デフォルトプロバイダーの読み込み
5. **arxiv-weekly への適用** - 同様の変更を適用
6. **テスト実行** - 500件の処理時間を確認

## 更新履歴

- 2026-02-02: 初版作成（ブレインストーミングセッション）
