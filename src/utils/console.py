"""Console helpers so emoji output doesn't crash on Windows code pages."""

from __future__ import annotations

import logging
import os
import sys


def setup_console() -> None:
    """Force UTF-8 stdout/stderr, load .env, and configure logging."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    from dotenv import load_dotenv

    load_dotenv()
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(levelname)s %(name)s: %(message)s",
    )
    # LiteLLM and httpx are very chatty at INFO.
    for noisy in ("LiteLLM", "litellm", "httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
