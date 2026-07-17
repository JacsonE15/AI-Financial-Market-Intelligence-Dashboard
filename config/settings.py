"""
Central configuration loaded from environment variables.

API keys should live in a local `.env` file (see `.env.example`).
Yahoo Finance does not require a key for Phase 1 market data.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

# Project root: .../Financial Morning Brief Dashboard
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"

load_dotenv(PROJECT_ROOT / ".env")


# Canonical Yahoo Finance tickers for the Global Market Overview.
# Labels are analyst-friendly display names used across the UI.
GLOBAL_MARKET_TICKERS: dict[str, str] = {
    "^GSPC": "S&P 500",
    "^IXIC": "Nasdaq",
    "^DJI": "Dow Jones",
    "^VIX": "VIX",
    "^TNX": "US 10Y Yield",
    "DX-Y.NYB": "USD Index",
    "GC=F": "Gold",
    "CL=F": "Crude Oil",
    "ES=F": "E-mini S&P",
    "NQ=F": "E-mini Nasdaq",
    "YM=F": "E-mini Dow",
    "RTY=F": "E-mini Russell",
}

DEFAULT_WATCHLIST: list[str] = ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "JPM", "XOM"]

DEFAULT_PORTFOLIO_WEIGHTS: dict[str, float] = {
    "AAPL": 0.18,
    "MSFT": 0.18,
    "NVDA": 0.14,
    "AMZN": 0.12,
    "GOOGL": 0.12,
    "META": 0.10,
    "JPM": 0.08,
    "XOM": 0.08,
}


@dataclass(frozen=True)
class Settings:
    """Runtime settings for the morning brief dashboard."""

    project_root: Path = PROJECT_ROOT
    data_dir: Path = DATA_DIR
    database_url: str = field(
        default_factory=lambda: os.getenv(
            "DATABASE_URL", f"sqlite:///{DATA_DIR / 'market_intelligence.db'}"
        )
    )
    default_lookback_days: int = field(
        default_factory=lambda: int(os.getenv("DEFAULT_LOOKBACK_DAYS", "90"))
    )
    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))
    force_demo_data: bool = field(
        default_factory=lambda: os.getenv("FORCE_DEMO_DATA", "").lower()
        in {"1", "true", "yes"}
    )

    # External APIs (Phase 2+)
    fred_api_key: str = field(default_factory=lambda: os.getenv("FRED_API_KEY", ""))
    news_api_key: str = field(default_factory=lambda: os.getenv("NEWS_API_KEY", ""))
    finnhub_api_key: str = field(default_factory=lambda: os.getenv("FINNHUB_API_KEY", ""))
    alpha_vantage_api_key: str = field(
        default_factory=lambda: os.getenv("ALPHA_VANTAGE_API_KEY", "")
    )
    qwen_api_key: str = field(default_factory=lambda: os.getenv("QWEN_API_KEY", ""))
    qwen_api_base: str = field(
        default_factory=lambda: os.getenv(
            "QWEN_API_BASE", "https://dashscope.aliyuncs.com/compatible-mode/v1"
        )
    )
    qwen_model: str = field(default_factory=lambda: os.getenv("QWEN_MODEL", "qwen-turbo"))

    market_tickers: dict[str, str] = field(default_factory=lambda: dict(GLOBAL_MARKET_TICKERS))
    default_watchlist: list[str] = field(default_factory=lambda: list(DEFAULT_WATCHLIST))
    default_portfolio_weights: dict[str, float] = field(
        default_factory=lambda: dict(DEFAULT_PORTFOLIO_WEIGHTS)
    )

    def ensure_directories(self) -> None:
        """Create local directories required by the app."""
        self.data_dir.mkdir(parents=True, exist_ok=True)


settings = Settings()
settings.ensure_directories()
