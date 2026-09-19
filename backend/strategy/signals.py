from dataclasses import dataclass, field
from typing import Literal
import pandas as pd
from config.settings import RSI_LONG_MAX, RSI_SHORT_MIN, VOL_MULT

Direction = Literal["LONG", "SHORT", "FLAT"]
_REQUIRED = ("ema_fast", "ema_slow", "macd_hist", "rsi", "atr", "vol_ma")


@dataclass
class Signal:
    direction: Direction
    reason: str
    rsi: float = 0.0
    atr: float = 0.0
    macd_hist: float = 0.0
    vol_ratio: float = 0.0


def generate_signal(df: pd.DataFrame) -> Signal:
    """
    Apply 4-indicator consensus on the last two candles of df.
    compute_indicators() must have been called first.
    Returns Signal with direction LONG | SHORT | FLAT and a plain-English reason.
    """
    if len(df) < 2:
        return Signal("FLAT", "not enough candles")

    prev, curr = df.iloc[-2], df.iloc[-1]

    # Guard: all indicators must be present and finite
    for col in _REQUIRED:
        if col not in df.columns or pd.isna(curr[col]):
            return Signal("FLAT", f"indicator not ready: {col}")

    rsi       = float(curr["rsi"])
    atr       = float(curr["atr"])
    macd_hist = float(curr["macd_hist"])
    vol_ratio = float(curr["volume"] / curr["vol_ma"]) if curr["vol_ma"] > 0 else 0.0

    # ── Rule 1: EMA crossover ──────────────────────────────────────────────
    prev_above = float(prev["ema_fast"]) > float(prev["ema_slow"])
    curr_above = float(curr["ema_fast"]) > float(curr["ema_slow"])

    long_cross  = (not prev_above) and curr_above
    short_cross = prev_above and (not curr_above)

    if not long_cross and not short_cross:
        return Signal("FLAT", "no EMA crossover", rsi=rsi, atr=atr, macd_hist=macd_hist, vol_ratio=vol_ratio)

    direction: Direction = "LONG" if long_cross else "SHORT"
    reasons = [f"EMA{int(curr['ema_fast'])} × EMA crossover"]

    # ── Rule 2: RSI gate ───────────────────────────────────────────────────
    if direction == "LONG" and rsi >= RSI_LONG_MAX:
        return Signal("FLAT", f"RSI={rsi:.1f} overbought (≥{RSI_LONG_MAX}), skipping LONG",
                      rsi=rsi, atr=atr, macd_hist=macd_hist, vol_ratio=vol_ratio)
    if direction == "SHORT" and rsi <= RSI_SHORT_MIN:
        return Signal("FLAT", f"RSI={rsi:.1f} oversold (≤{RSI_SHORT_MIN}), skipping SHORT",
                      rsi=rsi, atr=atr, macd_hist=macd_hist, vol_ratio=vol_ratio)
    reasons.append(f"RSI={rsi:.1f}")

    # ── Rule 3: MACD histogram gate ────────────────────────────────────────
    if direction == "LONG" and macd_hist <= 0:
        return Signal("FLAT", f"MACD hist={macd_hist:.4f} not positive, no momentum for LONG",
                      rsi=rsi, atr=atr, macd_hist=macd_hist, vol_ratio=vol_ratio)
    if direction == "SHORT" and macd_hist >= 0:
        return Signal("FLAT", f"MACD hist={macd_hist:.4f} not negative, no momentum for SHORT",
                      rsi=rsi, atr=atr, macd_hist=macd_hist, vol_ratio=vol_ratio)
    sign = "+" if macd_hist > 0 else ""
    reasons.append(f"MACD hist {sign}{macd_hist:.4f}")

    # ── Rule 4: Volume spike gate ──────────────────────────────────────────
    if vol_ratio < VOL_MULT:
        return Signal("FLAT", f"Volume {vol_ratio:.2f}× avg (need ≥{VOL_MULT}×)",
                      rsi=rsi, atr=atr, macd_hist=macd_hist, vol_ratio=vol_ratio)
    reasons.append(f"Vol {vol_ratio:.2f}× avg")

    return Signal(direction, " | ".join(reasons), rsi=rsi, atr=atr, macd_hist=macd_hist, vol_ratio=vol_ratio)
