from datetime import timezone

from sqlalchemy import (
    Column, Integer, String, Float, DateTime,
    TypeDecorator, UniqueConstraint, create_engine,
)
from sqlalchemy.orm import DeclarativeBase
from config.settings import DB_PATH

engine = create_engine(
    f"sqlite:///{DB_PATH}",
    echo=False,
    connect_args={"check_same_thread": False},
)


class Base(DeclarativeBase):
    pass


class UTCDateTime(TypeDecorator):
    # SQLite drops the UTC offset, so store naive UTC and re-attach the offset on read.
    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is not None and value.tzinfo is not None:
            value = value.astimezone(timezone.utc).replace(tzinfo=None)
        return value

    def process_result_value(self, value, dialect):
        if value is not None and value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value


class Candle(Base):
    __tablename__ = "candles"
    id = Column(Integer, primary_key=True)
    symbol = Column(String, nullable=False)
    timeframe = Column(String, nullable=False)
    timestamp = Column(DateTime(timezone=True), nullable=False)
    open = Column(Float)
    high = Column(Float)
    low = Column(Float)
    close = Column(Float)
    volume = Column(Float)
    __table_args__ = (UniqueConstraint("symbol", "timeframe", "timestamp"),)


class Trade(Base):
    __tablename__ = "trades"
    id = Column(Integer, primary_key=True)
    symbol = Column(String, nullable=False)
    direction = Column(String, nullable=False)   # LONG (spot, buy-only)
    entry_price = Column(Float, nullable=False)
    exit_price = Column(Float, nullable=True)
    quantity = Column(Float, nullable=False)
    sl_price = Column(Float, nullable=False)
    tp_price = Column(Float, nullable=False)
    entry_time = Column(UTCDateTime, nullable=False)
    exit_time = Column(UTCDateTime, nullable=True)
    pnl = Column(Float, nullable=True)
    exit_reason = Column(String, nullable=True)  # Take profit | Stop loss | Time exit | ...
    signal_reason = Column(String, nullable=False)
    mode = Column(String, nullable=False, default="paper", server_default="paper")  # paper | live
    entry_cost = Column(Float, nullable=True)       # USDT spent, fees included
    entry_order_id = Column(String, nullable=True)  # live: Binance market-buy orderId
    exit_order_id = Column(String, nullable=True)   # live: Binance OCO orderListId


# Columns added after the trades table first shipped; create_all never alters an existing table.
_ADDED_TRADE_COLUMNS = {
    "mode": "VARCHAR NOT NULL DEFAULT 'paper'",
    "entry_cost": "FLOAT",
    "entry_order_id": "VARCHAR",
    "exit_order_id": "VARCHAR",
}


def init_db() -> None:
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        existing = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(trades)")}
        for name, ddl in _ADDED_TRADE_COLUMNS.items():
            if name not in existing:
                conn.exec_driver_sql(f"ALTER TABLE trades ADD COLUMN {name} {ddl}")
