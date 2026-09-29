import pytest

from vingroup_crawler.errors import CrawlerError
from vingroup_crawler.extractor import _normalize_date, extract_article


ARTICLE_HTML = """
<html><head>
<meta property="og:title" content="Tập đoàn công bố dự án">
<script type="application/ld+json">{"@type":"NewsArticle","headline":"Tập đoàn công bố dự án","datePublished":"2025-08-07T09:00:00+07:00"}</script>
</head><body><nav>Menu</nav><article class="detail-content">
<p>Đây là đoạn mở đầu đủ dài để trình bày nội dung chính của bài viết thử nghiệm.</p>
<h2>Thông tin dự án</h2>
<p>Dự án được triển khai tại Việt Nam với nhiều hạng mục quan trọng trong năm nay.</p>
<p>Đại diện doanh nghiệp cho biết kế hoạch sẽ tạo thêm nhiều giá trị cho cộng đồng địa phương.</p>
<div class="related"><p>Tin liên quan này không được đưa vào nội dung bài.</p></div>
</article><footer>Footer</footer></body></html>
"""


def test_extracts_article_and_headings():
    article = extract_article(ARTICLE_HTML, "https://vingroup.net/tin-tuc-su-kien/bai-viet/123/du-an-moi")
    assert article.title == "Tập đoàn công bố dự án"
    assert article.publication_date == "2025-08-07"
    assert len(article.paragraphs) == 3
    assert article.headings == {2: "Thông tin dự án"}
    assert article.article_id == "123"
    assert "liên quan" not in " ".join(article.paragraphs)


def test_rejects_listing_page():
    with pytest.raises(CrawlerError, match="article body"):
        extract_article("<html><h1>News</h1><a>Item one</a><a>Item two</a></html>", "https://vingroup.net/news")


def test_normalizes_english_publication_date():
    assert _normalize_date("January 15, 2026") == "2026-01-15"


def test_extracts_date_from_clock_icon_paragraph():
    html = ARTICLE_HTML.replace('"datePublished"', '"notADate"').replace(
        '<nav>Menu</nav>', '<nav>Menu</nav><p><i class="far fa-clock"></i>18-05-2026</p>'
    )
    article = extract_article(html, "https://vingroup.net/en/news/detail/6926/example")
    assert article.publication_date == "2026-05-18"
