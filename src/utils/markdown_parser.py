"""Parse the markdown files the pipeline passes between stages.

Every stage writes articles as sections like:

    ## Title

    **Source:** hackernews
    **URL:** https://...
    **Key Topics:** LLM, agents

    Free-text summary...

    ---

This parser turns them back into dicts with snake_case keys
("Key Topics" -> "key_topics"), plus "title" and "summary".
"""

from __future__ import annotations

import re
from typing import Any

_FIELD_RE = re.compile(r"^\*\*(.+?):\*\*\s*(.*?)\s*$")


def _key(label: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", label.strip().lower()).strip("_")


def parse_articles_markdown(content: str) -> list[dict[str, Any]]:
    """Return one dict per `## ` section. Sections without a title are skipped."""
    articles: list[dict[str, Any]] = []
    for block in re.split(r"(?m)^## ", content)[1:]:
        lines = block.splitlines()
        title = lines[0].strip()
        if not title:
            continue
        item: dict[str, Any] = {"title": title}
        body: list[str] = []
        for line in lines[1:]:
            stripped = line.strip()
            if stripped == "---" or stripped.startswith("# "):
                break
            match = _FIELD_RE.match(stripped)
            if match:
                item[_key(match.group(1))] = match.group(2)
            elif stripped:
                body.append(stripped)
        item["summary"] = " ".join(body)
        articles.append(item)
    return articles


def parse_topics(value: Any) -> list[str]:
    """'LLM, agents' or ['LLM'] -> ['LLM', 'agents']."""
    if isinstance(value, list):
        return [str(t).strip() for t in value if str(t).strip()]
    if not value:
        return []
    return [t.strip() for t in str(value).split(",") if t.strip()]
