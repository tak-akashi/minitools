# 週次AIダイジェスト機能

## 概要
Google AlertsのNotion DBから過去1週間分の記事を取得し、AIが重要度を判定して上位20件を選出。週のトレンド総括と各記事の要約をSlackに出力する。

## 新規作成ファイル

### 1. LLM抽象化レイヤー（Ollama/OpenAI切り替え）
```
minitools/llm/
├── __init__.py          # get_llm_client() ファクトリ関数
├── base.py              # BaseLLMClient 抽象基底クラス
├── ollama_client.py     # OllamaClient
└── openai_client.py     # OpenAIClient (GPT-4o対応)
```

### 2. Notion Reader
```
minitools/readers/
├── __init__.py
└── notion.py            # NotionReader（日付フィルタでデータ取得）
```

### 3. 週次ダイジェストProcessor
- `minitools/processors/weekly_digest.py`
  - `rank_articles_by_importance()` - 重要度判定
  - `generate_trend_summary()` - 週のトレンド総括
  - `generate_article_summaries()` - 各記事3-4行要約

### 4. CLIスクリプト
- `scripts/weekly_digest.py`

## 既存ファイル変更

### `minitools/publishers/slack.py`
- `format_weekly_digest()` メソッド追加

### `pyproject.toml`
- `weekly-digest` コマンド追加
- `openai` 依存追加

### `settings.yaml`
```yaml
llm:
  provider: "ollama"  # or "openai"
  ollama:
    models:
      weekly_digest: "gemma3:27b"
  openai:
    models:
      weekly_digest: "gpt-4o"

defaults:
  weekly_digest:
    days_back: 7
    top_articles: 20
```

### `.env`
```
OPENAI_API_KEY=sk-xxxx
SLACK_WEEKLY_DIGEST_WEBHOOK_URL=https://hooks.slack.com/...
```

## データフロー

```
Notion DB (Google Alerts)
    ↓ NotionReader.get_articles_by_date_range()
    ↓ 過去7日分取得（日付フィルタ + ページネーション）
記事リスト (50-100件程度)
    ↓ WeeklyDigestProcessor.rank_articles_by_importance()
    ↓ LLMが重要度スコア(1-10)を付与
上位20件
    ↓ generate_trend_summary() + generate_article_summaries()
    ↓ トレンド総括 + 各記事3-4行要約
SlackPublisher.format_weekly_digest()
    ↓
Slack出力
```

## CLIコマンド

```bash
# 基本実行
uv run minitools-weekly-digest

# オプション
uv run minitools-weekly-digest --days 7 --top 20
uv run minitools-weekly-digest --provider openai  # OpenAI使用
uv run minitools-weekly-digest --dry-run          # Slack送信せず表示
uv run minitools-weekly-digest --output digest.md # ファイル保存
```

## Slack出力フォーマット

```
📰 週次AIダイジェスト
_2024/01/15 - 2024/01/21_

📈 今週のトレンド総括
[AIによる300文字程度の総括]

---

🔥 注目記事 TOP 20

🥇 1. [タイトル]
`ソース` #タグ1 #タグ2
[3-4行の要約]
<URL|記事を読む>

🥈 2. [タイトル]
...
```

## 実装順序

1. **LLM抽象化レイヤー** - `minitools/llm/`
   - base.py → ollama_client.py → openai_client.py → __init__.py

2. **NotionReader** - `minitools/readers/notion.py`
   - 日付フィルタ、ページネーション対応

3. **WeeklyDigestProcessor** - `minitools/processors/weekly_digest.py`
   - 重要度判定 → 総括生成 → 記事要約

4. **SlackPublisher変更** - format_weekly_digest()追加

5. **設定ファイル** - settings.yaml, .env

6. **CLIスクリプト** - scripts/weekly_digest.py

7. **pyproject.toml** - コマンド登録

## 検証方法

1. **NotionReader単体テスト**
   ```bash
   # Pythonで直接確認
   python -c "from minitools.readers.notion import NotionReader; ..."
   ```

2. **LLMクライアント確認**
   ```bash
   # Ollama
   uv run minitools-weekly-digest --dry-run --provider ollama
   # OpenAI
   uv run minitools-weekly-digest --dry-run --provider openai
   ```

3. **E2Eテスト**
   ```bash
   # dry-runで出力確認
   uv run minitools-weekly-digest --days 7 --top 5 --dry-run

   # Slack送信
   uv run minitools-weekly-digest --days 7 --top 20
   ```
