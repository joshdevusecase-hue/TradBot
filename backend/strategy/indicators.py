import pandas as pd
import pandas_ta as ta
from config.settings import (
    EMA_FAST, EMA_SLOW, RSI_PERIOD,
    MACD_FAST, MACD_SLOW, MACD_SIGNAL,
    ATR_PERIOD, VOL_MA_PERIOD,
)


def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Append indicator columns to a copy of df.
    All output column names are fixed strings (not dynamic) for easy reference downstream.

    Added columns:
      ema_fast, ema_slow, macd_hist, rsi, atr, vol_ma
    """
    df = df.copy()

    df["ema_fast"] = ta.ema(df["close"], length=EMA_FAST)
    df["ema_slow"] = ta.ema(df["close"], length=EMA_SLOW)

    macd = ta.macd(df["close"], fast=MACD_FAST, slow=MACD_SLOW, signal=MACD_SIGNAL)
    hist_col = f"MACDh_{MACD_FAST}_{MACD_SLOW}_{MACD_SIGNAL}"
    df["macd_hist"] = macd[hist_col] if macd is not None and hist_col in macd.columns else float("nan")

    df["rsi"] = ta.rsi(df["close"], length=RSI_PERIOD)
    df["atr"] = ta.atr(df["high"], df["low"], df["close"], length=ATR_PERIOD)
    df["vol_ma"] = ta.sma(df["volume"], length=VOL_MA_PERIOD)

    return df
