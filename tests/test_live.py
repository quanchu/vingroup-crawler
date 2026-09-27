import os

import pytest

from vingroup_crawler.crawler import fetch_html
from vingroup_crawler.extractor import extract_article


@pytest.mark.live
def test_live_extraction():
    url = os.getenv("VINGROUP_LIVE_URL")
    if not url:
        pytest.skip("set VINGROUP_LIVE_URL to opt in")
    html, resolved = fetch_html(url)
    article = extract_article(html, resolved)
    assert article.paragraphs
    assert article.title
