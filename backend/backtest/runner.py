"""
Backtester — replays the full signal pipeline on historical Binance candles.
Uses the PUBLIC Binance API (no auth, no testnet) so real market history is always available.
"""
import time
import math
import logging
from datetime import datetime, timezone, timedelta

import ccxt
import pandas as pd

from data.fetcher import closed_candles
from strategy.indicators import compute_indicators
from strategy.signals import generate_signal
from risk.manager import (
    stop_loss_price, take_profit_price,
    size_position, check_sl_tp,
)
from config.settings import SYMBOL, TIMEFRAME, STARTING_CAPITAL, MAX_HOLD_HRS

logger = logging.getLogger("tradbot.backtest")


def _fetch_historical(symbol: str, timeframe: str, days: int) -> pd.DataFrame:
    """Fetch up to `days` worth of historical candles from real Binance (public, no auth)."""
    exchange = ccxt.binance({"enableRateLimit": True})
    since_ms = int((datetime.now(tz=timezone.utc) - timedelta(days=days)).timestamp() * 1000)
    now_ms = int(datetime.now(tz=timezone.utc).timestamp() * 1000)

    all_candles: list = []
    cursor = since_ms
    while cursor < now_ms:
        try:
            batch = exchange.fetch_ohlcv(symbol, timeframe=timeframe, since=cursor, limit=1000)
        except Exception as e:
            logger.error(f"Backtest fetch error: {e}")
            break
        if not batch:
            break
        all_candles.extend(batch)
        cursor = batch[-1][0] + 1
        time.sleep(0.25)

    if not all_candles:
        return pd.DataFrame()

    df = pd.DataFrame(all_candles, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    df = df.set_index("timestamp").astype(float)
    df = df[~df.index.duplicated()]
    return df


def run_backtest(symbol: str = SYMBOL, days: int = 90) -> dict:
    logger.info(f"Backtest starting: {symbol} last {days} days")
    df_raw = closed_candles(_fetch_historical(symbol, TIMEFRAME, days))

    if df_raw.empty or len(df_raw) < 60:
        return {"error": "Not enough historical data", "total_trades": 0}

    df = compute_indicators(df_raw)
    df = df.dropna(subset=["ema_fast", "ema_slow", "rsi", "atr", "macd_hist", "vol_ma"])

    portfolio = STARTING_CAPITAL
    open_trade: dict | None = None
    trades: list[dict] = []

    for i in range(1, len(df)):
        window = df.iloc[: i + 1]
        curr = df.iloc[i]
        current_price = float(curr["close"])

        # ── Check exit on open trade ──────────────────────────────────────
        if open_trade is not None:
            trigger = check_sl_tp(
                current_price,
                open_trade["entry_price"],
                open_trade["sl_price"],
                open_trade["tp_price"],
                open_trade["direction"],
            )
            candles_held = i - open_trade["entry_idx"]
            time_up = candles_held >= MAX_HOLD_HRS

            if trigger or time_up:
                reason = trigger if trigger else "Time exit"
                dir_ = open_trade["direction"]
                if dir_ == "LONG":
                    pnl = (current_price - open_trade["entry_price"]) * open_trade["quantity"]
                else:
                    pnl = (open_trade["entry_price"] - current_price) * open_trade["quantity"]
                portfolio += pnl
                trades.append({
                    "direction": dir_,
                    "entry_price": open_trade["entry_price"],
                    "exit_price": current_price,
                    "pnl": round(pnl, 2),
                    "exit_reason": reason,
                    "signal_reason": open_trade["signal_reason"],
                    "portfolio_after": round(portfolio, 2),
                    "entry_time": open_trade["entry_time"],
                })
                open_trade = None
            # Always continue after checking exit (don't enter same candle)
            continue

        # ── Try to open a new trade ───────────────────────────────────────
        signal = generate_signal(window)
        if signal.direction in ("LONG", "SHORT") and signal.atr > 0:
            sl = stop_loss_price(current_price, signal.atr, signal.direction)
            tp = take_profit_price(current_price, signal.atr, signal.direction)
            qty = size_position(current_price, signal.atr, portfolio)
            if qty > 0:
                open_trade = {
                    "direction": signal.direction,
                    "entry_price": current_price,
                    "sl_price": sl,
                    "tp_price": tp,
                    "quantity": qty,
                    "entry_idx": i,
                    "signal_reason": signal.reason,
                    "entry_time": str(df.index[i]),
                }

    # ── Stats ─────────────────────────────────────────────────────────────
    pnls = [t["pnl"] for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]

    total_pnl = sum(pnls)
    total_return = (total_pnl / STARTING_CAPITAL) * 100
    win_rate = (len(wins) / len(pnls) * 100) if pnls else 0.0
    avg_win = sum(wins) / len(wins) if wins else 0.0
    avg_loss = abs(sum(losses) / len(losses)) if losses else 0.0
    rr = avg_win / avg_loss if avg_loss > 0 else 0.0

    if len(pnls) > 1:
        mean_p = sum(pnls) / len(pnls)
        std_p = math.sqrt(sum((p - mean_p) ** 2 for p in pnls) / len(pnls))
        sharpe = (mean_p / std_p * math.sqrt(252)) if std_p > 0 else 0.0
    else:
        sharpe = 0.0

    equity, peak, max_dd = STARTING_CAPITAL, STARTING_CAPITAL, 0.0
    for t in trades:
        equity = t["portfolio_after"]
        peak = max(peak, equity)
        dd = (peak - equity) / peak * 100
        max_dd = max(max_dd, dd)

    equity_curve = [{"date": "Start", "value": STARTING_CAPITAL}]
    for t in trades:
        equity_curve.append({"date": t["entry_time"][:10], "value": t["portfolio_after"]})

    logger.info(
        f"Backtest done: {len(trades)} trades | "
        f"return={total_return:.1f}% | win={win_rate:.0f}% | Sharpe={sharpe:.2f}"
    )

    return {
        "days": days,
        "total_trades": len(trades),
        "total_pnl": round(total_pnl, 2),
        "total_return_pct": round(total_return, 2),
        "win_rate": round(win_rate, 1),
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "rr_ratio": round(rr, 2),
        "sharpe": round(sharpe, 2),
        "max_drawdown_pct": round(max_dd, 2),
        "equity_curve": equity_curve,
        "trades": trades[-50:],  # last 50 for the API response
    }
