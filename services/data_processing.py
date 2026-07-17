"""
Data processing utilities for market prices and performance analytics.

Reusable helpers for returns, normalized prices, heatmaps, and summaries.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from config.settings import settings

logger = logging.getLogger(__name__)

OHLCV_COLUMNS = ["Open", "High", "Low", "Close", "Volume"]


def normalize_ohlcv(raw: pd.DataFrame, ticker: str) -> pd.DataFrame:
    """
    Convert a yfinance single-ticker frame into a tidy OHLCV table.

    Handles both capitalized Yahoo columns and already-lowercase variants.
    """
    if raw is None or raw.empty:
        return pd.DataFrame(
            columns=["date", "ticker", "open", "high", "low", "close", "volume"]
        )

    frame = raw.copy()
    frame = frame.reset_index()

    # Standardize column names
    rename_map = {}
    for col in frame.columns:
        key = str(col).strip().lower()
        if key in {"date", "datetime", "index"}:
            rename_map[col] = "date"
        elif key == "open":
            rename_map[col] = "open"
        elif key == "high":
            rename_map[col] = "high"
        elif key == "low":
            rename_map[col] = "low"
        elif key == "close" or key == "adj close":
            # Prefer Close; if Adj Close appears later it can overwrite.
            if "close" not in rename_map.values() or key == "close":
                rename_map[col] = "close"
        elif key == "volume":
            rename_map[col] = "volume"

    frame = frame.rename(columns=rename_map)

    required = ["date", "open", "high", "low", "close"]
    missing = [c for c in required if c not in frame.columns]
    if missing:
        raise ValueError(f"Missing OHLCV columns for {ticker}: {missing}")

    if "volume" not in frame.columns:
        frame["volume"] = np.nan

    out = frame[["date", "open", "high", "low", "close", "volume"]].copy()
    out["ticker"] = ticker
    out["date"] = pd.to_datetime(out["date"]).dt.date

    for col in ["open", "high", "low", "close", "volume"]:
        out[col] = pd.to_numeric(out[col], errors="coerce")

    out = out.dropna(subset=["close"]).sort_values("date").reset_index(drop=True)
    return out[["date", "ticker", "open", "high", "low", "close", "volume"]]


def compute_daily_returns(prices: pd.DataFrame) -> pd.DataFrame:
    """Add simple daily return = close_t / close_{t-1} - 1 per ticker."""
    if prices.empty:
        prices = prices.copy()
        prices["return"] = pd.Series(dtype=float)
        return prices

    out = prices.sort_values(["ticker", "date"]).copy()
    out["return"] = out.groupby("ticker")["close"].pct_change()
    return out


def pivot_closes(prices: pd.DataFrame) -> pd.DataFrame:
    """Wide close-price panel indexed by date, columns = ticker."""
    if prices.empty:
        return pd.DataFrame()
    panel = prices.pivot_table(index="date", columns="ticker", values="close", aggfunc="last")
    panel = panel.sort_index()
    return panel


def normalized_performance(prices: pd.DataFrame, base: float = 100.0) -> pd.DataFrame:
    """
    Rebase each series to `base` at the first available observation.

    Useful for historical comparison charts across assets with different levels.
    """
    panel = pivot_closes(prices)
    if panel.empty:
        return panel

    rebased = panel.apply(lambda s: s / s.dropna().iloc[0] * base if s.dropna().shape[0] else s)
    return rebased


def build_return_heatmap_matrix(prices: pd.DataFrame, periods: int = 20) -> pd.DataFrame:
    """
    Build a ticker x date matrix of recent daily returns for heatmap display.

    Uses the last `periods` trading days.
    """
    if prices.empty:
        return pd.DataFrame()

    panel = prices.pivot_table(index="date", columns="ticker", values="return", aggfunc="last")
    panel = panel.sort_index().tail(periods)

    # Map tickers to friendly names for the UI
    name_map = settings.market_tickers
    panel = panel.rename(columns=lambda t: name_map.get(t, t))
    return panel.T  # rows = assets, columns = dates


def period_performance_summary(prices: pd.DataFrame) -> pd.DataFrame:
    """
    Compute 1D / 5D / 1M performance and latest level for each ticker.
    """
    if prices.empty:
        return pd.DataFrame()

    rows = []
    for ticker, group in prices.groupby("ticker"):
        g = group.sort_values("date")
        closes = g["close"].dropna()
        if closes.empty:
            continue

        last = float(closes.iloc[-1])
        ret_1d = float(g["return"].iloc[-1]) if pd.notna(g["return"].iloc[-1]) else np.nan

        def _period_return(n: int) -> float:
            if len(closes) <= n:
                return np.nan
            return float(closes.iloc[-1] / closes.iloc[-(n + 1)] - 1)

        rows.append(
            {
                "ticker": ticker,
                "name": settings.market_tickers.get(ticker, ticker),
                "last_price": last,
                "return_1d": ret_1d,
                "return_5d": _period_return(5),
                "return_1m": _period_return(21),
                "as_of": g["date"].iloc[-1],
            }
        )

    return pd.DataFrame(rows).sort_values("name").reset_index(drop=True)


def format_pct(value: float | None, decimals: int = 2) -> str:
    """Format a decimal return as a percentage string."""
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return "—"
    return f"{value * 100:.{decimals}f}%"


def build_rule_based_market_summary(summary: pd.DataFrame) -> str:
    """
    Lightweight Phase-1 market summary without an LLM.

    Phase 2 replaces / augments this with Qwen (or another LLM) using the same inputs.
    """
    if summary.empty:
        return "Market data unavailable. Refresh the dashboard once network access is available."

    gainers = summary.dropna(subset=["return_1d"]).sort_values("return_1d", ascending=False)
    top = gainers.head(3)
    bottom = gainers.tail(3).sort_values("return_1d")

    def _line(row: pd.Series) -> str:
        return f"{row['name']} ({format_pct(row['return_1d'])})"

    vix_row = summary.loc[summary["ticker"] == "^VIX"]
    vix_note = ""
    if not vix_row.empty and pd.notna(vix_row.iloc[0]["return_1d"]):
        level = vix_row.iloc[0]["last_price"]
        chg = vix_row.iloc[0]["return_1d"]
        tone = "easing" if chg < 0 else "rising"
        vix_note = f" Volatility gauge (VIX) is at {level:.2f}, {tone} {format_pct(chg)} on the day."

    as_of = summary["as_of"].max()
    parts = [
        f"Overnight / latest session snapshot as of {as_of}.",
        f"Leaders: {', '.join(_line(r) for _, r in top.iterrows())}.",
        f"Laggards: {', '.join(_line(r) for _, r in bottom.iterrows())}.",
    ]
    if vix_note:
        parts.append(vix_note.strip())

    equity = summary[summary["ticker"].isin(["^GSPC", "^IXIC", "^DJI"])]
    if not equity.empty and equity["return_1d"].notna().any():
        avg = equity["return_1d"].mean()
        bias = "constructive" if avg > 0 else "soft" if avg < 0 else "mixed"
        parts.append(f"US equity complex bias appears {bias} versus the prior close.")

    return " ".join(parts)
