import pytest

from vingroup_crawler.discovery import article_language, discover_urls
from vingroup_crawler.errors import CrawlerError
from test_extractor import ARTICLE_HTML


def test_direct_urls_support_multiple_articles_and_reject_other_sections():
    urls = ["https://vingroup.net/tin-tuc-su-kien/bai-viet/9080/one",
            "https://vingroup.net/en/news/detail/42/two"]
    html = ARTICLE_HTML.replace("2025-08-07T09:00:00+07:00", "2026-01-15T09:00:00+07:00")
    found, _, failures = discover_urls(urls + [urls[0]], fetch=lambda url: (html, url))
    assert [(item.language, item.article_id) for item in found] == [("vi", "9080"), ("en", "42")]
    assert failures == []
    with pytest.raises(CrawlerError, match="Not a Vietnamese or English"):
        article_language("https://vingroup.net/en/news-events/articles/42/two")
