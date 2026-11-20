import pytest

from src.tools.calculator import CALCULATOR_SCHEMA, calculator
from src.tools.web_search import WEB_SEARCH_SCHEMA, web_search
from src.utils.llm_json import extract_json


@pytest.mark.parametrize(
    "expr, expected",
    [("2+3*4", 14), ("(95-80)/80*100", 18.75), ("sqrt(16)", 4.0), ("-2**3", -8), ("max(1, 5)", 5)],
)
def test_calculator(expr, expected):
    assert calculator(expr) == {"success": True, "expression": expr, "result": expected}


@pytest.mark.parametrize(
    "expr", ["__import__('os').system('echo hi')", "open('x')", "1/0", "2**99999", "a+1", "1+"]
)
def test_calculator_rejects_unsafe_or_invalid(expr):
    assert calculator(expr)["success"] is False


def test_web_search_mock():
    out = web_search("llm agents", num_results=50)
    assert out["mock"] and len(out["results"]) == 10
    assert "llm+agents" in out["results"][0]["url"]


def test_schemas_are_openai_shape():
    for schema in (CALCULATOR_SCHEMA, WEB_SEARCH_SCHEMA):
        assert schema["type"] == "function"
        assert schema["function"]["parameters"]["required"]


@pytest.mark.parametrize(
    "text, expected",
    [
        ('{"a": 1}', {"a": 1}),
        ('```json\n{"a": 2}\n```', {"a": 2}),
        ('Sure! Here it is: [{"id": 0}] hope that helps', [{"id": 0}]),
        ("```\n[1, 2]\n```", [1, 2]),
    ],
)
def test_extract_json(text, expected):
    assert extract_json(text) == expected


@pytest.mark.parametrize("text", ["", "no json here", "{broken"])
def test_extract_json_errors(text):
    with pytest.raises(ValueError):
        extract_json(text)
