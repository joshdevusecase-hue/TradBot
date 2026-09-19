import pandas as pd
from sqlalchemy.orm import Session
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from db import engine, Candle
from config.settings import SYMBOL, TIMEFRAME, CANDLE_LIMIT


def upsert_candles(df: pd.DataFrame, symbol: str = SYMBOL, timeframe: str = TIMEFRAME) -> None:
    """Insert new candles and refresh existing ones, so a candle saved while still forming gets its final values."""
    rows = [
        {
            "symbol": symbol,
            "timeframe": timeframe,
            "timestamp": ts.to_pydatetime(),
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": float(row["close"]),
            "volume": float(row["volume"]),
        }
        for ts, row in df.iterrows()
    ]
    with engine.begin() as conn:
        stmt = sqlite_insert(Candle).values(rows)
        stmt = stmt.on_conflict_do_update(
            index_elements=["symbol", "timeframe", "timestamp"],
            set_={col: stmt.excluded[col] for col in ("open", "high", "low", "close", "volume")},
        )
        conn.execute(stmt)


def load_candles(symbol: str = SYMBOL, timeframe: str = TIMEFRAME, limit: int = CANDLE_LIMIT) -> pd.DataFrame:
    """Load the most recent `limit` candles from SQLite, oldest first."""
    with Session(engine) as session:
        rows = (
            session.query(Candle)
            .filter_by(symbol=symbol, timeframe=timeframe)
            .order_by(Candle.timestamp.desc())
            .limit(limit)
            .all()
        )
    if not rows:
        return pd.DataFrame()
    rows = list(reversed(rows))
    index = pd.DatetimeIndex([r.timestamp for r in rows], name="timestamp", tz="UTC")
    return pd.DataFrame(
        {
            "open":   [r.open   for r in rows],
            "high":   [r.high   for r in rows],
            "low":    [r.low    for r in rows],
            "close":  [r.close  for r in rows],
            "volume": [r.volume for r in rows],
        },
        index=index,
    )
