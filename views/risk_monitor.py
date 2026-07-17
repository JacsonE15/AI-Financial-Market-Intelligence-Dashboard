"""Tab 3 — Derivatives & Risk Monitor."""

from __future__ import annotations

import streamlit as st

from components.charts import correlation_heatmap, drawdown_chart
from config.settings import settings
from services.data_processing import format_pct
from services.market_data import fetch_ohlcv
from services.risk_engine import (
    compute_portfolio_risk,
    default_futures_book,
    default_options_book,
    risk_alerts,
)


@st.cache_data(ttl=300, show_spinner=False)
def _load_risk_universe(tickers: tuple[str, ...], lookback_days: int):
    # Include benchmark for beta
    universe = list(dict.fromkeys(list(tickers) + ["^GSPC", "ES=F", "NQ=F", "CL=F", "GC=F", "YM=F", "SPY"]))
    prices, source = fetch_ohlcv(universe, lookback_days=lookback_days)
    return prices, source


def render_derivatives_risk() -> None:
    st.subheader("Derivatives & Risk Monitor")
    st.caption("Middle-office portfolio risk, options Greeks, and futures PnL / margin.")

    weights = dict(settings.default_portfolio_weights)
    lookback = st.select_slider("Risk lookback", options=[90, 120, 180, 252], value=180)

    c1, c2 = st.columns(2)
    with c1:
        var_limit = st.number_input("Desk VaR limit (daily, fraction)", min_value=0.005, max_value=0.1, value=0.02, step=0.005)
    with c2:
        dd_limit = st.number_input("Drawdown soft floor", min_value=-0.5, max_value=-0.01, value=-0.08, step=0.01)

    if st.button("Refresh risk data", type="primary"):
        _load_risk_universe.clear()

    with st.spinner("Computing portfolio risk..."):
        prices, source = _load_risk_universe(tuple(weights.keys()), lookback)

    if source != "yahoo":
        st.warning(f"Market data source: **{source}**")

    risk = compute_portfolio_risk(prices, weights, benchmark_ticker="^GSPC")
    if not risk:
        st.error("Unable to compute portfolio risk.")
        return

    st.markdown("##### Portfolio Risk Metrics")
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("VaR 95%", format_pct(risk["portfolio_var"]))
    m2.metric("Expected Shortfall", format_pct(risk["portfolio_es"]))
    m3.metric("Volatility (ann.)", format_pct(risk["portfolio_vol"]))
    m4.metric("Beta vs S&P", f"{risk['portfolio_beta']:.2f}" if risk["portfolio_beta"] == risk["portfolio_beta"] else "—")
    m5.metric("Max Drawdown", format_pct(risk["portfolio_drawdown"]))

    alerts = risk_alerts(risk, var_limit=var_limit, dd_limit=dd_limit)
    st.info("**Risk alerts**\n\n" + "\n".join(f"- {a}" for a in alerts))

    left, right = st.columns(2)
    with left:
        st.plotly_chart(correlation_heatmap(risk["corr"]), use_container_width=True)
    with right:
        st.plotly_chart(drawdown_chart(risk["drawdown_path"]), use_container_width=True)

    per = risk["per_name"].copy()
    if not per.empty:
        show = per.copy()
        show["weight"] = show["weight"].map(lambda x: f"{x:.0%}")
        show["volatility"] = show["volatility"].map(format_pct)
        show["VaR_95"] = show["VaR_95"].map(format_pct)
        show["beta"] = show["beta"].map(lambda x: f"{x:.2f}" if x == x else "—")
        show["max_drawdown"] = show["max_drawdown"].map(format_pct)
        st.markdown("##### Name-level Risk")
        st.dataframe(
            show.rename(
                columns={
                    "ticker": "Ticker",
                    "weight": "Weight",
                    "volatility": "Vol",
                    "VaR_95": "VaR 95%",
                    "beta": "Beta",
                    "max_drawdown": "Max DD",
                }
            ),
            use_container_width=True,
            hide_index=True,
        )

    # Spot map for options / futures marks
    latest = (
        prices.sort_values("date")
        .groupby("ticker")
        .tail(1)
        .set_index("ticker")["close"]
        .to_dict()
    )

    st.markdown("##### Options Monitoring")
    options = default_options_book(spot_map=latest)
    opt_show = options.copy()
    for col in ["spot", "mid", "delta", "gamma", "theta", "vega"]:
        opt_show[col] = opt_show[col].map(lambda x: f"{x:,.4f}" if abs(x) < 10 else f"{x:,.2f}")
    opt_show["iv"] = opt_show["iv"].map(lambda x: f"{x:.0%}")
    st.dataframe(
        opt_show.rename(
            columns={
                "underlying": "Underlying",
                "type": "Type",
                "strike": "Strike",
                "expiry": "Expiry",
                "spot": "Spot",
                "iv": "IV",
                "qty": "Qty",
                "mid": "Mid",
                "delta": "Delta",
                "gamma": "Gamma",
                "theta": "Theta",
                "vega": "Vega",
            }
        )[
            ["Underlying", "Type", "Strike", "Expiry", "Spot", "IV", "Qty", "Mid", "Delta", "Gamma", "Theta", "Vega"]
        ],
        use_container_width=True,
        hide_index=True,
    )
    g1, g2, g3, g4 = st.columns(4)
    g1.metric("Book Delta", f"{options['delta'].sum():,.2f}")
    g2.metric("Book Gamma", f"{options['gamma'].sum():,.4f}")
    g3.metric("Book Theta", f"{options['theta'].sum():,.2f}")
    g4.metric("Book Vega", f"{options['vega'].sum():,.2f}")

    st.markdown("##### Futures Monitoring")
    futures = default_futures_book(price_map=latest)
    fut_show = futures.copy()
    fut_show["last"] = fut_show["last"].map(lambda x: f"{x:,.2f}")
    fut_show["margin_requirement"] = fut_show["margin_requirement"].map(lambda x: f"${x:,.0f}")
    fut_show["daily_pnl"] = fut_show["daily_pnl"].map(lambda x: f"${x:,.0f}")
    fut_show["notional"] = fut_show["notional"].map(lambda x: f"${x:,.0f}")
    st.dataframe(
        fut_show.rename(
            columns={
                "contract": "Contract",
                "name": "Name",
                "position": "Position",
                "last": "Last",
                "margin_requirement": "Margin Req.",
                "daily_pnl": "Daily PnL",
                "notional": "Notional",
            }
        )[["Contract", "Name", "Position", "Last", "Margin Req.", "Daily PnL", "Notional"]],
        use_container_width=True,
        hide_index=True,
    )
    f1, f2 = st.columns(2)
    f1.metric("Total Margin", f"${futures['margin_requirement'].sum():,.0f}")
    f2.metric("Futures Daily PnL", f"${futures['daily_pnl'].sum():,.0f}")
