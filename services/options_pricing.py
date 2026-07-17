"""Black-Scholes option pricing and Greeks for middle-office monitoring."""

from __future__ import annotations

from math import exp, log, sqrt

from scipy.stats import norm


def _d1_d2(spot: float, strike: float, t: float, r: float, sigma: float) -> tuple[float, float]:
    if t <= 0 or sigma <= 0 or spot <= 0 or strike <= 0:
        return float("nan"), float("nan")
    d1 = (log(spot / strike) + (r + 0.5 * sigma**2) * t) / (sigma * sqrt(t))
    d2 = d1 - sigma * sqrt(t)
    return d1, d2


def black_scholes_greeks(
    spot: float,
    strike: float,
    t_years: float,
    r: float,
    sigma: float,
    option_type: str = "call",
) -> dict[str, float]:
    """
    Return mid-office Greeks.

    Theta is expressed per calendar day; Vega per 1% vol move.
    """
    opt = option_type.lower()
    d1, d2 = _d1_d2(spot, strike, t_years, r, sigma)
    if d1 != d1:  # NaN check
        return {"price": float("nan"), "delta": float("nan"), "gamma": float("nan"),
                "theta": float("nan"), "vega": float("nan")}

    pdf = norm.pdf(d1)
    gamma = pdf / (spot * sigma * sqrt(t_years))
    vega = spot * pdf * sqrt(t_years) / 100.0  # per 1% vol

    if opt == "call":
        price = spot * norm.cdf(d1) - strike * exp(-r * t_years) * norm.cdf(d2)
        delta = norm.cdf(d1)
        theta = (
            -(spot * pdf * sigma) / (2 * sqrt(t_years))
            - r * strike * exp(-r * t_years) * norm.cdf(d2)
        ) / 365.0
    else:
        price = strike * exp(-r * t_years) * norm.cdf(-d2) - spot * norm.cdf(-d1)
        delta = -norm.cdf(-d1)
        theta = (
            -(spot * pdf * sigma) / (2 * sqrt(t_years))
            + r * strike * exp(-r * t_years) * norm.cdf(-d2)
        ) / 365.0

    return {
        "price": float(price),
        "delta": float(delta),
        "gamma": float(gamma),
        "theta": float(theta),
        "vega": float(vega),
    }
