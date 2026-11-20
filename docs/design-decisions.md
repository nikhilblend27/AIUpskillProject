# Design Decisions

This document records why the code is shaped the way it is: the SOLID refactor from Milestone 2, and the choices made in Milestones 3–5 where the implementation departs from the curriculum's sample code.

## 1. SOLID principles

| Principle | Where | What it buys us |
|---|---|---|
| **Single Responsibility** | `ArticleTransformer` only shapes data. Fetchers only do I/O. `MarkdownStorage` only writes files. | We can test parsing without the network and storage without fetching. |
| **Open/Closed** | `BaseFetcher` + `FetcherFactory.register()` | `GitHubTrendingFetcher` was added with **zero edits** to existing fetchers, the orchestrator or the factory body. |
| **Liskov Substitution** | Contract in the `BaseFetcher` docstring, enforced by `tests/test_substitutability.py` | Every fetcher returns `list[Article]`, and returns `[]` (never `None`, never an exception) when its source is down. |
| **Interface Segregation** | `fetchers/interfaces.py` (`AuthenticatedFetcher`, `PaginatedFetcher`) | `BaseFetcher` has only two abstract methods. Only GitHub opts into auth. |
| **Dependency Inversion** | `ArticleStorage` ABC. `FetchOrchestrator(fetchers, storage)` | Tests inject mocks. Switching to `JSONStorage` is a one-line change in `src/main.py`, the only composition root. |

## 2. Design patterns

- **Template Method:** `BaseFetcher.fetch_and_save()` runs fetch → save, and `BaseAgent.execute()` runs load → process → save. Subclasses fill in only the steps that vary.
- **Factory:** `FetcherFactory` builds fetchers from names or from a config list (`config.DEFAULT_SOURCES`).
- **Strategy:** `RateLimitStrategy` has three implementations: `SemaphoreStrategy` (caps how many requests run at once), `TokenBucketStrategy` (caps requests per second and allows bursts) and `NoRateLimitStrategy` (a null object for tests). Each fetcher can take a different one.
- **Skill / Facade:** `SearchSkill` hides the MCP client behind `search()` and `save_articles()`.

## 3. Deviations from the curriculum sample code

| Curriculum sample | What we did | Why |
|---|---|---|
| `src/mcp/` package | `src/mcp_servers/` | A local package named `mcp` shadows the `mcp` SDK, so `from mcp.server import Server` would import our own folder. |
| `Tool(input_schema=...)` | `Tool(inputSchema=...)` | This is the field name in the pinned `mcp==1.1.2`. The other spelling silently drops the schema. |
| `aiosqlite` | stdlib `sqlite3` + `asyncio.to_thread` | Same async API with no extra dependency. |
| BeautifulSoup scraping of github.com/trending | GitHub Search API (`created:>7d`, sorted by stars) | No `bs4` dependency, a stable JSON contract, and no HTML that breaks when GitHub redesigns. |
| `print()` inside the MCP server | Logs go to stderr | stdout carries the JSON-RPC protocol. A stray print corrupts the stream. |
| One LLM call per article | Batches of 10 articles per call | Free-tier providers allow about 10 requests a minute. 55 articles take 6 calls instead of 55, and cost about 10× less. |
| Synchronous `completion()` | `litellm.acompletion` with retry and backoff | Agents stay async, and transient 429/503 errors (seen often on Gemini) are retried instead of crashing the run. |
| `eval()`-style calculator | AST whitelist evaluator | `eval` on LLM-supplied input is remote code execution. |
| Pipeline writes directly to `DatabaseManager` | Pipeline writes through MCP (`save_articles`) | Exercises the MCP server for real. The agents and the pipeline only talk to the database through MCP. |

## 4. Agent robustness

- Every LLM judgement is normalised: types are coerced, the score is clamped to 0–10, and topics are always a list.
- Unparseable or missing replies make that article "not relevant" with the error as the reasoning. One bad reply never stops the pipeline.
- `SummarizerAgent` falls back to a plain list of titles, and `WriterAgent` falls back to the raw summary, if the LLM fails.
- Tool errors are returned to the model as `{"success": false, "error": ...}` so it can recover. The tool loop stops after 10 rounds.

## 5. Trade-offs

- **More classes.** About 25 modules for a small app. Each one is short and has one job, but newcomers have more files to open.
- **Markdown as the format between stages.** It is easy to read and diff, but the stages have to parse it back. A shared parser (`utils/markdown_parser.py`) keeps writers and readers in step, and a round-trip test guards it.
- **Batched judging.** Cheaper and friendlier to rate limits. The cost is that one malformed reply affects up to 10 articles. Each of them falls back on its own, and the evaluator measures the impact.
