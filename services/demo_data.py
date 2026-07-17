"""
Deterministic demo market data for offline / rate-limited environments.

Used when Yahoo Finance is unavailable so Phase 1 UI can still be demonstrated.
"""

from __future__ import annotations

from datetime import datetime

import numpy as np
import pandas as pd

from config.settings import settings
from services.data_processing import compute_daily_returns

# Approximate starting levels for a believable cross-asset demo panel.
_BASE_LEVELS: dict[str, float] = {
    "^GSPC": 5200.0,
    "^IXIC": 16400.0,
    "^DJI": 39000.0,
    "^VIX": 15.5,
    "^TNX": 4.25,
    "DX-Y.NYB": 104.0,
    "GC=F": 2350.0,
    "CL=F": 78.0,
    "ES=F": 5200.0,
    "NQ=F": 18400.0,
    "YM=F": 39000.0,
    "RTY=F": 2050.0,
    # Equities / ETFs for watchlist & risk book demos
    "AAPL": 195.0,
    "MSFT": 430.0,
    "NVDA": 115.0,
    "AMZN": 185.0,
    "GOOGL": 175.0,
    "META": 510.0,
    "TSLA": 250.0,
    "JPM": 198.0,
    "XOM": 110.0,
    "SPY": 525.0,
    "QQQ": 450.0,
}

_DAILY_VOL: dict[str, float] = {
    "^GSPC": 0.009,
    "^IXIC": 0.012,
    "^DJI": 0.008,
    "^VIX": 0.05,
    "^TNX": 0.012,
    "DX-Y.NYB": 0.004,
    "GC=F": 0.008,
    "CL=F": 0.018,
    "ES=F": 0.009,
    "NQ=F": 0.012,
    "YM=F": 0.008,
    "RTY=F": 0.014,
    "AAPL": 0.015,
    "MSFT": 0.013,
    "NVDA": 0.028,
    "AMZN": 0.018,
    "GOOGL": 0.016,
    "META": 0.020,
    "TSLA": 0.032,
    "JPM": 0.014,
    "XOM": 0.016,
    "SPY": 0.009,
    "QQQ": 0.012,
}


def generate_demo_market_data(
    tickers: list[str] | None = None,
    lookback_days: int | None = None,
    seed: int = 42,
) -> pd.DataFrame:
    """
    Generate synthetic OHLCV + daily returns for the global market universe.

    Random walks are seeded for reproducibility across Streamlit reruns.
    """
    tickers = tickers or list(settings.market_tickers.keys())
    lookback_days = lookback_days or settings.default_lookback_days

    # Use business days only
    end = datetime.utcnow().date()
    dates = pd.bdate_range(end=end, periods=lookback_days)

    frames: list[pd.DataFrame] = []
    for i, ticker in enumerate(tickers):
        rng = np.random.default_rng(seed + i)
        level = _BASE_LEVELS.get(ticker, 100.0)
        vol = _DAILY_VOL.get(ticker, 0.01)
        shocks = rng.normal(0.0002, vol, size=len(dates))

        # Mild mean-reversion for VIX-like series
        if ticker == "^VIX":
            path = [level]
            for shock in shocks[1:]:
                prev = path[-1]
                path.append(max(10.0, prev + 0.15 * (15.0 - prev) + shock * prev))
            closes = np.array(path)
        else:
            closes = level * np.cumprod(1.0 + shocks)

        opens = closes * (1.0 + rng.normal(0, 0.001, size=len(dates)))
        highs = np.maximum(opens, closes) * (1.0 + np.abs(rng.normal(0, 0.003, size=len(dates))))
        lows = np.minimum(opens, closes) * (1.0 - np.abs(rng.normal(0, 0.003, size=len(dates))))
        volumes = rng.integers(1_000_000, 8_000_000, size=len(dates)).astype(float)

        frame = pd.DataFrame(
            {
                "date": [d.date() for d in dates],
                "ticker": ticker,
                "open": opens,
                "high": highs,
                "low": lows,
                "close": closes,
                "volume": volumes,
            }
        )
        frames.append(frame)

    combined = pd.concat(frames, ignore_index=True)
    return compute_daily_returns(combined)
