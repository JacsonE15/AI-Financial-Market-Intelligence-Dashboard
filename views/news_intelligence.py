"""Tab 4 — Financial News Intelligence."""

from __future__ import annotations

import streamlit as st

from components.charts import sentiment_bar_chart
from services.news_service import fetch_financial_news, persist_news


@st.cache_data(ttl=180, show_spinner=False)
def _load_news(query: str, limit: int):
    return fetch_financial_news(query=query, limit=limit)


def render_news_intelligence() -> None:
    st.subheader("Financial News Intelligence")
    st.caption("Collect, classify, score sentiment, and summarize market-moving headlines.")

    col_a, col_b, col_c = st.columns([2, 1, 1])
    with col_a:
        query = st.text_input(
            "Search query",
            value="stock market OR federal reserve OR earnings OR inflation",
        )
    with col_b:
        limit = st.selectbox("Articles", options=[10, 15, 20, 30], index=2)
    with col_c:
        category_filter = st.selectbox(
            "Category filter",
            options=["All", "Macro", "Sector", "Company", "General"],
        )

    c1, c2 = st.columns(2)
    with c1:
        refresh = st.button("Refresh news", type="primary", use_container_width=True)
    with c2:
        save_db = st.checkbox("Save to database", value=False)

    if refresh:
        _load_news.clear()

    with st.spinner("Fetching & scoring headlines..."):
        news, source = _load_news(query, limit)

    if source == "demo":
        st.warning(
            "Using **demo headlines** (set `NEWS_API_KEY` or `FINNHUB_API_KEY` in `.env` for live news)."
        )
    else:
        st.caption(f"News source: {source}")

    if news.empty:
        st.warning("No news returned.")
        return

    if save_db:
        try:
            n = persist_news(news)
            st.success(f"Saved {n} articles to the news table.")
        except Exception as exc:
            st.warning(f"Could not persist news: {exc}")

    filtered = news.copy()
    if category_filter != "All":
        filtered = filtered[filtered["category"] == category_filter]

    # KPI strip
    avg_sent = float(filtered["sentiment"].mean()) if not filtered.empty else 0.0
    bullish = int((filtered["sentiment"] > 0.05).sum())
    bearish = int((filtered["sentiment"] < -0.05).sum())
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Headlines", len(filtered))
    k2.metric("Avg Sentiment", f"{avg_sent:+.2f}")
    k3.metric("Bullish", bullish)
    k4.metric("Bearish", bearish)

    left, right = st.columns([1.2, 1])
    with left:
        st.plotly_chart(sentiment_bar_chart(filtered), use_container_width=True)
    with right:
        by_impact = filtered["market_impact"].value_counts().reset_index()
        by_impact.columns = ["Market Impact", "Count"]
        st.markdown("##### Impact Mix")
        st.dataframe(by_impact, use_container_width=True, hide_index=True)

    st.markdown("##### Headline Feed")
    for _, row in filtered.iterrows():
        sentiment = row["sentiment"]
        tone = "🟢" if sentiment > 0.05 else "🔴" if sentiment < -0.05 else "⚪"
        with st.expander(f"{tone} {row['title']}"):
            st.write(f"**Source:** {row['source']}  |  **Time:** {row['date']}")
            st.write(f"**Category:** {row['category']}  |  **Entity:** {row['entity']}")
            st.write(f"**Sentiment:** {sentiment:+.2f}  |  **Market impact:** {row['market_impact']}")
            st.write(row.get("summary") or row.get("content") or "")
            if row.get("url"):
                st.markdown(f"[Open article]({row['url']})")

    table = filtered.copy()
    table["date"] = table["date"].astype(str)
    table["sentiment"] = table["sentiment"].map(lambda x: f"{x:+.2f}")
    st.markdown("##### Tabular View")
    st.dataframe(
        table.rename(
            columns={
                "date": "Time",
                "title": "Headline",
                "source": "Source",
                "category": "Category",
                "entity": "Entity",
                "sentiment": "Sentiment",
                "market_impact": "Market Impact",
                "summary": "Summary",
            }
        )[["Time", "Headline", "Source", "Category", "Entity", "Sentiment", "Market Impact", "Summary"]],
        use_container_width=True,
        hide_index=True,
        height=360,
    )
