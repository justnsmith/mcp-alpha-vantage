import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import sys
from pathlib import Path

# Add src directory to Python path
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

from client import AlphaVantageClient, AlphaVantageError, RateLimitError
from models import StockQuote, SymbolMatch


@pytest.fixture
def mock_settings():
    """Mock settings fixture."""
    with patch("client.get_settings") as mock:
        settings = MagicMock()
        settings.alpha_vantage_api_key = "test_api_key"
        settings.alpha_vantage_base_url = "https://www.alphavantage.co/query"
        settings.request_timeout = 10
        settings.max_retries = 3
        settings.cache_ttl_quote = 60
        settings.cache_ttl_daily = 3600
        settings.cache_ttl_search = 86400
        mock.return_value = settings
        yield settings


@pytest.fixture
def client(mock_settings):
    """Create a test client."""
    with patch("client.httpx.AsyncClient"), patch("client.httpx.AsyncHTTPTransport"):
        return AlphaVantageClient()


def _make_mock_response(data: dict) -> MagicMock:
    response = MagicMock()
    response.json.return_value = data
    response.raise_for_status = MagicMock()
    return response


class TestAlphaVantageClient:
    """Test suite for AlphaVantageClient."""

    def test_client_initialization(self, client):
        """Test that client initializes correctly."""
        assert client is not None
        assert client._http is not None

    @pytest.mark.asyncio
    async def test_get_quote_success(self, client):
        """Test successful quote retrieval."""
        client._http.get = AsyncMock(return_value=_make_mock_response({
            "Global Quote": {
                "01. symbol": "AAPL",
                "05. price": "182.45",
                "09. change": "2.34",
                "10. change percent": "1.30%",
                "06. volume": "52341234",
                "07. latest trading day": "2024-01-15",
                "08. previous close": "180.11",
                "02. open": "180.50",
                "03. high": "183.20",
                "04. low": "179.80",
            }
        }))

        result = await client.get_quote("AAPL")

        assert isinstance(result, StockQuote)
        assert result.symbol == "AAPL"
        assert result.price == "182.45"
        assert result.change == "2.34"

    @pytest.mark.asyncio
    async def test_get_quote_cache_hit(self, client):
        """Second call for the same symbol should not make an HTTP request."""
        client._http.get = AsyncMock(return_value=_make_mock_response({
            "Global Quote": {
                "05. price": "182.45",
                "09. change": "2.34",
                "10. change percent": "1.30%",
                "06. volume": "52341234",
                "07. latest trading day": "2024-01-15",
                "08. previous close": "180.11",
                "02. open": "180.50",
                "03. high": "183.20",
                "04. low": "179.80",
            }
        }))

        await client.get_quote("AAPL")
        await client.get_quote("AAPL")

        assert client._http.get.call_count == 1

    @pytest.mark.asyncio
    async def test_get_quote_no_data(self, client):
        """Test quote retrieval with no data."""
        client._http.get = AsyncMock(return_value=_make_mock_response({"Global Quote": {}}))

        with pytest.raises(AlphaVantageError, match="No data found"):
            await client.get_quote("INVALID")

    @pytest.mark.asyncio
    async def test_get_quote_rate_limit(self, client):
        """Test rate limit error handling."""
        client._http.get = AsyncMock(return_value=_make_mock_response({
            "Note": "Thank you for using Alpha Vantage! Our standard API call frequency is 5 calls per minute."
        }))

        with pytest.raises(RateLimitError):
            await client.get_quote("AAPL")

    @pytest.mark.asyncio
    async def test_search_symbols_success(self, client):
        """Test successful symbol search."""
        client._http.get = AsyncMock(return_value=_make_mock_response({
            "bestMatches": [
                {
                    "1. symbol": "AAPL",
                    "2. name": "Apple Inc.",
                    "3. type": "Equity",
                    "4. region": "United States",
                    "8. currency": "USD",
                }
            ]
        }))

        results = await client.search_symbols("Apple")

        assert len(results) == 1
        assert isinstance(results[0], SymbolMatch)
        assert results[0].symbol == "AAPL"
        assert results[0].name == "Apple Inc."

    @pytest.mark.asyncio
    async def test_search_symbols_no_matches(self, client):
        """Test symbol search with no matches."""
        client._http.get = AsyncMock(return_value=_make_mock_response({"bestMatches": []}))

        with pytest.raises(AlphaVantageError, match="No symbols found"):
            await client.search_symbols("INVALID")

    @pytest.mark.asyncio
    async def test_get_daily_prices_success(self, client):
        """Test successful daily prices retrieval."""
        client._http.get = AsyncMock(return_value=_make_mock_response({
            "Time Series (Daily)": {
                "2024-01-15": {
                    "1. open": "180.50",
                    "2. high": "183.20",
                    "3. low": "179.80",
                    "4. close": "182.45",
                    "5. volume": "52341234",
                }
            }
        }))

        result = await client.get_daily_prices("AAPL")

        assert result["symbol"] == "AAPL"
        assert result["total_days_available"] == 1
        assert "2024-01-15" in result["recent_days"]

    @pytest.mark.asyncio
    async def test_get_batch_quotes_concurrent(self, client):
        """get_batch_quotes fetches all symbols and skips failures."""
        call_count = 0

        async def mock_get(url, params):
            nonlocal call_count
            call_count += 1
            symbol = params.get("symbol", "")
            if symbol == "BAD":
                return _make_mock_response({"Global Quote": {}})
            return _make_mock_response({
                "Global Quote": {
                    "05. price": "100.00",
                    "09. change": "1.00",
                    "10. change percent": "1.00%",
                    "06. volume": "1000000",
                    "07. latest trading day": "2024-01-15",
                    "08. previous close": "99.00",
                    "02. open": "99.50",
                    "03. high": "101.00",
                    "04. low": "98.00",
                }
            })

        client._http.get = mock_get

        quotes = await client.get_batch_quotes(["AAPL", "BAD", "MSFT"])

        assert len(quotes) == 2
        assert all(isinstance(q, StockQuote) for q in quotes)
