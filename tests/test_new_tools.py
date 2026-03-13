import json
import pytest
from unittest.mock import AsyncMock, patch
import sys
from pathlib import Path

src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

from models import (
    CompanyOverview,
    EarningsResult,
    AnnualEarning,
    QuarterlyEarning,
    NewsSentimentResult,
    NewsArticle,
    TickerSentiment,
    TechnicalIndicatorResult,
    IndicatorDataPoint,
)
import server


def _unwrap(tool):
    return getattr(tool, "fn", tool)


get_company_overview = _unwrap(server.get_company_overview)
get_technical_indicator = _unwrap(server.get_technical_indicator)
get_news_sentiment = _unwrap(server.get_news_sentiment)
get_earnings = _unwrap(server.get_earnings)


def _make_overview(**kwargs) -> CompanyOverview:
    defaults = dict(
        symbol="AAPL",
        name="Apple Inc.",
        description="Apple designs consumer electronics.",
        exchange="NASDAQ",
        currency="USD",
        country="USA",
        sector="TECHNOLOGY",
        industry="ELECTRONIC COMPUTERS",
        market_cap="3000000000000",
        pe_ratio="30.5",
        eps="6.12",
        beta="1.23",
        week_52_high="200.00",
        week_52_low="150.00",
    )
    defaults.update(kwargs)
    return CompanyOverview(**defaults)


def _make_indicator_result(indicator: str = "RSI") -> TechnicalIndicatorResult:
    return TechnicalIndicatorResult(
        symbol="AAPL",
        indicator=indicator,
        interval="daily",
        time_period=14 if indicator != "MACD" else None,
        recent_data=[
            IndicatorDataPoint(date="2024-01-15", values={"RSI": "62.34"}),
            IndicatorDataPoint(date="2024-01-12", values={"RSI": "58.90"}),
        ],
    )


def _make_news_result() -> NewsSentimentResult:
    return NewsSentimentResult(
        tickers="AAPL",
        topics=None,
        articles=[
            NewsArticle(
                title="Apple reports record earnings",
                url="https://example.com/1",
                time_published="20240115T120000",
                source="Reuters",
                summary="Apple beat estimates...",
                overall_sentiment_score=0.35,
                overall_sentiment_label="Bullish",
                ticker_sentiment=[
                    TickerSentiment(
                        ticker="AAPL",
                        relevance_score="0.9",
                        sentiment_score="0.42",
                        sentiment_label="Bullish",
                    )
                ],
            )
        ],
        count=1,
    )


def _make_earnings_result() -> EarningsResult:
    return EarningsResult(
        symbol="AAPL",
        annual_earnings=[
            AnnualEarning(fiscal_date_ending="2023-09-30", reported_eps="6.12"),
        ],
        quarterly_earnings=[
            QuarterlyEarning(
                fiscal_date_ending="2023-09-30",
                reported_date="2023-11-02",
                reported_eps="1.46",
                estimated_eps="1.39",
                surprise="0.07",
                surprise_percentage="5.03",
            ),
        ],
    )


# ---------------------------------------------------------------------------
# get_company_overview
# ---------------------------------------------------------------------------


class TestGetCompanyOverview:

    @pytest.mark.asyncio
    @patch("server.client")
    async def test_overview_success(self, mock_client):
        mock_client.get_company_overview = AsyncMock(return_value=_make_overview())

        result = json.loads(await get_company_overview("AAPL"))

        assert result["symbol"] == "AAPL"
        assert result["name"] == "Apple Inc."
        assert result["sector"] == "TECHNOLOGY"
        assert result["pe_ratio"] == "30.5"
        assert result["beta"] == "1.23"

    @pytest.mark.asyncio
    @patch("server.client")
    async def test_overview_rate_limit(self, mock_client):
        from client import RateLimitError

        mock_client.get_company_overview = AsyncMock(side_effect=RateLimitError("limit hit"))

        result = json.loads(await get_company_overview("AAPL"))
        assert "error" in result
        assert "Rate limit" in result["error"]

    @pytest.mark.asyncio
    @patch("server.client")
    async def test_overview_api_error(self, mock_client):
        from client import AlphaVantageError

        mock_client.get_company_overview = AsyncMock(side_effect=AlphaVantageError("not found"))

        result = json.loads(await get_company_overview("FAKE"))
        assert "error" in result


# ---------------------------------------------------------------------------
# get_technical_indicator
# ---------------------------------------------------------------------------


class TestGetTechnicalIndicator:

    @pytest.mark.asyncio
    @patch("server.client")
    async def test_rsi_success(self, mock_client):
        mock_client.get_technical_indicator = AsyncMock(return_value=_make_indicator_result("RSI"))

        result = json.loads(await get_technical_indicator("AAPL", "RSI"))

        assert result["symbol"] == "AAPL"
        assert result["indicator"] == "RSI"
        assert len(result["recent_data"]) == 2
        assert result["recent_data"][0]["date"] == "2024-01-15"
        assert "RSI" in result["recent_data"][0]["values"]

    @pytest.mark.asyncio
    @patch("server.client")
    async def test_macd_success(self, mock_client):
        macd_result = TechnicalIndicatorResult(
            symbol="AAPL",
            indicator="MACD",
            interval="daily",
            time_period=None,
            recent_data=[
                IndicatorDataPoint(
                    date="2024-01-15",
                    values={"MACD": "1.23", "MACD_Signal": "0.98", "MACD_Hist": "0.25"},
                )
            ],
        )
        mock_client.get_technical_indicator = AsyncMock(return_value=macd_result)

        result = json.loads(await get_technical_indicator("AAPL", "MACD"))

        assert result["indicator"] == "MACD"
        assert result["time_period"] is None
        assert "MACD" in result["recent_data"][0]["values"]

    @pytest.mark.asyncio
    @patch("server.client")
    async def test_indicator_api_error(self, mock_client):
        from client import AlphaVantageError

        mock_client.get_technical_indicator = AsyncMock(
            side_effect=AlphaVantageError("Unsupported indicator 'EMA'")
        )

        result = json.loads(await get_technical_indicator("AAPL", "EMA"))
        assert "error" in result

    @pytest.mark.asyncio
    @patch("server.client")
    async def test_indicator_rate_limit(self, mock_client):
        from client import RateLimitError

        mock_client.get_technical_indicator = AsyncMock(side_effect=RateLimitError("limit hit"))

        result = json.loads(await get_technical_indicator("AAPL", "RSI"))
        assert "error" in result
        assert "Rate limit" in result["error"]


# ---------------------------------------------------------------------------
# get_news_sentiment
# ---------------------------------------------------------------------------


class TestGetNewsSentiment:

    @pytest.mark.asyncio
    @patch("server.client")
    async def test_news_success(self, mock_client):
        mock_client.get_news_sentiment = AsyncMock(return_value=_make_news_result())

        result = json.loads(await get_news_sentiment(tickers="AAPL", limit=5))

        assert result["count"] == 1
        assert result["tickers"] == "AAPL"
        assert result["articles"][0]["overall_sentiment_label"] == "Bullish"
        assert result["articles"][0]["ticker_sentiment"][0]["ticker"] == "AAPL"

    @pytest.mark.asyncio
    @patch("server.client")
    async def test_news_empty_result(self, mock_client):
        mock_client.get_news_sentiment = AsyncMock(
            return_value=NewsSentimentResult(articles=[], count=0)
        )

        result = json.loads(await get_news_sentiment())

        assert result["count"] == 0
        assert result["articles"] == []

    @pytest.mark.asyncio
    @patch("server.client")
    async def test_news_rate_limit(self, mock_client):
        from client import RateLimitError

        mock_client.get_news_sentiment = AsyncMock(side_effect=RateLimitError("limit hit"))

        result = json.loads(await get_news_sentiment(tickers="AAPL"))
        assert "error" in result
        assert "Rate limit" in result["error"]


# ---------------------------------------------------------------------------
# get_earnings
# ---------------------------------------------------------------------------


class TestGetEarnings:

    @pytest.mark.asyncio
    @patch("server.client")
    async def test_earnings_success(self, mock_client):
        mock_client.get_earnings = AsyncMock(return_value=_make_earnings_result())

        result = json.loads(await get_earnings("AAPL"))

        assert result["symbol"] == "AAPL"
        assert len(result["annual_earnings"]) == 1
        assert len(result["quarterly_earnings"]) == 1
        assert result["quarterly_earnings"][0]["reported_eps"] == "1.46"
        assert result["quarterly_earnings"][0]["surprise_percentage"] == "5.03"

    @pytest.mark.asyncio
    @patch("server.client")
    async def test_earnings_rate_limit(self, mock_client):
        from client import RateLimitError

        mock_client.get_earnings = AsyncMock(side_effect=RateLimitError("limit hit"))

        result = json.loads(await get_earnings("AAPL"))
        assert "error" in result
        assert "Rate limit" in result["error"]

    @pytest.mark.asyncio
    @patch("server.client")
    async def test_earnings_api_error(self, mock_client):
        from client import AlphaVantageError

        mock_client.get_earnings = AsyncMock(side_effect=AlphaVantageError("No earnings data"))

        result = json.loads(await get_earnings("FAKE"))
        assert "error" in result
