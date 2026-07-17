"""
Portfolio risk calculations for middle-office monitoring.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from services.options_pricing import black_scholes_greeks


def historical_var(returns: pd.Series, confidence: float = 0.95) -> float:
    """Historical Value at Risk (positive number = loss magnitude)."""
    clean = returns.dropna()
    if clean.empty:
        return float("nan")
    return float(-np.percentile(clean, (1 - confidence) * 100))


def expected_shortfall(returns: pd.Series, confidence: float = 0.95) -> float:
    """Expected Shortfall / CVaR at the given confidence level."""
    clean = returns.dropna()
    if clean.empty:
        return float("nan")
    cutoff = -historical_var(clean, confidence)
    tail = clean[clean <= cutoff]
    if tail.empty:
        return float("nan")
    return float(-tail.mean())


def annualized_volatility(returns: pd.Series, trading_days: int = 252) -> float:
    """Annualized volatility from daily returns."""
    clean = returns.dropna()
    if len(clean) < 2:
        return float("nan")
    return float(clean.std(ddof=1) * np.sqrt(trading_days))


def beta_vs_benchmark(asset_returns: pd.Series, benchmark_returns: pd.Series) -> float:
    """OLS beta of asset vs benchmark using aligned daily returns."""
    aligned = pd.concat(
        [asset_returns.rename("a"), benchmark_returns.rename("b")], axis=1
    ).dropna()
    if aligned.shape[0] < 5:
        return float("nan")
    cov = np.cov(aligned["a"], aligned["b"])[0, 1]
    var_b = np.var(aligned["b"], ddof=1)
    if var_b == 0:
        return float("nan")
    return float(cov / var_b)


def correlation_matrix(returns_panel: pd.DataFrame) -> pd.DataFrame:
    """Pairwise correlation matrix for a wide returns panel."""
    return returns_panel.dropna(how="all").corr()


def max_drawdown(price_series: pd.Series) -> float:
    """Maximum drawdown as a negative fraction."""
    clean = price_series.dropna()
    if clean.empty:
        return float("nan")
    running_max = clean.cummax()
    drawdown = clean / running_max - 1.0
    return float(drawdown.min())


def drawdown_series(price_series: pd.Series) -> pd.Series:
    """Full drawdown path for charting."""
    clean = price_series.dropna()
    if clean.empty:
        return clean
    return clean / clean.cummax() - 1.0


def portfolio_returns(returns_panel: pd.DataFrame, weights: dict[str, float]) -> pd.Series:
    """Weighted portfolio daily returns from a wide returns panel."""
    cols = [c for c in weights if c in returns_panel.columns]
    if not cols:
        return pd.Series(dtype=float)
    w = pd.Series({c: weights[c] for c in cols}, dtype=float)
    w = w / w.sum()
    return returns_panel[cols].fillna(0.0).mul(w, axis=1).sum(axis=1)


def compute_portfolio_risk(
    prices: pd.DataFrame,
    weights: dict[str, float],
    benchmark_ticker: str = "^GSPC",
    confidence: float = 0.95,
) -> dict:
    """
    Aggregate middle-office risk metrics for a weighted equity book.
    """
    if prices.empty or not weights:
        return {}

    panel_close = prices.pivot_table(index="date", columns="ticker", values="close", aggfunc="last")
    panel_ret = prices.pivot_table(index="date", columns="ticker", values="return", aggfunc="last")
    panel_close = panel_close.sort_index()
    panel_ret = panel_ret.sort_index()

    port_ret = portfolio_returns(panel_ret, weights)
    # Portfolio NAV proxy from cumulative returns
    nav = (1 + port_ret.fillna(0)).cumprod() * 100.0

    bench_ret = panel_ret[benchmark_ticker] if benchmark_ticker in panel_ret.columns else pd.Series(dtype=float)

    corr = correlation_matrix(panel_ret[[c for c in weights if c in panel_ret.columns]])

    per_name = []
    for ticker, weight in weights.items():
        if ticker not in panel_ret.columns:
            continue
        r = panel_ret[ticker]
        c = panel_close[ticker] if ticker in panel_close.columns else pd.Series(dtype=float)
        per_name.append(
            {
                "ticker": ticker,
                "weight": weight,
                "volatility": annualized_volatility(r),
                "VaR_95": historical_var(r, confidence),
                "beta": beta_vs_benchmark(r, bench_ret) if not bench_ret.empty else float("nan"),
                "max_drawdown": max_drawdown(c),
            }
        )

    return {
        "portfolio_var": historical_var(port_ret, confidence),
        "portfolio_es": expected_shortfall(port_ret, confidence),
        "portfolio_vol": annualized_volatility(port_ret),
        "portfolio_beta": beta_vs_benchmark(port_ret, bench_ret) if not bench_ret.empty else float("nan"),
        "portfolio_drawdown": max_drawdown(nav),
        "corr": corr,
        "nav": nav,
        "drawdown_path": drawdown_series(nav),
        "per_name": pd.DataFrame(per_name),
        "port_returns": port_ret,
    }


def default_options_book(spot_map: dict[str, float] | None = None) -> pd.DataFrame:
    """Sample options book with live-ish spots when available."""
    spot_map = spot_map or {}
    today = datetime.utcnow().date()
    book = [
        {"underlying": "AAPL", "option_type": "call", "strike": 200, "expiry_days": 45, "iv": 0.28, "qty": 10},
        {"underlying": "MSFT", "option_type": "put", "strike": 420, "expiry_days": 30, "iv": 0.22, "qty": -5},
        {"underlying": "NVDA", "option_type": "call", "strike": 120, "expiry_days": 21, "iv": 0.45, "qty": 8},
        {"underlying": "SPY", "option_type": "put", "strike": 520, "expiry_days": 14, "iv": 0.16, "qty": -20},
        {"underlying": "AMZN", "option_type": "call", "strike": 190, "expiry_days": 60, "iv": 0.30, "qty": 6},
    ]
    rows = []
    for item in book:
        und = item["underlying"]
        # Reasonable demo spots if live prices missing
        defaults = {"AAPL": 195, "MSFT": 430, "NVDA": 115, "SPY": 525, "AMZN": 185}
        spot = float(spot_map.get(und, defaults.get(und, 100)))
        t = item["expiry_days"] / 365.0
        greeks = black_scholes_greeks(spot, item["strike"], t, r=0.045, sigma=item["iv"], option_type=item["option_type"])
        rows.append(
            {
                "underlying": und,
                "type": item["option_type"].upper(),
                "strike": item["strike"],
                "expiry": today + timedelta(days=item["expiry_days"]),
                "spot": spot,
                "iv": item["iv"],
                "qty": item["qty"],
                "mid": greeks["price"],
                "delta": greeks["delta"] * item["qty"],
                "gamma": greeks["gamma"] * item["qty"],
                "theta": greeks["theta"] * item["qty"],
                "vega": greeks["vega"] * item["qty"],
            }
        )
    return pd.DataFrame(rows)


def default_futures_book(price_map: dict[str, float] | None = None) -> pd.DataFrame:
    """Sample futures book with margin and daily PnL estimates."""
    price_map = price_map or {}
    specs = [
        {"contract": "ES=F", "name": "E-mini S&P", "position": 2, "multiplier": 50, "margin": 12000, "prior": 5200},
        {"contract": "NQ=F", "name": "E-mini Nasdaq", "position": -1, "multiplier": 20, "margin": 17000, "prior": 18400},
        {"contract": "CL=F", "name": "Crude Oil", "position": 3, "multiplier": 1000, "margin": 6500, "prior": 78},
        {"contract": "GC=F", "name": "Gold", "position": 1, "multiplier": 100, "margin": 9000, "prior": 2350},
        {"contract": "YM=F", "name": "E-mini Dow", "position": 1, "multiplier": 5, "margin": 9000, "prior": 39000},
    ]
    rows = []
    for s in specs:
        last = float(price_map.get(s["contract"], s["prior"]))
        daily_pnl = (last - s["prior"]) * s["multiplier"] * s["position"]
        # Tiny random-walk-like demo adjustment when using prior==last (offline)
        if abs(last - s["prior"]) < 1e-9:
            daily_pnl = s["position"] * s["multiplier"] * s["prior"] * 0.0025
            last = s["prior"] * (1 + 0.0025)
        rows.append(
            {
                "contract": s["contract"],
                "name": s["name"],
                "position": s["position"],
                "last": last,
                "multiplier": s["multiplier"],
                "margin_requirement": s["margin"] * abs(s["position"]),
                "daily_pnl": daily_pnl,
                "notional": last * s["multiplier"] * s["position"],
            }
        )
    return pd.DataFrame(rows)


def risk_alerts(risk: dict, var_limit: float = 0.02, dd_limit: float = -0.08) -> list[str]:
    """Generate human-readable risk alerts for the morning brief."""
    alerts: list[str] = []
    if not risk:
        return ["Risk engine returned no portfolio metrics."]

    var = risk.get("portfolio_var")
    es = risk.get("portfolio_es")
    dd = risk.get("portfolio_drawdown")
    vol = risk.get("portfolio_vol")

    if var == var and var > var_limit:
        alerts.append(f"Portfolio 95% VaR {var:.2%} exceeds desk limit {var_limit:.2%}.")
    if dd == dd and dd < dd_limit:
        alerts.append(f"Portfolio drawdown {dd:.2%} breached soft floor {dd_limit:.2%}.")
    if vol == vol and vol > 0.25:
        alerts.append(f"Annualized portfolio volatility elevated at {vol:.1%}.")
    if es == es:
        alerts.append(f"Expected Shortfall (95%): {es:.2%} of NAV on a 1-day horizon.")

    per = risk.get("per_name")
    if isinstance(per, pd.DataFrame) and not per.empty:
        hot = per.sort_values("VaR_95", ascending=False).head(2)
        for _, row in hot.iterrows():
            if row["VaR_95"] == row["VaR_95"]:
                alerts.append(f"{row['ticker']} name VaR {row['VaR_95']:.2%} (weight {row['weight']:.0%}).")

    if not alerts:
        alerts.append("No hard risk-limit breaches detected on the current book.")
    return alerts
