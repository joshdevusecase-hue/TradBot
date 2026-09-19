"""
Paper trading executor: simulated fills recorded in SQLite, no exchange orders.
Same interface as executor/orders.py (enter, check_exits) so scheduler.py doesn't care which runs.
"""
import logging
import pandas as pd
from strategy.signals import Signal
from tracker.trades import open_trade, close_trade, get_open_trade
from risk.manager import (
    size_position, stop_loss_price, take_profit_price,
    intrabar_exit, should_time_exit,
)
from tracker.performance import get_portfolio_value
from data.cache import load_candles
from data.fetcher import closed_candles
from config.settings import SYMBOL

logger = logging.getLogger("tradbot.paper")

MODE = "paper"


def enter(signal: Signal, current_price: float) -> int | None:
    """Open a paper position. Returns trade id or None if sizing fails."""
    portfolio = get_portfolio_value()
    qty = size_position(current_price, signal.atr, portfolio)
    if qty <= 0:
        logger.warning("Position size is zero — skipping entry.")
        return None

    sl = stop_loss_price(current_price, signal.atr, signal.direction)
    tp = take_profit_price(current_price, signal.atr, signal.direction)

    trade_id = open_trade(
        symbol=SYMBOL,
        direction=signal.direction,
        entry_price=current_price,
        quantity=qty,
        sl_price=sl,
        tp_price=tp,
        signal_reason=signal.reason,
        mode=MODE,
    )
    logger.info(
        f"[PAPER] Opened {signal.direction} #{trade_id} "
        f"entry={current_price} SL={sl} TP={tp} qty={qty:.6f} portfolio=${portfolio:,.2f}"
    )
    return trade_id


def check_exits(current_price: float) -> bool:
    """Close the open trade if a finished candle since entry touched its stop or target
    (as resting exchange orders would fill), or its time is up. Returns True if closed."""
    trade = get_open_trade(SYMBOL, MODE)
    if trade is None:
        return False

    candles = closed_candles(load_candles())
    for ts, c in candles[candles.index >= pd.Timestamp(trade.entry_time).floor("h")].iterrows():
        hit = intrabar_exit(c["open"], c["high"], c["low"], trade.sl_price, trade.tp_price)
        if hit is not None:
            price, reason = hit
            close_trade(trade.id, price, reason, exit_time=(ts + pd.Timedelta(hours=1)).to_pydatetime())
            logger.info(f"[PAPER] Closed #{trade.id} via {reason} at {price} (candle {ts:%H:%M} UTC)")
            return True

    if should_time_exit(trade.entry_time):
        close_trade(trade.id, current_price, "Time exit")
        logger.info(f"[PAPER] Closed #{trade.id} via Time exit at {current_price}")
        return True
    return False
