# Deployment Guide

The pipeline is designed to run locally. There are no servers to host: the MCP server is started on demand as a subprocess.

## Setup

```bash
python -m venv venv
venv\Scripts\activate            # Windows
# source venv/bin/activate       # macOS/Linux
pip install -r requirements.txt
cp .env.example .env             # set LITELLM_MODEL and the matching API key
python scripts/verify_setup.py
```

## Running

```bash
python src/complete_pipeline.py              # full run
python src/complete_pipeline.py --skip-fetch # reuse the last fetch (saves time while iterating on prompts)
```

## Scheduling

**macOS/Linux (cron), daily at 09:00:**
```
0 9 * * * cd /path/to/AIUpskillProject && venv/bin/python src/complete_pipeline.py >> data/pipeline.log 2>&1
```

**Windows Task Scheduler:**
1. Create Basic Task → Daily, 09:00.
2. Action: Start a program → `C:\path\to\AIUpskillProject\venv\Scripts\python.exe`
3. Arguments: `src\complete_pipeline.py`
4. Start in: `C:\path\to\AIUpskillProject`

## Monitoring

```bash
# How many articles are stored, by source
python -c "import asyncio; from src.storage.db_manager import DatabaseManager as D; print(asyncio.run(D().get_sources()))"
```
Set `LOG_LEVEL=DEBUG` in `.env` for verbose logs. Retries after provider errors are logged as `WARNING`.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `No model configured` | Set `LITELLM_MODEL` in `.env`. |
| Repeated `ServiceUnavailableError` / `RateLimitError` warnings | The provider is overloaded or you hit the free-tier limit. The run retries automatically. If it still fails, try again later or switch model. |
| A run seems stuck with no output | Each request has a deadline (`LLM_TIMEOUT_SECONDS`, default 90 s) and is retried up to 4 times, so a run fails within minutes rather than hanging. Check the provider's status page. |
| `AuthenticationError` | Wrong or missing API key for the provider named in `LITELLM_MODEL`. |
| `ModuleNotFoundError: src` | Run from the project root, or use `python -m src.complete_pipeline`. |
| GitHub source returns 0 articles | Anonymous Search API limit (10/min). Wait a minute or set `GITHUB_TOKEN`. |
| Emoji show as `?` in old Windows consoles | Cosmetic only. Use Windows Terminal, or set `PYTHONIOENCODING=utf-8`. |
