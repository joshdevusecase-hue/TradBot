"""
Paper trading executor.
Delegates entirely to tracker/trades.py — no exchange calls.
Exists so scheduler.py can call execute(signal) without caring about paper vs live.
"""
from strategy.signals import Signal
from tracker.trades import open_trade, close_trade, get_open_trade
from risk.manager import (
    size_position, stop_loss_price, take_profit_price,
    check_sl_tp, should_time_exit,
)
from tracker.performance import get_portfolio_value
from config.settings import SYMBOL
import logging

logger = logging.getLogger("tradbot.paper")


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
    )
    logger.info(
        f"[PAPER] Opened {signal.direction} #{trade_id} "
        f"entry={current_price} SL={sl} TP={tp} qty={qty:.6f} portfolio=${portfolio:,.2f}"
    )
    return trade_id


def check_exits(current_price: float) -> bool:
    """Check if the current open position should be closed. Returns True if closed."""
    trade = get_open_trade(SYMBOL)
    if trade is None:
        return False

    trigger = check_sl_tp(current_price, trade.entry_price, trade.sl_price, trade.tp_price, trade.direction)
    time_up = should_time_exit(trade.entry_time)

    if trigger:
        close_trade(trade.id, current_price, trigger)
        logger.info(f"[PAPER] Closed #{trade.id} via {trigger} at {current_price}")
        return True
    if time_up:
        close_trade(trade.id, current_price, "Time exit")
        logger.info(f"[PAPER] Closed #{trade.id} via Time exit at {current_price}")
        return True
    return False
