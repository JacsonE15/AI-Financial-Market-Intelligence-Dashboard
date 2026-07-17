"""Persist and load the equity watchlist from SQLite."""

from __future__ import annotations

from sqlalchemy import text

from config.settings import settings
from database.connection import get_engine, init_db


def load_watchlist() -> list[str]:
    """Return tickers from DB, or defaults when the table is empty."""
    init_db()
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT ticker FROM watchlist ORDER BY added_at, ticker")).fetchall()
    tickers = [r[0] for r in rows]
    return tickers or list(settings.default_watchlist)


def save_watchlist(tickers: list[str]) -> None:
    """Replace the stored watchlist with the provided ticker list."""
    init_db()
    clean = []
    seen = set()
    for t in tickers:
        sym = (t or "").strip().upper()
        if not sym or sym in seen:
            continue
        seen.add(sym)
        clean.append(sym)

    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM watchlist"))
        for sym in clean:
            conn.execute(text("INSERT INTO watchlist (ticker) VALUES (:t)"), {"t": sym})
