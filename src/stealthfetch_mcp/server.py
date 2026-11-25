"""StealthFetch MCP tools and stdio entry point."""

import asyncio
from typing import Any

from mcp.server.fastmcp import FastMCP

from .fetcher import FetchError, fetch_html, validate_url
from .license import UPGRADE_URL, Access, LicenseManager
from .parser import extract_structured_payload, html_to_clean_markdown

mcp = FastMCP("StealthFetch MCP")
MAX_BATCH_SIZE = 10
BATCH_CONCURRENCY = 3


def _upgrade(access: Access, *, pro_only: bool = False) -> dict[str, Any]:
    return {
        "error": {
            "code": "pro_required" if pro_only else "free_quota_exceeded",
            "message": (
                "Batch extraction requires StealthFetch Pro."
                if pro_only else "Today's 20 Free fetches are used. The quota resets at midnight UTC."
            ),
            "upgrade": {"plan": "Pro", "price_usd": 19, "billing": "one-time", "url": UPGRADE_URL},
        },
        "usage": _usage(access),
    }


def _usage(access: Access) -> dict[str, Any]:
    return {"tier": access.tier, "remaining_today": access.remaining}


async def _access(*, pro_only: bool = False) -> Access:
    return await asyncio.to_thread(LicenseManager.from_environment().acquire, pro_only=pro_only)


@mcp.tool()
async def fetch_clean_markdown(
    url: str, render_js: bool = False, max_chars: int = 15000
) -> dict[str, Any]:
    """Fetch one HTTP(S) page and return the main content as clean Markdown.

    Set render_js for pages whose content relies on JavaScript. Set max_chars
    to cap the Markdown size. Each request uses one daily fetch on the Free plan.
    """
    validate_url(url)
    if max_chars < 0:
        raise ValueError("max_chars must be nonnegative.")
    access = await _access()
    if not access.allowed:
        return _upgrade(access)
    page = await fetch_html(url, render_js)
    return {
        "url": page["url"],
        "transport": page["transport"],
        "markdown": html_to_clean_markdown(page["html"], max_chars),
        "usage": _usage(access),
    }


@mcp.tool()
async def extract_structured_data(url: str, render_js: bool = False) -> dict[str, Any]:
    """Extract JSON-LD, Open Graph, Twitter metadata, links, and prices from one URL.

    Includes the page title and summary. Set render_js when the source data is
    populated by JavaScript. Each request uses one daily fetch on the Free plan.
    """
    validate_url(url)
    access = await _access()
    if not access.allowed:
        return _upgrade(access)
    page = await fetch_html(url, render_js)
    return {
        "url": page["url"],
        "transport": page["transport"],
        **extract_structured_payload(page["html"], page["url"]),
        "usage": _usage(access),
    }


@mcp.tool()
async def batch_extract_urls(
    urls: list[str], render_js: bool = False
) -> list[dict[str, Any]] | dict[str, Any]:
    """Extract titles, summaries, and prices for up to 10 URLs with a Pro license.

    Runs at most three fetches concurrently per batch and preserves input
    order. A failed URL produces an error entry while other URLs continue.
    """
    access = await _access(pro_only=True)
    if not access.allowed:
        return _upgrade(access, pro_only=True)
    if not 1 <= len(urls) <= MAX_BATCH_SIZE:
        raise ValueError("Provide between 1 and 10 URLs.")

    slots = asyncio.Semaphore(BATCH_CONCURRENCY)

    async def extract(url: str) -> dict[str, Any]:
        try:
            async with slots:
                page = await fetch_html(url, render_js)
                data = extract_structured_payload(page["html"], page["url"])
                return {
                    "url": page["url"],
                    "title": data["title"],
                    "summary": data["summary"],
                    "prices": data["prices"],
                }
        except (FetchError, ValueError) as exc:
            return {"url": url, "error": str(exc)}

    return await asyncio.gather(*(extract(url) for url in urls))


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
