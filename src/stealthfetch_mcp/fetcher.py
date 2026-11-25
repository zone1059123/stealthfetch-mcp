"""Asynchronous HTTP fetching and Chromium rendering."""

import os
from urllib.parse import urlsplit

from bs4 import BeautifulSoup
from curl_cffi import requests
from playwright.async_api import Error as BrowserError
from playwright.async_api import async_playwright

MAX_HTML_BYTES = 4 * 1024 * 1024


class FetchError(RuntimeError):
    """The page could not be fetched."""


def validate_url(url: str) -> None:
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Provide an absolute HTTP or HTTPS URL.")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("URLs containing credentials are unsupported.")
    _ = parsed.port


def _is_shell(html: str) -> bool:
    if not html.strip():
        return True
    soup = BeautifulSoup(html, "html.parser")
    return len(soup.get_text(strip=True)) < 80 and (
        len(html) < 512 or soup.find("script") is not None
    )


async def _render(url: str, timeout: int) -> dict:
    try:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(
                executable_path=os.getenv("STEALTHFETCH_CHROMIUM") or None
            )
            try:
                page = await browser.new_page(accept_downloads=False)
                response = await page.goto(url, wait_until="networkidle", timeout=timeout * 1000)
                if response is None or not response.ok:
                    status = response.status if response else "unknown"
                    raise FetchError(f"Chromium returned HTTP {status}.")
                html = await page.content()
                if len(html.encode()) > MAX_HTML_BYTES:
                    raise FetchError("Rendered HTML exceeds 4 MiB.")
                return {"url": page.url, "html": html, "transport": "playwright"}
            finally:
                await browser.close()
    except BrowserError as exc:
        if "Executable doesn't exist" in str(exc) or "Failed to launch chromium because executable" in str(exc):
            raise FetchError(
                "Chromium is unavailable. Run 'playwright install chromium' in the "
                "server environment, or set STEALTHFETCH_CHROMIUM to a Chromium executable."
            ) from exc
        raise FetchError("Chromium could not render the page within the configured limits.") from exc


async def fetch_html(url: str, render_js: bool = False, timeout: int = 20) -> dict:
    """Fetch HTML with a browser fingerprint, then render challenges or short shells."""
    validate_url(url)
    if timeout <= 0:
        raise ValueError("timeout must be greater than zero.")
    if render_js:
        return await _render(url, timeout)

    try:
        async with requests.AsyncSession(impersonate="chrome") as session:
            async with session.stream("GET", url, timeout=timeout, max_redirects=5) as response:
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
                    async for chunk in response.aiter_content():
                        body.extend(chunk)
                        if len(body) > MAX_HTML_BYTES:
                            raise FetchError("HTML response exceeds 4 MiB.")
                    try:
                        html = body.decode(response.encoding, errors="replace")
                    except LookupError:
                        html = body.decode("utf-8", errors="replace")
                    if not _is_shell(html):
                        return {"url": response.url, "html": html, "transport": "curl_cffi"}
    except requests.RequestsError:
        pass

    return await _render(url, timeout)
