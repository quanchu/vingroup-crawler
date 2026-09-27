from __future__ import annotations

import json
import re
from datetime import datetime
from urllib.parse import unquote, urlsplit

from bs4 import BeautifulSoup, Tag

from .errors import CrawlerError
from .models import Article

BODY_SELECTORS = (
    ".detail-content",
    ".article-detail__content",
    ".news-detail-content",
    ".news-detail__content",
    ".article-content",
    "article .content",
    "article",
    "main article",
)
TITLE_SELECTORS = ("h1", ".detail-title", ".article-title", "[itemprop='headline']")
DATE_SELECTORS = (
    "time[datetime]",
    "[itemprop='datePublished']",
    ".detail-date",
    ".article-date",
    ".news-date",
)
REMOVE_SELECTORS = (
    "script", "style", "noscript", "nav", "footer", "form", "aside",
    ".share", ".sharing", ".social", ".related", ".related-news",
    ".cookie", ".cookies", ".breadcrumb", ".pagination", ".tags",
    ".toolbar", ".advertisement", ".banner", ".comments",
)
BOILERPLATE_RE = re.compile(
    r"^(chia sẻ|share|tin liên quan|related (news|stories)|xem thêm|back to top)$",
    re.IGNORECASE,
)


def _clean(text: str) -> str:
    return re.sub(r"[ \t\r\f\v]+", " ", text).strip()


def _json_ld(soup: BeautifulSoup) -> list[dict]:
    found: list[dict] = []
    for node in soup.select("script[type='application/ld+json']"):
        try:
            value = json.loads(node.string or node.get_text())
        except (json.JSONDecodeError, TypeError):
            continue
        queue = value if isinstance(value, list) else [value]
        for item in queue:
            if not isinstance(item, dict):
                continue
            graph = item.get("@graph")
            if isinstance(graph, list):
                queue.extend(graph)
            if item.get("@type") in {"Article", "NewsArticle", "ReportageNewsArticle"}:
                found.append(item)
    return found


def _metadata(soup: BeautifulSoup) -> tuple[str | None, str | None]:
    structured = _json_ld(soup)
    title = next((str(x["headline"]).strip() for x in structured if x.get("headline")), None)
    date = next((str(x["datePublished"]).strip() for x in structured if x.get("datePublished")), None)
    if not title:
        meta = soup.select_one("meta[property='og:title']")
        title = meta.get("content", "").strip() if meta else None
    if not date:
        meta = soup.select_one("meta[property='article:published_time']")
        date = meta.get("content", "").strip() if meta else None
    return title, _normalize_date(date)


def _normalize_date(value: str | None) -> str | None:
    if not value:
        return None
    value = _clean(value)
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        pass
    match = re.search(r"(?<!\d)(\d{1,2})[/-](\d{1,2})[/-](\d{4})(?!\d)", value)
    if match:
        day, month, year = map(int, match.groups())
        try:
            return datetime(year, month, day).date().isoformat()
        except ValueError:
            return value
    return value


def _score_candidate(node: Tag) -> float:
    paragraphs = [_clean(p.get_text(" ", strip=True)) for p in node.find_all("p")]
    meaningful = [p for p in paragraphs if len(p) >= 30]
    text_len = sum(len(p) for p in meaningful)
    link_len = sum(len(_clean(a.get_text(" ", strip=True))) for a in node.find_all("a"))
    classes = " ".join(node.get("class", [])).lower()
    bonus = 300 if any(k in classes for k in ("detail", "article", "content")) else 0
    penalty = 500 if any(k in classes for k in ("list", "related", "footer", "menu")) else 0
    return text_len + len(meaningful) * 80 + bonus - link_len * 1.5 - penalty


def _find_body(soup: BeautifulSoup) -> Tag:
    for selector in BODY_SELECTORS:
        candidates = soup.select(selector)
        if candidates:
            candidate = max(candidates, key=_score_candidate)
            if _score_candidate(candidate) >= 450:
                return candidate
    candidates = soup.find_all(["main", "article", "section", "div"])
    if candidates:
        candidate = max(candidates, key=_score_candidate)
        if _score_candidate(candidate) >= 700:
            return candidate
    raise CrawlerError("Could not confidently isolate an article body; the URL may be a listing page")


def extract_article(html: str, source_url: str) -> Article:
    soup = BeautifulSoup(html, "html.parser")
    structured_title, structured_date = _metadata(soup)
    body = _find_body(soup)
    for selector in REMOVE_SELECTORS:
        for node in body.select(selector):
            node.decompose()

    title = structured_title
    if not title:
        for selector in TITLE_SELECTORS:
            node = soup.select_one(selector)
            if node and _clean(node.get_text(" ", strip=True)):
                title = _clean(node.get_text(" ", strip=True))
                break
    if not title:
        raise CrawlerError("The page has no identifiable article title")

    date = structured_date
    if not date:
        for selector in DATE_SELECTORS:
            node = soup.select_one(selector)
            if node:
                date = _normalize_date(node.get("datetime") or node.get("content") or node.get_text(" ", strip=True))
                if date:
                    break

    paragraphs: list[str] = []
    headings: dict[int, str] = {}
    pending_heading: str | None = None
    for node in body.find_all(["h2", "h3", "h4", "p"], recursive=True):
        if node.find_parent(["p", "h2", "h3", "h4"]) is not None:
            continue
        text = _clean(node.get_text(" ", strip=True))
        if not text or BOILERPLATE_RE.match(text):
            continue
        if node.name in {"h2", "h3", "h4"}:
            pending_heading = text
        elif len(text) >= 20:
            paragraphs.append(text)
            if pending_heading:
                headings[len(paragraphs)] = pending_heading
                pending_heading = None

    if len(paragraphs) < 2 or sum(map(len, paragraphs)) < 200:
        raise CrawlerError("The page does not contain enough confidently isolated article text")

    parts = [unquote(p) for p in urlsplit(source_url).path.split("/") if p]
    slug = parts[-1] if parts else "article"
    id_match = re.search(r"(?:^|[-_])(\d{3,})(?:[-_]|$)", slug)
    article_id = id_match.group(1) if id_match else None
    return Article(
        source_url=source_url,
        title=title,
        publication_date=date,
        paragraphs=paragraphs,
        headings=headings,
        article_id=article_id,
        slug=slug,
    )
