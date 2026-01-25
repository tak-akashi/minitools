# Mermaid図

このドキュメントは、minitoolsプロジェクトの処理フローとクラス関係をMermaid図で説明します。

## ツール別シーケンス図

### ArXiv 処理フロー

```mermaid
sequenceDiagram
    participant User
    participant CLI as scripts/arxiv.py
    participant AC as ArxivCollector
    participant ArXiv as ArXiv API
    participant TR as Translator
    participant Ollama
    participant NP as NotionPublisher
    participant Notion
    participant SP as SlackPublisher
    participant Slack

    User->>CLI: arxiv --keywords "LLM" --date 2024-01-15
    CLI->>CLI: 日付範囲計算（月曜日は3日間）

    CLI->>AC: search(queries, start_date, end_date)
    AC->>ArXiv: GET /api/query
    ArXiv-->>AC: feedparser結果
    AC-->>CLI: papers[]

    loop 各論文
        CLI->>TR: translate_with_summary(title, abstract)
        TR->>Ollama: chat(model, prompt)
        Ollama-->>TR: {japanese_title, japanese_summary}
        TR-->>CLI: 翻訳結果
    end

    alt Notion保存
        CLI->>NP: batch_save_articles(database_id, papers)
        loop 各論文（並列、max=3）
            NP->>Notion: query(database_id, url)
            Notion-->>NP: 重複チェック結果
            opt 新規の場合
                NP->>Notion: pages.create()
                Notion-->>NP: page_id
            end
        end
        NP-->>CLI: {success, skipped, failed}
    end

    alt Slack送信
        CLI->>SP: send_articles(papers, date, title)
        SP->>Slack: POST webhook
        Slack-->>SP: 200 OK
        SP-->>CLI: true
    end

    CLI-->>User: 処理完了
```

### Medium Daily Digest 処理フロー

```mermaid
sequenceDiagram
    participant User
    participant CLI as scripts/medium.py
    participant MC as MediumCollector
    participant Gmail as Gmail API
    participant Jina as Jina AI Reader
    participant TR as Translator
    participant Ollama
    participant NP as NotionPublisher
    participant Notion
    participant SP as SlackPublisher
    participant Slack

    User->>CLI: medium --date 2024-01-15
    CLI->>MC: __aenter__()
    MC-->>CLI: collector

    CLI->>MC: get_digest_emails(date)
    MC->>Gmail: threads.list(query)
    Gmail-->>MC: threads[]
    MC->>Gmail: threads.get(thread_id)
    Gmail-->>MC: messages[]
    MC-->>CLI: messages[]

    CLI->>MC: extract_email_body(message)
    MC-->>CLI: html_content

    CLI->>MC: parse_articles(html_content)
    MC-->>CLI: articles[]

    loop バッチ処理（batch_size=5）
        par 並列処理
            CLI->>MC: fetch_article_content(url)
            MC->>Jina: GET r.jina.ai/{url}
            alt 成功
                Jina-->>MC: markdown_content
            else ブロック
                MC-->>MC: preview をフォールバック使用
            end
            MC-->>CLI: (content, author)

            CLI->>TR: translate_with_summary(title, content)
            TR->>Ollama: chat(model, prompt)
            Ollama-->>TR: {japanese_title, japanese_summary}
            TR-->>CLI: 翻訳結果
        end
    end

    CLI->>MC: __aexit__()

    alt Notion保存
        CLI->>NP: batch_save_articles(database_id, articles)
        NP-->>CLI: {stats, results}
    end

    alt Slack送信
        CLI->>SP: send_articles(articles, date, title)
        SP-->>CLI: true
    end

    CLI-->>User: 処理完了
```

### Google Alerts 処理フロー

```mermaid
sequenceDiagram
    participant User
    participant CLI as scripts/google_alerts.py
    participant GAC as GoogleAlertsCollector
    participant Gmail as Gmail API
    participant Web as 記事サイト
    participant TR as Translator
    participant Ollama
    participant NP as NotionPublisher
    participant SP as SlackPublisher

    User->>CLI: google-alerts --hours 6
    CLI->>GAC: get_alerts_emails(hours_back)
    GAC->>Gmail: messages.list(query)
    Gmail-->>GAC: message_ids[]

    loop 各メッセージ
        GAC->>Gmail: messages.get(id)
        Gmail-->>GAC: message
    end
    GAC-->>CLI: emails[]

    loop 各メール
        CLI->>GAC: parse_alerts(email)
        GAC-->>CLI: alerts[]
    end

    CLI->>GAC: fetch_articles_for_alerts(alerts)
    par 並列取得
        loop 各アラート
            GAC->>Web: GET article_url
            Web-->>GAC: html
            GAC->>GAC: BeautifulSoup解析
        end
    end
    GAC-->>CLI: (alerts with content)

    loop 各アラート
        CLI->>TR: translate_with_summary(title, content)
        TR->>Ollama: chat(model, prompt)
        Ollama-->>TR: {japanese_title, japanese_summary}
        TR-->>CLI: 翻訳結果
    end

    alt Notion保存
        CLI->>NP: batch_save_articles(database_id, alerts)
        NP-->>CLI: stats
    end

    alt Slack送信
        CLI->>SP: send_articles(alerts, title)
        SP-->>CLI: true
    end

    CLI-->>User: 処理完了
```

### YouTube 処理フロー

```mermaid
sequenceDiagram
    participant User
    participant CLI as scripts/youtube.py
    participant YC as YouTubeCollector
    participant YT as YouTube
    participant FFmpeg
    participant Whisper as MLX Whisper
    participant SU as Summarizer
    participant TR as Translator
    participant Ollama

    User->>CLI: youtube --url https://youtube.com/watch?v=xxx

    CLI->>YC: get_video_info(url)
    YC->>YT: extract_info(download=False)
    YT-->>YC: video_info
    YC-->>CLI: {title, uploader, duration, ...}

    CLI->>YC: download_audio(url)
    YC->>YT: extract_info(download=True)
    YT-->>YC: audio stream
    YC->>FFmpeg: extract audio to mp3
    FFmpeg-->>YC: audio_file.mp3
    YC-->>CLI: audio_file_path

    CLI->>YC: transcribe_audio(audio_file)
    YC->>Whisper: transcribe(audio_file, model)
    Whisper-->>YC: {text: transcript}
    YC-->>CLI: {text: transcript}

    CLI->>SU: summarize(transcript, max_length=500, language="english")
    SU->>Ollama: chat(model, prompt)
    Ollama-->>SU: english_summary
    SU-->>CLI: english_summary

    CLI->>TR: translate_to_japanese(summary)
    TR->>Ollama: chat(model, prompt)
    Ollama-->>TR: japanese_summary
    TR-->>CLI: japanese_summary

    CLI->>CLI: ファイル保存（transcript, summary）

    CLI-->>User: 結果表示
```

### Weekly Digest 処理フロー

```mermaid
sequenceDiagram
    participant User
    participant CLI as scripts/weekly_digest.py
    participant NR as NotionReader
    participant Notion as Notion DB
    participant WDP as WeeklyDigestProcessor
    participant DD as DuplicateDetector
    participant LLM as LLM Client
    participant Embed as Embedding Client
    participant SP as SlackPublisher
    participant Slack

    User->>CLI: weekly-digest --days 7 --top 20

    CLI->>NR: get_articles_by_date_range(db_id, start, end)
    NR->>Notion: databases.query(filter)
    Notion-->>NR: pages[]
    NR-->>CLI: articles[]

    CLI->>WDP: process(articles, top_n=20, deduplicate=True)

    Note over WDP: 1. 重要度スコアリング
    loop 各記事（並列、max=3）
        WDP->>LLM: chat_json(importance_prompt)
        LLM-->>WDP: {technical_impact, industry_impact, ...}
    end

    Note over WDP: 2. 重複除去
    WDP->>DD: detect_duplicates(candidates)
    DD->>Embed: embed_texts(article_texts)
    Embed-->>DD: embeddings[]
    DD->>DD: cosine_similarity clustering
    DD-->>WDP: groups[]
    WDP->>DD: select_representatives(groups, top_n)
    DD-->>WDP: top_articles[]

    Note over WDP: 3. トレンド総括生成
    WDP->>LLM: generate(trend_prompt)
    LLM-->>WDP: trend_summary

    Note over WDP: 4. 記事要約生成
    loop 各上位記事（並列、max=3）
        WDP->>LLM: generate(summary_prompt)
        LLM-->>WDP: digest_summary
    end

    WDP-->>CLI: {trend_summary, top_articles, ...}

    CLI->>SP: format_weekly_digest(start, end, summary, articles)
    SP-->>CLI: formatted_message

    alt Slack送信（非dry-run）
        CLI->>SP: send_message(message)
        SP->>Slack: POST webhook
        Slack-->>SP: 200 OK
        SP-->>CLI: true
    end

    CLI-->>User: 処理完了
```

### ArXiv Weekly Digest 処理フロー

```mermaid
sequenceDiagram
    participant User
    participant CLI as scripts/arxiv_weekly.py
    participant NR as NotionReader
    participant Notion as Notion DB
    participant AWP as ArxivWeeklyProcessor
    participant TrendR as TrendResearcher
    participant Tavily as Tavily API
    participant LLM as LLM Client
    participant SP as SlackPublisher
    participant Slack

    User->>CLI: arxiv-weekly --days 7 --top 10

    CLI->>NR: get_arxiv_papers_by_date_range(db_id, start, end)
    NR->>Notion: databases.query(filter=公開日)
    Notion-->>NR: pages[]
    NR-->>CLI: papers[]

    CLI->>AWP: process(papers, top_n=10, use_trends=True)

    Note over AWP: 1. トレンド調査
    AWP->>TrendR: get_current_trends()
    TrendR->>Tavily: search(query="AI trends", include_answer=True)
    Tavily-->>TrendR: {answer, results}
    TrendR-->>AWP: {summary, topics, sources}

    Note over AWP: 2. トレンドサマリー日本語化
    AWP->>LLM: generate(translate_prompt)
    LLM-->>AWP: japanese_trend_summary

    Note over AWP: 3. 重要度スコアリング
    loop 各論文（並列、max=3）
        AWP->>LLM: chat_json(importance_prompt with trends)
        LLM-->>AWP: {technical_novelty, industry_impact, practicality, trend_relevance}
    end

    Note over AWP: 4. 上位N件を選出
    AWP->>AWP: sorted by importance_score

    Note over AWP: 5. ハイライト生成
    loop 各上位論文（並列、max=3）
        AWP->>LLM: chat_json(highlights_prompt)
        LLM-->>AWP: {selection_reason, key_points}
    end

    AWP-->>CLI: {trend_info, papers, total_papers}

    CLI->>SP: format_arxiv_weekly(start, end, papers, trend_summary)
    SP-->>CLI: formatted_message

    alt Slack送信（非dry-run）
        CLI->>SP: send_message(message)
        SP->>Slack: POST webhook
        Slack-->>SP: 200 OK
        SP-->>CLI: true
    end

    CLI-->>User: 処理完了
```

## クラス関係図

```mermaid
classDiagram
    class ArxivCollector {
        +str base_url
        +ClientSession http_session
        +__aenter__()
        +__aexit__()
        +search(queries, start_date, end_date, max_results)
        +fetch_paper_details_async(paper_url)
    }

    class MediumCollector {
        +Service gmail_service
        +ClientSession http_session
        +str credentials_path
        +__aenter__()
        +__aexit__()
        +get_digest_emails(date)
        +parse_articles(html_content)
        +fetch_article_content(url, max_retries)
        +extract_email_body(message)
        -_authenticate_gmail()
        -_clean_url(url)
        -_extract_author_from_jina(content)
    }

    class GoogleAlertsCollector {
        +Service gmail_service
        +str credentials_path
        +get_alerts_emails(hours_back, date)
        +parse_alerts(message)
        +fetch_article_content(url, retry_count)
        +fetch_articles_for_alerts(alerts)
        -_authenticate_gmail()
        -_extract_body(message)
    }

    class YouTubeCollector {
        +Path output_dir
        +str whisper_model
        +dict ydl_opts
        +download_audio(url)
        +transcribe_audio(audio_file)
        +process_video(url)
        +get_video_info(url)
    }

    class Translator {
        +str model
        +Client client
        +translate_to_japanese(text, context)
        +translate_with_summary(title, content, author)
    }

    class Summarizer {
        +str model
        +Client client
        +summarize(text, max_length, language)
        +extract_key_points(text, num_points)
    }

    class NotionPublisher {
        +str api_key
        +str source_type
        +Client client
        +check_existing(database_id, url)
        +create_page(database_id, properties)
        +save_article(database_id, article_data)
        +batch_save_articles(database_id, articles, max_concurrent)
        -_normalize_url_by_source(url)
        -_build_article_properties(article_data)
        -_build_arxiv_properties(article_data)
        -_build_medium_properties(article_data)
        -_build_google_alerts_properties(article_data)
    }

    class SlackPublisher {
        +str webhook_url
        +ClientSession http_session
        +__aenter__()
        +__aexit__()
        +set_webhook_url(webhook_url)
        +send_message(message, webhook_url)
        +format_articles_message(articles, date, title)
        +send_articles(articles, webhook_url, date, title)
    }

    class Config {
        -Config _instance
        -dict _config
        -bool _initialized
        +load_config()
        +get(key_path, default)
        +get_api_key(service)$
        +reload()
        +to_dict()
    }

    class Article {
        +str title
        +str url
        +str author
        +str preview
        +str japanese_title
        +str summary
        +str japanese_summary
        +str date_processed
    }

    class Alert {
        +str title
        +str url
        +str source
        +str snippet
        +str japanese_title
        +str japanese_summary
        +str date_processed
        +str article_content
        +str email_date
        +List~str~ tags
    }

    class NotionReader {
        +str api_key
        +Client client
        +get_articles_by_date_range(database_id, start_date, end_date, date_property)
        +get_database_info(database_id)
        -_page_to_article(page)
        -_extract_property_value(prop)
    }

    class WeeklyDigestProcessor {
        +BaseLLMClient llm
        +BaseEmbeddingClient embedding_client
        +int max_concurrent
        +bool dedup_enabled
        +float similarity_threshold
        +float buffer_ratio
        +rank_articles_by_importance(articles)
        +select_top_articles(articles, top_n, deduplicate, buffer_ratio, similarity_threshold)
        +generate_trend_summary(articles)
        +generate_article_summaries(articles)
        +process(articles, top_n, deduplicate)
    }

    class DuplicateDetector {
        +BaseEmbeddingClient embedding_client
        +float similarity_threshold
        +detect_duplicates(articles)
        +select_representatives(groups, top_n)
        -_prepare_text(article)
        -_compute_embeddings(articles)
        -_cluster_by_similarity(embeddings)
    }

    class UnionFind {
        +List~int~ parent
        +List~int~ rank
        +find(x)
        +union(x, y)
        +get_groups()
    }

    class TrendResearcher {
        +str api_key
        +TavilyClient client
        +get_current_trends(query, max_results)
        -_extract_trends(response)
        -_generate_summary_from_results(results)
    }

    class ArxivWeeklyProcessor {
        +BaseLLMClient llm
        +TrendResearcher trend_researcher
        +int max_concurrent
        +rank_papers_by_importance(papers, trends)
        +select_top_papers(papers, top_n)
        +generate_paper_highlights(papers)
        +process(papers, top_n, use_trends)
        -_translate_trend_summary(trend_info)
        -_safe_get_score(value, default)
    }

    DuplicateDetector --> UnionFind : uses
    ArxivWeeklyProcessor --> TrendResearcher : uses
    ArxivWeeklyProcessor --> BaseLLMClient : uses

    class BaseLLMClient {
        <<abstract>>
        +chat(messages, model)*
        +generate(prompt, model)*
    }

    class BaseEmbeddingClient {
        <<abstract>>
        +embed_texts(texts)*
        +embed_text(text)*
    }

    class LangChainOllamaClient {
        +str default_model
        +chat(messages, model)
        +generate(prompt, model)
        +chat_json(messages, model)
    }

    class LangChainOpenAIClient {
        +str api_key
        +str default_model
        +chat(messages, model)
        +generate(prompt, model)
        +chat_json(messages, model)
    }

    class OllamaEmbeddingClient {
        +str model
        +embed_texts(texts)
        +embed_text(text)
    }

    class OpenAIEmbeddingClient {
        +str model
        +embed_texts(texts)
        +embed_text(text)
    }

    MediumCollector ..> Article : creates
    GoogleAlertsCollector ..> Alert : creates

    Translator --> Config : uses
    Summarizer --> Config : uses
    NotionPublisher --> Config : uses

    WeeklyDigestProcessor --> BaseLLMClient : uses
    WeeklyDigestProcessor --> DuplicateDetector : uses
    DuplicateDetector --> BaseEmbeddingClient : uses

    LangChainOllamaClient --|> BaseLLMClient : implements
    LangChainOpenAIClient --|> BaseLLMClient : implements
    OllamaEmbeddingClient --|> BaseEmbeddingClient : implements
    OpenAIEmbeddingClient --|> BaseEmbeddingClient : implements
```

## 非同期処理の状態遷移図

```mermaid
stateDiagram-v2
    [*] --> Pending: タスク作成

    Pending --> Running: Semaphore取得
    Running --> Success: 処理完了
    Running --> Retry: エラー発生

    Retry --> Waiting: リトライ待機
    Waiting --> Running: 待機完了 & リトライ回数 < 上限
    Waiting --> Failed: リトライ回数 >= 上限

    Success --> [*]: 結果返却
    Failed --> [*]: エラーログ出力

    note right of Pending
        asyncio.gather()で
        タスクがキューイング
    end note

    note right of Running
        Semaphoreで並列数制限
        max_concurrent=3
    end note

    note right of Retry
        Exponential Backoff
        2^attempt 秒待機
    end note
```

## 設定読み込みフロー図

```mermaid
flowchart TB
    START["Config インスタンス取得"] --> CHECK_INSTANCE{"_instance が存在?"}
    CHECK_INSTANCE -->|No| CREATE["新規インスタンス作成"]
    CHECK_INSTANCE -->|Yes| RETURN_INSTANCE["既存インスタンス返却"]
    CREATE --> LOAD_DOTENV[".env ファイル読み込み"]
    LOAD_DOTENV --> LOAD_CONFIG["load_config() 実行"]

    LOAD_CONFIG --> SEARCH_YAML{"settings.yaml 検索"}
    SEARCH_YAML --> PATH1["./settings.yaml"]
    SEARCH_YAML --> PATH2["./settings.yml"]
    SEARCH_YAML --> PATH3["~/.minitools/settings.yaml"]
    SEARCH_YAML --> PATH4["project_root/settings.yaml"]

    PATH1 --> CHECK_EXISTS1{"存在?"}
    PATH2 --> CHECK_EXISTS2{"存在?"}
    PATH3 --> CHECK_EXISTS3{"存在?"}
    PATH4 --> CHECK_EXISTS4{"存在?"}

    CHECK_EXISTS1 -->|Yes| LOAD_YAML["YAML読み込み"]
    CHECK_EXISTS1 -->|No| PATH2
    CHECK_EXISTS2 -->|Yes| LOAD_YAML
    CHECK_EXISTS2 -->|No| PATH3
    CHECK_EXISTS3 -->|Yes| LOAD_YAML
    CHECK_EXISTS3 -->|No| PATH4
    CHECK_EXISTS4 -->|Yes| LOAD_YAML
    CHECK_EXISTS4 -->|No| USE_DEFAULT["デフォルト設定使用"]

    LOAD_YAML --> INITIALIZED["_initialized = True"]
    USE_DEFAULT --> INITIALIZED
    INITIALIZED --> RETURN_INSTANCE
```

## バッチ処理フロー図

```mermaid
flowchart TB
    START["batch_save_articles 開始"] --> INIT["Semaphore(max_concurrent)初期化<br>stats = {success:0, skipped:0, failed:0}"]

    INIT --> CREATE_TASKS["全記事のタスク作成"]
    CREATE_TASKS --> GATHER["asyncio.gather(*tasks)"]

    GATHER --> TASK_LOOP{"各タスク実行"}

    TASK_LOOP --> ACQUIRE["semaphore.acquire()"]
    ACQUIRE --> CHECK_DUP["check_existing(url)"]

    CHECK_DUP --> DUP_RESULT{"重複?"}
    DUP_RESULT -->|Yes| SKIP["stats.skipped += 1"]
    DUP_RESULT -->|No| SAVE["save_article()"]

    SAVE --> SAVE_RESULT{"成功?"}
    SAVE_RESULT -->|Yes| SUCCESS["stats.success += 1"]
    SAVE_RESULT -->|No| FAIL["stats.failed += 1"]

    SKIP --> RELEASE["semaphore.release()"]
    SUCCESS --> RELEASE
    FAIL --> RELEASE

    RELEASE --> MORE_TASKS{"残タスク?"}
    MORE_TASKS -->|Yes| TASK_LOOP
    MORE_TASKS -->|No| LOG_RESULT["結果ログ出力"]

    LOG_RESULT --> RETURN["stats 返却"]
```

## URL正規化フロー図

```mermaid
flowchart TB
    START["_normalize_url_by_source(url)"] --> CHECK_SOURCE{"source_type?"}

    CHECK_SOURCE -->|arxiv| ARXIV_NORM["ArXiv正規化"]
    CHECK_SOURCE -->|medium| MEDIUM_NORM["Medium正規化"]
    CHECK_SOURCE -->|google_alerts| GA_NORM["Google Alerts正規化"]
    CHECK_SOURCE -->|other| RETURN_AS_IS["そのまま返却"]

    ARXIV_NORM --> ARXIV_1["http:// → https://"]
    ARXIV_1 --> ARXIV_2["export.arxiv.org → arxiv.org"]
    ARXIV_2 --> RETURN["正規化URL返却"]

    MEDIUM_NORM --> MEDIUM_1["クエリパラメータ除去<br>url.split('?')[0]"]
    MEDIUM_1 --> MEDIUM_2["末尾スラッシュ除去<br>url.rstrip('/')"]
    MEDIUM_2 --> MEDIUM_3["フラグメント除去<br>url.split('#')[0]"]
    MEDIUM_3 --> RETURN

    GA_NORM --> GA_1["クエリパラメータ除去"]
    GA_1 --> GA_2["末尾スラッシュ除去"]
    GA_2 --> GA_3["フラグメント除去"]
    GA_3 --> RETURN

    RETURN_AS_IS --> RETURN
```

## エラーリカバリーフロー図

```mermaid
flowchart TB
    START["HTTP リクエスト開始"] --> TRY["リクエスト実行"]

    TRY --> STATUS{"ステータス確認"}

    STATUS -->|200 OK| SUCCESS["成功: コンテンツ返却"]
    STATUS -->|403/422/429| RATE_LIMIT["レート制限エラー"]
    STATUS -->|その他エラー| OTHER_ERROR["その他エラー"]

    TRY -->|Timeout| TIMEOUT["タイムアウト"]
    TRY -->|Exception| EXCEPTION["例外発生"]

    RATE_LIMIT --> CHECK_RETRY1{"attempt < max_retries?"}
    TIMEOUT --> CHECK_RETRY2{"attempt < max_retries?"}
    EXCEPTION --> CHECK_RETRY3{"attempt < max_retries?"}
    OTHER_ERROR --> LOG_ERROR["エラーログ出力"]

    CHECK_RETRY1 -->|Yes| WAIT1["ランダム待機<br>(attempt+1) * uniform(2,5)"]
    CHECK_RETRY1 -->|No| FALLBACK{"フォールバック可能?"}

    CHECK_RETRY2 -->|Yes| WAIT2["待機<br>(attempt+1) * 2秒"]
    CHECK_RETRY2 -->|No| FALLBACK

    CHECK_RETRY3 -->|Yes| WAIT3["待機<br>(attempt+1) * 1.5秒"]
    CHECK_RETRY3 -->|No| FALLBACK

    WAIT1 --> TRY
    WAIT2 --> TRY
    WAIT3 --> TRY

    FALLBACK -->|Yes| USE_FALLBACK["フォールバック値使用<br>（preview, snippet等）"]
    FALLBACK -->|No| RETURN_EMPTY["空文字列返却"]

    USE_FALLBACK --> SUCCESS
    LOG_ERROR --> RETURN_EMPTY
```
