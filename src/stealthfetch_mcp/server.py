"""MCP stdio entry point."""

import asyncio
from typing import Any

from mcp.server.fastmcp import FastMCP

from .fetcher import fetch, validate_url
from .license import LicenseManager
from .parser import parse

mcp = FastMCP("stealthfetch-mcp")


def _fetch_page(url: str, render_js: bool) -> dict[str, Any]:
    validate_url(url)
    access = LicenseManager.from_environment().acquire()
    if not access.allowed:
        raise ValueError("Free daily quota exhausted. It resets at midnight UTC.")
    page = fetch(url, render_js=render_js)
    return {
        "url": page.url,
        "transport": page.transport,
        **parse(page.html, page.url),
        "usage": {"tier": access.tier, "remaining_today": access.remaining},
    }


@mcp.tool()
async def fetch_page(url: str, render_js: bool = False) -> dict[str, Any]:
    """Fetch an HTTP(S) page and extract Markdown, metadata, and prices.

    Set render_js for pages whose content depends on JavaScript.
    """
    return await asyncio.to_thread(_fetch_page, url, render_js)


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
