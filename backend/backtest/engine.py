import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

from risk.manager import intrabar_exit


@dataclass
class _Position:
    i: int
    entry: float
    qty: float
    sl: float
    tp: float
    cost: float


def simulate(
    df: pd.DataFrame,
    entries: pd.Series,
    exits: pd.Series | None,
    sl_mult: float,
    tp_mult: float,
    max_hold: int,
    fee_pct: float,
    capital: float,
    risk_pct: float,
) -> tuple[list[dict], pd.Series]:
    """
    Replay a buy-only spot strategy candle by candle, one position at a time.

    Entries fill at the signal candle's close. From the next candle on, the stop-loss and
    take-profit are checked against each candle's low/high the way resting exchange orders
    fill: the stop wins when both are touched in one candle, and a gap below the stop fills
    at the open. Exit signals and the time limit close at a candle's close. Fees are charged
    on both sides. A candle that closes a trade can't open one, matching the live scheduler.
    Returns (trades, hourly mark-to-market equity net of exit fees).
    """
    o, h, l, c, atr = (df[k].to_numpy(dtype=float) for k in ("open", "high", "low", "close", "atr"))
    enter = entries.to_numpy(dtype=bool)
    leave = exits.to_numpy(dtype=bool) if exits is not None else np.zeros(len(df), dtype=bool)
    fee = fee_pct / 100.0
    cash = capital
    pos: _Position | None = None
    trades: list[dict] = []
    equity = np.empty(len(df))

    for i in range(len(df)):
        exited = False
        if pos is not None:
            hit = intrabar_exit(o[i], h[i], l[i], pos.sl, pos.tp)
            if hit is None and leave[i]:
                hit = (c[i], "Exit signal")
            elif hit is None and i - pos.i >= max_hold:
                hit = (c[i], "Time exit")
            if hit is not None:
                price, reason = hit
                proceeds = pos.qty * price * (1 - fee)
                cash += proceeds
                trades.append({
                    "entry_time": df.index[pos.i],
                    "exit_time": df.index[i],
                    "entry_price": pos.entry,
                    "exit_price": price,
                    "quantity": pos.qty,
                    "pnl": proceeds - pos.cost,
                    "fees": pos.qty * (pos.entry + price) * fee,
                    "hours": i - pos.i,
                    "exit_reason": reason,
                })
                pos, exited = None, True

        if pos is None and not exited and enter[i] and atr[i] > 0:
            sl_dist = sl_mult * atr[i]
            qty = min(cash * risk_pct / 100.0 / sl_dist, cash * 0.95 / (c[i] * (1 + fee)))
            cost = qty * c[i] * (1 + fee)
            cash -= cost
            pos = _Position(i, c[i], qty, c[i] - sl_dist, c[i] + tp_mult * atr[i], cost)

        equity[i] = cash + (pos.qty * c[i] * (1 - fee) if pos is not None else 0.0)

    return trades, pd.Series(equity, index=df.index)


def summarize(trades: list[dict], equity: pd.Series, df: pd.DataFrame, capital: float, fee_pct: float) -> dict:
    pnls = np.array([t["pnl"] for t in trades], dtype=float)
    wins, losses = pnls[pnls > 0], pnls[pnls <= 0]

    daily = equity.resample("1D").last().dropna()
    rets = daily.pct_change()
    rets.iloc[0] = daily.iloc[0] / capital - 1
    sharpe = float(rets.mean() / rets.std() * math.sqrt(365)) if rets.std() > 0 else 0.0

    years = (df.index[-1] - df.index[0]) / pd.Timedelta(days=365)
    final = float(equity.iloc[-1])
    fee = fee_pct / 100.0
    first, last = float(df["close"].iloc[0]), float(df["close"].iloc[-1])

    return {
        "total_trades": len(trades),
        "total_pnl": round(final - capital, 2),
        "total_return_pct": round((final / capital - 1) * 100, 2),
        "annual_return_pct": round(((final / capital) ** (1 / years) - 1) * 100, 2) if years > 0 else 0.0,
        "win_rate": round(len(wins) / len(pnls) * 100, 1) if len(pnls) else 0.0,
        "avg_win": round(float(wins.mean()), 2) if len(wins) else 0.0,
        "avg_loss": round(float(-losses.mean()), 2) if len(losses) else 0.0,
        "rr_ratio": round(float(wins.mean() / -losses.mean()), 2) if len(wins) and len(losses) and losses.mean() < 0 else 0.0,
        "profit_factor": round(float(wins.sum() / -losses.sum()), 2) if len(losses) and losses.sum() < 0 else 0.0,
        "sharpe": round(sharpe, 2),
        "max_drawdown_pct": round(float((1 - equity / equity.cummax()).max() * 100), 2),
        "fees_paid": round(sum(t["fees"] for t in trades), 2),
        "time_in_market_pct": round(sum(t["hours"] for t in trades) / len(df) * 100, 1),
        "buy_hold_pct": round((last * (1 - fee) / (first * (1 + fee)) - 1) * 100, 2),
    }
