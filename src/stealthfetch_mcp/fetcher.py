"""HTTP fetching with a JavaScript-rendering fallback."""

import os
from dataclasses import dataclass
from urllib.parse import urlsplit

from curl_cffi import requests
from playwright.sync_api import Error as BrowserError
from playwright.sync_api import sync_playwright

MAX_HTML_BYTES = 4 * 1024 * 1024


@dataclass(frozen=True)
class Page:
    url: str
    html: str
    transport: str


class FetchError(RuntimeError):
    """The page could not be fetched."""


def validate_url(url: str) -> None:
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Provide an absolute HTTP or HTTPS URL.")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("URLs containing credentials are unsupported.")
    _ = parsed.port


def _render(url: str) -> Page:
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                executable_path=os.getenv("STEALTHFETCH_CHROMIUM") or None
            )
            try:
                page = browser.new_page(accept_downloads=False)
                response = page.goto(url, wait_until="load", timeout=25_000)
                if response is None or not response.ok:
                    status = response.status if response else "unknown"
                    raise FetchError(f"Browser returned HTTP {status}.")
                html = page.content()
                if len(html.encode()) > MAX_HTML_BYTES:
                    raise FetchError("Rendered page exceeds 4 MiB.")
                return Page(page.url, html, "playwright")
            finally:
                browser.close()
    except BrowserError as exc:
        raise FetchError(
            "Chromium rendering failed. Check the URL and Chromium installation."
        ) from exc


def fetch(url: str, *, render_js: bool = False) -> Page:
    """Fetch HTML over HTTP first, then render if necessary or requested."""
    validate_url(url)
    if render_js:
        return _render(url)

    try:
        with requests.Session(impersonate="chrome") as session:
            with session.stream("GET", url, timeout=15, max_redirects=5) as response:
                if response.status_code == 429:
                    raise FetchError("The site is rate limiting requests. Try again later.")
                if response.status_code not in {403, 503}:
                    if not 200 <= response.status_code < 300:
                        raise FetchError(f"Site returned HTTP {response.status_code}.")
                    content_type = response.headers.get("content-type", "").lower()
                    if content_type and not content_type.startswith(
                        ("text/html", "application/xhtml+xml")
                    ):
                        raise FetchError("The URL did not return HTML.")
                    body = bytearray()
                    for chunk in response.iter_content():
                        body.extend(chunk)
                        if len(body) > MAX_HTML_BYTES:
                            raise FetchError("HTML response exceeds 4 MiB.")
                    try:
                        html = body.decode(response.encoding, errors="replace")
                    except LookupError:
                        html = body.decode("utf-8", errors="replace")
                    if html.strip():
                        return Page(response.url, html, "curl_cffi")
    except requests.RequestsError:
        pass

    return _render(url)
