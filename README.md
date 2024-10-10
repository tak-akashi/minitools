# arXiv論文要約ツール（get_arxiv_summary_in_japanese.py）

このツールは、arXivから指定したキーワードで論文を検索し、その要約を日本語に翻訳してNotionデータベースに保存するPythonスクリプトです。

## 主な機能

1. arXiv APIを使用して論文を検索
2. 論文の要約を日本語に翻訳（ollamaを使用）
3. 翻訳した要約をNotionデータベースに保存
4. オプションでCSVファイルにも保存可能

## 使い方

1. 必要な環境変数を設定:
   - `NOTION_API_KEY`: NotionのAPIキー
   - `NOTION_DB_ID`: 保存先のNotionデータベースID

2. 必要なライブラリをインストール:
   ```
   pip install requests feedparser ollama pandas pytz
   ```

3. スクリプトを実行:
   ```
   python get_arxiv_summary_in_japanese.py [オプション]
   ```

   オプション:
   - `-q`, `--queries`: 検索キーワード（デフォルト: ["LLM", "(RAG OR FINETUNING)"]）
   - `-d`, `--days_before`: 何日前から検索するか（デフォルト: 1）
   - `-b`, `--base_date`: 検索終了日（デフォルト: 今日）
   - `-r`, `--max_results`: 最大検索結果数（デフォルト: 50）
   - `-c`, `--save_to_csv`: CSVファイルに保存するかどうか（フラグオプション）

4. 結果の確認:
   - Notionデータベースに保存された論文情報を確認
   - CSVファイルを指定した場合は `outputs` ディレクトリ内のファイルを確認

## 注意事項

- ollamaを使用して翻訳を行うため、事前にollamaのセットアップが必要です。
- Notion APIの利用にはアカウントとAPIキーの設定が必要です。
- 大量の論文を一度に処理する場合は、API制限に注意してください。
