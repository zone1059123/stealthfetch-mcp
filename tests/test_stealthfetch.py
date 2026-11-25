from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import httpx

from stealthfetch_mcp.license import FREE_DAILY_LIMIT, POLAR_VALIDATE, Access, LicenseManager
from stealthfetch_mcp.parser import parse

URL = "https://example.test/catalog/item"


def test_markdown_cleanup():
    result = parse(
        """<title>Catalog</title><nav>Menu</nav><main>
        <h1>Product</h1><script>alert('ignored')</script>
        <p hidden>Hidden</p><p><a href="/details">Details</a>
        <a href="javascript:alert(1)">Unsafe</a></p>
        </main><footer>Copyright</footer>""",
        URL,
    )

    assert result["title"] == "Catalog"
    assert result["markdown"] == "# Product\n\n[Details](https://example.test/details)\nUnsafe"


def test_structured_metadata_and_prices():
    result = parse(
        """<script type="application/ld+json">bad JSON</script>
        <script type="application/ld+json">
        {"@graph":[{"@type":"Product","offers":{"price":"19.99","priceCurrency":"usd"}}]}
        </script>
        <meta property="og:title" content="Product">
        <meta property="og:image" content="one.png">
        <meta property="og:image" content="two.png">
        <meta property="product:price:amount" content="22">
        <meta property="product:price:currency" content="gbp">
        <main>List price €24.99. Other offer $25.</main>""",
        URL,
    )

    assert len(result["json_ld"]) == 1
    assert result["json_ld"][0]["@graph"][0]["@type"] == "Product"
    assert result["open_graph"]["og:title"] == ["Product"]
    assert result["open_graph"]["og:image"] == ["one.png", "two.png"]
    assert result["prices"] == [
        {"amount": "19.99", "currency": "USD"},
        {"amount": "22", "currency": "GBP"},
        {"amount": "24.99", "currency": "EUR"},
        {"amount": "25", "currency": None, "symbol": "$"},
    ]


def test_free_quota_is_shared_and_atomic(tmp_path):
    db_path = tmp_path / "usage.sqlite3"
    manager = LicenseManager(db_path)
    with ThreadPoolExecutor(max_workers=8) as workers:
        outcomes = list(workers.map(lambda _: manager.acquire(), range(FREE_DAILY_LIMIT + 4)))

    assert sorted(outcome.remaining for outcome in outcomes if outcome.allowed) == list(
        range(FREE_DAILY_LIMIT)
    )
    assert all(outcome.tier == "free" for outcome in outcomes)
    assert LicenseManager(db_path).acquire() == Access(False, "free", 0)


def test_free_quota_resets_at_midnight_utc(tmp_path, monkeypatch):
    from stealthfetch_mcp import license

    class Clock:
        time = datetime(2026, 1, 1, 23, 59, tzinfo=UTC)

        @classmethod
        def now(cls, tz):
            return cls.time.astimezone(tz)

    monkeypatch.setattr(license, "datetime", Clock)
    manager = LicenseManager(tmp_path / "usage.sqlite3")
    for _ in range(FREE_DAILY_LIMIT):
        assert manager.acquire().allowed
    assert not manager.acquire().allowed
    Clock.time += timedelta(minutes=1)
    assert manager.acquire() == Access(True, "free", FREE_DAILY_LIMIT - 1)


def test_pro_is_cached_without_using_free_quota(tmp_path, monkeypatch):
    db_path = tmp_path / "usage.sqlite3"
    calls = []

    def validate(url, *, json, timeout):
        assert url == POLAR_VALIDATE
        assert json == {"key": "test-key", "organization_id": "test-org"}
        calls.append(url)
        return httpx.Response(200, json={"status": "granted", "expires_at": None})

    monkeypatch.setattr(httpx, "post", validate)
    manager = LicenseManager(db_path, "test-key", "test-org")
    for _ in range(FREE_DAILY_LIMIT + 1):
        assert manager.acquire() == Access(True, "pro", None)
    assert LicenseManager(db_path, "test-key", "test-org").acquire() == Access(True, "pro", None)
    assert len(calls) == 1
    assert LicenseManager(db_path).acquire() == Access(True, "free", FREE_DAILY_LIMIT - 1)


def test_expired_and_rejected_keys_use_free_quota(tmp_path, monkeypatch):
    expired = (datetime.now(UTC) - timedelta(seconds=1)).isoformat()
    responses = iter(
        [
            httpx.Response(200, json={"status": "granted", "expires_at": expired}),
            httpx.Response(404),
        ]
    )
    monkeypatch.setattr(httpx, "post", lambda *args, **kwargs: next(responses))
    manager = LicenseManager(tmp_path / "usage.sqlite3", "test-key", "test-org")
    assert manager.acquire() == Access(True, "free", FREE_DAILY_LIMIT - 1)
    assert manager.acquire() == Access(True, "free", FREE_DAILY_LIMIT - 2)
