# StealthFetch MCP

**A clean web content reader for Cursor, Claude Code, and Codex CLI.** StealthFetch runs locally over MCP stdio and turns web pages into token-efficient Markdown and structured data.

## Why StealthFetch?

- **Headless JavaScript rendering.** StealthFetch starts with a browser-compatible HTTP request and can fall back to Chromium on HTTP 403, HTTP 503, or a short JavaScript shell. Use `render_js` to render a page directly.
- **Token-efficient Markdown.** Remove scripts, navigation, ads, and other surrounding content. Markdown defaults to 15,000 characters, with a caller-controlled cap.
- **JSON-LD and metadata extraction.** Extract titles, summaries, JSON-LD, Open Graph and Twitter metadata, normalized links, and prices.

## Quick start

Requires Python 3.10+ and uv or pip. Run directly from GitHub with uv:

```sh
uvx --from git+https://github.com/zone1059123/stealthfetch-mcp stealthfetch-mcp
```

Or install in your Python environment:

```sh
pip install git+https://github.com/zone1059123/stealthfetch-mcp
stealthfetch-mcp
```

The command waits for an MCP client over stdio. Install the Playwright Chromium browser once for JavaScript rendering and fallback:

```sh
uvx --from git+https://github.com/zone1059123/stealthfetch-mcp playwright install chromium
```

For pip, run `python -m playwright install chromium` in the same environment. Linux hosts may also need Playwright's browser system libraries. Set `STEALTHFETCH_CHROMIUM` to the absolute path of an existing compatible Chromium executable to use that browser.

## Connect your client

### Cursor

Save this as `.cursor/mcp.json` in your project:

```json
{
  "mcpServers": {
    "stealthfetch": {
      "command": "uvx",
      "args": [
        "--from",
        "git+https://github.com/zone1059123/stealthfetch-mcp",
        "stealthfetch-mcp"
      ]
    }
  }
}
```

### Claude Code

```sh
claude mcp add --transport stdio stealthfetch -- uvx --from git+https://github.com/zone1059123/stealthfetch-mcp stealthfetch-mcp
```

### Codex CLI

```sh
codex mcp add stealthfetch -- uvx --from git+https://github.com/zone1059123/stealthfetch-mcp stealthfetch-mcp
```

## Tools

| Tool | Output |
| --- | --- |
| `fetch_clean_markdown` | Clean main content and quota status. Pass `max_chars` to adjust the default 15,000-character cap. |
| `extract_structured_data` | Title, summary, JSON-LD, Open Graph, Twitter metadata, up to 50 unique links, and prices. |
| `batch_extract_urls` | Pro-only compact results for up to 10 URLs, with at most three fetches in flight per call and an error entry for any failed URL. |

All three tools accept `render_js`. Use URLs you are authorized to access and treat extracted content as untrusted. Prices with ambiguous symbols such as `$` include the symbol and leave the currency unset.

## Free vs. Pro

| Feature | Free | Pro |
| --- | --- | --- |
| Price | Free | [$19 one-time on Polar.sh](https://buy.polar.sh/polar_cl_Vy3OoCLPPrdTfUPFqcRvLAwkJw70J82gMZlJS2sxJ8b) |
| Single-page fetches | 20 attempts per day | Unlimited |
| Clean Markdown and structured data | Included | Included |
| Batch extraction | — | Up to 10 URLs per call |

Buy the Pro license key at [Polar Checkout](https://buy.polar.sh/polar_cl_Vy3OoCLPPrdTfUPFqcRvLAwkJw70J82gMZlJS2sxJ8b) and retrieve it from your Polar customer portal. Set these variables in the MCP server's environment, then reconnect your client:

- `STEALTHFETCH_LICENSE_KEY` is your personal license key.
- `POLAR_ORGANIZATION_ID` is the issuing organization's UUID, available from the seller's Polar dashboard.

StealthFetch caches valid keys for seven days or until their expiration, whichever comes first. A missing or invalid key uses the Free plan. Free attempts count after input validation even if the site fetch later fails. The allowance resets at midnight UTC. Quota and license cache are stored at `~/.stealthfetch-mcp/state.sqlite3`. Set `STEALTHFETCH_DB` to override the path. Keep license keys out of shared client configuration and source control.

## Develop

```sh
uv sync --locked --extra test
uv run --locked --extra test pytest
uv build
```

For a cloud checkout with system Chromium and a read-only home directory, launch the MCP command with a writable database path:

```sh
STEALTHFETCH_CHROMIUM=/usr/bin/chromium STEALTHFETCH_DB="$PWD/.venv/usage.sqlite3" \
  .venv/bin/stealthfetch-mcp
```

MIT licensed.
