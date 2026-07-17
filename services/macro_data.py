"""Macro indicator collection via FRED with demo fallback."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import requests
from sqlalchemy import text

from config.settings import settings
from database.connection import get_engine, init_db

logger = logging.getLogger(__name__)

# Common FRED series used in morning macro updates.
FRED_SERIES: dict[str, str] = {
    "CPIAUCSL": "CPI (All Urban)",
    "UNRATE": "Unemployment Rate",
    "GDP": "Real GDP",
    "DFF": "Fed Funds Rate",
    "T10Y2Y": "10Y-2Y Spread",
    "VIXCLS": "VIX (FRED)",
}


def _demo_macro() -> pd.DataFrame:
    """Recent-looking macro snapshot for offline demos."""
    as_of = datetime.utcnow().date() - timedelta(days=2)
    values = {
        "CPIAUCSL": 314.2,
        "UNRATE": 4.1,
        "GDP": 22750.0,
        "DFF": 4.33,
        "T10Y2Y": -0.12,
        "VIXCLS": 16.8,
    }
    prior = {
        "CPIAUCSL": 313.5,
        "UNRATE": 4.0,
        "GDP": 22680.0,
        "DFF": 4.33,
        "T10Y2Y": -0.18,
        "VIXCLS": 15.9,
    }
    rows = []
    for code, name in FRED_SERIES.items():
        rows.append(
            {
                "date": as_of,
                "indicator": code,
                "name": name,
                "value": values[code],
                "prior": prior[code],
                "change": values[code] - prior[code],
            }
        )
    return pd.DataFrame(rows)


def fetch_fred_series(series_id: str, limit: int = 12) -> pd.DataFrame:
    """Pull observations for a single FRED series."""
    if not settings.fred_api_key:
        return pd.DataFrame()
    url = "https://api.stlouisfed.org/fred/series/observations"
    params = {
        "series_id": series_id,
        "api_key": settings.fred_api_key,
        "file_type": "json",
        "sort_order": "desc",
        "limit": limit,
    }
    resp = requests.get(url, params=params, timeout=20)
    resp.raise_for_status()
    obs = resp.json().get("observations", [])
    rows = []
    for item in obs:
        try:
            val = float(item["value"])
        except (TypeError, ValueError):
            continue
        rows.append({"date": item["date"], "indicator": series_id, "value": val})
    return pd.DataFrame(rows)


def fetch_macro_snapshot() -> tuple[pd.DataFrame, str]:
    """Latest macro levels + change vs prior print."""
    if not settings.fred_api_key:
        return _demo_macro(), "demo"

    frames = []
    try:
        for code in FRED_SERIES:
            hist = fetch_fred_series(code, limit=6)
            if hist.empty:
                continue
            hist = hist.sort_values("date")
            latest = hist.iloc[-1]
            prior = hist.iloc[-2] if len(hist) > 1 else latest
            frames.append(
                {
                    "date": pd.to_datetime(latest["date"]).date(),
                    "indicator": code,
                    "name": FRED_SERIES[code],
                    "value": float(latest["value"]),
                    "prior": float(prior["value"]),
                    "change": float(latest["value"] - prior["value"]),
                }
            )
    except Exception as exc:
        logger.warning("FRED fetch failed: %s", exc)
        return _demo_macro(), "demo"

    if not frames:
        return _demo_macro(), "demo"
    return pd.DataFrame(frames), "fred"


def persist_macro(macro: pd.DataFrame) -> int:
    if macro.empty:
        return 0
    init_db()
    engine = get_engine()
    sql = """
        INSERT INTO macro_indicator (date, indicator, value)
        VALUES (:date, :indicator, :value)
        ON CONFLICT(date, indicator) DO UPDATE SET value=excluded.value
    """
    n = 0
    with engine.begin() as conn:
        for _, row in macro.iterrows():
            conn.execute(
                text(sql),
                {
                    "date": str(row["date"]),
                    "indicator": row["indicator"],
                    "value": float(row["value"]) if not np.isnan(row["value"]) else None,
                },
            )
            n += 1
    return n


def macro_narrative(macro: pd.DataFrame) -> str:
    if macro.empty:
        return "Macro data unavailable."
    bits = []
    for _, row in macro.iterrows():
        bits.append(f"{row['name']}: {row['value']:.2f} (Δ {row['change']:+.2f})")
    return "Latest prints — " + "; ".join(bits) + "."
