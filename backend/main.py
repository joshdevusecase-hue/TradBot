import logging
import sys
import uvicorn
from config.settings import PAPER_MODE, MAX_CAPITAL_USDT, BINANCE_API_KEY, BINANCE_SECRET
from db import init_db
from scheduler import create_scheduler
from state import bot_state
from dashboard.app import app  # noqa: F401 — imported for uvicorn

# Piped or redirected output on Windows defaults to cp1252, which can't encode signal text like "≥".
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)


def _live_preflight() -> None:
    """Refuse to trade real money unless the cap, keys, strategy gate and account all check out."""
    if MAX_CAPITAL_USDT <= 0:
        sys.exit("Live trading needs a spending cap: set MAX_CAPITAL_USDT in backend/.env "
                 "(the most USDT the bot may use).")
    if not (BINANCE_API_KEY and BINANCE_SECRET):
        sys.exit("Live trading needs your Binance API key and secret in backend/.env.")

    from backtest.gate import evaluate_gate
    print("  Checking the strategy gate (365-day backtest)...")
    gate = evaluate_gate()
    bot_state["gate"] = gate
    if not gate["passed"]:
        sys.exit(f"Live trading is locked. It needs a {gate['rule']}; the current strategy has "
                 f"Sharpe {gate['sharpe']} over {gate['trades']} trades. "
                 "Set PAPER_MODE=true in backend/.env to keep paper trading.")

    from executor.orders import account_problem
    problem = account_problem()
    if problem:
        sys.exit(f"Live trading can't start: {problem}")
    print(f"  [OK] LIVE trading on Binance spot, capped at {MAX_CAPITAL_USDT:,.2f} USDT")


def main() -> None:
    print("\n" + "=" * 56)
    print("  TradBot starting up")
    print("=" * 56)

    if PAPER_MODE:
        print("  [OK] PAPER trading (simulated fills, no real orders)")
    else:
        _live_preflight()

    # Ensure all DB tables exist
    init_db()
    print("  [OK] Database ready")

    # Start the hourly pipeline scheduler (runs in background thread)
    scheduler = create_scheduler()
    scheduler.start()
    print("  [OK] Scheduler started - first pipeline run beginning now")
    print("  [OK] Dashboard API -> http://localhost:8000")
    print("  [OK] React dashboard -> cd frontend && npm run dev")
    print("=" * 56 + "\n")

    # Block on the FastAPI server
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="warning")


if __name__ == "__main__":
    main()
