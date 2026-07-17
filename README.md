# Financial Market Intelligence Dashboard

AI-powered daily morning briefing platform for Middle Office Analysts.

Phase 1 delivers a working Streamlit dashboard with a **Global Market Overview** tab powered by Yahoo Finance: daily returns, historical comparison, performance heatmap, trend charts, and a market summary.

All five tabs are now implemented:

| Tab | Features |
|---|---|
| 1 Global Markets | Cross-asset KPIs, returns, heatmap, trends, AI/rule summary |
| 2 Equity Watchlist | Customizable tickers, RSI/SMA/HV/52W, volume Δ, news sentiment |
| 3 Derivatives & Risk | VaR, ES, vol, beta, correlation, drawdown, options Greeks, futures PnL |
| 4 News Intelligence | Fetch/classify/sentiment/summaries + market impact |
| 5 AI Morning Report | Meeting brief from markets + macro + equities + risk + news |

## Quick start

```bash
cd "Financial Mroning Brief Dashboard"
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env               # optional — Yahoo Finance needs no key
streamlit run app.py
```

Open the local URL shown in the terminal (usually `http://localhost:8501`).

## Project layout

```
app.py                      # Streamlit entry — five-tab story layout
config/settings.py          # Environment config & market ticker universe
database/                   # SQLite schema + connection helpers
services/
  market_data.py            # Yahoo Finance download / persistence
  data_processing.py        # Returns, heatmaps, summaries
  risk_engine.py            # VaR, ES, beta, drawdown (Phase 2 ready)
  ai_report.py              # Rule-based + Qwen LLM hooks
components/charts.py        # Plotly visualizations
views/                      # Tab renderers
```

## Phase 1 features (Tab 1)

| Feature | Implementation |
|---|---|
| S&P 500, Nasdaq, Dow, VIX, 10Y, DXY, Gold, Oil, futures | `config/settings.py` ticker map |
| Yahoo Finance connection | `services/market_data.py` |
| Daily return | `services/data_processing.compute_daily_returns` |
| Historical comparison | Rebased-to-100 Plotly chart |
| Performance heatmap | Recent daily-return matrix |
| Trend charts | Single-asset close history |
| Market summary | Rule-based now; Qwen when `QWEN_API_KEY` is set |
| Local DB | SQLite `market_price` upsert (optional checkbox) |

## Extending to Phase 2

See the in-app placeholder tabs and the notes at the end of this README (also summarized after Phase 1 delivery in chat).

### Risk monitoring (Tab 3)

1. Define portfolio holdings (weights / notionals) in a new table or CSV.
2. Call helpers in `services/risk_engine.py` (`historical_var`, `expected_shortfall`, `correlation_matrix`, `max_drawdown`).
3. Persist daily outputs into `risk_metrics`.
4. Add options chain / futures position loaders and greeks (e.g. Black-Scholes or broker API).

### AI reporting (Tab 5)

1. Set `QWEN_API_KEY` (DashScope-compatible) in `.env`.
2. Aggregate Tab 1–4 context into a dict.
3. Call `services.ai_report.generate_morning_report(context)`.
4. Optionally export Markdown → PDF/PPTX for the morning meeting.

## Environment variables

Copy `.env.example` → `.env` for local development. Yahoo Finance works with empty keys.

## Deploy on Streamlit Cloud

1. Go to [share.streamlit.io](https://share.streamlit.io) and create a new app.
2. Repository: `JacsonE15/AI-Financial-Market-Intelligence-Dashboard`
3. Branch: `main`
4. Main file path: `app.py`
5. In **Advanced settings → Secrets**, paste (use your real keys; never commit them):

```toml
FRED_API_KEY = "your-fred-key"
NEWS_API_KEY = "your-newsapi-key"
```

Optional secrets:

```toml
FINNHUB_API_KEY = ""
QWEN_API_KEY = ""
QWEN_API_BASE = "https://dashscope.aliyuncs.com/compatible-mode/v1"
QWEN_MODEL = "qwen-turbo"
FORCE_DEMO_DATA = "false"
```

6. Click **Deploy**.

Notes:
- Config reads **Streamlit Secrets first**, then `.env` / environment variables.
- SQLite under `data/` is ephemeral on Cloud (fine for cache/watchlist; resets on reboot).
- Without API keys the app still runs using demo / rule-based fallbacks.
