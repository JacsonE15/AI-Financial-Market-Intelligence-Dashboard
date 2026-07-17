"""Technical indicators for the equity watchlist."""

from __future__ import annotations

import numpy as np
import pandas as pd


def rsi(close: pd.Series, window: int = 14) -> pd.Series:
    """Relative Strength Index (Wilder-style approximation via EWM)."""
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1 / window, min_periods=window, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / window, min_periods=window, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def sma(close: pd.Series, window: int) -> pd.Series:
    """Simple moving average."""
    return close.rolling(window=window, min_periods=window).mean()


def historical_volatility(returns: pd.Series, window: int = 21, trading_days: int = 252) -> float:
    """Annualized historical volatility over the trailing window."""
    clean = returns.dropna().tail(window)
    if len(clean) < 5:
        return float("nan")
    return float(clean.std(ddof=1) * np.sqrt(trading_days))


def build_watchlist_metrics(prices: pd.DataFrame) -> pd.DataFrame:
    """
    Compute per-ticker watchlist metrics from tidy OHLCV data.

    Columns: ticker, price, daily_return, volume_change, hist_vol,
    rsi_14, sma_20, sma_50, high_52w, low_52w, pct_from_high
    """
    if prices.empty:
        return pd.DataFrame()

    rows: list[dict] = []
    for ticker, group in prices.groupby("ticker"):
        g = group.sort_values("date").copy()
        closes = g["close"]
        volumes = g["volume"]
        rets = g["return"] if "return" in g.columns else closes.pct_change()

        if closes.empty:
            continue

        last_close = float(closes.iloc[-1])
        daily_ret = float(rets.iloc[-1]) if pd.notna(rets.iloc[-1]) else float("nan")

        vol_chg = float("nan")
        if len(volumes.dropna()) >= 2 and volumes.iloc[-2] not in (0, np.nan):
            vol_chg = float(volumes.iloc[-1] / volumes.iloc[-2] - 1)

        rsi_series = rsi(closes)
        sma20 = sma(closes, 20)
        sma50 = sma(closes, 50)

        # Prefer ~252 trading days; fall back to available history.
        window = min(252, len(closes))
        high_52w = float(closes.tail(window).max())
        low_52w = float(closes.tail(window).min())
        pct_from_high = (last_close / high_52w - 1.0) if high_52w else float("nan")

        rows.append(
            {
                "ticker": ticker,
                "price": last_close,
                "daily_return": daily_ret,
                "volume_change": vol_chg,
                "hist_vol": historical_volatility(rets),
                "rsi_14": float(rsi_series.iloc[-1]) if pd.notna(rsi_series.iloc[-1]) else float("nan"),
                "sma_20": float(sma20.iloc[-1]) if pd.notna(sma20.iloc[-1]) else float("nan"),
                "sma_50": float(sma50.iloc[-1]) if pd.notna(sma50.iloc[-1]) else float("nan"),
                "high_52w": high_52w,
                "low_52w": low_52w,
                "pct_from_high": pct_from_high,
                "as_of": g["date"].iloc[-1],
            }
        )

    return pd.DataFrame(rows).sort_values("ticker").reset_index(drop=True)
