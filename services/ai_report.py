"""
AI summarization and morning report generation.

Uses Qwen (DashScope-compatible) when configured; otherwise rich rule-based copy.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import pandas as pd
import requests

from config.settings import settings
from services.data_processing import build_rule_based_market_summary, format_pct

logger = logging.getLogger(__name__)


def generate_market_summary(performance_summary: pd.DataFrame) -> str:
    """Generate a short Global Market Overview narrative."""
    from config.settings import _secret_or_env

    api_key = _secret_or_env("QWEN_API_KEY")
    if api_key:
        try:
            return _chat(
                system=(
                    "You are a senior markets strategist preparing a concise morning brief "
                    "for a middle-office desk. Be factual, avoid hype, use 4-6 sentences."
                ),
                user=(
                    "Summarize the following market performance table for today's morning meeting:\n\n"
                    f"{performance_summary.to_string(index=False)}"
                ),
                api_key=api_key,
            )
        except Exception as exc:
            logger.warning("LLM summary failed, using rule-based fallback: %s", exc)

    return build_rule_based_market_summary(performance_summary)


def generate_morning_report(context: dict[str, Any]) -> str:
    """
    Produce a meeting-ready morning brief.

    Expected context keys: markets, macro, equities, risk_alerts, events, as_of.
    """
    from config.settings import _secret_or_env

    as_of = context.get("as_of") or datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    api_key = _secret_or_env("QWEN_API_KEY")

    if api_key:
        try:
            return _chat(
                system=(
                    "You are the desk's AI morning brief writer for middle-office analysts. "
                    "Write a crisp meeting brief with clear Markdown headings. "
                    "Keep each section to 3-5 bullets or short paragraphs. No fluff."
                ),
                user=(
                    f"Compose today's morning market brief (as of {as_of}) using this context JSON-like text:\n\n"
                    f"MARKETS:\n{context.get('markets', '')}\n\n"
                    f"MACRO:\n{context.get('macro', '')}\n\n"
                    f"EQUITIES:\n{context.get('equities', '')}\n\n"
                    f"RISK ALERTS:\n{context.get('risk_alerts', '')}\n\n"
                    f"EVENTS / NEWS:\n{context.get('events', '')}\n"
                ),
                api_key=api_key,
            )
        except Exception as exc:
            logger.warning("LLM morning report failed, using template: %s", exc)

    return _rule_based_morning_report(context, as_of)


def build_report_context(
    market_summary: str,
    macro_text: str,
    watchlist_metrics: pd.DataFrame,
    risk_alert_list: list[str],
    news: pd.DataFrame,
) -> dict[str, Any]:
    """Assemble structured context for the morning report generator."""
    equities = _equity_section(watchlist_metrics)
    events = _events_section(news)
    risk_text = "\n".join(f"- {a}" for a in risk_alert_list) if risk_alert_list else "- None"
    return {
        "as_of": datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
        "markets": market_summary,
        "macro": macro_text,
        "equities": equities,
        "risk_alerts": risk_text,
        "events": events,
    }


def _equity_section(metrics: pd.DataFrame) -> str:
    if metrics is None or metrics.empty:
        return "Watchlist data unavailable."
    ranked = metrics.dropna(subset=["daily_return"]).sort_values("daily_return", ascending=False)
    lines = []
    for _, row in ranked.head(3).iterrows():
        lines.append(f"Leader: {row['ticker']} {format_pct(row['daily_return'])} (RSI {row.get('rsi_14', float('nan')):.1f})")
    for _, row in ranked.tail(3).iterrows():
        lines.append(f"Laggard: {row['ticker']} {format_pct(row['daily_return'])}")
    return "\n".join(lines)


def _events_section(news: pd.DataFrame) -> str:
    if news is None or news.empty:
        return "No major headlines loaded."
    top = news.head(6)
    lines = []
    for _, row in top.iterrows():
        lines.append(
            f"- [{row.get('category', 'General')}] {row['title']} "
            f"({row.get('source', '')}; sentiment {row.get('sentiment', 0):+.2f}; {row.get('market_impact', '')})"
        )
    return "\n".join(lines)


def _rule_based_morning_report(context: dict[str, Any], as_of: str) -> str:
    return "\n".join(
        [
            f"# Morning Market Brief",
            f"*Prepared for middle-office desk — {as_of}*",
            "",
            "## Overnight Market Review",
            context.get("markets", "Pending market data."),
            "",
            "## Macro Updates",
            context.get("macro", "Macro feed unavailable."),
            "",
            "## Equity Market Movements",
            context.get("equities", "Watchlist unavailable."),
            "",
            "## Risk Alerts",
            context.get("risk_alerts", "- None"),
            "",
            "## Important Events Today",
            context.get("events", "No events listed."),
            "",
            "---",
            "_Auto-generated by Financial Market Intelligence. Verify critical figures before distribution._",
        ]
    )


def _chat(system: str, user: str, api_key: str | None = None) -> str:
    """Call an OpenAI-compatible chat completions endpoint (Qwen / DashScope)."""
    from config.settings import _secret_or_env

    key = (api_key or _secret_or_env("QWEN_API_KEY") or "").strip()
    if not key:
        raise RuntimeError("QWEN_API_KEY is missing")

    model = _secret_or_env("QWEN_MODEL", "qwen-turbo")
    base = _secret_or_env(
        "QWEN_API_BASE", "https://dashscope.aliyuncs.com/compatible-mode/v1"
    )

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.3,
    }
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    url = base.rstrip("/") + "/chat/completions"
    response = requests.post(url, json=payload, headers=headers, timeout=60)
    response.raise_for_status()
    data = response.json()
    return data["choices"][0]["message"]["content"].strip()
