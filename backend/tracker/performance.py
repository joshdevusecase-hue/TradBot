import math
import pandas as pd
from sqlalchemy.orm import Session
from db import engine, Trade
from config.settings import STARTING_CAPITAL, MAX_CAPITAL_USDT, TRADE_MODE

# A Sharpe ratio from a handful of days is noise; report none until there's a month of history.
_MIN_SHARPE_DAYS = 30


def _base_capital(mode: str) -> float:
    """Paper trades start from a notional $10k; live returns are measured against the user's cap."""
    return STARTING_CAPITAL if mode == "paper" else MAX_CAPITAL_USDT


def _closed(mode: str) -> list[Trade]:
    with Session(engine) as session:
        return (
            session.query(Trade)
            .filter(Trade.mode == mode, Trade.exit_price.isnot(None))
            .order_by(Trade.exit_time)
            .all()
        )


def get_portfolio_value() -> float:
    """Paper portfolio value = starting capital + all closed paper P&L."""
    return round(STARTING_CAPITAL + sum(t.pnl for t in _closed("paper")), 2)


def get_performance(mode: str = TRADE_MODE) -> dict:
    base = _base_capital(mode)
    closed = _closed(mode)

    if not closed:
        return {
            "total_pnl": 0.0,
            "total_return_pct": 0.0,
            "win_rate": 0.0,
            "total_trades": 0,
            "winning_trades": 0,
            "avg_win": 0.0,
            "avg_loss": 0.0,
            "rr_ratio": 0.0,
            "sharpe": None,
            "max_drawdown_pct": 0.0,
            "portfolio_value": base,
        }

    pnls = [t.pnl for t in closed]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]

    total_pnl = sum(pnls)
    win_rate = len(wins) / len(pnls) * 100
    avg_win = sum(wins) / len(wins) if wins else 0.0
    avg_loss = abs(sum(losses) / len(losses)) if losses else 0.0
    rr_ratio = avg_win / avg_loss if avg_loss > 0 else 0.0

    # Daily Sharpe on realised equity, annualised over 365 days like the backtest
    daily_pnl = pd.Series(pnls, index=pd.DatetimeIndex([t.exit_time for t in closed]).floor("D"))
    days = pd.date_range(pd.Timestamp(min(t.entry_time for t in closed)).floor("D"),
                         pd.Timestamp.now(tz="UTC").floor("D"), freq="D")
    daily_equity = base + daily_pnl.groupby(level=0).sum().reindex(days, fill_value=0.0).cumsum()
    rets = daily_equity.pct_change()
    rets.iloc[0] = daily_equity.iloc[0] / base - 1
    sharpe = None
    if len(rets) >= _MIN_SHARPE_DAYS:
        sharpe = float(rets.mean() / rets.std() * math.sqrt(365)) if rets.std() > 0 else 0.0

    # Max drawdown
    equity, peak, max_dd = base, base, 0.0
    for p in pnls:
        equity += p
        peak = max(peak, equity)
        dd = (peak - equity) / peak * 100
        max_dd = max(max_dd, dd)

    return {
        "total_pnl": round(total_pnl, 2),
        "total_return_pct": round(total_pnl / base * 100, 2),
        "win_rate": round(win_rate, 1),
        "total_trades": len(closed),
        "winning_trades": len(wins),
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "rr_ratio": round(rr_ratio, 2),
        "sharpe": round(sharpe, 2) if sharpe is not None else None,
        "max_drawdown_pct": round(max_dd, 2),
        "portfolio_value": round(base + total_pnl, 2),
    }


def get_equity_curve(mode: str = TRADE_MODE) -> list[dict]:
    equity = _base_capital(mode)
    points = [{"date": "Start", "value": equity}]
    for t in _closed(mode):
        equity += t.pnl
        label = t.exit_time.strftime("%d %b") if t.exit_time else "?"
        points.append({"date": label, "value": round(equity, 2)})
    return points
