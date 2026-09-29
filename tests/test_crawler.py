import plistlib

import httpx
import pytest

from vingroup_crawler.crawler import MAX_BYTES, _default_browser_executable, fetch_html, validate_url
from vingroup_crawler.errors import CrawlerError


@pytest.mark.parametrize("url", [
    "ftp://vingroup.net/a", "https://evil.vingroup.net/a",
    "https://vingroup.net.evil.test/a", "not a url",
])
def test_rejects_unsafe_urls(url):
    with pytest.raises(CrawlerError):
        validate_url(url)


def test_accepts_exact_hosts():
    assert validate_url("https://vingroup.net/a")
    assert validate_url("http://www.vingroup.net/a")


def test_resolves_macos_default_browser_without_hardcoded_app(tmp_path):
    preferences = tmp_path / "launchservices.plist"
    preferences.write_bytes(plistlib.dumps({"LSHandlers": [
        {"LSHandlerContentType": "com.apple.default-app.web-browser", "LSHandlerRoleAll": "example.browser"}
    ]}))
    bundle = tmp_path / "Applications/Example.app/Contents"
    (bundle / "MacOS").mkdir(parents=True)
    (bundle / "Info.plist").write_bytes(plistlib.dumps({
        "CFBundleIdentifier": "example.browser", "CFBundleExecutable": "Example"
    }))
    executable = bundle / "MacOS/Example"
    executable.touch()
    assert _default_browser_executable(preferences, (tmp_path / "Applications",)) == executable


def test_rejects_external_redirect():
    transport = httpx.MockTransport(lambda request: httpx.Response(302, headers={"location": "https://example.com/x"}))
    with httpx.Client(transport=transport) as client, pytest.raises(CrawlerError, match="host must be exactly"):
        fetch_html("https://vingroup.net/start", client=client)


def test_redirect_then_html():
    def handler(request):
        if request.url.path == "/start":
            return httpx.Response(302, headers={"location": "/article"})
        return httpx.Response(200, headers={"content-type": "text/html; charset=utf-8"}, text="<html>ok</html>")
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        html, url = fetch_html("https://vingroup.net/start", client=client)
    assert html == "<html>ok</html>"
    assert url == "https://vingroup.net/article"


def test_rejects_non_html_and_oversize():
    for response, message in [
        (httpx.Response(200, headers={"content-type": "application/pdf"}, content=b"x"), "Expected HTML"),
        (httpx.Response(200, headers={"content-type": "text/html", "content-length": str(MAX_BYTES + 1)}), "download limit"),
    ]:
        with httpx.Client(transport=httpx.MockTransport(lambda request, r=response: r)) as client:
            with pytest.raises(CrawlerError, match=message):
                fetch_html("https://vingroup.net/a", client=client)


def test_cloudflare_challenge_uses_browser_fallback():
    challenge = b"<html><head><title>Just a moment...</title></head><body></body></html>"
    response = httpx.Response(
        403,
        headers={"content-type": "text/html", "server": "cloudflare", "cf-mitigated": "challenge"},
        content=challenge,
    )
    calls = []

    def fallback(url):
        calls.append(url)
        return "<html><body>article</body></html>", "https://www.vingroup.net/article"

    with httpx.Client(transport=httpx.MockTransport(lambda request: response)) as client:
        html, resolved = fetch_html(
            "https://vingroup.net/article", client=client, browser_fetcher=fallback
        )
    assert calls == ["https://vingroup.net/article"]
    assert "article" in html
    assert resolved == "https://www.vingroup.net/article"


def test_cloudflare_503_uses_unattended_fallback():
    response = httpx.Response(503, headers={"content-type": "text/html", "cf-mitigated": "challenge"},
                              text="<title>Just a moment...</title>")
    with httpx.Client(transport=httpx.MockTransport(lambda request: response)) as client:
        html, _ = fetch_html("https://vingroup.net/en/news", client=client,
                             browser_fetcher=lambda url: ("<html>news</html>", url))
    assert html == "<html>news</html>"


def test_cloudflare_200_challenge_uses_unattended_fallback():
    response = httpx.Response(200, headers={"content-type": "text/html"},
                              text="<title>Just a moment...</title>")
    with httpx.Client(transport=httpx.MockTransport(lambda request: response)) as client:
        html, _ = fetch_html("https://vingroup.net/en/news", client=client,
                             browser_fetcher=lambda url: ("<html>news</html>", url))
    assert html == "<html>news</html>"


def test_ordinary_403_does_not_use_browser_fallback():
    response = httpx.Response(403, headers={"content-type": "text/html"}, text="Forbidden")
    called = False

    def fallback(url):
        nonlocal called
        called = True
        return "", url

    with httpx.Client(transport=httpx.MockTransport(lambda request: response)) as client:
        with pytest.raises(CrawlerError, match="HTTP 403"):
            fetch_html("https://vingroup.net/article", client=client, browser_fetcher=fallback)
    assert called is False
