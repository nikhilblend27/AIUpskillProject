"""BaseAgent: template method, retries, and the function-calling loop."""

import json

import litellm
import pytest

from src.agents.base_agent import BaseAgent

from .conftest import llm_message, tool_call


class EchoAgent(BaseAgent):
    async def _load_context(self, input_path):
        return {"text": input_path}

    async def _process(self, context):
        return {
            "reply": await self._call_llm(context["text"], system="be brief"),
            "stats": {"n": 1},
        }

    async def _save_result(self, result, output_path):
        self.saved = (result, output_path)


async def test_execute_runs_template_steps(fake_llm):
    fake_llm.replies = ["hello!"]
    agent = EchoAgent(model="m")
    meta = await agent.execute("hi", "out.md")
    assert meta["success"] and meta["stats"] == {"n": 1} and meta["llm_calls"] == 1
    assert agent.saved == ({"reply": "hello!", "stats": {"n": 1}}, "out.md")
    assert fake_llm.calls[0]["messages"][0] == {"role": "system", "content": "be brief"}


def test_requires_model(monkeypatch):
    monkeypatch.delenv("LITELLM_MODEL", raising=False)
    with pytest.raises(ValueError, match="LITELLM_MODEL"):
        EchoAgent()


async def test_retries_transient_errors(fake_llm):
    err = litellm.ServiceUnavailableError("busy", llm_provider="x", model="m")
    fake_llm.replies = [err, err, "ok"]
    agent = EchoAgent(model="m", retry_base_delay=0)
    assert await agent._call_llm("q") == "ok"
    assert agent.llm_calls == 3


async def test_gives_up_after_max_retries(fake_llm):
    err = litellm.ServiceUnavailableError("busy", llm_provider="x", model="m")
    fake_llm.replies = [err, err]
    with pytest.raises(litellm.ServiceUnavailableError):
        await EchoAgent(model="m", max_retries=1, retry_base_delay=0)._call_llm("q")


async def test_non_retryable_errors_raise_immediately(fake_llm):
    fake_llm.replies = [litellm.AuthenticationError("bad key", llm_provider="x", model="m")]
    agent = EchoAgent(model="m", retry_base_delay=0)
    with pytest.raises(litellm.AuthenticationError):
        await agent._call_llm("q")
    assert agent.llm_calls == 1


async def test_tool_loop_executes_tools_and_feeds_results_back(fake_llm):
    agent = EchoAgent(model="m", tools=[{"type": "function", "function": {"name": "add"}}])
    agent.register_tool_function("add", lambda a, b: {"sum": a + b})

    async def async_tool(x):
        return x * 2

    agent.register_tool_function("double", async_tool)
    fake_llm.replies = [
        llm_message(
            tool_calls=[
                tool_call("c1", "add", '{"a": 2, "b": 3}'),
                tool_call("c2", "double", '{"x": 4}'),
            ]
        ),
        llm_message(tool_calls=[tool_call("c3", "missing", "{}")]),
        "final answer",
    ]
    assert await agent._call_llm_with_tools("compute") == "final answer"

    second_call_msgs = fake_llm.calls[1]["messages"]
    tool_msgs = [m for m in second_call_msgs if m["role"] == "tool"]
    assert [json.loads(m["content"]) for m in tool_msgs] == [{"sum": 5}, 8]
    assert fake_llm.calls[0]["tools"] == agent.tools
    last_tool = [m for m in fake_llm.calls[2]["messages"] if m["role"] == "tool"][-1]
    assert "Unknown tool" in last_tool["content"]
    assert [t["tool"] for t in agent.tool_trace] == ["add", "double", "missing"]


async def test_tool_loop_round_cap(fake_llm):
    agent = EchoAgent(model="m")
    agent.register_tool_function("t", lambda: 1)
    fake_llm.replies = [llm_message(tool_calls=[tool_call(f"c{i}", "t", "{}")]) for i in range(3)]
    with pytest.raises(RuntimeError, match="exceeded"):
        await agent._call_llm_with_tools("loop", max_rounds=3)


async def test_tool_errors_are_reported_not_raised(fake_llm):
    agent = EchoAgent(model="m")
    agent.register_tool_function("boom", lambda: 1 / 0)
    fake_llm.replies = [llm_message(tool_calls=[tool_call("c1", "boom", "{}")]), "recovered"]
    assert await agent._call_llm_with_tools("x") == "recovered"
    assert "division by zero" in fake_llm.calls[1]["messages"][-1]["content"]


async def test_hung_request_times_out_and_retries(monkeypatch):
    import asyncio

    calls = []

    async def slow_then_ok(**kwargs):
        calls.append(kwargs["timeout"])
        if len(calls) == 1:
            await asyncio.sleep(10)
        return llm_message("ok")

    monkeypatch.setattr(litellm, "acompletion", slow_then_ok)
    agent = EchoAgent(model="m", request_timeout=0.01, retry_base_delay=0)  # deadline ~1s
    assert await agent._call_llm("q") == "ok"
    assert len(calls) == 2


async def test_daily_quota_is_not_retried(fake_llm):
    err = litellm.RateLimitError(
        "Quota exceeded: GenerateRequestsPerDayPerProjectPerModel-FreeTier",
        llm_provider="gemini",
        model="m",
    )
    fake_llm.replies = [err, "never reached"]
    agent = EchoAgent(model="m", retry_base_delay=0)
    with pytest.raises(litellm.RateLimitError):
        await agent._call_llm("q")
    assert agent.llm_calls == 1
