from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StockQuote(BaseModel):
    """Real-time stock quote data."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "symbol": "AAPL",
                "price": 182.45,
                "change": 2.34,
                "change_percent": 1.30,
                "volume": 52341234,
                "latest_trading_day": "2024-01-15",
                "previous_close": 180.11,
                "open": 180.50,
                "high": 183.20,
                "low": 179.80,
            }
        }
    )

    symbol: str
    price: float
    change: float
    change_percent: float
    volume: int
    latest_trading_day: str
    previous_close: float
    open: float
    high: float
    low: float
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now())

    @field_validator("change_percent", mode="before")
    @classmethod
    def parse_change_percent(cls, v: Any) -> float:
        if isinstance(v, str):
            return float(v.rstrip("%"))
        return float(v)


class DailyPrice(BaseModel):
    """Daily price data for a single day."""

    model_config = ConfigDict(populate_by_name=True)

    open: str = Field(alias="1. open")
    high: str = Field(alias="2. high")
    low: str = Field(alias="3. low")
    close: str = Field(alias="4. close")
    volume: str = Field(alias="5. volume")


class DailyPrices(BaseModel):
    """Historical daily prices for a stock."""

    symbol: str
    recent_days: Dict[str, DailyPrice]
    total_days_available: int
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now())


class SymbolMatch(BaseModel):
    """Symbol search result."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "symbol": "AAPL",
                "name": "Apple Inc.",
                "type": "Equity",
                "region": "United States",
                "currency": "USD",
            }
        }
    )

    symbol: str
    name: str
    type: str
    region: str
    currency: str


class SymbolSearchResult(BaseModel):
    """Symbol search results."""

    query: str
    matches: list[SymbolMatch]
    count: int
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now())


class ErrorResponse(BaseModel):
    """Error response structure."""

    error: str
    symbol: Optional[str] = None
    query: Optional[str] = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now())


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    service: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now())


class PerformerMetrics(BaseModel):
    """Performance metrics for a single stock."""

    symbol: str
    name: Optional[str] = None
    current_price: float
    previous_close: float
    change: float
    change_percent: float
    volume: int
    period: str  # e.g., "1day", "5day", "1month"
    intraday_range_percent: Optional[float] = None  # (high - low) / previous_close * 100


class TopPerformersResult(BaseModel):
    """Results from top performers analysis."""

    period: str
    metric: str  # e.g., "change_percent", "volume"
    performers: list[PerformerMetrics]
    count: int
    analyzed_count: int  # How many stocks were analyzed
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now())


class MarketBreadth(BaseModel):
    """Breadth statistics across a set of symbols."""

    advancing: int
    declining: int
    unchanged: int
    advance_decline_ratio: Optional[float] = None  # None if no decliners


class MarketSummaryResult(BaseModel):
    """Aggregated market summary across benchmark and/or custom symbols."""

    symbols_requested: list[str]
    symbols_retrieved: int
    average_change_percent: float
    total_volume: int
    top_gainer: Optional[PerformerMetrics] = None
    top_loser: Optional[PerformerMetrics] = None
    breadth: MarketBreadth
    quotes: list[PerformerMetrics]
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now())


class StockComparison(BaseModel):
    """Side-by-side comparison of multiple stocks."""

    symbols: list[str]
    quotes: list[PerformerMetrics]
    highest_gainer: Optional[PerformerMetrics] = None
    biggest_loser: Optional[PerformerMetrics] = None
    highest_volume: Optional[PerformerMetrics] = None
    most_volatile: Optional[PerformerMetrics] = None
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now())


class ScreenResult(BaseModel):
    """Results from a stock screening operation."""

    criteria_applied: str
    matched: list[PerformerMetrics]
    matched_count: int
    total_screened: int
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now())


class PortfolioHolding(BaseModel):
    """Single holding in a portfolio snapshot."""

    symbol: str
    shares: float
    current_price: float
    market_value: float
    change: float
    change_percent: float
    daily_pnl: float


class PortfolioSnapshot(BaseModel):
    """Aggregated snapshot of a stock portfolio."""

    total_market_value: float
    total_daily_pnl: float
    total_daily_pnl_percent: float
    holdings: list[PortfolioHolding]
    top_contributor: Optional[PortfolioHolding] = None
    top_detractor: Optional[PortfolioHolding] = None
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now())


class CompanyOverview(BaseModel):
    """Company fundamentals from Alpha Vantage OVERVIEW endpoint."""

    symbol: str
    name: str
    description: str
    exchange: str
    currency: str
    country: str
    sector: str
    industry: str
    market_cap: Optional[str] = None
    pe_ratio: Optional[str] = None
    peg_ratio: Optional[str] = None
    book_value: Optional[str] = None
    dividend_yield: Optional[str] = None
    eps: Optional[str] = None
    profit_margin: Optional[str] = None
    return_on_equity: Optional[str] = None
    revenue_ttm: Optional[str] = None
    beta: Optional[str] = None
    week_52_high: Optional[str] = None
    week_52_low: Optional[str] = None
    moving_avg_50: Optional[str] = None
    moving_avg_200: Optional[str] = None
    analyst_target_price: Optional[str] = None
    forward_pe: Optional[str] = None
    price_to_book: Optional[str] = None
    ev_to_ebitda: Optional[str] = None
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now())


class TickerSentiment(BaseModel):
    """Sentiment data for a specific ticker within a news article."""

    ticker: str
    relevance_score: str
    sentiment_score: str
    sentiment_label: str


class NewsArticle(BaseModel):
    """A single news article with sentiment data."""

    title: str
    url: str
    time_published: str
    source: str
    summary: str
    overall_sentiment_score: float
    overall_sentiment_label: str
    ticker_sentiment: list[TickerSentiment]


class NewsSentimentResult(BaseModel):
    """News and sentiment results from Alpha Vantage NEWS_SENTIMENT endpoint."""

    tickers: Optional[str] = None
    topics: Optional[str] = None
    articles: list[NewsArticle]
    count: int
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now())


class IndicatorDataPoint(BaseModel):
    """A single data point for a technical indicator."""

    date: str
    values: Dict[str, str]


class TechnicalIndicatorResult(BaseModel):
    """Technical indicator data from Alpha Vantage."""

    symbol: str
    indicator: str
    interval: str
    time_period: Optional[int] = None
    recent_data: list[IndicatorDataPoint]
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now())


class AnnualEarning(BaseModel):
    """Annual earnings for a single fiscal year."""

    fiscal_date_ending: str
    reported_eps: Optional[str] = None


class QuarterlyEarning(BaseModel):
    """Quarterly earnings with estimate and surprise data."""

    fiscal_date_ending: str
    reported_date: Optional[str] = None
    reported_eps: Optional[str] = None
    estimated_eps: Optional[str] = None
    surprise: Optional[str] = None
    surprise_percentage: Optional[str] = None


class EarningsResult(BaseModel):
    """Earnings history from Alpha Vantage EARNINGS endpoint."""

    symbol: str
    annual_earnings: list[AnnualEarning]
    quarterly_earnings: list[QuarterlyEarning]
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now())
