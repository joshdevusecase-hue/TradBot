from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.orm import Session
from db import engine, Trade
from config.settings import FEE_PCT, TRADE_MODE


def open_trade(
    symbol: str,
    direction: str,
    entry_price: float,
    quantity: float,
    sl_price: float,
    tp_price: float,
    signal_reason: str,
    entry_time: Optional[datetime] = None,
    mode: str = TRADE_MODE,
    entry_cost: Optional[float] = None,
    entry_order_id: Optional[str] = None,
    exit_order_id: Optional[str] = None,
) -> int:
    """Insert a new open trade. Returns the new trade id.

    entry_cost is the USDT actually spent including fees; paper trades default to the fee model.
    """
    if entry_cost is None:
        entry_cost = quantity * entry_price * (1 + FEE_PCT / 100.0)
    trade = Trade(
        symbol=symbol,
        direction=direction,
        entry_price=entry_price,
        quantity=quantity,
        sl_price=sl_price,
        tp_price=tp_price,
        signal_reason=signal_reason,
        entry_time=entry_time or datetime.now(tz=timezone.utc),
        mode=mode,
        entry_cost=entry_cost,
        entry_order_id=entry_order_id,
        exit_order_id=exit_order_id,
    )
    with Session(engine) as session:
        session.add(trade)
        session.commit()
        return trade.id


def set_exit_order(trade_id: int, exit_order_id: str) -> None:
    with Session(engine) as session:
        session.get(Trade, trade_id).exit_order_id = exit_order_id
        session.commit()


def close_trade(
    trade_id: int,
    exit_price: float,
    exit_reason: str,
    exit_time: Optional[datetime] = None,
    proceeds: Optional[float] = None,
) -> Optional[Trade]:
    """Set exit fields and P&L = USDT received − USDT spent. Returns the updated trade or None.

    Live trades pass the actual proceeds; paper trades model the exit fee.
    """
    with Session(engine) as session:
        trade = session.get(Trade, trade_id)
        if trade is None:
            return None
        fee = FEE_PCT / 100.0
        if proceeds is None:
            proceeds = trade.quantity * exit_price * (1 - fee)
        cost = trade.entry_cost if trade.entry_cost is not None else trade.quantity * trade.entry_price * (1 + fee)
        trade.exit_price = exit_price
        trade.exit_time = exit_time or datetime.now(tz=timezone.utc)
        trade.exit_reason = exit_reason
        trade.pnl = round(proceeds - cost, 2)
        session.commit()
        session.refresh(trade)
        # Detach so the object can be used outside the session
        session.expunge(trade)
        return trade


def get_open_trade(symbol: str, mode: str = TRADE_MODE) -> Optional[Trade]:
    """Return the current open trade for symbol in this mode, or None."""
    with Session(engine) as session:
        trade = (
            session.query(Trade)
            .filter(Trade.symbol == symbol, Trade.mode == mode, Trade.exit_price.is_(None))
            .order_by(Trade.entry_time.desc())
            .first()
        )
        if trade:
            session.expunge(trade)
        return trade


def get_recent_trades(limit: int = 50, mode: str = TRADE_MODE) -> list[Trade]:
    with Session(engine) as session:
        trades = (
            session.query(Trade)
            .filter(Trade.mode == mode)
            .order_by(Trade.entry_time.desc())
            .limit(limit)
            .all()
        )
        for t in trades:
            session.expunge(t)
        return trades
