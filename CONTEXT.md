# TradBot — Project Context

> **For any LLM picking up this project**: read this file first. It is the single source of truth.

---

## What this project is

A personal, locally-hosted automated crypto trading bot that trades BTC/USDT on Binance (paper trading by default: real market data, simulated fills), requires zero human intervention, and holds each position for at most 24 hours. It runs a 4-indicator consensus strategy, manages risk automatically, and exposes a React dashboard at localhost:5173.

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

Paper mode: **ON** (PAPER_MODE=true in .env, also the default). No real money is at risk. The bot trades on paper by itself while `python backend/main.py` runs; it is **not** ready for real money (see Known issues).

---

## Architecture decisions & why

| Decision | Reason |
|---|---|
| Binance via CCXT | Unified API for market data and (live mode) orders |
| Paper mode reads the real market, not the testnet | Paper mode sends no orders, so the testnet adds nothing. Testnet prices track the real market (median gap 0.002%), but its volume is ~8% of real with 0.41 correlation, which skews the volume rule |
| Paper mode runs keyless | Only public endpoints are used; API keys are only read when PAPER_MODE=false |
| `fetchCurrencies: False` | Skips a signed currency-metadata call the bot doesn't need |
| Signals judge closed candles only | `closed_candles()` drops the still-forming hourly candle; judging it mid-hour compared partial volume against full-hour averages |
| Candle upsert refreshes rows | A candle saved while forming gets its final values on the next run (previously `do_nothing` froze it) |
| Scheduler runs at hh:00:30 UTC | Judges each candle 30s after it closes, matching the backtest's close-price entries; also runs once at startup |
| Time exit rounds hours held | Exits are checked hourly; rounding stops a few seconds of jitter pushing the 23h exit to 24h |
| Pure indicators, no ML | Beginner-friendly; every trade is explainable; no training data needed |
| SQLite not Postgres | Single-user local app; no server setup needed |
| FastAPI not Flask | Async-native, auto-generates `/docs` Swagger UI at localhost:8000/docs |
| APScheduler background | Shares process with uvicorn; no second terminal needed |
| `state.py` module dict | Thread-safe shared state between scheduler thread and FastAPI async loop |
| Centralised `db.py` | Single SQLAlchemy Base + engine avoids circular imports |
| Backtest uses public Binance | No auth needed for historical OHLCV |
| `UTCDateTime` column type (db.py) | SQLite drops UTC offsets; trade times are stored naive-UTC and returned aware-UTC so time-exit math works |
| Absolute `DB_PATH` | The bot always uses `backend/tradbot.db`, whichever folder it's launched from |

---

## Tech stack

| Layer | Technology |
|---|---|
| Exchange | CCXT (Binance, public market data) |
| Indicators | pandas-ta |
| Scheduler | APScheduler 3.x BackgroundScheduler (cron trigger) |
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
  scheduler.py              Pipeline job at hh:00:30 UTC (fetch → closed candles → indicators → signal → execute)
  state.py                  Shared bot_state dict (running, last_signal, etc.)
  db.py                     SQLAlchemy engine, Candle model, Trade model, init_db()
  config/settings.py        All tunable parameters + .env loading
  data/fetcher.py           Binance market data (keyless in paper mode) + closed_candles()
  data/cache.py             SQLite candle upsert (refreshes existing rows) + load
  strategy/indicators.py    Compute EMA9/21, MACD, RSI, ATR, VolMA
  strategy/signals.py       4-rule consensus → Signal dataclass (LONG/SHORT/FLAT)
  risk/manager.py           Position size, SL/TP prices, time-exit, SL/TP check
  executor/paper.py         Simulated fills (no exchange calls)
  executor/orders.py        Real CCXT market orders (PAPER_MODE=false only)
  tracker/trades.py         Open/close/query trades in SQLite
  tracker/performance.py    Portfolio value, win rate, Sharpe, equity curve
  dashboard/app.py          FastAPI REST API (all /api/* endpoints)
  backtest/runner.py        Historical replay — fetches public Binance candles
  .env.example              Template for .env (optional in paper mode)

frontend/src/
  App.jsx + App.css         App shell + all CSS tokens
  api/client.js             Axios base config (proxy → localhost:8000)
  components/StatusBar.jsx  Bot status, mode badge, last signal, "Backend offline" banner
  components/OpenPosition.jsx  Live unrealised P&L card (polls every 30s)
  components/EquityCurve.jsx   Recharts line chart + perf stats strip
  components/TradeLog.jsx      Last 50 trades table
  components/PerformanceCard.jsx  Backtest runner + results chart
```

---

## Strategy summary

**All 4 rules must agree to enter a trade (judged on the last closed hourly candle):**

1. **EMA 9/21 crossover** — EMA9 crosses above EMA21 → LONG; below → SHORT
2. **RSI(14) gate** — LONG only if RSI < 65; SHORT only if RSI > 35
3. **MACD histogram** — positive for LONG, negative for SHORT
4. **Volume spike** — candle volume > 1.5× 20-period average

**Exits (whichever fires first, checked hourly):**
- Stop-loss: 1.5× ATR(14) from entry
- Take-profit: 2.5× ATR(14) from entry
- Time-exit: force-close at the 23rd hourly check

**Risk:** 2% of portfolio per trade (capped at 95% of the portfolio in notional), max 1 open position.

---

## How to run

```bash
# Terminal 1 — backend (from the repo root)
pip install -r backend/requirements.txt   # first time only
python backend/main.py                    # FastAPI at http://localhost:8000

# Terminal 2 — frontend
cd frontend
npm install                               # first time only
npm run dev                               # React at http://localhost:5173
```

Only the backend needs to run for the bot to trade; the dashboard is just for viewing. The bot stops whenever that terminal closes or the PC sleeps.

Swagger API docs auto-generated at: http://localhost:8000/docs

If the dashboard's status bar says **Backend offline**, the backend isn't running. Start it as above. (Vite's dev proxy answers with an empty HTTP 500 when the backend is down, so a bare 500 in the browser usually means "not running", not a server bug.)

---

## Environment variables (.env — never commit)

Optional in paper mode. See `backend/.env.example`.

```
PAPER_MODE=true
BINANCE_API_KEY=   # only used when PAPER_MODE=false
BINANCE_SECRET=    # only used when PAPER_MODE=false
```

The user's `.env` currently holds Binance **testnet** keys from https://testnet.binance.vision. Paper mode doesn't use them; they would only be useful for a future "real orders on the testnet" test mode.

---

## Future ML phase (Phase 8+)

See PLAN.md → "Future Phase: ML Integration" section.

Goal: add a GradientBoostingClassifier as a final gate in `strategy/signals.py` that scores each signal's probability of success (>= 0.65 threshold). New files: `strategy/ml_scorer.py`, `models/scorer_v1.pkl`. Only start after the bot has run in paper mode for 2+ weeks.

---

## Known issues / TODOs

**Strategy**
- Latest 90-day backtest (2026-09-19): 20 trades, -2.16% return, 35% win rate, Sharpe -1.62, max drawdown 4.8%. Below the Sharpe > 1.0 gate, so stay in paper mode
- Backtest and paper fills ignore fees and slippage. Binance spot taker fees (0.1% per side) on ~$9.5k positions would cost roughly another 4% over those 20 trades
- SL/TP are checked against hourly closes, not intra-hour highs/lows, in both the backtest and paper mode

**Before any real-money (live) run** — `executor/orders.py` is not ready:
- SHORT signals place a spot market sell, which needs BTC already held; Binance spot can't short. Needs margin/futures, or a long-only strategy (the backtest currently assumes shorts)
- No exchange-side stop-loss/take-profit orders; exits only happen at the hourly check while the PC and backend are running
- Position size uses STARTING_CAPITAL + closed P&L, not the real account balance
- Never tested against a real exchange; add a testnet-orders mode and test there first
- `frontend/src/App.jsx` header hardcodes "Paper Mode"; make it follow `/api/status` before any live run

**Other**
- Backtest replays candle by candle; 90 days (~2,160 candles) takes ~4s, 365 days takes longer (frontend timeout is 120s)
- No authentication on the FastAPI endpoints (localhost-only, personal use, acceptable)
