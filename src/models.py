from datetime import datetime
from typing import Dict, Optional

from pydantic import BaseModel, ConfigDict, Field


class StockQuote(BaseModel):
    """Real-time stock quote data."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "symbol": "AAPL",
                "price": "182.45",
                "change": "2.34",
                "change_percent": "1.30%",
                "volume": "52341234",
                "latest_trading_day": "2024-01-15",
                "previous_close": "180.11",
                "open": "180.50",
                "high": "183.20",
                "low": "179.80",
            }
        }
    )

    symbol: str
    price: str
    change: str
    change_percent: str
    volume: str
    latest_trading_day: str
    previous_close: str
    open: str
    high: str
    low: str
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now())


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
