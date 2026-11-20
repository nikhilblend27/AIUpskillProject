# Architecture

This document covers the implemented system. The curriculum's orientation doc is in [`architecture/overview.md`](architecture/overview.md), and the reasons behind the design are in [`design-decisions.md`](design-decisions.md).

## Data flow

```
 HackerNewsFetcher   RSSFetcher (Verge)   GitHubTrendingFetcher        ← src/fetchers/
        └──────────────┬──────────────────────┘
                       ▼
              FetchOrchestrator  — asyncio.gather, de-dupe by URL         ← src/orchestrator.py
                       │
                       ▼
        data/articles/all_articles.md ─────► MCP save_articles ─► SQLite
                       │                                       (data/news_agent.db)
                       ▼                                              ▲
              NewsFilterAgent  — batched LLM judging, threshold 6     │
                       │  data/context/filtered_articles.md           │
                       ├──────────────► MCP save_articles (scores) ───┤
                       ▼                                              │
              SummarizerAgent  ◄── SearchSkill.search(topic) ── MCP search_articles
                       │  data/context/summary.md
                       ▼
                WriterAgent
                       │
                       ▼
          data/output/newsletter.md
```

## Components

### Fetchers (M1–M2)
- `BaseFetcher` holds the shared logic: an aiohttp session with a timeout and User-Agent, rate-limited `_get_json` and `_get_text`, and the `fetch_and_save` template method.
- **HackerNews** gets the top-story IDs, then fetches each story at the same time under a `SemaphoreStrategy(10)`. Text-only posts link to the HN thread.
- **RSS** downloads with aiohttp and parses with feedparser in a worker thread. The source name is derived from the host, for example `rss_theverge_com`.
- **GitHub Trending** uses the Search API: repositories created in the last 7 days, sorted by stars. Set `GITHUB_TOKEN` for higher rate limits.

### Agents (M3–M4)
All agents extend `BaseAgent`, which provides:
- `execute(input, output)`, which runs `_load_context` → `_process` → `_save_result`
- `_call_llm`, which calls LiteLLM `acompletion` with exponential backoff on 429, 5xx, timeouts and connection errors
- `_call_llm_with_tools`, the OpenAI-style function-calling loop (at most 10 rounds; tool errors are returned to the model)

| Agent | Input → Output | LLM calls |
|---|---|---|
| `NewsFilterAgent` | all_articles.md → filtered_articles.md | ⌈N/10⌉ |
| `EnhancedFilterAgent` | same, with calculator and web_search tools | ≥ N |
| `SummarizerAgent` | filtered_articles.md → summary.md | ≤ 6 (one per topic group) |
| `WriterAgent` | summary.md → newsletter.md | 1 |

### MCP (M4)
- `src/mcp_servers/database_server.py` serves five tools over stdio: `save_articles`, `search_articles`, `get_article`, `query_articles` and `get_sources`. The tool logic is in `handle_tool()`, so it can be unit-tested without the transport.
- `src/mcp_servers/client.py` starts any server module as `python -m <module>` and opens a `ClientSession`.
- `src/skills/search_skill.py` is the agent-facing API. Use it as `async with SearchSkill()` to keep one server process open for the whole pipeline.
- `hello_server.py` and `simple_client.py` are the Evening 16 hello-world.

### Storage
- `MarkdownStorage` and `JSONStorage` implement `ArticleStorage`.
- `DatabaseManager` uses SQLite with an upsert on `url`. A later save without a relevance score never erases an earlier one. Search uses escaped `LIKE` over title, summary and topics.

### Evaluation (M5)
`FilterEvaluator` runs `NewsFilterAgent.judge_articles` on `data/evaluation/golden_dataset.json`. It reports accuracy, precision, recall, F1, the confusion matrix, score MAE and an analysis of each failure in `data/evaluation/evaluation_report.md`.

## Configuration

| Env var | Default | Purpose |
|---|---|---|
| `LITELLM_MODEL` | (required) | Any LiteLLM model string |
| `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / `GEMINI_API_KEY` | — | Key for whichever provider you chose |
| `NEWS_DB_PATH` | `data/news_agent.db` | SQLite file used by the MCP server |
| `GITHUB_TOKEN` | — | Optional. Raises the GitHub API rate limit |
| `LLM_TIMEOUT_SECONDS` | `90` | Deadline for each LLM request. Requests that time out are retried |
| `LOG_LEVEL` | `INFO` | Logging verbosity |

Sources are configured in `src/config.py` (`DEFAULT_SOURCES`). Adding an RSS feed is a one-line change there.

## Performance (measured on a laptop, 2026-11-19)

- Fetching 55 articles from 3 sources: about 2.4 s
- Full pipeline: 11 LLM calls in total. Wall time is dominated by the LLM provider (about 4 minutes on `gemini-3.6-flash`, including retries after 503 errors).
- Offline test suite: 106 tests in about 32 s, 84 % line coverage.

## Security

- API keys live only in `.env`, which is gitignored.
- The calculator never uses `eval`. It walks the AST against a whitelist and caps exponents.
- SQL is always parameterised, and `LIKE` wildcards in search input are escaped.
- The MCP server only exposes the article store. It has no arbitrary SQL tool.
