import logging
import uvicorn
from db import init_db
from scheduler import create_scheduler
from dashboard.app import app  # noqa: F401 — imported for uvicorn

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)


def main() -> None:
    print("\n" + "═" * 56)
    print("  TradBot starting up")
    print("═" * 56)

    # Ensure all DB tables exist
    init_db()
    print("  ✓ Database ready")

    # Start the hourly pipeline scheduler (runs in background thread)
    scheduler = create_scheduler()
    scheduler.start()
    print("  ✓ Scheduler started — first pipeline run beginning now")
    print("  ✓ Dashboard API → http://localhost:8000")
    print("  ✓ React dashboard → cd frontend && npm run dev")
    print("═" * 56 + "\n")

    # Block on the FastAPI server
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="warning")


if __name__ == "__main__":
    main()
