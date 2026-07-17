"""
Market data collection via Yahoo Finance (yfinance).

Provides download helpers for the Global Market Overview and equity watchlists.
Results can optionally be persisted to the `market_price` table.

Fallback order when live download fails:
1. Cached rows in the local `market_price` table
2. Deterministic demo data (`services.demo_data`)
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta
from typing import Iterable

import pandas as pd
import yfinance as yf
from sqlalchemy import text

from config.settings import settings
from database.connection import get_engine, init_db
from services.data_processing import compute_daily_returns, normalize_ohlcv
from services.demo_data import generate_demo_market_data

logger = logging.getLogger(__name__)

EMPTY_OHLCV = pd.DataFrame(
    columns=["date", "ticker", "open", "high", "low", "close", "volume", "return"]
)


def _parse_batch_download(raw: pd.DataFrame, ticker_list: list[str]) -> list[pd.DataFrame]:
    """Normalize a yfinance batch download into tidy per-ticker frames."""
    frames: list[pd.DataFrame] = []
    if raw is None or raw.empty:
        return frames

    if len(ticker_list) == 1:
        try:
            frames.append(normalize_ohlcv(raw, ticker_list[0]))
        except Exception as exc:
            logger.warning("Failed to normalize %s: %s", ticker_list[0], exc)
        return frames

    for ticker in ticker_list:
        try:
            if isinstance(raw.columns, pd.MultiIndex):
                if ticker not in raw.columns.get_level_values(0):
                    continue
                subset = raw[ticker].dropna(how="all")
                if subset.empty:
                    continue
                frames.append(normalize_ohlcv(subset, ticker))
            else:
                frames.append(normalize_ohlcv(raw, ticker))
        except Exception as exc:
            logger.warning("Failed to normalize %s: %s", ticker, exc)
    return frames


def _download_yahoo_batch(
    ticker_list: list[str],
    start: datetime,
    end: datetime,
) -> pd.DataFrame:
    """
    Attempt a single batch Yahoo download.

    Falls back to a short sequential pass only when the batch partially succeeds
    for a subset of tickers (not when the network is entirely blocked).
    """
    try:
        raw = yf.download(
            tickers=ticker_list,
            start=start.strftime("%Y-%m-%d"),
            end=(end + timedelta(days=1)).strftime("%Y-%m-%d"),
            group_by="ticker",
            auto_adjust=True,
            threads=True,
            progress=False,
        )
    except Exception as exc:
        logger.warning("Yahoo batch download failed: %s", exc)
        return EMPTY_OHLCV.copy()

    frames = _parse_batch_download(raw, ticker_list)
    recovered = {f["ticker"].iloc[0] for f in frames if not f.empty}

    # If batch got nothing, do not burn time on per-ticker retries.
    if not recovered:
        return EMPTY_OHLCV.copy()

    missing = [t for t in ticker_list if t not in recovered]
    for ticker in missing[:6]:  # cap sequential recovery attempts
        try:
            single = yf.download(
                tickers=ticker,
                start=start.strftime("%Y-%m-%d"),
                end=(end + timedelta(days=1)).strftime("%Y-%m-%d"),
                auto_adjust=True,
                threads=False,
                progress=False,
            )
            if single is not None and not single.empty:
                frames.append(normalize_ohlcv(single, ticker))
        except Exception as exc:
            logger.warning("Sequential recovery failed for %s: %s", ticker, exc)
        time.sleep(0.25)

    if not frames:
        return EMPTY_OHLCV.copy()

    combined = pd.concat(frames, ignore_index=True)
    return compute_daily_returns(combined)


def fetch_ohlcv(
    tickers: Iterable[str],
    lookback_days: int | None = None,
    end: datetime | None = None,
    allow_demo_fallback: bool = True,
) -> tuple[pd.DataFrame, str]:
    """
    Download OHLCV history for one or more tickers.

    Returns
    -------
    prices : tidy DataFrame
        Columns: date, ticker, open, high, low, close, volume, return
    source : str
        One of ``yahoo``, ``database``, ``demo``.
    """
    lookback_days = lookback_days or settings.default_lookback_days
    end = end or datetime.utcnow()
    start = end - timedelta(days=lookback_days + 14)

    ticker_list = list(tickers)
    if not ticker_list:
        return EMPTY_OHLCV.copy(), "yahoo"

    # Optional force-demo for offline demos / CI.
    if settings.force_demo_data:
        return generate_demo_market_data(ticker_list, lookback_days=lookback_days), "demo"

    combined = _download_yahoo_batch(ticker_list, start=start, end=end)
    if not combined.empty:
        cutoff = (end - timedelta(days=lookback_days)).date()
        combined = combined[combined["date"] >= cutoff].reset_index(drop=True)
        if not combined.empty:
            return combined, "yahoo"

    logger.warning("Live Yahoo download incomplete/empty; trying database cache")
    cached = load_market_prices_from_db(ticker_list, lookback_days=lookback_days)
    if not cached.empty:
        return cached, "database"

    if allow_demo_fallback:
        logger.warning("Using demo market data fallback")
        return generate_demo_market_data(ticker_list, lookback_days=lookback_days), "demo"

    return EMPTY_OHLCV.copy(), "yahoo"


def fetch_global_markets(lookback_days: int | None = None) -> tuple[pd.DataFrame, str]:
    """Download the standard Global Market Overview universe."""
    return fetch_ohlcv(settings.market_tickers.keys(), lookback_days=lookback_days)


def get_latest_snapshot(prices: pd.DataFrame) -> pd.DataFrame:
    """
    Build a one-row-per-ticker snapshot with latest price and daily return.

    Columns: ticker, name, close, daily_return, volume, date
    """
    if prices.empty:
        return pd.DataFrame(
            columns=["ticker", "name", "close", "daily_return", "volume", "date"]
        )

    latest_idx = prices.groupby("ticker")["date"].idxmax()
    latest = prices.loc[latest_idx].copy()
    latest["name"] = latest["ticker"].map(settings.market_tickers).fillna(latest["ticker"])
    latest = latest.rename(columns={"return": "daily_return"})
    return latest[["ticker", "name", "close", "daily_return", "volume", "date"]].sort_values(
        "name"
    )


def persist_market_prices(prices: pd.DataFrame) -> int:
    """
    Upsert market prices into the `market_price` table.

    Returns the number of rows written.
    """
    if prices.empty:
        return 0

    init_db()
    engine = get_engine()
    rows = prices.copy()
    rows["date"] = pd.to_datetime(rows["date"]).dt.strftime("%Y-%m-%d")

    upsert_sql = """
        INSERT INTO market_price (date, ticker, open, high, low, close, volume, return)
        VALUES (:date, :ticker, :open, :high, :low, :close, :volume, :return)
        ON CONFLICT(date, ticker) DO UPDATE SET
            open=excluded.open,
            high=excluded.high,
            low=excluded.low,
            close=excluded.close,
            volume=excluded.volume,
            return=excluded.return
    """

    records = rows[
        ["date", "ticker", "open", "high", "low", "close", "volume", "return"]
    ].to_dict(orient="records")

    written = 0
    with engine.begin() as conn:
        for record in records:
            # SQLite uses NULL-safe floats; convert NaN -> None
            clean = {
                key: (None if pd.isna(value) else value) for key, value in record.items()
            }
            conn.execute(text(upsert_sql), clean)
            written += 1

    logger.info("Persisted %s market_price rows", written)
    return written


def load_market_prices_from_db(
    tickers: Iterable[str] | None = None,
    lookback_days: int | None = None,
) -> pd.DataFrame:
    """Load previously stored prices from SQLite (optional cache path)."""
    init_db()
    lookback_days = lookback_days or settings.default_lookback_days
    cutoff = (datetime.utcnow() - timedelta(days=lookback_days)).strftime("%Y-%m-%d")

    sql = "SELECT date, ticker, open, high, low, close, volume, return FROM market_price WHERE date >= :cutoff"
    params: dict = {"cutoff": cutoff}

    ticker_list = list(tickers) if tickers is not None else []
    if ticker_list:
        placeholders = ", ".join([f":t{i}" for i in range(len(ticker_list))])
        sql += f" AND ticker IN ({placeholders})"
        for i, ticker in enumerate(ticker_list):
            params[f"t{i}"] = ticker

    sql += " ORDER BY date ASC"

    engine = get_engine()
    with engine.connect() as conn:
        df = pd.read_sql(text(sql), conn, params=params)

    if not df.empty:
        df["date"] = pd.to_datetime(df["date"]).dt.date
    return df
