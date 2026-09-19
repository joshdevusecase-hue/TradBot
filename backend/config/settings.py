import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Exchange
BINANCE_API_KEY: str = os.getenv("BINANCE_API_KEY", "")
BINANCE_SECRET: str = os.getenv("BINANCE_SECRET", "")
PAPER_MODE: bool = os.getenv("PAPER_MODE", "true").lower() == "true"

# Trading pair
SYMBOL: str = "BTC/USDT"
TIMEFRAME: str = "1h"
CANDLE_LIMIT: int = 200  # candles to fetch per run

# Indicators
EMA_FAST: int = 9
EMA_SLOW: int = 21
RSI_PERIOD: int = 14
RSI_LONG_MAX: float = 65.0   # skip buy entries above this RSI
MACD_FAST: int = 12
MACD_SLOW: int = 26
MACD_SIGNAL: int = 9
ATR_PERIOD: int = 14
VOL_MA_PERIOD: int = 20
VOL_MULT: float = 1.5  # volume must be this many times the MA

# Risk management
SL_ATR_MULT: float = 1.5   # stop-loss distance in ATR multiples
TP_ATR_MULT: float = 2.5   # take-profit distance in ATR multiples
RISK_PCT: float = 2.0       # % of portfolio to risk per trade
MAX_HOLD_HRS: int = 23      # hard time-exit after this many hours
FEE_PCT: float = 0.1        # Binance spot fee per side (%), charged on entry and exit

# Dashboard
DASHBOARD_HOST: str = "0.0.0.0"
DASHBOARD_PORT: int = 8000

# Database (absolute, so every launch folder uses the same file)
DB_PATH: str = str(Path(__file__).resolve().parent.parent / "tradbot.db")

# Portfolio
STARTING_CAPITAL: float = 10_000.0  # USD, used for paper mode sizing and backtest
