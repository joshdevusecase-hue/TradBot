# TradBot — Project Context

> **For any LLM picking up this project**: read this file first. It is the single source of truth.

---

## What this project is

A personal, locally-hosted automated crypto trading bot for BTC/USDT on **Binance spot, buy-only**. It requires zero human intervention, holds each position for at most 24 hours, runs a 4-indicator consensus strategy, manages risk automatically, and exposes a React dashboard at localhost:5173.

**End goal (user's decision, 2026-09-19):** live trading on the user's real Binance account (no testnet), sized within a fixed USDT cap the user sets. The user chose to improve the strategy first and build live trading only once a strategy passes the backtest gate.

---

## Current status

- Phases 1–7 (scaffold → dashboard → backtester) ✓
- Phase 8 — Strategy rework (spot buy-only, fees included) ✓ **gate not passed** (see "Strategy research")
- Phase 9 — Live trading on Binance spot: **blocked** until a strategy passes the gate. `main.py` refuses to start with `PAPER_MODE=false`
- Phase 10+ — ML: future

Paper mode: **ON**. The bot trades on paper by itself (real market data, simulated fills, fees included) while `python backend/main.py` runs.

---

## Rules for working on this project

- **Real API keys:** the user enters them in `backend/.env` themselves. Never ask for them, never read or print `.env`, never commit it
- **Real money:** never run live mode or place orders on the user's account; the user switches live trading on. Claude is not a licensed financial advisor: amounts and go-live decisions are the user's
- **Git:** commit each verified change and push to `master` on https://github.com/joshdevusecase-hue/TradBot.git
- Keep this file and the PLAN.md architecture diagram current with every change

---

## Architecture decisions & why

| Decision | Reason |
|---|---|
| Binance spot, buy-only | User's choice; spot can't sell BTC the account doesn't hold, so no shorts |
| Binance via CCXT | Unified API for market data and (live mode) orders |
| Paper mode reads the real market, not the testnet | Paper mode sends no orders, so the testnet adds nothing. Testnet prices track the real market (median gap 0.002%), but its volume is ~8% of real with 0.41 correlation, which skews the volume rule |
| Paper mode runs keyless | Only public endpoints are used; API keys are only read when PAPER_MODE=false |
| `fetchCurrencies: False` | Skips a signed currency-metadata call the bot doesn't need |
| Fees in every result | `FEE_PCT` = 0.1% per side (Binance spot) in the backtest and paper P&L; fees were the difference between break-even and losing |
| Stops/targets filled inside the candle | `risk.manager.intrabar_exit()` fills a stop or target as soon as a candle's low/high touches it (stop first if both touch; gap below the stop fills at the open), like resting exchange orders. Shared by the backtest engine and paper executor |
| Daily-return Sharpe (×√365) | The gate needs a standard Sharpe; the old per-trade ×√252 version flattered results (e.g. "4.83" on 30 days). Paper Sharpe shows "—" until 30 days of history |
| `long_entries()` + `generate_signal()` | Vectorised rules for backtests, per-candle rules with plain-English reasons for the live bot; verified identical on 4,000 real candles |
| Signals judge closed candles only | `closed_candles()` drops the still-forming hourly candle; judging it mid-hour compared partial volume against full-hour averages |
| Candle upsert refreshes rows | A candle saved while forming gets its final values on the next run |
| Scheduler runs at hh:00:30 UTC | Judges each candle 30s after it closes, matching the backtest's close-price entries; also runs once at startup |
| Time exit rounds hours held | Exits are checked hourly; rounding stops a few seconds of jitter pushing the 23h exit to 24h |
| Live mode blocked at startup | `executor/orders.py` has no spending cap, no exchange-side stops and no fee-aware sell size yet (Phase 9) |
| Pure indicators, no ML | Beginner-friendly; every trade is explainable; no training data needed |
| SQLite not Postgres | Single-user local app; no server setup needed |
| FastAPI not Flask | Async-native, auto-generates `/docs` Swagger UI at localhost:8000/docs |
| APScheduler background | Shares process with uvicorn; no second terminal needed |
| `state.py` module dict | Thread-safe shared state between scheduler thread and FastAPI async loop |
| Centralised `db.py` | Single SQLAlchemy Base + engine avoids circular imports |
| `UTCDateTime` column type (db.py) | SQLite drops UTC offsets; trade times are stored naive-UTC and returned aware-UTC so time-exit math works |
| Absolute `DB_PATH` | The bot always uses `backend/tradbot.db`, whichever folder it's launched from |

---

## Tech stack

| Layer | Technology |
|---|---|
| Exchange | CCXT (Binance spot, public market data) |
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
  main.py                   Entry point — starts scheduler + FastAPI; refuses PAPER_MODE=false until Phase 9
  scheduler.py              Pipeline job at hh:00:30 UTC (fetch → closed candles → indicators → signal → execute)
  state.py                  Shared bot_state dict (running, last_signal, etc.)
  db.py                     SQLAlchemy engine, Candle model, Trade model, init_db()
  config/settings.py        All tunable parameters (incl. FEE_PCT) + .env loading
  data/fetcher.py           Binance market data (keyless in paper mode) + closed_candles()
  data/cache.py             SQLite candle upsert (refreshes existing rows) + load
  strategy/indicators.py    Compute EMA9/21, MACD, RSI, ATR, VolMA
  strategy/signals.py       Buy-only 4-rule consensus: long_entries() (vectorised) + generate_signal() (LONG/FLAT)
  risk/manager.py           Position size, SL/TP prices, intrabar_exit(), time exit
  executor/paper.py         Simulated fills; exits via intrabar_exit() on candles since entry
  executor/orders.py        Legacy live market orders — unsafe, to be rewritten in Phase 9
  tracker/trades.py         Open/close/query trades; P&L net of fees
  tracker/performance.py    Portfolio value, win rate, daily Sharpe, equity curve
  dashboard/app.py          FastAPI REST API (all /api/* endpoints)
  backtest/engine.py        Buy-only simulation + summary stats (fees, drawdown, buy & hold)
  backtest/runner.py        Fetches public Binance history and runs the engine for /api/backtest
  .env.example              Template for .env (optional in paper mode)

frontend/src/
  App.jsx + App.css         App shell + all CSS tokens
  api/client.js             Axios base config (proxy → localhost:8000)
  components/StatusBar.jsx  Bot status, mode badge, last signal, "Backend offline" banner
  components/OpenPosition.jsx  Live unrealised P&L card (polls every 30s)
  components/EquityCurve.jsx   Recharts line chart + paper performance stats
  components/TradeLog.jsx      Last 50 trades table
  components/PerformanceCard.jsx  Backtest runner: stats incl. fees and buy & hold, daily equity chart
frontend/vite.config.js     /api proxy target: TRADBOT_API env var, default http://localhost:8000
```

---

## Strategy summary

**Buy when all 4 rules agree on the last closed hourly candle (spot, buy-only):**

1. **EMA 9/21 crossover** — EMA9 crosses above EMA21
2. **RSI(14) gate** — RSI < 65
3. **MACD histogram** — positive
4. **Volume spike** — candle volume ≥ 1.5× 20-period average

**Exits (whichever fires first):**
- Stop-loss: 1.5× ATR(14) below entry, filled when a candle touches it
- Take-profit: 2.5× ATR(14) above entry, filled when a candle touches it (stop wins if both touch in one candle)
- Time-exit: sell at the 23rd hourly check

**Risk:** 2% of portfolio per trade (capped at 95% of the portfolio in notional), max 1 open position. **Costs:** 0.1% fee per side.

---

## Strategy research (Phase 8, 2026-09-19)

- **Data:** 35,062 hourly BTC/USDT candles, 2022-09-19 → 2026-09-19 (public Binance)
- **Protocol:** choose settings on 2022-09-20 → 2025-03-19 (BTC +344%), test once on unseen 2025-03-20 → 2026-09-19 (BTC −5.3%). Gate: unseen Sharpe > 1.0 with ≥ 20 trades. Don't pick a strategy by looking at unseen results (that just fits the past)
- **Tested:** 49 hourly + 49 four-hour variants of: EMA cross + trend filter (EMA200/1200 or 50/300 on 4h), breakout above the 24–48h high + trend, dip (RSI < 30/35) in an uptrend; ATR stop/target grids; optional exit signals
- **Result:** 0 of 98 passed. Best in-sample picks: hourly breakout (unseen Sharpe −0.59, −14.0%), 4-hour breakout (unseen Sharpe −0.68, −10.9%)
- **Fees decide it:** current rules on the unseen period make 0.0% before fees and −10.1% after; the best hourly breakout makes +18.4% before fees, −6.8% at 0.075% (BNB discount), −14.0% at 0.1%
- **Latest dashboard backtest (90 days to 2026-09-19):** 11 trades, −3.28%, Sharpe −1.99, $205.90 fees, while buy & hold returned +26.9%
- Research scripts lived in the session scratchpad and weren't committed; the engine they used is `backend/backtest/engine.py`

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

Only the backend needs to run for the bot to trade; the dashboard is just for viewing. The bot stops whenever that terminal closes or the PC sleeps. After pulling code changes, restart the backend (Ctrl+C, then run it again).

To point a second dashboard at another backend: set `TRADBOT_API=http://localhost:8001` before `npm run dev -- --port 5174`.

Swagger API docs auto-generated at: http://localhost:8000/docs

If the dashboard's status bar says **Backend offline**, the backend isn't running. Start it as above. (Vite's dev proxy answers with an empty HTTP 500 when the backend is down, so a bare 500 in the browser usually means "not running", not a server bug.)

---

## Environment variables (.env — never commit)

Optional in paper mode. See `backend/.env.example`.

```
PAPER_MODE=true
BINANCE_API_KEY=   # only used when PAPER_MODE=false (Phase 9)
BINANCE_SECRET=    # only used when PAPER_MODE=false (Phase 9)
```

The user will put real Binance keys here for Phase 9 (trading enabled, withdrawals disabled). Paper mode never reads them.

---

## Future ML phase (Phase 10+)

See PLAN.md → "Future Phase: ML Integration" section.

Goal: add a GradientBoostingClassifier as a final gate in `strategy/signals.py` that scores each signal's probability of success (>= 0.65 threshold). New files: `strategy/ml_scorer.py`, `models/scorer_v1.pkl`. Only start after live trading (Phase 9) is settled and 2+ weeks of paper data exist.

---

## Known issues / TODOs

**Strategy**
- No tested strategy passes the gate after fees (see "Strategy research"). Phase 9 stays blocked until one does

**Phase 9 — live trading (not built)** — `executor/orders.py` is legacy and unsafe:
- No `MAX_CAPITAL_USDT` cap; sizes from STARTING_CAPITAL + closed P&L instead of the real balance
- No exchange-side stop-loss/take-profit (OCO); exits only happen at the hourly check while the PC runs
- Sells the ordered quantity, but Binance takes the buy fee out of the BTC received (unless paid in BNB), so the sell would fail
- No lot-size / minimum-order handling, no reconciliation with the exchange after a restart, fees not read from real fills
- `frontend/src/App.jsx` header hardcodes "Paper Mode"; make it follow `/api/status`

**Other**
- Stops/targets are modelled from hourly high/low; a candle touching both is assumed to hit the stop first
- Backtest replays candle by candle; 365 days takes several seconds (frontend timeout is 120s)
- No authentication on the FastAPI endpoints (localhost-only, personal use, acceptable)
