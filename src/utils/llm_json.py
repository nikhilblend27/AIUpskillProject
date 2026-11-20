"""Pull JSON out of LLM replies, which often wrap it in prose or ``` fences."""

from __future__ import annotations

import json
import re
from typing import Any

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)


def extract_json(text: str) -> Any:
    """Return the first JSON object/array found in `text`.

    Raises ValueError if nothing parseable is present.
    """
    if not text or not text.strip():
        raise ValueError("empty LLM response")

    candidates = [m.group(1) for m in _FENCE_RE.finditer(text)] + [text]
    decoder = json.JSONDecoder()
    for candidate in candidates:
        candidate = candidate.strip()
        for i, ch in enumerate(candidate):
            if ch in "{[":
                try:
                    value, _ = decoder.raw_decode(candidate[i:])
                    return value
                except json.JSONDecodeError:
                    continue
    raise ValueError(f"no JSON found in LLM response: {text[:120]!r}")
