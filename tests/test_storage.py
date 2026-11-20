import json

from src.storage.base_storage import ArticleStorage
from src.storage.json_storage import JSONStorage
from src.storage.markdown_storage import MarkdownStorage
from src.utils.markdown_parser import parse_articles_markdown


def test_markdown_storage_save(tmp_storage, make_article):
    path = tmp_storage.save([make_article(1)], "one.md")
    content = path.read_text(encoding="utf-8")
    assert path.name == "one.md"
    assert "**Total Articles:** 1" in content and "## Article 1" in content


def test_markdown_storage_multiple_articles_parse_back(tmp_storage, make_article):
    articles = [make_article(i) for i in range(5)]
    parsed = parse_articles_markdown(tmp_storage.save(articles, "many.md").read_text("utf-8"))
    assert [p["url"] for p in parsed] == [a.url for a in articles]


def test_markdown_storage_default_filename(tmp_storage, make_article):
    assert tmp_storage.save([make_article()]).name.startswith("articles_")


def test_unicode_is_preserved(tmp_storage, make_article):
    path = tmp_storage.save([make_article(title="Café — naïve 🚀")], "u.md")
    assert "Café — naïve 🚀" in path.read_text(encoding="utf-8")


def test_json_storage_is_substitutable(tmp_path, make_article):
    storage: ArticleStorage = JSONStorage(tmp_path)
    path = storage.save([make_article(1), make_article(2)], "x.md")
    data = json.loads(path.read_text(encoding="utf-8"))
    assert path.suffix == ".json" and data["total"] == 2
    assert data["articles"][0]["published_at"].startswith("2026-01-01")


def test_storages_implement_interface():
    assert issubclass(MarkdownStorage, ArticleStorage)
    assert issubclass(JSONStorage, ArticleStorage)
