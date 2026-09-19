import logging
from datetime import datetime, timezone
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from db import engine, Trade
from tracker.performance import get_performance, get_equity_curve
from config.settings import PAPER_MODE, SYMBOL, TRADE_MODE, MAX_CAPITAL_USDT, MAX_HOLD_HRS
from state import bot_state

logger = logging.getLogger("tradbot.api")

app = FastAPI(title="TradBot API", version="1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


# ── Status ──────────────────────────────────────────────────────────────────

@app.get("/api/status")
def get_status():
    return {
        **bot_state,
        "symbol": SYMBOL,
        "max_capital_usdt": None if PAPER_MODE else MAX_CAPITAL_USDT,
        "server_time": datetime.now(tz=timezone.utc).isoformat(),
    }


# ── Open position ────────────────────────────────────────────────────────────

@app.get("/api/position")
def get_position():
    with Session(engine) as session:
        trade = (
            session.query(Trade)
            .filter(Trade.symbol == SYMBOL, Trade.mode == TRADE_MODE, Trade.exit_price.is_(None))
            .order_by(Trade.entry_time.desc())
            .first()
        )
        if trade is None:
            return {"open": False}

        # Snapshot values before session closes
        t = {k: getattr(trade, k) for k in [
            "id", "symbol", "direction", "entry_price", "quantity",
            "sl_price", "tp_price", "entry_time", "signal_reason"
        ]}

    # Live price
    try:
        from data.fetcher import fetch_ticker
        current_price: float = fetch_ticker(t["symbol"])["last"]
    except Exception:
        current_price = t["entry_price"]

    unrealised = round((current_price - t["entry_price"]) * t["quantity"], 2)
    cost_basis = t["entry_price"] * t["quantity"]
    pct = round((unrealised / cost_basis) * 100, 2) if cost_basis else 0.0

    entry_time: datetime = t["entry_time"]
    hours_held = (datetime.now(tz=timezone.utc) - entry_time).total_seconds() / 3600
    time_remaining = round(max(0.0, MAX_HOLD_HRS - hours_held), 1)

    return {
        "open": True,
        **t,
        "entry_time": entry_time.isoformat(),
        "current_price": current_price,
        "unrealised_pnl": unrealised,
        "unrealised_pct": pct,
        "time_remaining_h": time_remaining,
    }


# ── Closed trades ────────────────────────────────────────────────────────────

@app.get("/api/trades")
def get_trades(limit: int = 50):
    with Session(engine) as session:
        trades = (
            session.query(Trade)
            .filter(Trade.mode == TRADE_MODE)
            .order_by(Trade.entry_time.desc())
            .limit(limit)
            .all()
        )
        return [
            {
                "id": t.id,
                "symbol": t.symbol,
                "direction": t.direction,
                "entry_price": t.entry_price,
                "exit_price": t.exit_price,
                "quantity": t.quantity,
                "sl_price": t.sl_price,
                "tp_price": t.tp_price,
                "entry_time": t.entry_time.isoformat() if t.entry_time else None,
                "exit_time": t.exit_time.isoformat() if t.exit_time else None,
                "pnl": t.pnl,
                "exit_reason": t.exit_reason,
                "signal_reason": t.signal_reason,
            }
            for t in trades
        ]


# ── Performance ──────────────────────────────────────────────────────────────

@app.get("/api/performance")
def get_performance_endpoint():
    return get_performance()


@app.get("/api/equity")
def get_equity_endpoint():
    return get_equity_curve()


# ── Backtest (runs synchronously — may take ~30s) ────────────────────────────

@app.get("/api/backtest")
def run_backtest_endpoint(days: int = 90):
    from backtest.runner import run_backtest
    try:
        return run_backtest(days=days)
    except Exception as e:
        logger.exception("Backtest failed")
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")
