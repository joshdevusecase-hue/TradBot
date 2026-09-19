import ccxt
import pandas as pd
from config.settings import (
    BINANCE_API_KEY, BINANCE_SECRET, PAPER_MODE,
    SYMBOL, TIMEFRAME, CANDLE_LIMIT,
)


def build_exchange(with_keys: bool = not PAPER_MODE) -> ccxt.binance:
    # Paper mode only reads public market data, so it runs keyless against the real market.
    keys = {"apiKey": BINANCE_API_KEY, "secret": BINANCE_SECRET} if with_keys else {}
    return ccxt.binance({
        **keys,
        "enableRateLimit": True,
        "options": {
            "defaultType": "spot",
            # Load spot markets only. ccxt also loads futures markets by default and, with keys,
            # makes signed margin-pair calls that a spot-only bot never needs.
            "fetchMarkets": {"types": ["spot"]},
            "fetchMargins": False,
            # Skip the signed wallet-metadata call; the bot never needs it.
            "fetchCurrencies": False,
            # Binance rejects signed requests when the PC clock drifts; sync with its clock first.
            "adjustForTimeDifference": with_keys,
        },
    })


_exchange: ccxt.binance = build_exchange()


def fetch_ohlcv(symbol: str = SYMBOL, timeframe: str = TIMEFRAME, limit: int = CANDLE_LIMIT) -> pd.DataFrame:
    """Fetch the latest `limit` candles for `symbol` from Binance.

    Returns a DataFrame with columns: timestamp, open, high, low, close, volume.
    timestamp is a timezone-aware UTC datetime.
    """
    raw = _exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
    df = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    df = df.set_index("timestamp")
    return df.astype(float)


def closed_candles(df: pd.DataFrame, timeframe: str = TIMEFRAME) -> pd.DataFrame:
    """Drop the still-forming candle; the strategy only judges finished candles."""
    candle = pd.Timedelta(seconds=ccxt.Exchange.parse_timeframe(timeframe))
    return df[df.index + candle <= pd.Timestamp.now(tz="UTC")]


def fetch_ticker(symbol: str = SYMBOL) -> dict:
    """Return the current ticker (last price, bid, ask) for `symbol`."""
    return _exchange.fetch_ticker(symbol)


def get_exchange() -> ccxt.binance:
    return _exchange


if __name__ == "__main__":
    print(f"Paper mode: {PAPER_MODE}")
    df = fetch_ohlcv()
    print(f"Fetched {len(df)} candles for {SYMBOL} ({TIMEFRAME})")
    print(df.tail())
