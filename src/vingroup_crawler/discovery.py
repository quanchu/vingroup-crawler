from __future__ import annotations

import re
from collections.abc import Callable
from urllib.parse import urlsplit

from .crawler import validate_url
from .errors import CrawlerError
from .extractor import extract_article, extract_article_id
from .models import Article, DiscoveredArticle

DETAIL_PATTERNS = {
    "vi": re.compile(r"^/(?:vi/)?tin-tuc-su-kien/(?:bai-viet|chi-tiet)/\d+(?:/|$)", re.IGNORECASE),
    "en": re.compile(r"^/en/news/detail/\d+(?:/|$)", re.IGNORECASE),
}
Fetch = Callable[[str], tuple[str, str]]


def article_language(url: str) -> str:
    parsed = urlsplit(validate_url(url))
    for language, pattern in DETAIL_PATTERNS.items():
        if pattern.match(parsed.path):
            return language
    raise CrawlerError(f"Not a Vietnamese or English Vingroup news article URL: {url}")


def discover_urls(urls: list[str], *, fetch: Fetch) -> tuple[list[DiscoveredArticle], dict[tuple[str, str], Article], list[tuple[DiscoveredArticle, str]]]:
    discovered: list[DiscoveredArticle] = []
    extracted: dict[tuple[str, str], Article] = {}
    failures: list[tuple[DiscoveredArticle, str]] = []
    seen: set[tuple[str, str]] = set()
    for url in urls:
        language = article_language(url)
        article_id = extract_article_id(url)
        if not article_id:
            raise CrawlerError(f"Article URL has no numeric ID: {url}")
        key = (language, article_id)
        if key in seen:
            continue
        seen.add(key)
        try:
            html, resolved = fetch(url)
            if article_language(resolved) != language or extract_article_id(resolved) != article_id:
                raise CrawlerError(f"Article redirected outside its news detail route: {resolved}")
            article = extract_article(html, resolved)
            if not article.publication_date:
                raise CrawlerError(f"Article has no publication date: {resolved}")
            item = DiscoveredArticle(language=language, article_id=article_id, source_url=resolved, publication_date=article.publication_date)
            discovered.append(item)
            extracted[key] = article
        except Exception as exc:
            failures.append((DiscoveredArticle(language=language, article_id=article_id, source_url=url, publication_date=""), str(exc)))
    return discovered, extracted, failures
