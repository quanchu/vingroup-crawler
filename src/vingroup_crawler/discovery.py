from __future__ import annotations

import re
from collections.abc import Callable
from datetime import date
from urllib.parse import urljoin, urlsplit, urlunsplit

from bs4 import BeautifulSoup

from .errors import CrawlerError
from .extractor import extract_article, extract_article_id
from .models import Article, DiscoveredArticle

LISTING_URLS = {
    "vi": "https://vingroup.net/tin-tuc-su-kien",
    "en": "https://vingroup.net/en/news-events",
}
DETAIL_PATTERNS = {
    "vi": re.compile(r"/tin-tuc-su-kien/bai-viet/\d+(?:/|$)", re.IGNORECASE),
    "en": re.compile(r"/en/news-events/articles/\d+(?:/|$)", re.IGNORECASE),
}
NEXT_TEXT = re.compile(r"^(?:next|tiếp|sau|›|»)$", re.IGNORECASE)
Fetch = Callable[[str], tuple[str, str]]


def _canonical_url(url: str, *, keep_query: bool = False) -> str:
    parsed = urlsplit(url)
    query = parsed.query if keep_query else ""
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path.rstrip("/"), query, ""))


def parse_listing(html: str, listing_url: str, language: str) -> tuple[list[str], str | None]:
    soup = BeautifulSoup(html, "html.parser")
    pattern = DETAIL_PATTERNS[language]
    articles: list[str] = []
    seen: set[str] = set()
    for anchor in soup.select("a[href]"):
        target = _canonical_url(urljoin(listing_url, anchor.get("href", "")))
        parsed = urlsplit(target)
        if parsed.hostname not in {"vingroup.net", "www.vingroup.net"} or not pattern.search(parsed.path):
            continue
        if target not in seen:
            seen.add(target)
            articles.append(target)

    next_url: str | None = None
    candidates = list(soup.select("a[rel~=next][href], a.next[href], .pagination a[href]"))
    for anchor in candidates:
        text = " ".join(anchor.get_text(" ", strip=True).split())
        rel = {str(value).lower() for value in anchor.get("rel", [])}
        classes = {str(value).lower() for value in anchor.get("class", [])}
        if "next" not in rel and "next" not in classes and not NEXT_TEXT.match(text):
            continue
        candidate = _canonical_url(urljoin(listing_url, anchor.get("href", "")), keep_query=True)
        parsed = urlsplit(candidate)
        if parsed.hostname in {"vingroup.net", "www.vingroup.net"}:
            next_url = candidate
            break
    return articles, next_url


def discover_articles(
    start: date,
    end: date,
    *,
    fetch: Fetch,
) -> tuple[
    list[DiscoveredArticle],
    dict[tuple[str, str], Article],
    list[tuple[DiscoveredArticle, str]],
]:
    if end < start:
        raise CrawlerError("--to must be on or after --from")
    discovered: list[DiscoveredArticle] = []
    extracted: dict[tuple[str, str], Article] = {}
    failures: list[tuple[DiscoveredArticle, str]] = []
    seen_keys: set[tuple[str, str]] = set()

    for language, first_url in LISTING_URLS.items():
        listing_url: str | None = first_url
        visited_pages: set[str] = set()
        while listing_url:
            if listing_url in visited_pages:
                raise CrawlerError(f"{language} listing pagination loop detected at {listing_url}")
            visited_pages.add(listing_url)
            listing_html, resolved_listing = fetch(listing_url)
            links, next_url = parse_listing(listing_html, resolved_listing, language)
            if not links:
                raise CrawlerError(f"No {language} article links found at {resolved_listing}")

            page_dates: list[date] = []
            new_on_page = 0
            for link in links:
                article_id = extract_article_id(link)
                if not article_id:
                    continue
                key = (language, article_id)
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                new_on_page += 1
                try:
                    detail_html, resolved_url = fetch(link)
                    article = extract_article(detail_html, resolved_url)
                    if not article.article_id or not article.publication_date:
                        raise CrawlerError(f"Article is missing a canonical ID or publication date: {resolved_url}")
                    published = date.fromisoformat(article.publication_date)
                except Exception as exc:
                    failed_item = DiscoveredArticle(
                        language=language,
                        article_id=article_id,
                        source_url=link,
                        publication_date="",
                    )
                    failures.append((failed_item, str(exc)))
                    continue
                page_dates.append(published)
                if start <= published <= end:
                    actual_key = (language, article.article_id)
                    extracted[actual_key] = article
                    discovered.append(DiscoveredArticle(
                        language=language,
                        article_id=article.article_id,
                        source_url=article.source_url,
                        publication_date=article.publication_date,
                    ))

            if page_dates and max(page_dates) < start:
                break
            if not next_url or new_on_page == 0:
                break
            listing_url = next_url

    discovered.sort(key=lambda item: (item.publication_date, item.language, int(item.article_id)))
    return discovered, extracted, failures
