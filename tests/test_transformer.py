import time
from datetime import UTC

from src.transformers.article_transformer import ArticleTransformer, clean_text

T = ArticleTransformer()


def test_hackernews_transform_and_skips():
    raw = [
        {"id": 1, "type": "story", "title": "Story", "url": "https://a", "time": 0, "score": 5},
        {
            "id": 2,
            "type": "story",
            "title": "Ask HN: thing",
            "time": 0,
            "text": "<p>Hi &amp; bye</p>",
        },
        {"id": 3, "type": "job", "title": "Hiring", "url": "https://job"},
        {"id": 4, "type": "story", "title": "Dead", "url": "https://d", "dead": True},
        {"id": 5, "type": "story", "url": "https://no-title"},
        None,
    ]
    articles = T.transform_hackernews(raw)
    assert [a.title for a in articles] == ["Story", "Ask HN: thing"]
    assert articles[0].score == 5 and articles[0].source == "hackernews"
    assert articles[1].url == "https://news.ycombinator.com/item?id=2"
    assert articles[1].summary == "Hi & bye"
    assert articles[0].published_at.tzinfo == UTC


def test_rss_transform_dates_and_html():
    entries = [
        {
            "title": "A",
            "link": "https://a",
            "summary": "<b>bold</b> text",
            "published_parsed": time.gmtime(86400),
        },
        {"title": "B", "link": "https://b", "published": "Tue, 10 Jun 2025 04:00:00 GMT"},
        {"title": "C", "link": "https://c", "updated": "2025-06-10T04:00:00Z"},
        {"title": "D", "link": "https://d", "published": "garbage"},
        {"title": "", "link": "https://skip"},
        {"title": "no link"},
    ]
    articles = T.transform_rss(entries, source="rss_x")
    assert [a.title for a in articles] == ["A", "B", "C", "D"]
    assert articles[0].summary == "bold text" and articles[0].published_at.year == 1970
    assert articles[1].published_at.year == 2025 and articles[2].published_at.month == 6
    assert all(a.source == "rss_x" for a in articles)


def test_clean_text_truncates():
    out = clean_text("word " * 200, max_chars=50)
    assert len(out) <= 50 and out.endswith("...")
    assert clean_text(None) == ""
