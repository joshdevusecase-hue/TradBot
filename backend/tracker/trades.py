from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.orm import Session
from db import engine, Trade
from config.settings import FEE_PCT


def open_trade(
    symbol: str,
    direction: str,
    entry_price: float,
    quantity: float,
    sl_price: float,
    tp_price: float,
    signal_reason: str,
    entry_time: Optional[datetime] = None,
) -> int:
    """Insert a new open trade. Returns the new trade id."""
    trade = Trade(
        symbol=symbol,
        direction=direction,
        entry_price=entry_price,
        quantity=quantity,
        sl_price=sl_price,
        tp_price=tp_price,
        signal_reason=signal_reason,
        entry_time=entry_time or datetime.now(tz=timezone.utc),
    )
    with Session(engine) as session:
        session.add(trade)
        session.commit()
        return trade.id


def close_trade(
    trade_id: int, exit_price: float, exit_reason: str, exit_time: Optional[datetime] = None
) -> Optional[Trade]:
    """Set exit fields and compute buy-side P&L net of fees on both sides. Returns the updated trade or None."""
    with Session(engine) as session:
        trade = session.get(Trade, trade_id)
        if trade is None:
            return None
        trade.exit_price = exit_price
        trade.exit_time = exit_time or datetime.now(tz=timezone.utc)
        trade.exit_reason = exit_reason
        fee = FEE_PCT / 100.0
        trade.pnl = round(trade.quantity * (exit_price * (1 - fee) - trade.entry_price * (1 + fee)), 2)
        session.commit()
        session.refresh(trade)
        # Detach so the object can be used outside the session
        session.expunge(trade)
        return trade


def get_open_trade(symbol: str) -> Optional[Trade]:
    """Return the current open trade for symbol, or None."""
    with Session(engine) as session:
        trade = (
            session.query(Trade)
            .filter(Trade.symbol == symbol, Trade.exit_price.is_(None))
            .order_by(Trade.entry_time.desc())
            .first()
        )
        if trade:
            session.expunge(trade)
        return trade


def get_recent_trades(limit: int = 50) -> list[Trade]:
    with Session(engine) as session:
        trades = (
            session.query(Trade)
            .order_by(Trade.entry_time.desc())
            .limit(limit)
            .all()
        )
        for t in trades:
            session.expunge(t)
        return trades
