"""Base class for every agent (M3).

* Template Method: `execute()` = load -> process -> save; subclasses fill in steps.
* LLM access goes through LiteLLM, so the provider is just the LITELLM_MODEL env var.
* Transient provider errors (rate limits, 5xx, timeouts) are retried with backoff.
* `_call_llm_with_tools()` runs the OpenAI-style function-calling loop.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
import os
from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any

import litellm

logger = logging.getLogger(__name__)
litellm.suppress_debug_info = True  # we log retries ourselves

# Errors worth retrying — the request may succeed if we wait a bit.
_RETRYABLE = (
    litellm.RateLimitError,
    litellm.ServiceUnavailableError,
    litellm.InternalServerError,
    litellm.APIConnectionError,
    litellm.Timeout,
)

MAX_TOOL_ROUNDS = 10


class BaseAgent(ABC):
    def __init__(
        self,
        model: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        temperature: float | None = None,
        max_retries: int = 4,
        retry_base_delay: float = 2.0,
        request_timeout: float | None = None,
    ):
        self.model = model or os.getenv("LITELLM_MODEL")
        if not self.model:
            raise ValueError(
                "No model configured. Set LITELLM_MODEL in .env or pass model= to the agent."
            )
        self.tools: list[dict[str, Any]] = list(tools or [])
        self.tool_functions: dict[str, Callable[..., Any]] = {}
        self.temperature = temperature
        self.max_retries = max_retries
        self.retry_base_delay = retry_base_delay
        self.request_timeout = float(request_timeout or os.getenv("LLM_TIMEOUT_SECONDS", 90))
        self.llm_calls = 0

    @property
    def name(self) -> str:
        return self.__class__.__name__

    # -- Template Method ---------------------------------------------------
    async def execute(self, input_path: str, output_path: str) -> dict[str, Any]:
        logger.info("%s starting (model=%s)", self.name, self.model)
        context = await self._load_context(input_path)
        result = await self._process(context)
        await self._save_result(result, output_path)
        self.last_result = result  # full in-memory result, for callers that need more than the file
        logger.info("%s done — %d LLM calls", self.name, self.llm_calls)
        return {
            "agent": self.name,
            "input_path": str(input_path),
            "output_path": str(output_path),
            "success": True,
            "llm_calls": self.llm_calls,
            "stats": result.get("stats", {}),
        }

    @abstractmethod
    async def _load_context(self, input_path: str) -> dict[str, Any]: ...

    @abstractmethod
    async def _process(self, context: dict[str, Any]) -> dict[str, Any]: ...

    @abstractmethod
    async def _save_result(self, result: dict[str, Any], output_path: str) -> None: ...

    # -- LLM helpers -------------------------------------------------------
    @staticmethod
    def _messages(prompt: str, system: str | None) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        return messages

    async def _completion(self, **kwargs: Any) -> Any:
        """litellm.acompletion with retry/backoff on transient errors."""
        if self.temperature is not None:
            kwargs.setdefault("temperature", self.temperature)
        for attempt in range(self.max_retries + 1):
            try:
                self.llm_calls += 1
                # Hard deadline: without it a stalled provider connection hangs the run forever.
                return await asyncio.wait_for(
                    litellm.acompletion(model=self.model, timeout=self.request_timeout, **kwargs),
                    timeout=self.request_timeout * 1.1 + 1,
                )
            except (*_RETRYABLE, TimeoutError) as exc:
                # A daily quota won't reset within our backoff window — fail fast.
                daily_quota = isinstance(exc, litellm.RateLimitError) and "perday" in str(
                    exc
                ).lower().replace(" ", "")
                if attempt == self.max_retries or daily_quota:
                    raise
                # Rate limits need a longer pause than a blip.
                factor = 5 if isinstance(exc, litellm.RateLimitError) else 1
                delay = self.retry_base_delay * factor * (2**attempt)
                logger.warning(
                    "%s: %s (attempt %d/%d) — retrying in %.0fs",
                    self.name,
                    type(exc).__name__,
                    attempt + 1,
                    self.max_retries,
                    delay,
                )
                await asyncio.sleep(delay)
        raise RuntimeError("unreachable")

    async def _call_llm(self, prompt: str, system: str | None = None) -> str:
        response = await self._completion(messages=self._messages(prompt, system))
        return response.choices[0].message.content or ""

    # -- Function calling --------------------------------------------------
    def register_tool_function(self, name: str, function: Callable[..., Any]) -> None:
        """Bind a Python callable (sync or async) to a tool schema name."""
        self.tool_functions[name] = function

    async def _run_tool(self, name: str, raw_args: str | None) -> Any:
        if name not in self.tool_functions:
            return {"success": False, "error": f"Unknown tool {name!r}"}
        try:
            args = json.loads(raw_args or "{}")
            result = self.tool_functions[name](**args)
            if inspect.isawaitable(result):
                result = await result
            return result
        except Exception as exc:  # noqa: BLE001 — report tool errors back to the model
            logger.warning("tool %s failed: %s", name, exc)
            return {"success": False, "error": str(exc)}

    async def _call_llm_with_tools(
        self, prompt: str, system: str | None = None, max_rounds: int = MAX_TOOL_ROUNDS
    ) -> str:
        """Loop: model asks for tools -> we run them -> feed results back -> until text."""
        messages = self._messages(prompt, system)
        self.tool_trace: list[dict[str, Any]] = []
        for _ in range(max_rounds):
            response = await self._completion(messages=messages, tools=self.tools or None)
            msg = response.choices[0].message
            tool_calls = getattr(msg, "tool_calls", None)
            if not tool_calls:
                return msg.content or ""

            messages.append(msg.model_dump(exclude_none=True))
            for call in tool_calls:
                result = await self._run_tool(call.function.name, call.function.arguments)
                self.tool_trace.append(
                    {"tool": call.function.name, "args": call.function.arguments, "result": result}
                )
                logger.info("tool %s(%s)", call.function.name, call.function.arguments)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "name": call.function.name,
                        "content": json.dumps(result, default=str),
                    }
                )
        raise RuntimeError(f"Tool-call loop exceeded {max_rounds} rounds")
