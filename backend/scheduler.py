import logging
from datetime import datetime, timezone
from apscheduler.schedulers.background import BackgroundScheduler
from config.settings import SYMBOL, PAPER_MODE, TRADE_MODE
from state import bot_state

logger = logging.getLogger("tradbot.scheduler")


def run_pipeline() -> None:
    bot_state["running"] = True
    bot_state["last_run"] = datetime.now(tz=timezone.utc).isoformat()

    try:
        from data.fetcher import fetch_ohlcv, fetch_ticker, closed_candles
        from data.cache import upsert_candles, load_candles
        from strategy.indicators import compute_indicators
        from strategy.signals import generate_signal
        from tracker.trades import get_open_trade

        # 1. Fetch + cache candles
        df_fresh = fetch_ohlcv()
        upsert_candles(df_fresh)
        df = closed_candles(load_candles())

        if df.empty or len(df) < 50:
            logger.warning("Not enough candles yet — waiting for more data.")
            return

        # 2. Indicators
        df = compute_indicators(df)

        # 3. Signal
        signal = generate_signal(df)
        bot_state["last_signal"] = signal.direction
        bot_state["last_signal_reason"] = signal.reason
        logger.info(f"Signal: {signal.direction} — {signal.reason}")

        # 4. Resolve executor based on mode
        executor = __import__("executor.paper", fromlist=["enter", "check_exits"]) \
                   if PAPER_MODE else \
                   __import__("executor.orders", fromlist=["enter", "check_exits"])

        # 5. Current price
        ticker = fetch_ticker(SYMBOL)
        current_price: float = ticker["last"]

        # 6. Check exits on any open position first (always, even while live buys are locked)
        closed = executor.check_exits(current_price)

        # 7. Open new position if signal fired and no open trade
        if not closed and signal.direction == "LONG" and signal.atr > 0:
            if not PAPER_MODE and not (bot_state.get("gate") or {}).get("passed"):
                bot_state["last_signal_reason"] = f"{signal.reason} — not bought: the strategy gate has locked live buys"
                logger.warning("Buy signal skipped: the strategy gate has locked live buys")
            elif get_open_trade(SYMBOL, TRADE_MODE) is None:
                executor.enter(signal, current_price)

    except Exception:
        logger.exception("Pipeline error")
    finally:
        bot_state["running"] = False


def refresh_gate() -> None:
    """Re-run the strategy gate; a failed check locks live buys until the next one passes."""
    try:
        from backtest.gate import evaluate_gate
        bot_state["gate"] = evaluate_gate()
    except Exception:
        logger.exception("Strategy gate check failed; live buys stay locked until the next check")
        bot_state["gate"] = {**(bot_state.get("gate") or {}), "passed": False}
    gate = bot_state["gate"]
    logger.info(f"Strategy gate {'passed' if gate.get('passed') else 'locked'}: "
                f"Sharpe {gate.get('sharpe')}, {gate.get('trades')} trades")


def create_scheduler() -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone="UTC")
    # Binance's hourly candles close on the UTC hour; judge each one 30s after it closes,
    # the same close-price entry the backtest assumes.
    scheduler.add_job(
        run_pipeline,
        trigger="cron",
        minute=0,
        second=30,
        id="pipeline",
        next_run_time=datetime.now(tz=timezone.utc),  # run immediately on startup
    )
    # Daily gate re-check. Live mode already checked it before starting (main.py); paper mode
    # checks once at startup too, so the dashboard can show whether live trading would unlock.
    first_gate_run = {"next_run_time": datetime.now(tz=timezone.utc)} if PAPER_MODE else {}
    scheduler.add_job(refresh_gate, trigger="cron", hour=0, minute=5, id="gate", **first_gate_run)
    return scheduler
