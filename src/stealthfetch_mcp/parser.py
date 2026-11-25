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


def _main_content(soup: BeautifulSoup):
    for element in soup.select(
        "head, script, style, noscript, template, iframe, svg, nav, footer, "
        "aside, form, [hidden], [aria-hidden=true], [role=banner], "
        ".ad, .ads, .advertisement, .sponsored, [data-ad-slot]"
    ):
        element.decompose()
    return soup.find("main") or soup.find("article") or soup.body or soup


def _http_url(url: str, value: str) -> str | None:
    try:
        destination = urljoin(url, value.strip())
        parsed = urlsplit(destination)
        if parsed.scheme in {"http", "https"} and (parsed.hostname or not url):
            return destination
        if not url and not parsed.scheme:
            return destination
    except ValueError:
        pass
    return None


def _markdown(content, max_chars: int) -> str:
    if max_chars < 0:
        raise ValueError("max_chars must be nonnegative.")
    result = markdownify(str(content), heading_style="ATX").strip()
    return re.sub(r"\n{3,}", "\n\n", result)[:max_chars].rstrip()


def html_to_clean_markdown(html: str, max_chars: int = 15000) -> str:
    """Keep the main page content and return at most max_chars characters."""
    return _markdown(_prepare_content(BeautifulSoup(html, "html.parser"), ""), max_chars)


def _prepare_content(soup: BeautifulSoup, url: str):
    content = _main_content(soup)
    for tag in content.find_all(["a", "img"]):
        attr = "href" if tag.name == "a" else "src"
        if tag.has_attr(attr):
            destination = _http_url(url, tag[attr])
            if destination:
                tag[attr] = destination
            else:
                del tag[attr]
    return content


def _extract(html: str, url: str, *, include_markdown: bool = False) -> dict[str, Any]:
    soup = BeautifulSoup(html, "html.parser")
    title = soup.title.get_text(" ", strip=True) if soup.title else None
    json_ld = []
    open_graph: dict[str, list[str]] = {}
    twitter: dict[str, list[str]] = {}
    description = None
    for tag in soup.find_all("script"):
        if tag.get("type", "").split(";", 1)[0].strip().lower() != "application/ld+json":
            continue
        try:
            value = json.loads(tag.get_text())
        except (ValueError, RecursionError):
            continue
        if isinstance(value, (dict, list)):
            json_ld.append(value)
    for tag in soup.find_all("meta", content=True):
        prop = (tag.get("property") or tag.get("name") or "").lower()
        if prop.startswith(("og:", "product:")):
            open_graph.setdefault(prop, []).append(tag["content"])
        elif prop.startswith("twitter:"):
            twitter.setdefault(prop, []).append(tag["content"])
        elif prop == "description" and description is None:
            description = tag["content"].strip()

    content = _prepare_content(soup, url)
    text = content.get_text(" ", strip=True)
    description = (
        description or next(iter(open_graph.get("og:description", [])), None)
        or next(iter(twitter.get("twitter:description", [])), None) or text
    )
    links = list(dict.fromkeys(
        link for tag in content.find_all("a", href=True)
        if (link := tag["href"])
    ))[:50]

    prices = list(_structured_prices(json_ld))
    for prefix in ("product:price", "og:price"):
        amounts = open_graph.get(f"{prefix}:amount", [])
        currencies = open_graph.get(f"{prefix}:currency", [])
        prices.extend(
            {"amount": amount, "currency": currency.upper()}
            for amount, currency in zip(amounts, currencies)
        )
    for match in _MONEY.finditer(text):
        code, symbol, amount, trailing_amount, trailing_code = match.groups()
        currency = code or trailing_code or _SYMBOLS.get(symbol)
        price = {"amount": amount or trailing_amount, "currency": currency.upper() if currency else None}
        if symbol and not currency:
            price["symbol"] = symbol
        prices.append(price)

    unique_prices = list({tuple(sorted(price.items())): price for price in prices}.values())
    result = {
        "title": title,
        "summary": description[:500],
        "json_ld": json_ld,
        "open_graph": open_graph,
        "twitter": twitter,
        "links": links,
        "prices": unique_prices,
    }
    if include_markdown:
        result["markdown"] = _markdown(content, 15000)
    return result


def extract_structured_payload(html: str, url: str) -> dict:
    """Extract metadata, the first 50 unique links, and price candidates."""
    return _extract(html, url)


def parse(html: str, url: str) -> dict[str, Any]:
    """Return metadata together with the main Markdown content."""
    return _extract(html, url, include_markdown=True)
