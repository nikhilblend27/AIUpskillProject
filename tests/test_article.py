from datetime import datetime

import pytest

from src.models.article import Article
from src.utils.markdown_parser import parse_articles_markdown, parse_topics


def test_article_creation(sample_article_kwargs):
    article = Article(**sample_article_kwargs)
    assert article.title == "Sample article for tests"
    assert article.summary == "" and article.score == 0


@pytest.mark.parametrize("field", ["title", "url"])
def test_article_requires_title_and_url(sample_article_kwargs, field):
    sample_article_kwargs[field] = "  "
    with pytest.raises(ValueError):
        Article(**sample_article_kwargs)


def test_article_normalises_whitespace(sample_article_kwargs):
    sample_article_kwargs["title"] = "  Multi \n line   title "
    assert Article(**sample_article_kwargs).title == "Multi line title"


def test_to_markdown_round_trips_through_parser(make_article):
    article = make_article(3, summary="Hello world")
    parsed = parse_articles_markdown(article.to_markdown())
    assert parsed == [
        {
            "title": "Article 3",
            "source": "test",
            "url": "https://example.com/3",
            "published": "2026-01-01 12:03",
            "score": "3",
            "summary": "Hello world",
        }
    ]


def test_to_dict_serialises_datetime(sample_article_kwargs):
    data = Article(**sample_article_kwargs).to_dict()
    assert data["published_at"] == datetime(2026, 1, 1, 12).isoformat()


def test_parser_skips_file_header_and_stops_at_separator():
    md = "# Header\n\n**Total:** 2\n\n---\n\n## A\n\n**URL:** u1\n\nbody a\n\n---\n\n## B\n\nbody b\n"
    parsed = parse_articles_markdown(md)
    assert [p["title"] for p in parsed] == ["A", "B"]
    assert parsed[0]["url"] == "u1" and parsed[0]["summary"] == "body a"
    assert "total" not in parsed[0]


@pytest.mark.parametrize(
    "value, expected",
    [("LLM, agents ,", ["LLM", "agents"]), (["x", " "], ["x"]), (None, []), ("", [])],
)
def test_parse_topics(value, expected):
    assert parse_topics(value) == expected
