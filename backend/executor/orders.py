"""
Live order executor — used only when PAPER_MODE=false.
Places real market orders on Binance via CCXT.
"""
import logging
from strategy.signals import Signal
from tracker.trades import open_trade, close_trade, get_open_trade
from risk.manager import (
    size_position, stop_loss_price, take_profit_price,
    check_sl_tp, should_time_exit,
)
from tracker.performance import get_portfolio_value
from data.fetcher import get_exchange
from config.settings import SYMBOL

logger = logging.getLogger("tradbot.orders")


def enter(signal: Signal, current_price: float) -> int | None:
    exchange = get_exchange()
    portfolio = get_portfolio_value()
    qty = size_position(current_price, signal.atr, portfolio)
    if qty <= 0:
        return None

    sl = stop_loss_price(current_price, signal.atr, signal.direction)
    tp = take_profit_price(current_price, signal.atr, signal.direction)
    side = "buy" if signal.direction == "LONG" else "sell"

    order = exchange.create_market_order(SYMBOL, side, qty)
    fill_price = order.get("average") or current_price

    trade_id = open_trade(
        symbol=SYMBOL,
        direction=signal.direction,
        entry_price=fill_price,
        quantity=qty,
        sl_price=sl,
        tp_price=tp,
        signal_reason=signal.reason,
    )
    logger.info(f"[LIVE] Opened {signal.direction} #{trade_id} fill={fill_price} qty={qty}")
    return trade_id


def check_exits(current_price: float) -> bool:
    trade = get_open_trade(SYMBOL)
    if trade is None:
        return False

    trigger = check_sl_tp(current_price, trade.entry_price, trade.sl_price, trade.tp_price, trade.direction)
    time_up = should_time_exit(trade.entry_time)

    if trigger or time_up:
        reason = trigger if trigger else "Time exit"
        side = "sell" if trade.direction == "LONG" else "buy"
        exchange = get_exchange()
        order = exchange.create_market_order(SYMBOL, side, trade.quantity)
        fill_price = order.get("average") or current_price
        close_trade(trade.id, fill_price, reason)
        logger.info(f"[LIVE] Closed #{trade.id} via {reason} at {fill_price}")
        return True
    return False
