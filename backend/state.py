from config.settings import PAPER_MODE, TRADE_MODE

# Shared in-process state updated by the scheduler and read by the API.
# Thread-safe for simple dict reads/writes under Python's GIL.
bot_state: dict = {
    "running": False,
    "last_run": None,
    "last_signal": "FLAT",
    "last_signal_reason": "Bot just started — waiting for first hourly run",
    "paper_mode": PAPER_MODE,
    "trade_mode": TRADE_MODE,
    "gate": None,  # latest backtest/gate.evaluate_gate() result
}
