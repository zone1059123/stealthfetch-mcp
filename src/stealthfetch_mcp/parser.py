"""Extract machine-readable metadata and human-readable Markdown."""

import json
import re
from typing import Any
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup
from markdownify import markdownify

_MONEY = re.compile(
    r"(?<!\w)(?:(USD|EUR|GBP|JPY|TWD|CAD|AUD)\s+|([$€£¥])\s*)"
    r"(\d+(?:[,.]\d+)*(?:[ \u00a0]\d{3})*)(?!\w)"
    r"|(\d+(?:[,.]\d+)*)\s+(USD|EUR|GBP|JPY|TWD|CAD|AUD)\b",
    re.IGNORECASE,
)
_SYMBOLS = {"€": "EUR", "£": "GBP"}


def _structured_prices(value: Any):
    if isinstance(value, dict):
        currency = value.get("priceCurrency")
        if isinstance(currency, str) and re.fullmatch(r"[A-Za-z]{3}", currency):
            for key in ("price", "lowPrice", "highPrice"):
                amount = value.get(key)
                if type(amount) in (str, int, float) and str(amount).strip():
                    yield {"amount": str(amount), "currency": currency.upper()}
        for child in value.values():
            yield from _structured_prices(child)
    elif isinstance(value, list):
        for child in value:
            yield from _structured_prices(child)


def parse(html: str, url: str) -> dict[str, Any]:
    soup = BeautifulSoup(html, "html.parser")
    title = soup.title.get_text(" ", strip=True) if soup.title else None
    json_ld = []
    open_graph: dict[str, list[str]] = {}
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            value = json.loads(tag.get_text())
        except (ValueError, RecursionError):
            continue
        if isinstance(value, (dict, list)):
            json_ld.append(value)
    for tag in soup.find_all("meta", property=True, content=True):
        prop = tag["property"].lower()
        if prop.startswith(("og:", "product:")):
            open_graph.setdefault(prop, []).append(tag["content"])

    for element in soup.select(
        "head, script, style, noscript, template, iframe, svg, nav, footer, "
        "aside, form, [hidden], [aria-hidden=true]"
    ):
        element.decompose()

    content = soup.find("main") or soup.find("article") or soup.body or soup
    for tag in content.find_all(["a", "img"]):
        attr = "href" if tag.name == "a" else "src"
        if tag.has_attr(attr):
            destination = urljoin(url, tag[attr])
            if urlsplit(destination).scheme in {"http", "https"}:
                tag[attr] = destination
            else:
                del tag[attr]

    prices = list(_structured_prices(json_ld))
    for prefix in ("product:price", "og:price"):
        amounts = open_graph.get(f"{prefix}:amount", [])
        currencies = open_graph.get(f"{prefix}:currency", [])
        prices.extend(
            {"amount": amount, "currency": currency.upper()}
            for amount, currency in zip(amounts, currencies)
        )
    for match in _MONEY.finditer(content.get_text(" ", strip=True)):
        code, symbol, amount, trailing_amount, trailing_code = match.groups()
        currency = code or trailing_code or _SYMBOLS.get(symbol)
        price = {"amount": amount or trailing_amount, "currency": currency.upper() if currency else None}
        if symbol and not currency:
            price["symbol"] = symbol
        prices.append(price)

    unique_prices = list({tuple(sorted(price.items())): price for price in prices}.values())
    return {
        "title": title,
        "json_ld": json_ld,
        "open_graph": open_graph,
        "markdown": markdownify(str(content), heading_style="ATX").strip(),
        "prices": unique_prices,
    }
