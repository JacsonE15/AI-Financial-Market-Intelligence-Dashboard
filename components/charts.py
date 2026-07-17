"""Plotly chart builders for the morning brief dashboard."""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from config.settings import settings


CHART_LAYOUT = dict(
    template="plotly_white",
    margin=dict(l=40, r=20, t=50, b=40),
    font=dict(family="IBM Plex Sans, Segoe UI, sans-serif", size=12),
    hovermode="x unified",
)


def price_trend_chart(prices: pd.DataFrame, ticker: str, name: str | None = None) -> go.Figure:
    """Historical close-price line chart for a single ticker."""
    subset = prices.loc[prices["ticker"] == ticker].sort_values("date")
    title = name or settings.market_tickers.get(ticker, ticker)

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=subset["date"],
            y=subset["close"],
            mode="lines",
            name=title,
            line=dict(color="#0B3D5C", width=2),
            fill="tozeroy",
            fillcolor="rgba(11, 61, 92, 0.08)",
        )
    )
    fig.update_layout(
        **CHART_LAYOUT,
        title=f"{title} — Price Trend",
        yaxis_title="Price",
        xaxis_title="Date",
        height=380,
    )
    return fig


def normalized_comparison_chart(rebased: pd.DataFrame) -> go.Figure:
    """Multi-asset historical comparison on a rebased (100) scale."""
    if rebased.empty:
        fig = go.Figure()
        fig.update_layout(**CHART_LAYOUT, title="Historical Comparison", height=400)
        return fig

    name_map = settings.market_tickers
    fig = go.Figure()
    for ticker in rebased.columns:
        label = name_map.get(ticker, ticker)
        fig.add_trace(
            go.Scatter(
                x=rebased.index,
                y=rebased[ticker],
                mode="lines",
                name=label,
            )
        )

    fig.update_layout(
        **CHART_LAYOUT,
        title="Historical Comparison (Rebased to 100)",
        yaxis_title="Index Level (100 = start)",
        xaxis_title="Date",
        height=420,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
    )
    return fig


def return_heatmap(heatmap: pd.DataFrame) -> go.Figure:
    """Daily-return heatmap: assets x recent sessions."""
    if heatmap.empty:
        fig = go.Figure()
        fig.update_layout(**CHART_LAYOUT, title="Performance Heatmap", height=420)
        return fig

    z = heatmap.values * 100  # percent
    fig = px.imshow(
        z,
        x=[str(c) for c in heatmap.columns],
        y=list(heatmap.index),
        color_continuous_scale=["#8B1E1E", "#F5F5F5", "#1B5E3B"],
        color_continuous_midpoint=0,
        aspect="auto",
        labels=dict(color="Return %"),
    )
    fig.update_traces(
        hovertemplate="Asset: %{y}<br>Date: %{x}<br>Return: %{z:.2f}%<extra></extra>"
    )
    fig.update_layout(
        **CHART_LAYOUT,
        title="Daily Return Heatmap (Recent Sessions)",
        height=460,
        xaxis_title="",
        yaxis_title="",
    )
    return fig


def daily_return_bar_chart(snapshot: pd.DataFrame) -> go.Figure:
    """Bar chart of latest daily returns across the market universe."""
    data = snapshot.dropna(subset=["daily_return"]).copy()
    if data.empty:
        fig = go.Figure()
        fig.update_layout(**CHART_LAYOUT, title="Daily Returns", height=360)
        return fig

    data = data.sort_values("daily_return")
    colors = ["#1B5E3B" if v >= 0 else "#8B1E1E" for v in data["daily_return"]]

    fig = go.Figure(
        go.Bar(
            x=data["daily_return"] * 100,
            y=data["name"],
            orientation="h",
            marker_color=colors,
            text=[f"{v * 100:.2f}%" for v in data["daily_return"]],
            textposition="outside",
        )
    )
    fig.update_layout(
        **CHART_LAYOUT,
        title="Daily Returns by Asset",
        xaxis_title="Daily Return (%)",
        yaxis_title="",
        height=max(360, 28 * len(data) + 80),
    )
    return fig


def correlation_heatmap(corr: pd.DataFrame) -> go.Figure:
    """Portfolio correlation matrix heatmap."""
    if corr is None or corr.empty:
        fig = go.Figure()
        fig.update_layout(**CHART_LAYOUT, title="Correlation Matrix", height=400)
        return fig

    fig = px.imshow(
        corr.values,
        x=list(corr.columns),
        y=list(corr.index),
        color_continuous_scale=["#8B1E1E", "#F5F5F5", "#0B3D5C"],
        zmin=-1,
        zmax=1,
        aspect="auto",
        text_auto=".2f",
    )
    fig.update_layout(**CHART_LAYOUT, title="Return Correlation Matrix", height=420)
    return fig


def drawdown_chart(drawdown: pd.Series) -> go.Figure:
    """Portfolio drawdown path."""
    fig = go.Figure()
    if drawdown is None or drawdown.empty:
        fig.update_layout(**CHART_LAYOUT, title="Portfolio Drawdown", height=320)
        return fig

    fig.add_trace(
        go.Scatter(
            x=list(drawdown.index),
            y=drawdown.values * 100,
            mode="lines",
            fill="tozeroy",
            line=dict(color="#8B1E1E", width=2),
            fillcolor="rgba(139, 30, 30, 0.12)",
            name="Drawdown",
        )
    )
    fig.update_layout(
        **CHART_LAYOUT,
        title="Portfolio Drawdown",
        yaxis_title="Drawdown (%)",
        height=320,
    )
    return fig


def sentiment_bar_chart(news: pd.DataFrame) -> go.Figure:
    """Average sentiment by news category."""
    if news is None or news.empty:
        fig = go.Figure()
        fig.update_layout(**CHART_LAYOUT, title="Sentiment by Category", height=320)
        return fig

    agg = news.groupby("category")["sentiment"].mean().sort_values()
    colors = ["#1B5E3B" if v >= 0 else "#8B1E1E" for v in agg.values]
    fig = go.Figure(go.Bar(x=agg.values, y=agg.index, orientation="h", marker_color=colors))
    fig.update_layout(
        **CHART_LAYOUT,
        title="Average Sentiment by Category",
        xaxis_title="Sentiment (-1 to +1)",
        height=320,
    )
    return fig
