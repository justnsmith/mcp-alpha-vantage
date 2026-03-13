from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path


class Settings(BaseSettings):
    """Application settings."""

    # Alpha Vantage API
    alpha_vantage_api_key: str = Field(default="", description="Alpha Vantage API key")
    alpha_vantage_base_url: str = Field(
        default="https://www.alphavantage.co/query",
        description="Alpha Vantage API base URL",
    )
    # Server settings
    request_timeout: int = Field(
        default=10, description="API request timeout in seconds", ge=1, le=60
    )
    max_retries: int = Field(default=3, description="Maximum number of retries", ge=0, le=5)

    # Cache TTLs (seconds)
    cache_ttl_quote: int = Field(default=60, description="TTL for stock quote cache", ge=0)
    cache_ttl_daily: int = Field(
        default=3600, description="TTL for daily price cache", ge=0
    )
    cache_ttl_search: int = Field(
        default=86400, description="TTL for symbol search cache", ge=0
    )
    cache_ttl_overview: int = Field(
        default=86400, description="TTL for company overview cache", ge=0
    )
    cache_ttl_indicator: int = Field(
        default=900, description="TTL for technical indicator cache", ge=0
    )
    cache_ttl_news: int = Field(
        default=900, description="TTL for news sentiment cache", ge=0
    )
    cache_ttl_earnings: int = Field(
        default=86400, description="TTL for earnings cache", ge=0
    )

    model_config = SettingsConfigDict(
        env_file=str(Path(__file__).parent.parent / ".env"),  # Go up to root
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


# Global settings instance
_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """Get or create settings instance."""
    global _settings
    if _settings is None:
        _settings = Settings()
        key = _settings.alpha_vantage_api_key
        if key:
            print(f"API Key loaded: {key[:4]}...{key[-4:]} (length: {len(key)})")
        else:
            print("WARNING: No API key loaded!")
    return _settings
