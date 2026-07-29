"""Tab 5 — AI Morning Report Generator."""

from __future__ import annotations

import streamlit as st

from config.settings import settings
from services.ai_report import build_report_context, generate_market_summary, generate_morning_report
from services.data_processing import period_performance_summary
from services.indicators import build_watchlist_metrics
from services.macro_data import fetch_macro_snapshot, macro_narrative, persist_macro
from services.market_data import fetch_global_markets, fetch_ohlcv
from services.news_service import fetch_financial_news
from services.risk_engine import compute_portfolio_risk, risk_alerts
from services.watchlist_store import load_watchlist


@st.cache_data(ttl=300, show_spinner=False)
def _gather_morning_inputs(lookback_days: int):
    market_prices, market_source = fetch_global_markets(lookback_days=lookback_days)
    market_summary_df = period_performance_summary(market_prices)
    markets_text = generate_market_summary(market_summary_df)

    watchlist = load_watchlist()
    eq_prices, eq_source = fetch_ohlcv(watchlist, lookback_days=max(lookback_days, 252))
    metrics = build_watchlist_metrics(eq_prices)

    weights = dict(settings.default_portfolio_weights)
    risk_universe = list(dict.fromkeys(list(weights.keys()) + ["^GSPC"]))
    risk_prices, risk_source = fetch_ohlcv(risk_universe, lookback_days=lookback_days)
    risk = compute_portfolio_risk(risk_prices, weights)
    alerts = risk_alerts(risk)

    macro, macro_source = fetch_macro_snapshot()
    macro_text = macro_narrative(macro)

    news, news_source, _news_err = fetch_financial_news(limit=12)

    return {
        "markets_text": markets_text,
        "macro_text": macro_text,
        "macro": macro,
        "metrics": metrics,
        "alerts": alerts,
        "news": news,
        "sources": {
            "markets": market_source,
            "equities": eq_source,
            "risk": risk_source,
            "macro": macro_source,
            "news": news_source,
        },
    }


def render_morning_report() -> None:
    st.subheader("AI Morning Report Generator")
    st.caption("Meeting-ready overnight brief combining markets, macro, equities, risk, and news.")

    lookback = st.select_slider("Data lookback for report inputs", options=[60, 90, 120, 180], value=90)
    persist = st.checkbox("Persist macro snapshot to DB", value=False)

    c1, c2 = st.columns(2)
    with c1:
        generate = st.button("Generate morning report", type="primary", use_container_width=True)
    with c2:
        if st.button("Clear cached inputs", use_container_width=True):
            _gather_morning_inputs.clear()
            st.session_state.pop("morning_report_md", None)

    if settings.qwen_api_key:
        st.success(f"LLM enabled — model `{settings.qwen_model}`")
    else:
        st.info("No `QWEN_API_KEY` set — generating a structured rule-based brief (still meeting-ready).")

    if generate:
        with st.spinner("Gathering desk inputs and drafting the brief..."):
            payload = _gather_morning_inputs(lookback)
            if persist and not payload["macro"].empty:
                try:
                    persist_macro(payload["macro"])
                except Exception as exc:
                    st.warning(f"Macro persistence failed: {exc}")

            context = build_report_context(
                market_summary=payload["markets_text"],
                macro_text=payload["macro_text"],
                watchlist_metrics=payload["metrics"],
                risk_alert_list=payload["alerts"],
                news=payload["news"],
            )
            report_md = generate_morning_report(context)
            st.session_state["morning_report_md"] = report_md
            st.session_state["morning_report_sources"] = payload["sources"]
            st.session_state["morning_report_context"] = context

    report_md = st.session_state.get("morning_report_md")
    if not report_md:
        st.markdown(
            """
            Click **Generate morning report** to assemble:
            - Overnight market review (Tab 1 universe)
            - Macro updates (FRED or demo)
            - Equity watchlist movers
            - Risk alerts from the derivatives book
            - Important headlines / events
            """
        )
        return

    sources = st.session_state.get("morning_report_sources", {})
    st.caption(
        "Sources — "
        + ", ".join(f"{k}: {v}" for k, v in sources.items())
    )

    st.markdown(report_md)
    st.download_button(
        "Download Markdown brief",
        data=report_md,
        file_name="morning_market_brief.md",
        mime="text/markdown",
        use_container_width=True,
    )

    with st.expander("View raw context fed to the generator"):
        ctx = st.session_state.get("morning_report_context", {})
        for key in ["markets", "macro", "equities", "risk_alerts", "events"]:
            st.markdown(f"**{key}**")
            st.text(ctx.get(key, ""))
