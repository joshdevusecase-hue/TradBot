from datetime import datetime, timezone, timedelta
from config.settings import SL_ATR_MULT, TP_ATR_MULT, RISK_PCT, MAX_HOLD_HRS


def size_position(entry_price: float, atr: float, portfolio_value: float) -> float:
    """
    Fixed-fraction sizing: risk exactly RISK_PCT% of portfolio per trade.
    Quantity = risk_amount / sl_distance, capped at 95% of portfolio.
    """
    risk_amount = portfolio_value * (RISK_PCT / 100.0)
    sl_distance = SL_ATR_MULT * atr
    if sl_distance <= 0 or entry_price <= 0:
        return 0.0
    qty = risk_amount / sl_distance
    max_qty = (portfolio_value * 0.95) / entry_price
    return round(min(qty, max_qty), 8)


def stop_loss_price(entry: float, atr: float, direction: str) -> float:
    dist = SL_ATR_MULT * atr
    return round(entry - dist if direction == "LONG" else entry + dist, 2)


def take_profit_price(entry: float, atr: float, direction: str) -> float:
    dist = TP_ATR_MULT * atr
    return round(entry + dist if direction == "LONG" else entry - dist, 2)


def should_time_exit(entry_time: datetime) -> bool:
    # Exits are checked hourly; rounding stops a few seconds of timing jitter from
    # pushing the 23h exit to the next check at 24h.
    held_hours = (datetime.now(tz=timezone.utc) - entry_time) / timedelta(hours=1)
    return round(held_hours) >= MAX_HOLD_HRS


def check_sl_tp(current_price: float, entry: float, sl: float, tp: float, direction: str) -> str | None:
    """Return 'Take profit', 'Stop loss', or None."""
    if direction == "LONG":
        if current_price <= sl:
            return "Stop loss"
        if current_price >= tp:
            return "Take profit"
    else:
        if current_price >= sl:
            return "Stop loss"
        if current_price <= tp:
            return "Take profit"
    return None
