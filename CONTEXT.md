# TradBot — Project Context

> **For any LLM picking up this project**: read this file first. It is the single source of truth.

---

## What this project is

A personal, locally-hosted automated crypto trading bot that trades BTC/USDT on Binance (paper/testnet by default), requires zero human intervention, and holds each position for at most 24 hours. It runs a 4-indicator consensus strategy, manages risk automatically, and exposes a React dashboard at localhost:5173.

---

## Current status

**All Phases 1–7 complete.**

- Phase 1 — Scaffold + Binance connection ✓
- Phase 2 — Candle cache + indicators ✓
- Phase 3 — Signal engine ✓
- Phase 4 — Risk manager + executors ✓
- Phase 5 — APScheduler pipeline ✓
- Phase 6 — FastAPI dashboard + React frontend ✓
- Phase 7 — Backtester ✓

Paper mode: **ON** (PAPER_MODE=true in .env). No real money is at risk.

---

## Architecture decisions & why

| Decision | Reason |
|---|---|
| Binance via CCXT | Unified API; `set_sandbox_mode(True)` switches to testnet cleanly |
| `fetchCurrencies: False` | Testnet has no `/sapi` wallet endpoints — this skips them |
| Pure indicators, no ML | Beginner-friendly; every trade is explainable; no training data needed |
| SQLite not Postgres | Single-user local app; no server setup needed |
| FastAPI not Flask | Async-native, auto-generates `/docs` Swagger UI at localhost:8000/docs |
| APScheduler background | Shares process with uvicorn; no second terminal needed |
| `state.py` module dict | Thread-safe shared state between scheduler thread and FastAPI async loop |
| Centralised `db.py` | Single SQLAlchemy Base + engine avoids circular imports |
| Backtest uses public Binance | No auth needed for historical OHLCV; testnet keys not required |
| `UTCDateTime` column type (db.py) | SQLite drops UTC offsets; trade times are stored naive-UTC and returned aware-UTC so time-exit math works |
| Absolute `DB_PATH` | The bot always uses `backend/tradbot.db`, whichever folder it's launched from |

---

## Tech stack

| Layer | Technology |
|---|---|
| Exchange | CCXT (Binance testnet) |
| Indicators | pandas-ta |
| Scheduler | APScheduler 3.x BackgroundScheduler |
| Database | SQLite via SQLAlchemy 2 |
| Backend API | FastAPI + uvicorn |
| Frontend | React 18 + Vite 5 |
| Charts | Recharts |
| HTTP client | Axios |
| Config | python-dotenv |

---

## Key files

```
backend/
  main.py                   Entry point — starts scheduler + FastAPI together
  scheduler.py              Hourly pipeline job (fetch → indicators → signal → execute)
  state.py                  Shared bot_state dict (running, last_signal, etc.)
  db.py                     SQLAlchemy engine, Candle model, Trade model, init_db()
  config/settings.py        All tunable parameters + .env loading
  data/fetcher.py           CCXT OHLCV fetch (testnet when PAPER_MODE=true)
  data/cache.py             SQLite candle upsert + load
  strategy/indicators.py    Compute EMA9/21, MACD, RSI, ATR, VolMA
  strategy/signals.py       4-rule consensus → Signal dataclass (LONG/SHORT/FLAT)
  risk/manager.py           Position size, SL/TP prices, time-exit, SL/TP check
  executor/paper.py         Simulated fills (no exchange calls)
  executor/orders.py        Real CCXT market orders (PAPER_MODE=false only)
  tracker/trades.py         Open/close/query trades in SQLite
  tracker/performance.py    Portfolio value, win rate, Sharpe, equity curve
  dashboard/app.py          FastAPI REST API (all /api/* endpoints)
  backtest/runner.py        Historical replay — fetches public Binance candles

frontend/src/
  App.jsx + App.css         App shell + all CSS tokens
  api/client.js             Axios base config (proxy → localhost:8000)
  components/StatusBar.jsx  Bot status, mode badge, last signal
  components/OpenPosition.jsx  Live unrealised P&L card (polls every 30s)
  components/EquityCurve.jsx   Recharts line chart + perf stats strip
  components/TradeLog.jsx      Last 50 trades table
  components/PerformanceCard.jsx  Backtest runner + results chart
```

---

## Strategy summary

**All 4 rules must agree to enter a trade:**

1. **EMA 9/21 crossover** — EMA9 crosses above EMA21 → LONG; below → SHORT
2. **RSI(14) gate** — LONG only if RSI < 65; SHORT only if RSI > 35
3. **MACD histogram** — positive for LONG, negative for SHORT
4. **Volume spike** — current volume > 1.5× 20-period average

**Exits (whichever fires first):**
- Stop-loss: 1.5× ATR(14) from entry
- Take-profit: 2.5× ATR(14) from entry
- Time-exit: force-close after 23h

**Risk:** 2% of portfolio per trade, max 1 open position.

---

## How to run

```bash
# Terminal 1 — backend
cd backend
pip install -r requirements.txt   # first time only
cp .env.example .env               # fill in Binance testnet keys
python main.py                     # FastAPI at http://localhost:8000

# Terminal 2 — frontend
cd frontend
npm install                        # first time only
npm run dev                        # React at http://localhost:5173
```

Swagger API docs auto-generated at: http://localhost:8000/docs

If the dashboard's status bar says **Backend offline**, the backend isn't running. Start it as above. (Vite's dev proxy answers with an empty HTTP 500 when the backend is down, so a bare 500 in the browser usually means "not running", not a server bug.)

---

## Environment variables (.env — never commit)

```
BINANCE_API_KEY=your_testnet_key
BINANCE_SECRET=your_testnet_secret
PAPER_MODE=true
```

Testnet keys: https://testnet.binance.vision (GitHub login → "Generate HMAC_SHA256 Key")

---

## Future ML phase (Phase 8+)

See PLAN.md → "Future Phase: ML Integration" section.

Goal: add a GradientBoostingClassifier as a final gate in `strategy/signals.py` that scores each signal's probability of success (>= 0.65 threshold). New files: `strategy/ml_scorer.py`, `models/scorer_v1.pkl`. Only start after the bot has run in paper mode for 2+ weeks.

---

## Known issues / TODOs

- `executor/orders.py` is written but untested on live Binance (intentional — stay in paper mode until backtest Sharpe > 1.0)
- Backtest replays candle by candle; 90 days (~2,160 candles) takes ~4s, 365 days takes longer (frontend timeout is 120s)
- No authentication on the FastAPI endpoints (localhost-only, personal use, acceptable)
- Latest 90-day backtest (2026-09-19): 20 trades, -2.16% return, 35% win rate, Sharpe -1.62. Below the Sharpe > 1.0 gate, so stay in paper mode
