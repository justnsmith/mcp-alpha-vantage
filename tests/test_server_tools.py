import json
import pytest
from unittest.mock import AsyncMock, patch
import sys
from pathlib import Path

# Add src directory to Python path
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

from models import StockQuote

# FastMCP may wrap tools as FunctionTool objects (.fn) or return the plain
# function depending on the version. Support both.
import server


def _unwrap(tool):
    return getattr(tool, "fn", tool)


compare_stocks = _unwrap(server.compare_stocks)
screen_stocks = _unwrap(server.screen_stocks)
get_portfolio_snapshot = _unwrap(server.get_portfolio_snapshot)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_quote(
    symbol: str,
    price: str,
    change: str,
    previous_close: str,
    volume: str,
    high: str,
    low: str,
) -> StockQuote:
    return StockQuote(
        symbol=symbol,
        price=price,
        change=change,
        change_percent="0%",
        volume=volume,
        latest_trading_day="2024-01-15",
        previous_close=previous_close,
        open=price,
        high=high,
        low=low,
    )


# Reusable sample quotes used across multiple tests
_SAMPLE_QUOTES = [
    _make_quote("AAPL", "182.45", "2.34", "180.11", "52000000", "183.20", "179.80"),
    _make_quote("MSFT", "375.00", "-5.00", "380.00", "20000000", "378.00", "370.00"),
    _make_quote("TSLA", "250.00", "10.00", "240.00", "80000000", "260.00", "245.00"),
    _make_quote("GOOGL", "140.00", "-1.00", "141.00", "15000000", "142.00", "138.00"),
]


# ---------------------------------------------------------------------------
# compare_stocks
# ---------------------------------------------------------------------------


class TestCompareStocks:

    @pytest.mark.asyncio
    @patch("server.client")
    async def test_compare_stocks_success(self, mock_client):
        """compare_stocks returns JSON with per-stock metrics and highlights."""
        mock_client.get_batch_quotes = AsyncMock(return_value=_SAMPLE_QUOTES)

        result = json.loads(await compare_stocks("AAPL,MSFT,TSLA,GOOGL"))

        assert "quotes" in result
        assert len(result["quotes"]) == 4
        assert result["highest_gainer"]["symbol"] == "TSLA"  # +10 / 240 = 4.17 %
        assert result["biggest_loser"]["symbol"] == "MSFT"  # -5 / 380 = -1.32 %
        assert result["highest_volume"]["symbol"] == "TSLA"  # 80 M

    @pytest.mark.asyncio
    @patch("server.client")
    async def test_compare_stocks_intraday_range(self, mock_client):
        """compare_stocks populates intraday_range_percent on each quote."""
        mock_client.get_batch_quotes = AsyncMock(return_value=[
            _make_quote("AAPL", "182.45", "2.34", "180.11", "1000000", "190.00", "170.00"),
        ])

        result = json.loads(await compare_stocks("AAPL"))

        quote = result["quotes"][0]
        assert quote["intraday_range_percent"] is not None
        # (190 - 170) / 180.11 * 100 ≈ 11.1%
        assert abs(quote["intraday_range_percent"] - 11.1) < 0.5

    @pytest.mark.asyncio
    @patch("server.client")
    async def test_compare_stocks_most_volatile(self, mock_client):
        """most_volatile reflects the widest intraday range."""
        mock_client.get_batch_quotes = AsyncMock(return_value=[
            _make_quote("AAPL", "100.00", "1.00", "99.00", "1000", "102.00", "98.00"),  # range 4
            _make_quote("MSFT", "100.00", "1.00", "99.00", "1000", "115.00", "85.00"),  # range 30
        ])

        result = json.loads(await compare_stocks("AAPL,MSFT"))

        assert result["most_volatile"]["symbol"] == "MSFT"

    @pytest.mark.asyncio
    async def test_compare_stocks_no_symbols(self):
        """compare_stocks returns an error when given an empty string."""
        result = json.loads(await compare_stocks(""))
        assert "error" in result

    @pytest.mark.asyncio
    async def test_compare_stocks_too_many_symbols(self):
        """compare_stocks enforces the 50-symbol limit."""
        symbols = ",".join([f"SYM{i}" for i in range(51)])
        result = json.loads(await compare_stocks(symbols))
        assert "error" in result

    @pytest.mark.asyncio
    @patch("server.client")
    async def test_compare_stocks_rate_limit(self, mock_client):
        """compare_stocks propagates rate-limit errors gracefully."""
        from client import RateLimitError

        mock_client.get_batch_quotes = AsyncMock(side_effect=RateLimitError("limit hit"))

        result = json.loads(await compare_stocks("AAPL,MSFT"))
        assert "error" in result
        assert "Rate limit" in result["error"]


# ---------------------------------------------------------------------------
# screen_stocks
# ---------------------------------------------------------------------------


class TestScreenStocks:

    @pytest.mark.asyncio
    @patch("server.client")
    async def test_screen_gainers_only(self, mock_client):
        """direction='gainers' excludes stocks that are flat or down."""
        mock_client.get_batch_quotes = AsyncMock(return_value=_SAMPLE_QUOTES)

        result = json.loads(await screen_stocks("AAPL,MSFT,TSLA,GOOGL", direction="gainers"))

        symbols = [m["symbol"] for m in result["matched"]]
        assert "AAPL" in symbols
        assert "TSLA" in symbols
        assert "MSFT" not in symbols
        assert "GOOGL" not in symbols

    @pytest.mark.asyncio
    @patch("server.client")
    async def test_screen_losers_only(self, mock_client):
        """direction='losers' excludes stocks that are flat or up."""
        mock_client.get_batch_quotes = AsyncMock(return_value=_SAMPLE_QUOTES)

        result = json.loads(await screen_stocks("AAPL,MSFT,TSLA,GOOGL", direction="losers"))

        symbols = [m["symbol"] for m in result["matched"]]
        assert "MSFT" in symbols
        assert "GOOGL" in symbols
        assert "AAPL" not in symbols
        assert "TSLA" not in symbols

    @pytest.mark.asyncio
    @patch("server.client")
    async def test_screen_min_change_percent(self, mock_client):
        """min_change_percent filters out stocks below the threshold."""
        mock_client.get_batch_quotes = AsyncMock(return_value=_SAMPLE_QUOTES)

        # TSLA ≈ +4.17 %, AAPL ≈ +1.30 %  → only TSLA should pass 2 %
        result = json.loads(await screen_stocks("AAPL,MSFT,TSLA,GOOGL", min_change_percent=2.0))

        symbols = [m["symbol"] for m in result["matched"]]
        assert "TSLA" in symbols
        assert "AAPL" not in symbols
        assert "MSFT" not in symbols

    @pytest.mark.asyncio
    @patch("server.client")
    async def test_screen_min_volume(self, mock_client):
        """min_volume filters out stocks with insufficient trading activity."""
        mock_client.get_batch_quotes = AsyncMock(return_value=_SAMPLE_QUOTES)

        # Only TSLA (80 M) and AAPL (52 M) exceed 25 M threshold
        result = json.loads(await screen_stocks("AAPL,MSFT,TSLA,GOOGL", min_volume=25_000_000))

        symbols = [m["symbol"] for m in result["matched"]]
        assert "TSLA" in symbols
        assert "AAPL" in symbols
        assert "MSFT" not in symbols
        assert "GOOGL" not in symbols

    @pytest.mark.asyncio
    @patch("server.client")
    async def test_screen_combined_criteria(self, mock_client):
        """Multiple criteria are ANDed together."""
        mock_client.get_batch_quotes = AsyncMock(return_value=_SAMPLE_QUOTES)

        # gainers AND volume >= 60 M → only TSLA (80 M, +4.17 %) qualifies; AAPL is 52 M
        result = json.loads(
            await screen_stocks(
                "AAPL,MSFT,TSLA,GOOGL",
                direction="gainers",
                min_volume=60_000_000,
            )
        )

        symbols = [m["symbol"] for m in result["matched"]]
        assert symbols == ["TSLA"]

    @pytest.mark.asyncio
    @patch("server.client")
    async def test_screen_no_matches(self, mock_client):
        """screen_stocks returns an empty list when nothing passes the filter."""
        mock_client.get_batch_quotes = AsyncMock(return_value=_SAMPLE_QUOTES)

        result = json.loads(await screen_stocks("AAPL,MSFT,TSLA,GOOGL", min_change_percent=50.0))

        assert result["matched_count"] == 0
        assert result["matched"] == []

    @pytest.mark.asyncio
    @patch("server.client")
    async def test_screen_criteria_applied_string(self, mock_client):
        """criteria_applied describes which filters were used."""
        mock_client.get_batch_quotes = AsyncMock(return_value=_SAMPLE_QUOTES)

        result = json.loads(
            await screen_stocks(
                "AAPL,TSLA",
                direction="gainers",
                min_volume=1_000_000,
            )
        )

        assert "gainers" in result["criteria_applied"]
        assert "volume" in result["criteria_applied"]

    @pytest.mark.asyncio
    async def test_screen_invalid_direction(self):
        """screen_stocks returns an error for an invalid direction value."""
        result = json.loads(await screen_stocks("AAPL,MSFT", direction="sideways"))
        assert "error" in result

    @pytest.mark.asyncio
    async def test_screen_no_symbols(self):
        """screen_stocks returns an error when given an empty string."""
        result = json.loads(await screen_stocks(""))
        assert "error" in result


# ---------------------------------------------------------------------------
# get_portfolio_snapshot
# ---------------------------------------------------------------------------


class TestGetPortfolioSnapshot:

    @pytest.mark.asyncio
    @patch("server.client")
    async def test_snapshot_success(self, mock_client):
        """get_portfolio_snapshot computes market values and daily P&L."""
        mock_client.get_batch_quotes = AsyncMock(return_value=[
            _make_quote("AAPL", "182.45", "2.34", "180.11", "1000000", "183.00", "180.00"),
            _make_quote("MSFT", "375.00", "-5.00", "380.00", "1000000", "378.00", "370.00"),
        ])

        result = json.loads(await get_portfolio_snapshot("AAPL:10,MSFT:5"))

        # AAPL: 10 * 182.45 = 1824.50, daily P&L: 10 * 2.34 = 23.40
        # MSFT: 5 * 375.00 = 1875.00, daily P&L: 5 * -5.00 = -25.00
        assert abs(result["total_market_value"] - 3699.50) < 0.01
        assert abs(result["total_daily_pnl"] - (23.40 - 25.00)) < 0.01

    @pytest.mark.asyncio
    @patch("server.client")
    async def test_snapshot_top_contributor_and_detractor(self, mock_client):
        """top_contributor and top_detractor reflect the correct holdings."""
        mock_client.get_batch_quotes = AsyncMock(return_value=[
            _make_quote("AAPL", "182.45", "2.34", "180.11", "1000000", "183.00", "180.00"),
            _make_quote("MSFT", "375.00", "-5.00", "380.00", "1000000", "378.00", "370.00"),
            _make_quote("TSLA", "250.00", "10.00", "240.00", "1000000", "260.00", "245.00"),
        ])

        result = json.loads(await get_portfolio_snapshot("AAPL:10,MSFT:5,TSLA:20"))

        # TSLA daily P&L: 20 * 10 = +200 (top contributor)
        # MSFT daily P&L: 5 * -5 = -25 (top detractor)
        assert result["top_contributor"]["symbol"] == "TSLA"
        assert result["top_detractor"]["symbol"] == "MSFT"

    @pytest.mark.asyncio
    @patch("server.client")
    async def test_snapshot_fractional_shares(self, mock_client):
        """get_portfolio_snapshot handles fractional share counts."""
        mock_client.get_batch_quotes = AsyncMock(return_value=[
            _make_quote("AAPL", "100.00", "10.00", "90.00", "1000", "105.00", "95.00"),
        ])

        result = json.loads(await get_portfolio_snapshot("AAPL:0.5"))

        holding = result["holdings"][0]
        assert abs(holding["market_value"] - 50.00) < 0.01
        assert abs(holding["daily_pnl"] - 5.00) < 0.01

    @pytest.mark.asyncio
    async def test_snapshot_invalid_format_missing_colon(self):
        """get_portfolio_snapshot returns an error for missing colon separator."""
        result = json.loads(await get_portfolio_snapshot("AAPL10"))
        assert "error" in result

    @pytest.mark.asyncio
    async def test_snapshot_invalid_share_count(self):
        """get_portfolio_snapshot returns an error for non-numeric share count."""
        result = json.loads(await get_portfolio_snapshot("AAPL:abc"))
        assert "error" in result

    @pytest.mark.asyncio
    async def test_snapshot_zero_shares(self):
        """get_portfolio_snapshot returns an error for zero share count."""
        result = json.loads(await get_portfolio_snapshot("AAPL:0"))
        assert "error" in result

    @pytest.mark.asyncio
    async def test_snapshot_no_holdings(self):
        """get_portfolio_snapshot returns an error for an empty input."""
        result = json.loads(await get_portfolio_snapshot(""))
        assert "error" in result

    @pytest.mark.asyncio
    async def test_snapshot_too_many_symbols(self):
        """get_portfolio_snapshot enforces the 50-symbol limit."""
        holdings = ",".join([f"SYM{i}:1" for i in range(51)])
        result = json.loads(await get_portfolio_snapshot(holdings))
        assert "error" in result

    @pytest.mark.asyncio
    @patch("server.client")
    async def test_snapshot_rate_limit(self, mock_client):
        """get_portfolio_snapshot propagates rate-limit errors gracefully."""
        from client import RateLimitError

        mock_client.get_batch_quotes = AsyncMock(side_effect=RateLimitError("limit hit"))

        result = json.loads(await get_portfolio_snapshot("AAPL:10"))
        assert "error" in result
        assert "Rate limit" in result["error"]
