"""
Backtester — replays the strategy on historical Binance candles with the realistic engine
(spot buy-only, fees on both sides, stop-loss/take-profit filled inside each candle).
Uses the PUBLIC Binance API (no auth, no testnet) so real market history is always available.
"""
import time
import logging
from datetime import datetime, timezone, timedelta

import ccxt
import pandas as pd

from backtest.engine import simulate, summarize
from data.fetcher import closed_candles
from strategy.indicators import compute_indicators
from strategy.signals import long_entries
from config.settings import (
    SYMBOL, TIMEFRAME, STARTING_CAPITAL, MAX_HOLD_HRS,
    SL_ATR_MULT, TP_ATR_MULT, FEE_PCT, RISK_PCT,
)

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

    trades, equity = simulate(
        df, long_entries(df), None, SL_ATR_MULT, TP_ATR_MULT, MAX_HOLD_HRS,
        FEE_PCT, STARTING_CAPITAL, RISK_PCT,
    )
    stats = summarize(trades, equity, df, STARTING_CAPITAL, FEE_PCT)
    logger.info(
        f"Backtest done: {stats['total_trades']} trades | return={stats['total_return_pct']:.1f}% | "
        f"win={stats['win_rate']:.0f}% | Sharpe={stats['sharpe']:.2f} | fees=${stats['fees_paid']:,.0f}"
    )

    daily = equity.resample("1D").last().dropna()
    return {
        "days": days,
        "fee_pct": FEE_PCT,
        **stats,
        "equity_curve": [{"date": "Start", "value": STARTING_CAPITAL}]
        + [{"date": f"{ts:%Y-%m-%d}", "value": round(float(v), 2)} for ts, v in daily.items()],
        "trades": [
            {
                **t,
                "entry_time": t["entry_time"].isoformat(),
                "exit_time": t["exit_time"].isoformat(),
                "pnl": round(float(t["pnl"]), 2),
                "fees": round(float(t["fees"]), 2),
            }
            for t in trades[-50:]
        ],
    }
