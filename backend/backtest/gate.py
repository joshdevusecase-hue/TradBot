from datetime import datetime, timezone

from backtest.runner import run_backtest
from config.settings import GATE_DAYS, GATE_MIN_SHARPE, GATE_MIN_TRADES

RULE = (f"{GATE_DAYS}-day backtest (fees included) with a Sharpe ratio above {GATE_MIN_SHARPE} "
        f"over at least {GATE_MIN_TRADES} trades")


def evaluate_gate() -> dict:
    """Backtest the current strategy on recent history; live buys stay locked unless it clears RULE."""
    result = run_backtest(days=GATE_DAYS)
    ok = "error" not in result
    return {
        "passed": ok and result["sharpe"] > GATE_MIN_SHARPE and result["total_trades"] >= GATE_MIN_TRADES,
        "sharpe": result.get("sharpe"),
        "trades": result.get("total_trades"),
        "return_pct": result.get("total_return_pct"),
        "rule": RULE,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }
