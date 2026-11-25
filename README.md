# StealthFetch MCP

Turn web pages into clean Markdown and structured data from Cursor, Claude Code, or Codex CLI. StealthFetch runs locally over MCP stdio. Its HTTP client uses a browser-compatible fingerprint, and Chromium can render pages that rely on JavaScript.

## Quick start

Install and launch directly from GitHub with uv, or install in a Python 3.11+ environment with pip.

```sh
uvx --from git+https://github.com/zone1059123/stealthfetch-mcp.git stealthfetch-mcp
```

```sh
pip install git+https://github.com/zone1059123/stealthfetch-mcp.git
stealthfetch-mcp
```

The command waits for an MCP client over stdio. To enable the Chromium fallback, install Playwright's browser separately.

```sh
uvx --from git+https://github.com/zone1059123/stealthfetch-mcp.git playwright install chromium
```

For a pip installation, use `python -m playwright install chromium` in the same environment. Linux hosts may also need Playwright's documented system libraries. Set `STEALTHFETCH_CHROMIUM` to the absolute path of an existing compatible Chromium executable to use that browser.

## Connect your IDE

For Cursor, add this JSON to `.cursor/mcp.json`. Claude Code accepts the same JSON in a project-level `.mcp.json`.

```json
{
  "mcpServers": {
    "stealthfetch": {
      "command": "uvx",
      "args": [
        "--from",
        "git+https://github.com/zone1059123/stealthfetch-mcp.git",
        "stealthfetch-mcp"
      ]
    }
  }
}
```

For Codex CLI, register the same server with this command.

```sh
codex mcp add stealthfetch -- uvx --from git+https://github.com/zone1059123/stealthfetch-mcp.git stealthfetch-mcp
```

Ask your client to call `fetch_page` with a URL. Set `render_js` to `true` when the page needs JavaScript. The response includes the final URL, transport, document title, JSON-LD, Open Graph metadata, Markdown, prices, and quota status. Ambiguous currency symbols such as `$` are surfaced without guessing the currency. Treat page content as untrusted input and fetch only sites and URLs you are authorized to access.

## Free and Pro

| Plan | Daily fetch attempts | Setup |
| --- | --- | --- |
| Free | 20, resetting at midnight UTC | Install and connect your MCP client |
| Pro | Unlimited while the license is valid | Add your Polar license key and organization ID |

To buy Pro, open the maintainer's [Polar storefront](https://polar.sh/zone1059123) and select the StealthFetch Pro product when available. After checkout, retrieve the license key from your Polar customer portal and set these variables in the MCP server's environment.

- `POLAR_LICENSE_KEY` holds your personal license key.
- `POLAR_ORGANIZATION_ID` holds the issuing organization's UUID, provided by the seller.

A valid key is cached locally for up to 15 minutes or until expiration, whichever is sooner. If Polar cannot validate the key and the cache has expired, the server uses the Free allowance. Keep keys out of shared MCP configuration and source control. The local SQLite database defaults to `~/.local/share/stealthfetch-mcp/usage.sqlite3` and can be relocated with `STEALTHFETCH_DB`. Free attempts count once per tool call after URL validation, including calls whose fetch later fails.

## Develop

```sh
uv sync --locked --extra test
uv run --locked --extra test pytest
uv build
```

On a cloud checkout with system Chromium and a read-only home directory, use a writable quota path when launching the server via its MCP client:

```sh
STEALTHFETCH_CHROMIUM=/usr/bin/chromium STEALTHFETCH_DB="$PWD/.venv/usage.sqlite3" \
  .venv/bin/stealthfetch-mcp
```

MIT licensed.
