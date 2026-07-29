"""Tab 2 — Equity Watchlist."""

from __future__ import annotations

import streamlit as st

from components.charts import price_trend_chart
from config.settings import settings
from services.data_processing import format_pct
from services.indicators import build_watchlist_metrics
from services.market_data import fetch_ohlcv
from services.news_service import fetch_financial_news, sentiment_by_ticker
from services.watchlist_store import load_watchlist, save_watchlist


@st.cache_data(ttl=300, show_spinner=False)
def _load_watchlist_data(tickers: tuple[str, ...], lookback_days: int):
    prices, source = fetch_ohlcv(list(tickers), lookback_days=lookback_days)
    metrics = build_watchlist_metrics(prices)
    news, news_source, _news_err = fetch_financial_news(
        query=" OR ".join(tickers[:6]) if tickers else "stocks",
        limit=30,
    )
    scores = sentiment_by_ticker(news, list(tickers))
    if not metrics.empty:
        metrics = metrics.copy()
        metrics["news_sentiment"] = metrics["ticker"].map(scores).fillna(0.0)
    return prices, metrics, source, news_source


def render_equity_watchlist() -> None:
    st.subheader("Equity Watchlist")
    st.caption("Customizable equity monitor with technicals and news sentiment for the morning desk.")

    if "watchlist" not in st.session_state:
        st.session_state.watchlist = load_watchlist()

    left, right = st.columns([2, 1])
    with left:
        tickers_text = st.text_input(
            "Watchlist tickers (comma-separated)",
            value=", ".join(st.session_state.watchlist),
            help="Example: AAPL, MSFT, NVDA, JPM",
        )
    with right:
        lookback = st.selectbox("History", options=[120, 180, 252, 360], index=2, format_func=lambda d: f"{d} days")

    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("Apply watchlist", type="primary", use_container_width=True):
            parsed = [t.strip().upper() for t in tickers_text.split(",") if t.strip()]
            if not parsed:
                st.error("Add at least one ticker.")
            else:
                st.session_state.watchlist = parsed
                save_watchlist(parsed)
                _load_watchlist_data.clear()
                st.success(f"Watchlist updated ({len(parsed)} names).")
    with c2:
        if st.button("Reset to defaults", use_container_width=True):
            st.session_state.watchlist = list(settings.default_watchlist)
            save_watchlist(st.session_state.watchlist)
            _load_watchlist_data.clear()
    with c3:
        if st.button("Refresh data", use_container_width=True):
            _load_watchlist_data.clear()

    tickers = tuple(st.session_state.watchlist)
    if not tickers:
        st.warning("Watchlist is empty.")
        return

    with st.spinner("Loading watchlist prices & sentiment..."):
        prices, metrics, source, news_source = _load_watchlist_data(tickers, lookback)

    if source != "yahoo":
        st.warning(f"Price source: **{source}** (live Yahoo unavailable or forced demo).")
    else:
        st.caption("Price source: Yahoo Finance")
    st.caption(f"Sentiment source: {news_source}")

    if metrics.empty:
        st.warning("No watchlist metrics available.")
        return

    # KPI strip for top movers
    movers = metrics.dropna(subset=["daily_return"]).sort_values("daily_return", ascending=False)
    top_cols = st.columns(min(4, len(movers)))
    for i, (_, row) in enumerate(movers.head(4).iterrows()):
        with top_cols[i]:
            st.metric(row["ticker"], f"${row['price']:,.2f}", format_pct(row["daily_return"]))

    display = metrics.copy()
    display["daily_return"] = display["daily_return"].map(format_pct)
    display["volume_change"] = display["volume_change"].map(format_pct)
    display["hist_vol"] = display["hist_vol"].map(lambda x: format_pct(x) if x == x else "—")
    display["rsi_14"] = display["rsi_14"].map(lambda x: f"{x:.1f}" if x == x else "—")
    display["sma_20"] = display["sma_20"].map(lambda x: f"{x:,.2f}" if x == x else "—")
    display["sma_50"] = display["sma_50"].map(lambda x: f"{x:,.2f}" if x == x else "—")
    display["price"] = display["price"].map(lambda x: f"{x:,.2f}")
    display["high_52w"] = display["high_52w"].map(lambda x: f"{x:,.2f}")
    display["low_52w"] = display["low_52w"].map(lambda x: f"{x:,.2f}")
    display["pct_from_high"] = display["pct_from_high"].map(format_pct)
    display["news_sentiment"] = display["news_sentiment"].map(lambda x: f"{x:+.2f}")

    st.markdown("##### Watchlist Monitor")
    st.dataframe(
        display.rename(
            columns={
                "ticker": "Ticker",
                "price": "Price",
                "daily_return": "Daily Return",
                "volume_change": "Volume Δ",
                "hist_vol": "Hist. Vol",
                "rsi_14": "RSI(14)",
                "sma_20": "SMA20",
                "sma_50": "SMA50",
                "high_52w": "52W High",
                "low_52w": "52W Low",
                "pct_from_high": "% from High",
                "news_sentiment": "News Sentiment",
                "as_of": "As of",
            }
        )[
            [
                "Ticker",
                "Price",
                "Daily Return",
                "Volume Δ",
                "Hist. Vol",
                "RSI(14)",
                "SMA20",
                "SMA50",
                "52W High",
                "52W Low",
                "% from High",
                "News Sentiment",
                "As of",
            ]
        ],
        use_container_width=True,
        hide_index=True,
    )

    st.markdown("##### Name Drill-down")
    selected = st.selectbox("Select ticker", options=list(tickers))
    mrow = metrics.loc[metrics["ticker"] == selected]
    if not mrow.empty:
        r = mrow.iloc[0]
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("RSI(14)", f"{r['rsi_14']:.1f}" if r["rsi_14"] == r["rsi_14"] else "—")
        k2.metric("Hist. Vol", format_pct(r["hist_vol"]))
        k3.metric("52W High", f"${r['high_52w']:,.2f}")
        k4.metric("News Sentiment", f"{r['news_sentiment']:+.2f}")
    st.plotly_chart(price_trend_chart(prices, selected, selected), use_container_width=True)
