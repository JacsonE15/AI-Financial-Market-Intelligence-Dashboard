"""
Financial Market Intelligence Dashboard
=======================================
AI-powered morning briefing platform for Middle Office Analysts.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _hydrate_env_from_streamlit_secrets() -> None:
    """
    Copy Streamlit Cloud secrets into environment variables before Settings loads.

    This makes Cloud Secrets work even for code paths that only call os.getenv().
    """
    try:
        from config.settings import hydrate_env_from_streamlit_secrets

        hydrate_env_from_streamlit_secrets()
    except Exception:
        # Local runs without secrets.toml are fine.
        pass


_hydrate_env_from_streamlit_secrets()

from config.settings import hydrate_env_from_streamlit_secrets, reload_settings, settings
from database.connection import init_db
from views.equity_watchlist import render_equity_watchlist
from views.global_markets import render_global_market_overview
from views.morning_report import render_morning_report
from views.news_intelligence import render_news_intelligence
from views.risk_monitor import render_derivatives_risk

logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))


def _apply_page_config() -> None:
    st.set_page_config(
        page_title="Financial Market Intelligence",
        page_icon="📈",
        layout="wide",
        initial_sidebar_state="expanded",
    )


def _inject_styles() -> None:
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Serif:wght@600&display=swap');

        html, body, [class*="css"] {
            font-family: 'IBM Plex Sans', sans-serif;
        }
        .main-title {
            font-family: 'IBM Plex Serif', Georgia, serif;
            font-size: 1.85rem;
            font-weight: 600;
            color: #0B3D5C;
            margin-bottom: 0.15rem;
        }
        .main-subtitle {
            color: #5A6A75;
            margin-bottom: 1.25rem;
        }
        div[data-testid="stMetric"] {
            background: linear-gradient(180deg, #F7FAFC 0%, #EEF3F7 100%);
            border: 1px solid #D5E0E8;
            border-radius: 8px;
            padding: 0.75rem 0.9rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def main() -> None:
    _apply_page_config()
    _inject_styles()

    # Re-read Cloud Secrets on every run so newly saved keys are picked up.
    key_status = hydrate_env_from_streamlit_secrets()
    runtime_settings = reload_settings()

    try:
        init_db()
    except Exception as exc:
        st.sidebar.warning(f"Database init skipped/failed: {exc}")

    st.markdown(
        '<div class="main-title">Financial Market Intelligence</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="main-subtitle">Daily morning briefing workspace for Middle Office Analysts</div>',
        unsafe_allow_html=True,
    )

    with st.sidebar:
        st.header("Desk Controls")
        st.write("All five tabs are active: markets, equities, risk, news, and AI brief.")
        st.divider()
        st.markdown("##### API key status")
        st.caption("Shows whether Cloud Secrets / env were detected (values never displayed).")
        st.write(
            f"- FRED: `{'yes' if key_status.get('FRED_API_KEY') else 'no'}`  \n"
            f"- NEWS_API_KEY: `{'yes' if key_status.get('NEWS_API_KEY') else 'no'}`  \n"
            f"- FINNHUB: `{'yes' if key_status.get('FINNHUB_API_KEY') else 'no'}`  \n"
            f"- Qwen: `{'yes' if key_status.get('QWEN_API_KEY') else 'no'}`"
        )
        if not key_status.get("NEWS_API_KEY") and not key_status.get("FINNHUB_API_KEY"):
            st.error(
                "News key not detected on THIS app. "
                "Open Manage app → ⋮ → Settings → Secrets and paste top-level TOML, then Save + Reboot."
            )
        st.divider()
        st.caption(f"Lookback default: {runtime_settings.default_lookback_days} days")
        st.caption(f"DB: `{runtime_settings.database_url}`")
        if runtime_settings.qwen_api_key:
            st.success("Qwen API key detected")
        else:
            st.info("No LLM key — rule-based summaries/reports")
        if runtime_settings.news_api_key or runtime_settings.finnhub_api_key:
            st.success("News API configured")
        else:
            st.caption("News: demo headlines (add API key for live)")
        if runtime_settings.fred_api_key:
            st.success("FRED API configured")
        else:
            st.caption("Macro: demo FRED snapshot")

    tab1, tab2, tab3, tab4, tab5 = st.tabs(
        [
            "1 · Global Markets",
            "2 · Equity Watchlist",
            "3 · Derivatives & Risk",
            "4 · News Intelligence",
            "5 · AI Morning Report",
        ]
    )

    with tab1:
        render_global_market_overview()
    with tab2:
        render_equity_watchlist()
    with tab3:
        render_derivatives_risk()
    with tab4:
        render_news_intelligence()
    with tab5:
        render_morning_report()


if __name__ == "__main__":
    main()
