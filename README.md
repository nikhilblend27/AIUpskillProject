# AI Upskill Project: AI News Pipeline

A multi-agent pipeline that runs on your laptop. It fetches tech news from three sources, uses an LLM to keep only the AI/ML stories, summarises them by topic, and writes a daily newsletter. Articles are stored in SQLite and exposed to the agents through an **MCP** server.

Built for **Blend's AI engineering onboarding curriculum** (Milestones 0–5). The curriculum's milestone docs are in [`docs/milestones/`](docs/milestones/).

## Features

- **Async fetching** from Hacker News, RSS (The Verge) and GitHub Trending. 55 articles in about 2.5 s.
- **SOLID design:** a new source is a new class plus one config line. See [design decisions](docs/design-decisions.md).
- **LLM agents** via LiteLLM, so any provider works: Filter → Summarize → Write.
- **Function calling:** `EnhancedFilterAgent` can use calculator and web-search tools.
- **MCP database server** with five tools (save, search, get, query, sources), used by the pipeline and by `SearchSkill`.
- **Evaluation** against a golden dataset of 20 hand-labelled cases: accuracy, precision, recall, F1 and a confusion matrix.
- **106 offline tests** (no network, no LLM tokens), 84 % coverage, ruff-clean.

## Quick start

```bash
python -m venv venv
venv\Scripts\activate                 # Windows   (macOS/Linux: source venv/bin/activate)
pip install -r requirements.txt
cp .env.example .env                  # set LITELLM_MODEL + the matching API key
python scripts/verify_setup.py

python src/complete_pipeline.py       # full pipeline
```

Outputs:

| File | Contents |
|---|---|
| `data/articles/all_articles.md` | Everything that was fetched |
| `data/context/filtered_articles.md` | AI/ML-relevant articles, each with a score and reasoning |
| `data/context/summary.md` | Summaries grouped by topic |
| `data/output/newsletter.md` | **The newsletter** |
| `data/news_agent.db` | SQLite store behind the MCP server |

## Running individual pieces

```bash
python src/main.py                           # M1/M2: fetch only
python src/pipeline.py                       # M3: fetch + filter
python -m src.mcp_servers.simple_client      # M4: hello-world MCP round trip
python src/complete_pipeline.py --skip-fetch # M4: reuse the last fetch
python src/evaluation/evaluator.py           # M5: evaluate the filter
```

## Architecture

```
Fetchers ─► Orchestrator ─► all_articles.md ─► NewsFilterAgent ─► SummarizerAgent ─► WriterAgent ─► newsletter.md
                                   │                  │                  ▲
                                   └──── MCP save ────┴──── SQLite ◄─────┘ MCP search (SearchSkill)
```

Details: [docs/architecture.md](docs/architecture.md) · [docs/design-decisions.md](docs/design-decisions.md) · [docs/deployment.md](docs/deployment.md)

## Project structure

```
src/
├── models/article.py            Article dataclass
├── fetchers/                    BaseFetcher, HackerNews, RSS, GitHubTrending, optional interfaces
├── transformers/                Raw payload → Article
├── storage/                     ArticleStorage ABC, Markdown, JSON, SQLite DatabaseManager
├── strategies/                  Rate-limit strategies (Semaphore, TokenBucket, None)
├── factories/                   FetcherFactory
├── agents/                      BaseAgent, NewsFilter, EnhancedFilter, Summarizer, Writer
├── tools/                       calculator (safe AST), web_search (mock)
├── mcp_servers/                 database_server, hello_server, client helpers
├── skills/search_skill.py       Agent-facing facade over the MCP server
├── evaluation/evaluator.py      Golden-dataset metrics + report
├── utils/                       markdown parser, JSON extraction, rate limiter, console
├── config.py                    Paths + default sources
├── orchestrator.py              Concurrent fetch, de-dupe
├── main.py / pipeline.py / complete_pipeline.py   Entry points (M1-2 / M3 / M4)
tests/                           106 offline tests (+ opt-in network/llm tests)
data/evaluation/golden_dataset.json
```

## Tests and code quality

```bash
pytest                         # offline suite (default)
pytest --cov=src               # with coverage
pytest -m network              # opt-in live API smoke tests
ruff check src tests && ruff format src tests
```

## Extending

- **New source:** subclass `BaseFetcher` (implement `fetch_articles` and `get_source_name`), call `FetcherFactory.register("name", YourFetcher)`, and add `{"type": "name"}` to `DEFAULT_SOURCES`. No existing code changes.
- **New MCP tool:** add a `Tool(...)` to `TOOLS` and a branch in `handle_tool()` in `src/mcp_servers/database_server.py`, then a wrapper method on `SearchSkill`.
- **Different model:** change `LITELLM_MODEL` in `.env`, for example `claude-haiku-4-5-20251001` or `gpt-4o-mini`.

## Evaluation

See [`data/evaluation/evaluation_report.md`](data/evaluation/evaluation_report.md), which `python src/evaluation/evaluator.py` regenerates.

## Milestones

| Milestone | Status |
|---|---|
| [M0 — Setup](docs/milestones/milestone-0-setup.md) | ✅ |
| [M1 — Async News Fetcher](docs/milestones/milestone-1-async-fetcher.md) | ✅ |
| [M2 — SOLID Refactoring](docs/milestones/milestone-2-solid-refactoring.md) | ✅ |
| [M3 — First Agent](docs/milestones/milestone-3-first-agent.md) | ✅ |
| [M4 — MCP Pipeline](docs/milestones/milestone-4-mcp-pipeline.md) | ✅ |
| [M5 — Evaluation](docs/milestones/milestone-5-evaluation.md) | ✅ |
