from __future__ import annotations

import os
import plistlib
import sys
from collections.abc import Callable
from pathlib import Path
from urllib.parse import urljoin, urlsplit
from xml.parsers.expat import ExpatError

import httpx

from .errors import CrawlerError

ALLOWED_HOSTS = {"vingroup.net", "www.vingroup.net"}
MAX_REDIRECTS = 5
MAX_BYTES = 5 * 1024 * 1024
USER_AGENT = "vingroup-crawler/0.1 (+article research)"
BROWSER_TIMEOUT_MS = 30_000
CHALLENGE_MARKERS = (
    b"<title>Just a moment...</title>",
    b"/cdn-cgi/challenge-platform/",
    b"Enable JavaScript and cookies to continue",
)


def validate_url(url: str) -> str:
    try:
        parsed = urlsplit(url.strip())
        port = parsed.port
    except ValueError as exc:
        raise CrawlerError(f"Invalid URL: {exc}") from exc
    if parsed.scheme not in {"http", "https"}:
        raise CrawlerError("URL must use http:// or https://")
    if parsed.username or parsed.password or port not in {None, 80, 443}:
        raise CrawlerError("URL credentials and nonstandard ports are not allowed")
    if (parsed.hostname or "").lower() not in ALLOWED_HOSTS:
        raise CrawlerError("URL host must be exactly vingroup.net or www.vingroup.net")
    return url.strip()


def _read_limited(response: httpx.Response) -> bytes:
    declared = response.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > MAX_BYTES:
        raise CrawlerError(f"Page exceeds the {MAX_BYTES // 1024 // 1024} MiB download limit")
    chunks: list[bytes] = []
    size = 0
    for chunk in response.iter_bytes():
        size += len(chunk)
        if size > MAX_BYTES:
            raise CrawlerError(f"Page exceeds the {MAX_BYTES // 1024 // 1024} MiB download limit")
        chunks.append(chunk)
    return b"".join(chunks)


def _is_cloudflare_challenge(response: httpx.Response, body: bytes) -> bool:
    return (
        response.headers.get("cf-mitigated", "").lower() == "challenge"
        or any(marker.lower() in body.lower() for marker in CHALLENGE_MARKERS)
        or (response.status_code == 403 and response.headers.get("server", "").lower() == "cloudflare")
    )


def _default_browser_executable(
    preferences: Path | None = None,
    application_dirs: tuple[Path, ...] | None = None,
) -> Path:
    preferences = preferences or Path.home() / "Library/Preferences/com.apple.LaunchServices/com.apple.launchservices.secure.plist"
    application_dirs = application_dirs or (Path("/Applications"), Path.home() / "Applications", Path("/System/Applications"))
    try:
        handlers = plistlib.loads(preferences.read_bytes()).get("LSHandlers", [])
        browser_id = next(
            (item.get("LSHandlerRoleAll") for item in handlers
             if item.get("LSHandlerContentType") == "com.apple.default-app.web-browser"),
            None,
        ) or next(
            (item.get("LSHandlerRoleAll") for item in handlers if item.get("LSHandlerURLScheme") == "https"),
            None,
        )
    except (OSError, ValueError, TypeError, ExpatError) as exc:
        raise CrawlerError(f"Could not read macOS default browser setting: {exc}") from exc
    if not browser_id:
        raise CrawlerError("macOS has no default browser configured")
    if browser_id.casefold() == "com.apple.safari":
        raise CrawlerError("Default Safari cannot be launched through Playwright's Chromium engine")
    for directory in application_dirs:
        for bundle in directory.glob("*.app"):
            try:
                info = plistlib.loads((bundle / "Contents/Info.plist").read_bytes())
            except (OSError, ValueError, TypeError, ExpatError):
                continue
            if str(info.get("CFBundleIdentifier", "")).casefold() == browser_id.casefold():
                executable = bundle / "Contents/MacOS" / info.get("CFBundleExecutable", "")
                if executable.is_file():
                    return executable
    raise CrawlerError(f"Could not locate the macOS default browser application ({browser_id})")


def fetch_html_with_browser(url: str) -> tuple[str, str]:
    """Try an unattended Chromium fetch after an HTTP challenge."""
    original = validate_url(url)
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except ImportError as exc:  # pragma: no cover - installation error
        raise CrawlerError("Chromium fallback is unavailable; run `uv sync` first") from exc

    profile = Path(os.getenv("VINGROUP_BROWSER_PROFILE", ".vingroup-browser-profile"))
    profile.mkdir(parents=True, exist_ok=True)
    blocked_navigation: list[str] = []
    try:
        with sync_playwright() as playwright:
            launch_options = {
                "headless": True,
                "viewport": {"width": 1280, "height": 900},
                "locale": "vi-VN",
                "ignore_default_args": ["--enable-automation"],
                "args": ["--disable-blink-features=AutomationControlled"],
            }
            channel = os.getenv("VINGROUP_BROWSER_CHANNEL", "default" if sys.platform == "darwin" else "chromium").strip()
            if channel == "default":
                launch_options["executable_path"] = str(_default_browser_executable())
            elif channel and channel != "chromium":
                launch_options["channel"] = channel
            try:
                context = playwright.chromium.launch_persistent_context(
                    str(profile),
                    **launch_options,
                )
            except PlaywrightError as exc:
                if channel and channel not in {"chromium", "default"} and (
                    "Executable doesn't exist" in str(exc) or "not found" in str(exc).lower()
                ):
                    launch_options.pop("channel", None)
                    try:
                        context = playwright.chromium.launch_persistent_context(
                            str(profile), **launch_options
                        )
                    except PlaywrightError as fallback_exc:
                        if "Executable doesn't exist" in str(fallback_exc):
                            raise CrawlerError(
                                "Chromium is not installed; run `uv run playwright install chromium`"
                            ) from fallback_exc
                        raise
                elif "Executable doesn't exist" in str(exc):
                    raise CrawlerError(
                        "Chromium is not installed; run `uv run playwright install chromium`"
                    ) from exc
                else:
                    raise
            try:
                page = context.pages[0] if context.pages else context.new_page()
                page.set_default_timeout(BROWSER_TIMEOUT_MS)
                page.add_init_script(
                    "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
                )

                def route_request(route) -> None:
                    request = route.request
                    if request.is_navigation_request() and request.frame == page.main_frame:
                        try:
                            validate_url(request.url)
                        except CrawlerError:
                            blocked_navigation.append(request.url)
                            route.abort("blockedbyclient")
                            return
                    if request.resource_type in {"image", "media", "font"}:
                        route.abort("blockedbyclient")
                    else:
                        route.continue_()

                page.route("**/*", route_request)
                response = page.goto(original, wait_until="domcontentloaded", timeout=BROWSER_TIMEOUT_MS)
                if blocked_navigation:
                    raise CrawlerError("Browser navigation attempted to leave vingroup.net")
                if response is None:
                    raise CrawlerError("Chromium received no response from Vingroup")
                request = response.request
                hops = 0
                while request is not None:
                    validate_url(request.url)
                    request = request.redirected_from
                    hops += 1
                    if hops > MAX_REDIRECTS + 1:
                        raise CrawlerError(f"Too many redirects (maximum {MAX_REDIRECTS})")
                page.wait_for_function(
                    """() => {
                        const title = document.title.toLowerCase();
                        const html = document.documentElement.innerHTML;
                        return !title.includes('just a moment') &&
                               !html.includes('/cdn-cgi/challenge-platform/') &&
                               document.body && document.body.innerText.trim().length > 100;
                    }""",
                    timeout=BROWSER_TIMEOUT_MS,
                )
                if blocked_navigation:
                    raise CrawlerError("Browser navigation attempted to leave vingroup.net")
                resolved = validate_url(page.url)
                content_type = (response.headers.get("content-type") or "").split(";", 1)[0].lower()
                if content_type and content_type not in {"text/html", "application/xhtml+xml"}:
                    raise CrawlerError(f"Expected HTML but received {content_type}")
                html = page.content()
                if len(html.encode("utf-8")) > MAX_BYTES:
                    raise CrawlerError(f"Page exceeds the {MAX_BYTES // 1024 // 1024} MiB download limit")
                return html, resolved
            finally:
                context.close()
    except PlaywrightTimeoutError as exc:
        raise CrawlerError(
            f"Cloudflare challenge did not clear in unattended {channel or 'Chromium'} within 30 seconds; Vingroup is blocking automated access"
        ) from exc
    except CrawlerError:
        raise
    except PlaywrightError as exc:
        raise CrawlerError(f"Chromium fallback failed: {exc}") from exc


def fetch_html(
    url: str,
    *,
    client: httpx.Client | None = None,
    browser_fetcher: Callable[[str], tuple[str, str]] | None = None,
) -> tuple[str, str]:
    current = validate_url(url)
    owned = client is None
    http = client or httpx.Client(
        follow_redirects=False,
        timeout=httpx.Timeout(15.0, connect=10.0),
        headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"},
    )
    try:
        for hop in range(MAX_REDIRECTS + 1):
            try:
                with http.stream("GET", current) as response:
                    if response.status_code in {301, 302, 303, 307, 308}:
                        if hop == MAX_REDIRECTS:
                            raise CrawlerError(f"Too many redirects (maximum {MAX_REDIRECTS})")
                        location = response.headers.get("location")
                        if not location:
                            raise CrawlerError("Redirect response did not include a Location header")
                        current = validate_url(urljoin(current, location))
                        continue
                    if response.status_code in {403, 429, 503}:
                        raw = _read_limited(response)
                        if _is_cloudflare_challenge(response, raw):
                            fallback = browser_fetcher or fetch_html_with_browser
                            return fallback(current)
                        response.raise_for_status()
                    response.raise_for_status()
                    content_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
                    if content_type not in {"text/html", "application/xhtml+xml"}:
                        raise CrawlerError(f"Expected HTML but received {content_type or 'an unknown content type'}")
                    raw = _read_limited(response)
                    if _is_cloudflare_challenge(response, raw):
                        fallback = browser_fetcher or fetch_html_with_browser
                        return fallback(current)
                    encoding = response.encoding or "utf-8"
                    return raw.decode(encoding, errors="replace"), validate_url(str(response.url))
            except httpx.HTTPStatusError as exc:
                raise CrawlerError(f"Vingroup returned HTTP {exc.response.status_code}") from exc
            except httpx.HTTPError as exc:
                raise CrawlerError(f"Could not download the article: {exc}") from exc
        raise CrawlerError("Redirect handling failed")
    finally:
        if owned:
            http.close()
