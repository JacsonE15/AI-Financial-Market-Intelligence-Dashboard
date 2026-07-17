"""
SQL schema definitions for the market intelligence platform.

Tables align with the project requirements and are created on first run.
"""

BASE_SCHEMA_SQL: list[str] = [
    """
    CREATE TABLE IF NOT EXISTS market_price (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date DATE NOT NULL,
        ticker TEXT NOT NULL,
        open REAL,
        high REAL,
        low REAL,
        close REAL,
        volume REAL,
        return REAL,
        UNIQUE(date, ticker)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS macro_indicator (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date DATE NOT NULL,
        indicator TEXT NOT NULL,
        value REAL,
        UNIQUE(date, indicator)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS news (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date DATETIME NOT NULL,
        title TEXT NOT NULL,
        content TEXT,
        sentiment REAL,
        source TEXT,
        url TEXT,
        category TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS risk_metrics (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date DATE NOT NULL,
        ticker TEXT NOT NULL,
        volatility REAL,
        VaR REAL,
        beta REAL,
        correlation REAL,
        UNIQUE(date, ticker)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_market_price_ticker_date
    ON market_price(ticker, date)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_macro_indicator_name_date
    ON macro_indicator(indicator, date)
    """,
    """
    CREATE TABLE IF NOT EXISTS watchlist (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ticker TEXT NOT NULL UNIQUE,
        added_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """,
]
