# TradBot — Complete Implementation Plan

## Context

Build a personal, locally-hosted automated crypto trading bot for a **complete trading beginner** that:
- Trades **BTC/USDT on Binance** with no human intervention
- Holds positions for a **maximum of 24 hours** (intraday swing)
- Uses **pure technical indicators** — transparent, no ML, no external data needed (Phase 1–7)
- ML integration is planned as a separate future phase (Phase 8+)
- Exposes a **local web dashboard** (user checks it manually, no push alerts)
- Starts in **paper trading mode** (real market data, simulated fills) — zero real money until the user is confident
- All historical data for backtesting is fetched **free from Binance's own API**
- A `CONTEXT.md` in the project root keeps full project context for LLM handoffs

---

## Architecture Diagram

> **Keep this up to date.** Every time a new module or layer is added, update this diagram before marking the phase complete.

```mermaid
flowchart TD
    subgraph External["External"]
        BINANCE["Binance API\n(CCXT · real market data;\norders only in live mode)"]
    end

    subgraph Scheduler["Python Backend — Scheduler (hourly, 30s after each candle closes)"]
        direction TB
        FETCH["data/fetcher.py\nFetch OHLCV candles"]
        CACHE["data/cache.py\nSQLite candle cache"]
        IND["strategy/indicators.py\nEMA9/21 · MACD · RSI · ATR · Vol"]
        SIG["strategy/signals.py\nSignal: LONG / SHORT / FLAT + reason"]
        RISK["risk/manager.py\nPosition size · SL · TP · time-exit"]
        EXEC_P["executor/paper.py\nPaper fill simulation"]
        EXEC_L["executor/orders.py\nLive CCXT order placement"]
        TRACK["tracker/trades.py\nLog trade to SQLite"]
    end

    subgraph Storage["Storage"]
        DB["SQLite\ntrades · candles"]
    end

    subgraph API["Python Backend — FastAPI (port 8000)"]
        RT["/api/status\n/api/position\n/api/trades\n/api/performance\n/api/equity\n/api/backtest"]
        BT["backtest/runner.py\nReplay strategy on 30–365 days"]
    end

    subgraph Frontend["React Frontend — Vite (port 5173)"]
        STATUS["StatusBar\nBot status · last signal"]
        POS["OpenPosition\nEntry · current price · P&L"]
        CHART["EquityCurve\nRecharts line chart"]
        LOG["TradeLog\nLast 50 trades table"]
        PERF["PerformanceCard\nRun backtest · results chart"]
    end

    BINANCE -->|OHLCV| FETCH
    FETCH --> CACHE
    CACHE -->|closed candles only| IND
    IND --> SIG
    SIG --> RISK
    RISK -->|PAPER_MODE=true| EXEC_P
    RISK -->|PAPER_MODE=false| EXEC_L
    EXEC_L -->|place order| BINANCE
    EXEC_P --> TRACK
    EXEC_L --> TRACK
    TRACK --> DB
    DB --> RT
    RT -->|JSON / Axios| STATUS
    RT -->|JSON / Axios| POS
    RT -->|JSON / Axios| CHART
    RT -->|JSON / Axios| LOG
    BINANCE -->|history| BT
    BT --> RT
    RT -->|JSON / Axios| PERF
```

---

## Strategy Decision (owner: Claude — newbie-safe)

**Why pure technical indicators (no ML for now):**
- Complete beginner → every trade must be explainable: "the bot bought because X happened"
- No training data needed, no model to maintain, no overfitting risk
- These 4 indicators have been used for decades on BTC with consistent results
- Easy to tune: changing one number changes one behaviour

**Signal pipeline (all 4 must agree to enter a trade):**

| # | Indicator | Rule | What it catches |
|---|---|---|---|
| 1 | EMA 9 / EMA 21 | EMA9 crosses above EMA21 → LONG; crosses below → SHORT | Trend direction |
| 2 | RSI (14) | Only enter LONG if RSI < 65; only SHORT if RSI > 35 | Avoids entering at exhaustion peaks |
| 3 | MACD (12/26/9) | Histogram must be positive (LONG) or negative (SHORT) | Momentum confirmation |
| 4 | Volume | Current candle volume > 1.5× 20-period average | Ensures real move, not a fake-out |

**Exit rules (whichever hits first):**
- **Stop-loss:** 1.5× ATR(14) below entry — dynamic, adapts to market volatility
- **Take-profit:** 2.5× ATR(14) above entry — gives ~1.67:1 reward-to-risk ratio
- **Hard time-exit:** force-close after 23h regardless of P&L (max 1 day rule)

**Position sizing:**
- Risk 2% of portfolio per trade (fixed-fraction method — industry standard for beginners)
- Max 1 open trade at any time

---

## Tech Stack

| Layer | Technology | Purpose |
|---|---|---|
| Language | Python 3.11 | Main runtime |
| Exchange | CCXT (Binance) | Unified exchange API; public market data (orders only in live mode) |
| Indicators | pandas-ta | EMA, MACD, RSI, ATR, Volume MA — one-line calls |
| Scheduler | APScheduler | Run signal check each hour, 30s after the candle closes |
| Database | SQLite (via SQLAlchemy) | Candle cache, trade log, P&L history |
| Backend API | FastAPI (Python) | REST JSON API at http://localhost:8000 |
| Frontend | React (Vite) | Dashboard UI at http://localhost:5173 |
| Charts | Recharts (React lib) | Equity curve, candle/price charts |
| HTTP client | Axios | React → FastAPI data fetching |
| Config | python-dotenv | Keep API keys in .env, out of code |

No ML libraries needed in Phase 1–7. No external data files needed.

**Architecture note:** FastAPI is a pure REST API (returns JSON only, no HTML). React is a standalone Vite app that fetches from FastAPI. Both run locally; CORS is enabled on FastAPI for localhost:5173.

---

## Project Structure

```
TradBot/                     # repo root
├── PLAN.md                  # ← Full implementation plan (this document)
├── CONTEXT.md               # ← LLM handoff doc
├── .gitignore
│
├── backend/                 # All Python code — run from inside this folder
│   ├── config/
│   │   └── settings.py      # All tunable params (thresholds, pairs, risk %)
│   ├── data/
│   │   ├── fetcher.py       # CCXT OHLCV fetch from Binance + closed_candles() filter
│   │   └── cache.py         # SQLite candle store — upsert refreshes half-finished candles
│   ├── strategy/
│   │   ├── indicators.py    # Compute EMA9/21, MACD, RSI14, ATR14, VolMA20
│   │   └── signals.py       # Combine 4 indicators → LONG / SHORT / FLAT
│   ├── risk/
│   │   └── manager.py       # Position size, SL/TP prices, time-exit logic
│   ├── executor/
│   │   ├── orders.py        # Place market orders via CCXT (no exchange-side SL/TP yet)
│   │   └── paper.py         # Paper engine: simulate fills when PAPER_MODE=true
│   ├── tracker/
│   │   ├── trades.py        # SQLAlchemy Trade model — log every trade
│   │   └── performance.py   # Win rate, total P&L, Sharpe ratio
│   ├── dashboard/
│   │   └── app.py           # FastAPI REST API routes (JSON only)
│   ├── backtest/
│   │   └── runner.py        # Replay pipeline on Binance historical candles
│   ├── scheduler.py         # APScheduler: run full pipeline every 1h
│   ├── main.py              # Entry point: start scheduler + FastAPI together
│   ├── requirements.txt
│   └── .env.example
│
└── frontend/                # React app (Vite) — run from inside this folder
    ├── src/
    │   ├── components/
    │   │   ├── StatusBar.jsx
    │   │   ├── OpenPosition.jsx
    │   │   ├── EquityCurve.jsx
    │   │   ├── TradeLog.jsx
    │   │   └── PerformanceCard.jsx
    │   ├── api/
    │   │   └── client.js
    │   ├── App.jsx
    │   └── main.jsx
    ├── index.html
    ├── package.json
    └── vite.config.js
```

---

## Configuration

**.env (never committed; optional in paper mode, see `backend/.env.example`):**
```
PAPER_MODE=true
BINANCE_API_KEY=   # live mode only
BINANCE_SECRET=    # live mode only
```

**config/settings.py:**
```python
SYMBOL        = "BTC/USDT"
TIMEFRAME     = "1h"
EMA_FAST      = 9
EMA_SLOW      = 21
RSI_PERIOD    = 14
RSI_LONG_MAX  = 65
RSI_SHORT_MIN = 35
MACD_FAST     = 12
MACD_SLOW     = 26
MACD_SIGNAL   = 9
ATR_PERIOD    = 14
VOL_MA_PERIOD = 20
VOL_MULT      = 1.5
SL_ATR_MULT   = 1.5
TP_ATR_MULT   = 2.5
RISK_PCT      = 2.0
MAX_HOLD_HRS  = 23
DASHBOARD_PORT= 8000
```

---

## Build Phases

### Phase 1 — Project Scaffold + Binance Connection ✅
- All directories and skeleton files created
- PLAN.md and CONTEXT.md written to project root
- requirements.txt and frontend/package.json defined
- .env.example and .gitignore created
- data/fetcher.py: CCXT Binance init (keyless public market data in paper mode), fetch last 200 1h candles
- config/settings.py: all strategy params

### Phase 2 — Candle Cache + Indicators ✅
- `data/cache.py`: SQLite candle table; upsert refreshes candles saved while still forming
- `strategy/indicators.py`: EMA9/21, MACD hist, RSI14, ATR14, VolMA20 via pandas-ta

### Phase 3 — Signal Engine ✅
- `strategy/signals.py`: EMA crossover + RSI + MACD + Volume → Signal(direction, reason)

### Phase 4 — Risk Manager + Executor ✅
- `risk/manager.py`: size_position, stop_loss_price, take_profit_price, should_time_exit
- `executor/paper.py`: simulate fills in paper mode
- `executor/orders.py`: real CCXT orders (PAPER_MODE=false only)
- `tracker/trades.py`: SQLAlchemy Trade model

### Phase 5 — Scheduler (Main Loop) ✅
- `scheduler.py`: APScheduler job at hh:00:30 UTC — fetch → closed candles → indicators → signal → risk → execute → log
- `main.py`: start scheduler + FastAPI uvicorn together

### Phase 6 — Dashboard (React + FastAPI) ✅
- `dashboard/app.py`: FastAPI with CORS, JSON endpoints
- `frontend/`: React Vite app with StatusBar, OpenPosition, EquityCurve, TradeLog, PerformanceCard

### Phase 7 — Backtesting ✅
- `backtest/runner.py`: fetch 1y Binance candles, replay pipeline, compute Sharpe
- Gate: Sharpe > 1.0 before PAPER_MODE=false

---

## Future Phase: ML Integration (Phase 8+)

> Do not build until Phases 1–7 complete and 2+ weeks of paper trade data collected.

- **Model:** GradientBoostingClassifier (scikit-learn)
- **Features:** indicator values at signal time
- **Label:** 1 if price moved ≥1.5% in signal direction within 12h
- **Data:** fetched free from Binance API (no external files needed)
- **Threshold:** confidence ≥ 0.65 to take trade
- **New files:** `strategy/ml_scorer.py`, `models/scorer_v1.pkl`
- **Integration:** final gate in `signals.py` after indicator rules pass

---

## Verification Checklist

1. `cd backend && pip install -r requirements.txt` completes
2. `cd backend && python main.py` → FastAPI at localhost:8000
3. `cd frontend && npm run dev` → React at localhost:5173
4. Fetcher returns valid candles from Binance (real market data)
5. Indicators compute on 200-candle window with no NaN in last row
6. Signal returns a Signal object with non-empty reason string
7. Paper LONG → logged in SQLite → visible in dashboard
8. Time-exit fires at 23h in paper mode
9. Backtest on 1y completes; equity curve shown
10. `.env` is gitignored; CONTEXT.md is up to date
