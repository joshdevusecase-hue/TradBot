from sqlalchemy import (
    Column, Integer, String, Float, DateTime,
    UniqueConstraint, create_engine,
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
    direction = Column(String, nullable=False)   # LONG | SHORT
    entry_price = Column(Float, nullable=False)
    exit_price = Column(Float, nullable=True)
    quantity = Column(Float, nullable=False)
    sl_price = Column(Float, nullable=False)
    tp_price = Column(Float, nullable=False)
    entry_time = Column(DateTime(timezone=True), nullable=False)
    exit_time = Column(DateTime(timezone=True), nullable=True)
    pnl = Column(Float, nullable=True)
    exit_reason = Column(String, nullable=True)  # Take profit | Stop loss | Time exit
    signal_reason = Column(String, nullable=False)


def init_db() -> None:
    Base.metadata.create_all(engine)
