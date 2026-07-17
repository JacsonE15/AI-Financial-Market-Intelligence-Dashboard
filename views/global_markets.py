"""Tab 1 — Global Market Overview."""

from __future__ import annotations

import streamlit as st

from components.charts import (
    daily_return_bar_chart,
    normalized_comparison_chart,
    price_trend_chart,
    return_heatmap,
)
from services.ai_report import generate_market_summary
from services.data_processing import (
    build_return_heatmap_matrix,
    format_pct,
    normalized_performance,
    period_performance_summary,
)
from services.market_data import fetch_global_markets, get_latest_snapshot, persist_market_prices


@st.cache_data(ttl=300, show_spinner=False)
def _load_global_market_data(lookback_days: int) -> tuple:
    """Cached market download + derived tables (5-minute TTL)."""
    prices, source = fetch_global_markets(lookback_days=lookback_days)
    snapshot = get_latest_snapshot(prices)
    summary = period_performance_summary(prices)
    rebased = normalized_performance(prices)
    heatmap = build_return_heatmap_matrix(prices, periods=min(20, lookback_days))
    return prices, snapshot, summary, rebased, heatmap, source


def render_global_market_overview() -> None:
    """Render the Phase-1 Global Market Overview tab."""
    st.subheader("Global Market Overview")
    st.caption(
        "Cross-asset snapshot for the morning desk — equities, volatility, rates, FX, commodities, and major futures."
    )

    col_a, col_b, col_c = st.columns([1.2, 1, 1])
    with col_a:
        lookback = st.select_slider(
            "Lookback window",
            options=[30, 60, 90, 180, 252],
            value=90,
            format_func=lambda d: f"{d} days",
        )
    with col_b:
        persist = st.checkbox("Save to local DB", value=False, help="Upsert into SQLite market_price table")
    with col_c:
        refresh = st.button("Refresh market data", type="primary", use_container_width=True)

    if refresh:
        _load_global_market_data.clear()

    try:
        with st.spinner("Fetching Yahoo Finance market data..."):
            prices, snapshot, summary, rebased, heatmap, source = _load_global_market_data(lookback)
    except Exception as exc:
        st.error(f"Unable to load market data: {exc}")
        st.info("Check your network connection. Yahoo Finance may occasionally rate-limit requests.")
        return

    if prices.empty or snapshot.empty:
        st.warning("No market data returned. Try refreshing in a moment.")
        return

    if source == "yahoo":
        st.caption("Data source: Yahoo Finance (live)")
    elif source == "database":
        st.warning("Live Yahoo download unavailable — showing cached database prices.")
    else:
        st.warning(
            "Live Yahoo download unavailable (rate limit / network). "
            "Showing deterministic **demo data** so the dashboard remains usable. "
            "Click Refresh later to retry live prices."
        )

    if persist:
        try:
            n = persist_market_prices(prices)
            st.success(f"Persisted {n} rows to the local database.")
        except Exception as exc:
            st.warning(f"Could not persist prices: {exc}")

    # --- KPI strip ---
    st.markdown("##### Session Snapshot")
    kpi_cols = st.columns(4)
    focus_order = ["^GSPC", "^IXIC", "^DJI", "^VIX"]
    focus = snapshot.set_index("ticker").reindex(focus_order).dropna(how="all")

    for i, (ticker, row) in enumerate(focus.iterrows()):
        with kpi_cols[i]:
            delta = row.get("daily_return")
            delta_str = format_pct(delta) if delta == delta else None
            st.metric(
                label=row.get("name", ticker),
                value=f"{row['close']:,.2f}",
                delta=delta_str,
            )

    # Remaining assets as compact metrics
    others = snapshot[~snapshot["ticker"].isin(focus_order)]
    if not others.empty:
        other_cols = st.columns(min(4, len(others)))
        for i, (_, row) in enumerate(others.iterrows()):
            with other_cols[i % len(other_cols)]:
                st.metric(
                    label=row["name"],
                    value=f"{row['close']:,.2f}",
                    delta=format_pct(row["daily_return"]),
                )

    st.divider()

    # --- AI / rule-based summary ---
    st.markdown("##### Market Summary")
    narrative = generate_market_summary(summary)
    st.info(narrative)

    # --- Charts ---
    left, right = st.columns([1.15, 1])
    with left:
        st.plotly_chart(daily_return_bar_chart(snapshot), use_container_width=True)
    with right:
        st.plotly_chart(return_heatmap(heatmap), use_container_width=True)

    st.plotly_chart(normalized_comparison_chart(rebased), use_container_width=True)

    # Single-asset historical drill-down
    st.markdown("##### Historical Price Chart")
    name_to_ticker = {v: k for k, v in zip(snapshot["ticker"], snapshot["name"])}
    # Prefer friendly names while keeping stable ordering
    options = list(snapshot.sort_values("name")["name"])
    selected_name = st.selectbox("Select asset", options=options, index=options.index("S&P 500") if "S&P 500" in options else 0)
    selected_ticker = name_to_ticker[selected_name]
    st.plotly_chart(
        price_trend_chart(prices, selected_ticker, selected_name),
        use_container_width=True,
    )

    # Performance table
    st.markdown("##### Performance Table")
    display = summary.copy()
    for col in ["return_1d", "return_5d", "return_1m"]:
        display[col] = display[col].map(lambda x: format_pct(x))
    display["last_price"] = display["last_price"].map(lambda x: f"{x:,.2f}")
    display = display.rename(
        columns={
            "name": "Asset",
            "ticker": "Ticker",
            "last_price": "Last",
            "return_1d": "1D",
            "return_5d": "5D",
            "return_1m": "1M",
            "as_of": "As of",
        }
    )
    st.dataframe(
        display[["Asset", "Ticker", "Last", "1D", "5D", "1M", "As of"]],
        use_container_width=True,
        hide_index=True,
    )
