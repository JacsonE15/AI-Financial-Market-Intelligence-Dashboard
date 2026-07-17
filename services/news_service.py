"""
Financial news collection, classification, and sentiment scoring.

Uses News API / Finnhub when keys are present; otherwise demo headlines.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta
from typing import Any

import pandas as pd
import requests
from sqlalchemy import text

from config.settings import settings
from database.connection import get_engine, init_db

logger = logging.getLogger(__name__)

# Simple lexicon for offline sentiment (adequate for demo / fallback).
_POS = {
    "surge", "rally", "gain", "gains", "beat", "strong", "growth", "record",
    "upgrade", "bullish", "optimistic", "rise", "rises", "jump", "jumps",
    "profit", "outperform", "expand", "recovery", "lift", "eases", "ease",
    "upside", "firm", "improving", "support",
}
_NEG = {
    "fall", "falls", "drop", "drops", "miss", "weak", "cut", "cuts", "downgrade",
    "bearish", "fear", "risk", "lawsuit", "probe", "decline", "declines",
    "loss", "recession", "inflation", "selloff", "slump", "warning",
}

_SECTOR_KEYWORDS: dict[str, list[str]] = {
    "Technology": ["apple", "microsoft", "nvidia", "google", "meta", "semiconductor", "ai", "chip", "software", "cloud"],
    "Financials": ["bank", "fed", "treasury", "yield", "credit", "jpmorgan", "goldman", "fintech"],
    "Energy": ["oil", "crude", "opec", "energy", "gas", "exxon", "chevron"],
    "Healthcare": ["pharma", "drug", "biotech", "fda", "health", "hospital"],
    "Macro": ["inflation", "gdp", "unemployment", "cpi", "fomc", "rate cut", "rate hike", "jobs", "recession"],
}

_COMPANY_TICKERS: dict[str, str] = {
    "apple": "AAPL",
    "microsoft": "MSFT",
    "nvidia": "NVDA",
    "amazon": "AMZN",
    "google": "GOOGL",
    "alphabet": "GOOGL",
    "meta": "META",
    "tesla": "TSLA",
    "jpmorgan": "JPM",
    "exxon": "XOM",
}


def score_sentiment(text: str) -> float:
    """Return sentiment in [-1, 1] from a lightweight lexicon."""
    tokens = re.findall(r"[a-zA-Z']+", (text or "").lower())
    if not tokens:
        return 0.0
    score = 0
    for tok in tokens:
        if tok in _POS:
            score += 1
        elif tok in _NEG:
            score -= 1
    # Normalize roughly into [-1, 1]
    return max(-1.0, min(1.0, score / max(3.0, len(tokens) * 0.08)))


def classify_news(title: str, content: str = "") -> tuple[str, str]:
    """
    Classify into (category, entity).

    category ∈ {Sector, Macro, Company, General}
    entity is ticker or sector label when detected.
    """
    blob = f"{title} {content}".lower()
    for company, ticker in _COMPANY_TICKERS.items():
        if company in blob:
            return "Company", ticker

    # Macro first so Fed / CPI / GDP are not swallowed by sector lists.
    for key in _SECTOR_KEYWORDS.get("Macro", []):
        if key in blob:
            return "Macro", "Macro"

    for sector, keys in _SECTOR_KEYWORDS.items():
        if sector == "Macro":
            continue
        if any(k in blob for k in keys):
            return "Sector", sector
    return "General", "—"


def estimate_market_impact(sentiment: float, category: str) -> str:
    """Map sentiment + category into a qualitative impact label."""
    magnitude = abs(sentiment)
    if category == "Macro" and magnitude >= 0.35:
        level = "High"
    elif magnitude >= 0.45:
        level = "High"
    elif magnitude >= 0.2:
        level = "Medium"
    else:
        level = "Low"
    direction = "Bullish" if sentiment > 0.05 else "Bearish" if sentiment < -0.05 else "Neutral"
    return f"{level} / {direction}"


def summarize_headline(title: str, content: str = "") -> str:
    """Short extractive summary (1 sentence) without an LLM."""
    body = (content or "").strip()
    if body:
        sentence = re.split(r"(?<=[.!?])\s+", body)[0]
        if len(sentence) > 40:
            return sentence[:220] + ("…" if len(sentence) > 220 else "")
    return title


def _demo_news(limit: int = 20) -> pd.DataFrame:
    """Deterministic sample wire for offline / no-API environments."""
    now = datetime.utcnow()
    samples = [
        ("Apple supplier chain eases; analysts lift AAPL targets", "Reuters", "Technology",
         "Apple's key Asian suppliers reported improving utilization, supporting near-term iPhone production."),
        ("Fed officials signal patience on next rate move", "Bloomberg", "Macro",
         "Several Fed speakers emphasized data dependence as markets reprice the path of policy rates."),
        ("Nvidia demand remains firm as AI capex cycle extends", "CNBC", "Technology",
         "Cloud providers reiterated elevated GPU orders, keeping NVDA in focus for equity desks."),
        ("Crude oil slips on inventory build and demand concerns", "WSJ", "Energy",
         "A larger-than-expected inventory build weighed on WTI futures in overnight trade."),
        ("JPMorgan flags softer credit card spending growth", "FT", "Financials",
         "Management commentary pointed to moderating consumer spending momentum into the quarter."),
        ("Treasury yields edge higher ahead of CPI release", "MarketWatch", "Macro",
         "The 10-year yield firmed as investors positioned for the inflation print."),
        ("Microsoft cloud margins surprise to the upside", "Barron's", "Technology",
         "Azure growth and cost discipline helped lift profitability versus consensus."),
        ("Biotech shares fall after FDA delay on key drug", "Yahoo Finance", "Healthcare",
         "The agency requested additional trial data, pushing the decision timeline out by months."),
        ("Dollar strengthens as risk appetite softens", "Reuters", "Macro",
         "Safe-haven demand supported the USD index while equity futures turned mixed."),
        ("Exxon outlines higher upstream spending plan", "Bloomberg", "Energy",
         "The company guided to elevated capex focused on high-return projects."),
        ("Tesla deliveries miss quiet expectations", "CNBC", "Company",
         "Deliveries came in slightly below the quiet survey, pressuring the shares pre-market."),
        ("Unemployment claims remain contained", "AP", "Macro",
         "Initial jobless claims stayed near cycle lows, supporting a soft-landing narrative."),
    ]
    rows = []
    for i, (title, source, _, content) in enumerate(samples[:limit]):
        sentiment = score_sentiment(f"{title} {content}")
        category, entity = classify_news(title, content)
        rows.append(
            {
                "date": now - timedelta(hours=i * 2 + 1),
                "title": title,
                "content": content,
                "summary": summarize_headline(title, content),
                "sentiment": sentiment,
                "source": source,
                "url": "",
                "category": category,
                "entity": entity,
                "market_impact": estimate_market_impact(sentiment, category),
            }
        )
    return pd.DataFrame(rows)


def _fetch_newsapi(query: str, limit: int) -> list[dict[str, Any]]:
    if not settings.news_api_key:
        return []
    url = "https://newsapi.org/v2/everything"
    params = {
        "q": query,
        "language": "en",
        "sortBy": "publishedAt",
        "pageSize": min(limit, 50),
        "apiKey": settings.news_api_key,
    }
    resp = requests.get(url, params=params, timeout=20)
    resp.raise_for_status()
    articles = resp.json().get("articles", [])
    out = []
    for a in articles:
        out.append(
            {
                "date": a.get("publishedAt"),
                "title": a.get("title") or "",
                "content": a.get("description") or a.get("content") or "",
                "source": (a.get("source") or {}).get("name") or "NewsAPI",
                "url": a.get("url") or "",
            }
        )
    return out


def _fetch_finnhub(query: str, limit: int) -> list[dict[str, Any]]:
    if not settings.finnhub_api_key:
        return []
    # Company news endpoint works best with a symbol; fall back to general market news.
    symbol = query.upper() if re.fullmatch(r"[A-Z]{1,5}", query.upper()) else None
    if symbol:
        url = "https://finnhub.io/api/v1/company-news"
        today = datetime.utcnow().date()
        params = {
            "symbol": symbol,
            "from": (today - timedelta(days=7)).isoformat(),
            "to": today.isoformat(),
            "token": settings.finnhub_api_key,
        }
    else:
        url = "https://finnhub.io/api/v1/news"
        params = {"category": "general", "token": settings.finnhub_api_key}

    resp = requests.get(url, params=params, timeout=20)
    resp.raise_for_status()
    articles = resp.json()
    if not isinstance(articles, list):
        return []
    out = []
    for a in articles[:limit]:
        ts = a.get("datetime")
        dt = datetime.utcfromtimestamp(ts) if isinstance(ts, (int, float)) else datetime.utcnow()
        out.append(
            {
                "date": dt.isoformat(),
                "title": a.get("headline") or "",
                "content": a.get("summary") or "",
                "source": a.get("source") or "Finnhub",
                "url": a.get("url") or "",
            }
        )
    return out


def _enrich(raw_rows: list[dict[str, Any]]) -> pd.DataFrame:
    rows = []
    for item in raw_rows:
        title = item.get("title") or ""
        content = item.get("content") or ""
        sentiment = score_sentiment(f"{title} {content}")
        category, entity = classify_news(title, content)
        date_val = item.get("date")
        try:
            date_parsed = pd.to_datetime(date_val, utc=True).tz_localize(None)
        except Exception:
            date_parsed = datetime.utcnow()
        rows.append(
            {
                "date": date_parsed,
                "title": title,
                "content": content,
                "summary": summarize_headline(title, content),
                "sentiment": sentiment,
                "source": item.get("source") or "Unknown",
                "url": item.get("url") or "",
                "category": category,
                "entity": entity,
                "market_impact": estimate_market_impact(sentiment, category),
            }
        )
    return pd.DataFrame(rows)


def fetch_financial_news(query: str = "stock market OR federal reserve OR earnings", limit: int = 25) -> tuple[pd.DataFrame, str]:
    """
    Collect and enrich financial news.

    Returns (dataframe, source_label).
    """
    raw: list[dict[str, Any]] = []
    source = "demo"

    try:
        if settings.news_api_key:
            raw = _fetch_newsapi(query, limit)
            source = "newsapi"
        elif settings.finnhub_api_key:
            raw = _fetch_finnhub(query, limit)
            source = "finnhub"
    except Exception as exc:
        logger.warning("Live news fetch failed: %s", exc)
        raw = []

    if not raw:
        return _demo_news(limit), "demo"

    frame = _enrich(raw)
    if frame.empty:
        return _demo_news(limit), "demo"
    return frame.head(limit).reset_index(drop=True), source


def persist_news(news: pd.DataFrame) -> int:
    """Upsert-style insert into the news table (append by title+date)."""
    if news.empty:
        return 0
    init_db()
    engine = get_engine()
    sql = """
        INSERT INTO news (date, title, content, sentiment, source, url, category)
        VALUES (:date, :title, :content, :sentiment, :source, :url, :category)
    """
    written = 0
    with engine.begin() as conn:
        for _, row in news.iterrows():
            conn.execute(
                text(sql),
                {
                    "date": pd.to_datetime(row["date"]).strftime("%Y-%m-%d %H:%M:%S"),
                    "title": row["title"],
                    "content": row.get("summary") or row.get("content") or "",
                    "sentiment": float(row["sentiment"]) if pd.notna(row["sentiment"]) else None,
                    "source": row.get("source"),
                    "url": row.get("url"),
                    "category": row.get("category"),
                },
            )
            written += 1
    return written


def sentiment_by_ticker(news: pd.DataFrame, tickers: list[str]) -> dict[str, float]:
    """Average news sentiment for watchlist names (0 if no articles)."""
    scores = {t: 0.0 for t in tickers}
    if news.empty:
        return scores
    for ticker in tickers:
        mask = (news["entity"] == ticker) | news["title"].str.contains(ticker, case=False, na=False)
        subset = news.loc[mask, "sentiment"]
        if not subset.empty:
            scores[ticker] = float(subset.mean())
    return scores
