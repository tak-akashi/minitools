# arXiv論文要約ツール（get_arxiv_summary_in_japanese.py）

このツールは、arXivから指定したキーワードで論文を検索し、その要約を日本語に翻訳してNotionデータベースに保存し、結果をSlackに通知するPythonスクリプトです。

## 主な機能

1. arXiv APIを使用して論文を検索
2. 論文の要約を日本語に翻訳（ollamaを使用）
3. 翻訳した要約をNotionデータベースに保存
4. 処理結果をSlackに通知

## 使い方

1. 必要な環境変数を設定:
   - `NOTION_API_KEY`: NotionのAPIキー
   - `NOTION_DB_ID`: 保存先のNotionデータベースID
   - `SLACK_WEBHOOK_URL`: SlackのWebhook URL

2. 必要なライブラリをインストール:
   ```
   pip install requests feedparser ollama python-dotenv pytz
   ```

3. スクリプトを実行:
   ```
   python script/get_arxiv_summary_in_japanese.py [オプション]
   ```

   オプション:
   - `-q`, `--queries`: 検索キーワード（デフォルト: ["LLM", "(RAG OR FINETUNING OR AGENT)"]）
   - `-d`, `--days_before`: 何日前から検索するか（デフォルト: 1）
   - `-b`, `--base_date`: 検索終了日（デフォルト: 昨日）
   - `-r`, `--max_results`: 最大検索結果数（デフォルト: 50）
   - `--no-slack`: Slackへの投稿をスキップ（フラグオプション）

4. 結果の確認:
   - Notionデータベースに保存された論文情報を確認
   - Slackに送信された通知を確認

## 注意事項

- ollamaを使用して翻訳を行うため、事前にollamaのセットアップが必要です。
- Notion APIの利用にはアカウントとAPIキーの設定が必要です。
- 大量の論文を一度に処理する場合は、API制限に注意してください。



# YouTube動画の要約ツール（get_youtube_summary_in_japanese.py）

このツールは、YouTubeの動画URLを入力として受け取り、その内容を要約して日本語で出力するPythonスクリプトです。

## 主な機能

1. YouTubeから音声データをダウンロード
2. 音声データを文字起こし（mlx_whisperを使用）
3. 文字起こしされたテキストを要約
4. 要約を日本語に翻訳（必要な場合）
5. 結果をファイルに保存

## 使い方

1. 必要なライブラリをインストール:
   ```
   pip install yt_dlp mlx_whisper ollama argparse
   ```

2. スクリプトを実行:
   ```
   python get_youtube_summary_in_japanese.py [オプション]
   ```

   オプション:
   - `-u`, `--youtube_url`: YouTube動画のURL
   - `-o`, `--output_dir`: 出力ディレクトリ
   - `-m`, `--model_path`: 使用する音声認識モデルのパス

3. 結果の確認:
   - `outputs/temp` ディレクトリ内の `youtube_summary.txt` ファイルに要約が保存されます
   - `outputs/temp` ディレクトリ内の `audio_transcript.txt` ファイルに文字起こしの結果が保存されます

## 必要な環境

- Python 3.x
- FFmpeg（`/opt/homebrew/bin/ffmpeg` にインストールされていることを想定）
- Apple Silicon搭載のMac（MLXフレームワークを使用するため）
- ollama（要約と翻訳に使用）
- インターネット接続（YouTube動画のダウンロードと外部APIの利用のため）

## 注意事項

- FFmpegがインストールされている必要があります
- ollamaを使用して要約と翻訳を行うため、事前にollamaのセットアップが必要です
- 処理の進行状況はログファイル（`outputs/logs/youtube.log`）で確認できます
- このスクリプトはApple Silicon搭載のMac上で動作することを前提としています。他の環境で使用する場合は、MLXフレームワークの代替を検討する必要があります。



# Gmailからメールを抽出して日本語要約してNotionへ書き出すツール（medium_daily_digest_to_notion.py）

このツールは、Gmail経由で受信したMedium Daily Digestメールから記事情報を抽出し、日本語の要約を付けてNotionデータベースに保存するPythonスクリリプトです。

## 主な機能

1.  **Gmail API連携**: 特定の日付のMedium Daily Digestメールを自動で検索・取得します。
2.  **記事情報抽出**: メールのHTMLコンテンツを解析し、各記事のタイトル、URL、著者名を抽出します。
3.  **翻訳と要約**: Ollamaを利用して、記事のタイトルと本文を日本語に翻訳・要約します。
4.  **Notionへの保存**: 処理した記事情報を指定したNotionデータベースに保存します。重複チェック機能も備えています。

## 使い方

1.  **Gmail APIの準備**:
    - Google Cloud PlatformでGmail APIを有効にし、認証情報（`credentials.json`）をダウンロードしてプロジェクトのルートディレクトリに配置します。
    - 初回実行時にブラウザで認証が求められます。認証後、`token.pickle`が生成され、以降の実行では自動で認証されます。

2.  **必要な環境変数を設定**:
    - `.env`ファイルを作成し、以下の変数を設定します。
      ```
      NOTION_API_KEY="your_notion_api_key"
      NOTION_DB_ID_DAILY_DIGEST="your_notion_database_id"
      # GMAIL_CREDENTIALS_PATH="path/to/your/credentials.json" # オプション
      ```

3.  **必要なライブラリをインストール**:
    ```bash
    pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib requests beautifulsoup4 notion-client ollama python-dotenv
    ```

4.  **スクリプトを実行**:
    - 今日のダイジェストを処理する場合:
      ```bash
      python script/medium_daily_digest_to_notion.py
      ```
    - 特定の日付のダイジェストを処理する場合:
      ```bash
      python script/medium_daily_digest_to_notion.py --date YYYY-MM-DD
      ```

5.  **結果の確認**:
    - 指定したNotionデータベースに記事が保存されていることを確認します。

## 注意事項

-   Ollamaがローカル環境で起動している必要があります。
-   Gmail APIの認証情報(`credentials.json`)が必要です。
-   Notionデータベースには、`Title`(Title), `Japanese Title`(Rich Text), `URL`(URL), `Author`(Rich Text), `Summary`(Rich Text), `Date`(Date) のプロパティが正しく設定されている必要があります。
