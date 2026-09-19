from dataclasses import dataclass
from typing import Literal
import pandas as pd
from config.settings import RSI_LONG_MAX, VOL_MULT, EMA_FAST, EMA_SLOW

Direction = Literal["LONG", "FLAT"]
_REQUIRED = ("ema_fast", "ema_slow", "macd_hist", "rsi", "atr", "vol_ma")


@dataclass
class Signal:
    direction: Direction
    reason: str
    rsi: float = 0.0
    atr: float = 0.0
    macd_hist: float = 0.0
    vol_ratio: float = 0.0


def long_entries(df: pd.DataFrame) -> pd.Series:
    """Every candle where all four buy rules pass: the vectorised twin of generate_signal, for backtests."""
    cross_up = (df["ema_fast"] > df["ema_slow"]) & (df["ema_fast"].shift(1) <= df["ema_slow"].shift(1))
    vol_ratio = df["volume"] / df["vol_ma"]
    return cross_up & (df["rsi"] < RSI_LONG_MAX) & (df["macd_hist"] > 0) & (vol_ratio >= VOL_MULT)


def generate_signal(df: pd.DataFrame) -> Signal:
    """
    Apply the 4-rule buy consensus to the last candle of df (compute_indicators() first).
    Spot buy-only: returns LONG or FLAT, with a plain-English reason.
    """
    if len(df) < 2:
        return Signal("FLAT", "not enough candles")

    prev, curr = df.iloc[-2], df.iloc[-1]

    for col in _REQUIRED:
        if col not in df.columns or pd.isna(curr[col]):
            return Signal("FLAT", f"indicator not ready: {col}")
    if pd.isna(prev["ema_fast"]) or pd.isna(prev["ema_slow"]):
        return Signal("FLAT", "indicator not ready: ema_slow")

    rsi       = float(curr["rsi"])
    atr       = float(curr["atr"])
    macd_hist = float(curr["macd_hist"])
    vol_ratio = float(curr["volume"] / curr["vol_ma"]) if curr["vol_ma"] > 0 else 0.0
    values = dict(rsi=rsi, atr=atr, macd_hist=macd_hist, vol_ratio=vol_ratio)

    # ── Rule 1: EMA crossover ──────────────────────────────────────────────
    prev_above = float(prev["ema_fast"]) > float(prev["ema_slow"])
    curr_above = float(curr["ema_fast"]) > float(curr["ema_slow"])
    if prev_above or not curr_above:
        crossed_down = prev_above and not curr_above
        reason = (f"EMA{EMA_FAST} crossed below EMA{EMA_SLOW}; buy-only, so no trade"
                  if crossed_down else "no EMA crossover")
        return Signal("FLAT", reason, **values)
    reasons = [f"EMA{EMA_FAST}/{EMA_SLOW} crossover"]

    # ── Rule 2: RSI gate ───────────────────────────────────────────────────
    if rsi >= RSI_LONG_MAX:
        return Signal("FLAT", f"RSI={rsi:.1f} overbought (≥{RSI_LONG_MAX}), skipping buy", **values)
    reasons.append(f"RSI={rsi:.1f}")

    # ── Rule 3: MACD histogram gate ────────────────────────────────────────
    if macd_hist <= 0:
        return Signal("FLAT", f"MACD hist={macd_hist:.4f} not positive, no upward momentum", **values)
    reasons.append(f"MACD hist +{macd_hist:.4f}")

    # ── Rule 4: Volume spike gate ──────────────────────────────────────────
    if vol_ratio < VOL_MULT:
        return Signal("FLAT", f"Volume {vol_ratio:.2f}× avg (need ≥{VOL_MULT}×)", **values)
    reasons.append(f"Vol {vol_ratio:.2f}× avg")

    return Signal("LONG", " | ".join(reasons), **values)
