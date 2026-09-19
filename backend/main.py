import logging
import sys
import uvicorn
from config.settings import PAPER_MODE
from db import init_db
from scheduler import create_scheduler
from dashboard.app import app  # noqa: F401 — imported for uvicorn

# Piped or redirected output on Windows defaults to cp1252, which can't encode signal text like "≥".
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)


def main() -> None:
    if not PAPER_MODE:
        # executor/orders.py has no spending cap or exchange-side stops yet (PLAN.md Phase 9).
        sys.exit("PAPER_MODE=false, but live trading isn't built yet (PLAN.md Phase 9). "
                 "Set PAPER_MODE=true in backend/.env to run the bot on paper.")

    print("\n" + "=" * 56)
    print("  TradBot starting up")
    print("=" * 56)

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
