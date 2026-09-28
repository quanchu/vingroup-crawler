from datetime import date

from vingroup_crawler.discovery import discover_articles, parse_listing
from test_extractor import ARTICLE_HTML


def test_parse_vietnamese_listing_and_next_page():
    html = """
    <a href="/tin-tuc-su-kien/bai-viet/9080/article-one">One</a>
    <div class="pagination"><a class="next" href="?page=2">Tiếp</a></div>
    """
    links, next_url = parse_listing(html, "https://vingroup.net/tin-tuc-su-kien?page=1", "vi")
    assert links == ["https://vingroup.net/tin-tuc-su-kien/bai-viet/9080/article-one"]
    assert next_url == "https://vingroup.net/tin-tuc-su-kien?page=2"


def test_discovery_filters_detail_dates():
    vi_listing = '<a href="/tin-tuc-su-kien/bai-viet/9080/one">One</a>'
    en_listing = '<a href="/en/news-events/articles/42/two">Two</a>'
    vi_detail = ARTICLE_HTML.replace("2025-08-07T09:00:00+07:00", "2026-01-15T09:00:00+07:00")
    en_detail = ARTICLE_HTML.replace("2025-08-07T09:00:00+07:00", "2025-12-31T09:00:00+07:00")

    def fetch(url):
        if url.endswith("tin-tuc-su-kien"):
            return vi_listing, url
        if url.endswith("news-events"):
            return en_listing, url
        if "9080" in url:
            return vi_detail, url
        return en_detail, url

    found, articles, failures = discover_articles(date(2026, 1, 1), date(2026, 1, 31), fetch=fetch)
    assert [(item.language, item.article_id) for item in found] == [("vi", "9080")]
    assert ("vi", "9080") in articles
    assert failures == []
