# TradBot — Project Context

> **For any LLM picking up this project**: read this file first. It is the single source of truth.

---

## What this project is

A personal, locally-hosted automated crypto trading bot for BTC/USDT on **Binance spot, buy-only**. It requires zero human intervention, holds each position for at most 24 hours, runs a 4-indicator consensus strategy, manages risk automatically, and exposes a React dashboard at localhost:5173.

**End goal (user's decision, 2026-09-19):** live trading on the user's real Binance account (no testnet), sized within a fixed USDT cap the user sets. Live trading is built but **locked**: it only unlocks when a strategy passes the backtest gate.

---

## Current status

- Phases 1–7 (scaffold → dashboard → backtester) ✓
- Phase 8 — Strategy rework (spot buy-only, fees included) ✓ **gate not passed** (see "Strategy research")
- Phase 9 — Live trading on Binance spot ✓ **built, locked by the strategy gate** (365-day Sharpe −0.39 over 42 trades on 2026-09-19; needs > 1.0)
- Phase 10+ — ML: future

Paper mode: **ON**. The bot trades on paper by itself (real market data, simulated fills, fees included) while `python backend/main.py` runs. The dashboard's status bar shows whether live trading would unlock.

---

## Rules for working on this project

- **Real API keys:** the user enters them in `backend/.env` themselves. Never ask for them, never read or print `.env`, never commit it. Tests set dummy keys in the environment (env vars override `.env`)
- **Real money:** never run live mode, `check_live.py` with real keys, or any order on the user's account; the user does that. Test live code against the simulated exchange in `backend/tests/`. Claude is not a licensed financial advisor: amounts and go-live decisions are the user's
- **Git:** commit each verified change and push to `master` on https://github.com/joshdevusecase-hue/TradBot.git
- Keep this file and the PLAN.md architecture diagram current with every change

---

## How live trading works (Phase 9)

1. **Preflight** (`main.py`, only when `PAPER_MODE=false`), in this order: `MAX_CAPITAL_USDT` > 0 → API key/secret set → strategy gate passes → account can trade spot. Any failure exits with a plain message. The gate runs before any signed request
2. **Gate** (`backtest/gate.py`): 365-day backtest of the current strategy, fees included, must have Sharpe > 1.0 over ≥ 20 trades. Re-checked daily at 00:05 UTC; a failing or erroring check pauses new buys but open trades keep being managed. In paper mode it runs at startup and daily too, just for the dashboard chip
3. **Buy** (`executor/orders.py`): market buy sized by the 2% risk rule from min(cap, free USDT); skipped if below Binance's minimum (5 USDT / 0.00001 BTC). The trade is recorded before protection is placed
4. **Protect:** OCO sell of the BTC actually received (buy fee deducted unless paid in BNB): LIMIT_MAKER take-profit at entry + 2.5 ATR, STOP_LOSS market stop at entry − 1.5 ATR. Binance holds it, so it works while the PC is off. If Binance rejects it, the bot sells immediately ("Protection failed")
5. **Hourly check:** reads the OCO legs. Filled → record the real proceeds (fees from `myTrades`). No working stop (partial target fill, cancelled on Binance, crash before the OCO) → cancel what's left and market-sell ("Take profit (partial)" / "Stop-loss order missing"). 23 hours up → cancel the pair and market-sell ("Time exit"). A fill racing the cancel is recorded as that fill. Dust under Binance's minimum stays in the account and is valued at the current price in P&L
6. **Readiness check** (`check_live.py`, user runs it): keys, account, balances, key permissions (trading on, withdrawals off, IP restriction), OCO support, a validated-not-executed test buy (`/api/v3/order/test`), and the gate. Places no orders, prints no keys

**Going live, when a strategy passes (user steps):** create a Binance API key (Spot & Margin Trading on, withdrawals off, IP-restricted if possible) → put `BINANCE_API_KEY`, `BINANCE_SECRET`, `MAX_CAPITAL_USDT` in `backend/.env` → run `python backend/check_live.py` → set `PAPER_MODE=true` → `false` and restart the bot.

---

## Architecture decisions & why

| Decision | Reason |
|---|---|
| Binance spot, buy-only | User's choice; spot can't sell BTC the account doesn't hold, so no shorts |
| Fixed `MAX_CAPITAL_USDT` cap | User's choice: the bot never uses more than this, even if the account holds more; live returns are measured against it |
| Exchange-held OCO for every live trade | Protection keeps working while the PC is off or the bot crashes |
| STOP_LOSS (market) stop leg | BTCUSDT allows it; a triggered stop always sells, unlike a stop-limit that can be skipped in a fast drop |
| Raw Binance endpoints for trading (`private_post_order`, `private_post_orderlist_oco`, `private_get_orderlist/order/mytrades`, `private_delete_order`) | ccxt has no unified OCO; parsing Binance's documented JSON directly keeps order handling in one format |
| Spot-only market loading (`fetchMarkets` spot, `fetchMargins` off) | ccxt otherwise loads futures markets and makes signed margin calls when keys are set; with a bad key, even loading markets failed |
| `adjustForTimeDifference` when keyed | Binance rejects signed requests if the PC clock drifts |
| Gate checked before any signed request | With a failing strategy, the user's keys are never used |
| Trades table `mode` column | Paper and live history never mix; the dashboard shows the running mode only |
| `init_db()` adds new columns | `create_all` never alters existing tables; the user's database upgrades in place |
| Paper mode reads the real market, not the testnet | Paper mode sends no orders, so the testnet adds nothing; testnet volume is ~8% of real (0.41 correlation), which skews the volume rule |
| Paper mode runs keyless | Only public endpoints are used; API keys are only read when live |
| Fees in every result | `FEE_PCT` = 0.1% per side in the backtest and paper P&L; live P&L uses real fills |
| Stops/targets filled inside the candle | `risk.manager.intrabar_exit()` (stop wins if both touch; gap below the stop fills at the open), shared by the backtest engine and paper executor, matching how the live OCO behaves |
| Daily-return Sharpe (×√365) | Standard definition for the gate; paper Sharpe shows "—" until 30 days of history |
| `long_entries()` + `generate_signal()` | Vectorised rules for backtests, per-candle rules with reasons for the live bot; verified identical on 4,000 real candles |
| Signals judge closed candles only; candle upsert refreshes rows | The still-forming candle is never judged, and a candle saved mid-hour gets its final values |
| Scheduler runs at hh:00:30 UTC | Judges each candle 30s after it closes, matching the backtest's close-price entries |
| Time exit rounds hours held | Hourly checks; rounding stops a few seconds of jitter pushing the 23h exit to 24h |
| Pure indicators, no ML | Beginner-friendly; every trade is explainable |
| SQLite, FastAPI, APScheduler in-process, `state.py` dict, central `db.py` | Single-user local app; one process; no circular imports |
| `UTCDateTime` column type | SQLite drops UTC offsets; trade times are stored naive-UTC and returned aware-UTC |
| Absolute `DB_PATH` | The bot always uses `backend/tradbot.db`, whichever folder it's launched from |

---

## Tech stack

| Layer | Technology |
|---|---|
| Exchange | CCXT 4.5 (Binance spot) |
| Indicators | pandas-ta |
| Scheduler | APScheduler 3.x BackgroundScheduler (cron triggers) |
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
  main.py                   Entry point — live preflight, then scheduler + FastAPI
  check_live.py             Read-only live-trading readiness check (the user runs it)
  scheduler.py              Pipeline at hh:00:30 UTC; daily gate re-check at 00:05 UTC; live buys need the gate
  state.py                  Shared bot_state dict (running, last_signal, trade_mode, gate)
  db.py                     SQLAlchemy engine, Candle + Trade models, init_db() with column upgrades
  config/settings.py        All parameters: strategy, FEE_PCT, MAX_CAPITAL_USDT, GATE_*, TRADE_MODE
  data/fetcher.py           build_exchange() (keyless in paper mode, spot-only markets) + closed_candles()
  data/cache.py             SQLite candle upsert (refreshes existing rows) + load
  strategy/indicators.py    Compute EMA9/21, MACD, RSI, ATR, VolMA
  strategy/signals.py       Buy-only 4-rule consensus: long_entries() (vectorised) + generate_signal() (LONG/FLAT)
  risk/manager.py           Position size, SL/TP prices, intrabar_exit(), time exit
  executor/paper.py         Simulated fills; exits via intrabar_exit() on candles since entry
  executor/orders.py        Live: capped market buy, OCO protection, settlement of fills/cancels/time exits
  tracker/trades.py         Open/close/query trades by mode; P&L = proceeds − entry cost
  tracker/performance.py    Per-mode stats: portfolio value, win rate, daily Sharpe, equity curve
  dashboard/app.py          FastAPI REST API (all /api/* endpoints; running mode only)
  backtest/engine.py        Buy-only simulation + summary stats (fees, drawdown, buy & hold)
  backtest/runner.py        Fetches public Binance history and runs the engine for /api/backtest
  backtest/gate.py          evaluate_gate(): the 365-day Sharpe gate for live buys
  .env.example              Template: PAPER_MODE, keys, MAX_CAPITAL_USDT
  tests/live_sim.py         16 live-trading scenarios against tests/fake_binance.py (real market rules, faked orders)

frontend/src/
  App.jsx + App.css         App shell + all CSS tokens
  api/client.js             Axios base config (proxy → localhost:8000)
  components/StatusBar.jsx  Mode badge (Live shows the cap), "Live trading locked/unlocked" gate chip, last signal, offline banner
  components/OpenPosition.jsx  Live unrealised P&L card (polls every 30s)
  components/EquityCurve.jsx   Recharts line chart + performance stats for the running mode
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
- Stop-loss: 1.5× ATR(14) below entry
- Take-profit: 2.5× ATR(14) above entry (stop wins if both touch in one candle)
- Time-exit: sell at the 23rd hourly check

**Risk:** 2% of capital per trade (capped at 95% of capital in notional), max 1 open position. Capital = $10k notional (paper) or min(`MAX_CAPITAL_USDT`, free USDT) (live). **Costs:** 0.1% fee per side.

---

## Strategy research (Phase 8, 2026-09-19)

- **Data:** 35,062 hourly BTC/USDT candles, 2022-09-19 → 2026-09-19 (public Binance)
- **Protocol:** choose settings on 2022-09-20 → 2025-03-19 (BTC +344%), test once on unseen 2025-03-20 → 2026-09-19 (BTC −5.3%). Gate: unseen Sharpe > 1.0 with ≥ 20 trades. Don't pick a strategy by looking at unseen results (that just fits the past)
- **Tested:** 49 hourly + 49 four-hour variants of: EMA cross + trend filter, breakout above the 24–48h high + trend, dip (RSI < 30/35) in an uptrend; ATR stop/target grids; optional exit signals
- **Result:** 0 of 98 passed. Best in-sample picks: hourly breakout (unseen Sharpe −0.59, −14.0%), 4-hour breakout (unseen Sharpe −0.68, −10.9%)
- **Fees decide it:** current rules on the unseen period make 0.0% before fees and −10.1% after; the best hourly breakout makes +18.4% before fees, −6.8% at 0.075% (BNB discount), −14.0% at 0.1%
- **Latest backtests (to 2026-09-19):** 90 days: 11 trades, −3.28%, Sharpe −1.99, $205.90 fees, while buy & hold returned +26.9%. 365 days (the gate): 42 trades, −3.2%, Sharpe −0.39, $791 fees
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

# Live-trading readiness (read-only, after filling backend/.env)
python backend/check_live.py
```

Only the backend needs to run for the bot to trade; the dashboard is just for viewing. The bot stops whenever that terminal closes or the PC sleeps (live positions stay protected by their OCO on Binance, but the 23-hour exit needs the bot running). After pulling code changes, restart the backend (Ctrl+C, then run it again).

To point a second dashboard at another backend: set `TRADBOT_API=http://localhost:8001` before `npm run dev -- --port 5174`.

Swagger API docs auto-generated at: http://localhost:8000/docs

If the dashboard's status bar says **Backend offline**, the backend isn't running. (Vite's dev proxy answers with an empty HTTP 500 when the backend is down, so a bare 500 in the browser usually means "not running", not a server bug.)

---

## Environment variables (.env — never commit)

Optional in paper mode. See `backend/.env.example`.

```
PAPER_MODE=true
BINANCE_API_KEY=     # live only
BINANCE_SECRET=      # live only
MAX_CAPITAL_USDT=    # live only: most USDT the bot may use
```

---

## Future ML phase (Phase 10+)

See PLAN.md → "Future Phase: ML Integration" section.

Goal: add a GradientBoostingClassifier as a final gate in `strategy/signals.py` that scores each signal's probability of success (>= 0.65 threshold). New files: `strategy/ml_scorer.py`, `models/scorer_v1.pkl`. Only start after live trading is settled and 2+ weeks of paper data exist.

---

## Known issues / TODOs

**Strategy**
- No tested strategy passes the gate after fees (see "Strategy research"), so live trading stays locked

**Live trading**
- Never run against the real account yet; tested against a simulated Binance: `python backend/tests/live_sim.py` (16 scenarios, dummy keys, throwaway database). Re-run it after any change to live code. The first real run should use a small cap
- The 23-hour exit and the settlement of fills need the bot running; the OCO protects the position meanwhile
- Buy fees paid in BNB aren't counted in live P&L (BTC and USDT fees are)
- A crash in the milliseconds between a market buy and recording the trade would leave BTC the bot doesn't know about
- The hourly check sells at market when a trade has no working stop; if the user cancels the OCO on Binance by hand, the bot sells the position on its next check

**Other**
- Stops/targets in the backtest and paper mode are modelled from hourly high/low
- Backtest replays candle by candle; 365 days takes several seconds (frontend timeout is 120s)
- No authentication on the FastAPI endpoints (localhost-only, personal use, acceptable)
