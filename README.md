# mcp-alpha-vantage

An MCP server that exposes Alpha Vantage market data to LLM clients. Ask your assistant about stock quotes, historical prices, market summaries, and portfolio performance without leaving the conversation.

## Table of Contents

- [Requirements](#requirements)
- [Setup](#setup)
- [Configuration](#configuration)
- [Running the Server](#running-the-server)
- [Tools](#tools)
  - [get_stock_quote](#get_stock_quote)
  - [get_daily_prices](#get_daily_prices)
  - [search_symbol](#search_symbol)
  - [analyze_top_performers](#analyze_top_performers)
  - [get_market_summary](#get_market_summary)
  - [compare_stocks](#compare_stocks)
  - [screen_stocks](#screen_stocks)
  - [get_portfolio_snapshot](#get_portfolio_snapshot)
- [Development](#development)
- [Scripts](#scripts)
- [CI](#ci)

---

## Requirements

- Python 3.10 or higher
- An [Alpha Vantage API key](https://www.alphavantage.co/support/#api-key) (free tier works)

---

## Setup

```bash
git clone https://github.com/your-org/mcp-alpha-vantage.git
cd mcp-alpha-vantage
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

---

## Configuration

Copy the example env file and add your key:

```bash
cp .env.example .env
```

`.env`:
```
ALPHA_VANTAGE_API_KEY=your_key_here
```

The server reads this file automatically on startup. The free Alpha Vantage tier allows 5 API requests per minute and 500 per day. All tools that accept multiple symbols enforce a 50-symbol cap to stay within those limits.

---

## Running the Server

**stdio mode** (for MCP clients like Claude Desktop):
```bash
make run
```

**HTTP mode** (for development or HTTP-based MCP clients):
```bash
make run-http
```

The HTTP server starts on `http://0.0.0.0:8000`. A health check endpoint is available at `GET /health`.

To connect Claude Desktop, add the following to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "alpha-vantage": {
      "command": "/path/to/.venv/bin/python",
      "args": ["/path/to/src/server.py"]
    }
  }
}
```

---

## Tools

### get_stock_quote

Fetches the current quote for a single symbol.

| Parameter | Type | Description |
|-----------|------|-------------|
| `symbol` | string | Ticker symbol, e.g. `AAPL` |

Returns current price, change, change percent, volume, open, high, low, and previous close.

---

### get_daily_prices

Returns daily OHLCV data for a symbol.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `symbol` | string | — | Ticker symbol |
| `outputsize` | string | `compact` | `compact` = last 100 days, `full` = 20+ years |

---

### search_symbol

Searches for ticker symbols by company name or keywords.

| Parameter | Type | Description |
|-----------|------|-------------|
| `keywords` | string | Company name or search terms, e.g. `Apple` |

Returns up to 10 matches with symbol, company name, type, region, and currency.

---

### analyze_top_performers

Ranks a list of symbols by a chosen metric.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `symbols` | string | — | Comma-separated tickers, e.g. `AAPL,MSFT,GOOGL` |
| `limit` | int | `10` | Number of results to return |
| `metric` | string | `change_percent` | `change_percent` or `volume` |

---

### get_market_summary

Fetches a broad market overview using benchmark ETFs (SPY, QQQ, DIA, IWM, VIX) with optional additional symbols. Returns per-symbol metrics plus aggregate stats: average change, total volume, top gainer, top loser, and advance/decline breadth.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `symbols` | string | `""` | Optional extra symbols to include alongside benchmarks |

---

### compare_stocks

Compares multiple stocks side-by-side and identifies standouts.

| Parameter | Type | Description |
|-----------|------|-------------|
| `symbols` | string | Comma-separated tickers |

In addition to per-symbol metrics, the response highlights the `highest_gainer`, `biggest_loser`, `highest_volume`, and `most_volatile` stock (by intraday high-low range as a percent of previous close).

---

### screen_stocks

Filters a watchlist down to symbols that meet all supplied criteria. All filter parameters are optional and are ANDed together. Results are sorted by change percent, descending.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `symbols` | string | — | Comma-separated tickers to screen |
| `direction` | string | `any` | `gainers`, `losers`, or `any` |
| `min_change_percent` | float | — | Minimum daily change % |
| `max_change_percent` | float | — | Maximum daily change % |
| `min_volume` | int | — | Minimum share volume |

The response includes a `criteria_applied` field describing which filters were active.

---

### get_portfolio_snapshot

Computes real-time market values and daily P&L for a set of positions. Supports fractional shares.

| Parameter | Type | Description |
|-----------|------|-------------|
| `holdings` | string | Comma-separated `SYMBOL:shares` pairs, e.g. `AAPL:10,MSFT:5,GOOGL:2.5` |

Returns per-holding market value and daily dollar P&L, plus portfolio totals (total market value, total daily P&L, total daily P&L percent), and the `top_contributor` and `top_detractor` by dollar impact.

---

## Development

```bash
# Run tests
make test

# Check formatting and linting
make lint

# Run type checker
make typecheck

# Auto-format
make format
```

Tests are in `tests/` and use `unittest.mock` to avoid live API calls. All server tools are tested against mocked quotes.

---

## Scripts

The `scripts/` directory contains shell scripts for common tasks. Each script auto-detects and uses `.venv/bin` when present, so no manual activation is required.

| Script | Description |
|--------|-------------|
| `scripts/check.sh` | Runs `black --check`, `ruff check`, and `mypy`. Reports pass/fail for each step. Exits non-zero if anything fails. |
| `scripts/fix.sh` | Runs `black` and `ruff --fix` to reformat and auto-correct lint issues in place. Run `check.sh` afterwards to confirm. |
| `scripts/ci.sh` | Reproduces the full GitHub Actions pipeline locally — lint job then test job — with a combined summary at the end. |

```bash
# Check everything without changing files
bash scripts/check.sh

# Auto-fix formatting and lint issues
bash scripts/fix.sh

# Run the full CI pipeline locally
bash scripts/ci.sh
```

---

## CI

Two jobs run on every push and pull request to `main` or `develop`:

**lint** — runs `black --check`, `ruff check`, and `mypy` on Python 3.12.

**test** — runs the full pytest suite across Python 3.10, 3.11, and 3.12.
