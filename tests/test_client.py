import pytest
from unittest.mock import Mock, patch
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
        settings = Mock()
        settings.alpha_vantage_api_key = "test_api_key"
        settings.alpha_vantage_base_url = "https://www.alphavantage.co/query"
        settings.request_timeout = 10
        settings.max_retries = 3
        mock.return_value = settings
        yield settings


@pytest.fixture
def client(mock_settings):
    """Create a test client."""
    return AlphaVantageClient()


class TestAlphaVantageClient:
    """Test suite for AlphaVantageClient."""

    def test_client_initialization(self, client):
        """Test that client initializes correctly."""
        assert client is not None
        assert client.session is not None

    @patch("client.requests.Session.get")
    def test_get_quote_success(self, mock_get, client):
        """Test successful quote retrieval."""
        # Mock response
        mock_response = Mock()
        mock_response.json.return_value = {
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
        }
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        # Test
        result = client.get_quote("AAPL")

        # Assertions
        assert isinstance(result, StockQuote)
        assert result.symbol == "AAPL"
        assert result.price == "182.45"
        assert result.change == "2.34"

    @patch("client.requests.Session.get")
    def test_get_quote_no_data(self, mock_get, client):
        """Test quote retrieval with no data."""
        mock_response = Mock()
        mock_response.json.return_value = {"Global Quote": {}}
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        with pytest.raises(AlphaVantageError, match="No data found"):
            client.get_quote("INVALID")

    @patch("client.requests.Session.get")
    def test_get_quote_rate_limit(self, mock_get, client):
        """Test rate limit error handling."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "Note": "Thank you for using Alpha Vantage! Our standard API call frequency is 5 calls per minute."
        }
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        with pytest.raises(RateLimitError):
            client.get_quote("AAPL")

    @patch("client.requests.Session.get")
    def test_search_symbols_success(self, mock_get, client):
        """Test successful symbol search."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "bestMatches": [
                {
                    "1. symbol": "AAPL",
                    "2. name": "Apple Inc.",
                    "3. type": "Equity",
                    "4. region": "United States",
                    "8. currency": "USD",
                }
            ]
        }
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        results = client.search_symbols("Apple")

        assert len(results) == 1
        assert isinstance(results[0], SymbolMatch)
        assert results[0].symbol == "AAPL"
        assert results[0].name == "Apple Inc."

    @patch("client.requests.Session.get")
    def test_search_symbols_no_matches(self, mock_get, client):
        """Test symbol search with no matches."""
        mock_response = Mock()
        mock_response.json.return_value = {"bestMatches": []}
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        with pytest.raises(AlphaVantageError, match="No symbols found"):
            client.search_symbols("INVALID")

    @patch("client.requests.Session.get")
    def test_get_daily_prices_success(self, mock_get, client):
        """Test successful daily prices retrieval."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "Time Series (Daily)": {
                "2024-01-15": {
                    "1. open": "180.50",
                    "2. high": "183.20",
                    "3. low": "179.80",
                    "4. close": "182.45",
                    "5. volume": "52341234",
                }
            }
        }
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        result = client.get_daily_prices("AAPL")

        assert result["symbol"] == "AAPL"
        assert result["total_days_available"] == 1
        assert "2024-01-15" in result["recent_days"]
