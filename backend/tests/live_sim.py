"""
Live-trading scenarios against a simulated Binance (real market rules, faked account and orders).
Run from the TradBot folder:  python backend/tests/live_sim.py
Uses a throwaway database and dummy keys; it can't reach a real account or place a real order.
"""
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone

# Dummy keys and paper mode for this process (env vars win over backend/.env).
os.environ.update({"PAPER_MODE": "true", "BINANCE_API_KEY": "dummy", "BINANCE_SECRET": "dummy",
                   "MAX_CAPITAL_USDT": "500"})
sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.dirname(HERE), HERE]

import logging
logging.basicConfig(level=logging.CRITICAL)

import config.settings as settings
settings.DB_PATH = os.path.join(tempfile.mkdtemp(), "live.db")

from sqlalchemy.orm import Session
from db import init_db, engine, Trade
import executor.orders as live
import scheduler
import strategy.signals as signals
from state import bot_state
from strategy.signals import Signal
from tracker.trades import open_trade
from fake_binance import FakeBinance

init_db()
fake = FakeBinance()
live.get_exchange = lambda: fake
SIG = Signal("LONG", "test signal", atr=300.0)
results = []


def check(name, ok, detail=""):
    results.append(ok)
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f" — {detail}" if detail else ""))


def trade(tid):
    with Session(engine) as s:
        t = s.get(Trade, tid)
        s.expunge(t)
        return t


def backdate(tid, delta):
    with Session(engine) as s:
        s.get(Trade, tid).entry_time = datetime.now(timezone.utc) - delta
        s.commit()


def orders_after_buy():
    return [e for e in fake.log[1:] if e[0] == "order"]


# A. Buy within the cap, protected by an OCO on the BTC actually received
fake.reset()
tid = live.enter(SIG, fake.price)
t = trade(tid)
oco = next(e[1] for e in fake.log if e[0] == "oco")
spent = float(fake.orders[int(t.entry_order_id)]["cummulativeQuoteQty"])
check("A  buy stays within the 500 USDT cap", spent <= 500, f"spent {spent:.2f} of 1,000 USDT free")
check("A  OCO sells the BTC received after the fee", oco["quantity"] == "0.00592" and t.quantity == 0.00592,
      f"bought 0.00593, fee 0.00000593 BTC, protecting {oco['quantity']}")
check("A  OCO is a take-profit limit above and a market stop below",
      oco["aboveType"] == "LIMIT_MAKER" and float(oco["abovePrice"]) == 80750
      and oco["belowType"] == "STOP_LOSS" and float(oco["belowStopPrice"]) == 79550,
      f"target {oco['abovePrice']}, stop {oco['belowStopPrice']}")
check("A  trade recorded as live with its Binance order ids",
      t.mode == "live" and t.entry_order_id and t.exit_order_id and abs(t.entry_cost - 474.40) < 1e-6)

# B. Hourly check while Binance still holds both orders
check("B  nothing to do while the stop and target are working",
      live.check_exits(fake.price) is False and trade(tid).exit_price is None and not orders_after_buy())

# C. Target fills on Binance
fake.fill_leg(int(t.exit_order_id), "tp")
live.check_exits(fake.price)
t = trade(tid)
want = round(0.00592 * 80750 * 0.999 - 474.40, 2)
check("C  target filled -> Take profit, P&L from real fills", t.exit_reason == "Take profit" and t.pnl == want,
      f"P&L {t.pnl} (expected {want}), no extra orders: {not orders_after_buy()}")

# D. Stop fills on Binance
fake.reset()
tid = live.enter(SIG, fake.price)
fake.fill_leg(int(trade(tid).exit_order_id), "sl")
live.check_exits(fake.price)
t = trade(tid)
want = round(0.00592 * 79550 * 0.999 - 474.40, 2)
check("D  stop filled -> Stop loss", t.exit_reason == "Stop loss" and t.pnl == want, f"P&L {t.pnl} (expected {want})")

# E. 23-hour exit: cancel the pair, sell at market
fake.reset()
tid = live.enter(SIG, fake.price)
backdate(tid, timedelta(hours=22, minutes=59, seconds=55))
fake.price = 80_200.0
live.check_exits(fake.price)
t = trade(tid)
check("E  time up -> orders cancelled, BTC sold at market", t.exit_reason == "Time exit"
      and any(e[0] == "cancel" for e in fake.log) and orders_after_buy() == [("order", "SELL", "0.00592")],
      f"BTC left {fake.bal['BTC']:.8f} (dust), P&L {t.pnl}")

# F. Target only partly fills; Binance cancels the stop; the rest must not sit unprotected
fake.reset()
tid = live.enter(SIG, fake.price)
fake.fill_leg(int(trade(tid).exit_order_id), "tp", fraction=0.4)
live.check_exits(fake.price)
t = trade(tid)
check("F  partial target -> remainder cancelled and sold", t.exit_reason == "Take profit (partial)"
      and orders_after_buy() == [("order", "SELL", "0.00355")], f"BTC left {fake.bal['BTC']:.8f}, P&L {t.pnl}")

# G. Both orders cancelled by hand on Binance
fake.reset()
tid = live.enter(SIG, fake.price)
fake.cancel_list(int(trade(tid).exit_order_id))
live.check_exits(fake.price)
t = trade(tid)
check("G  protection cancelled outside the bot -> sold at market", t.exit_reason == "Stop-loss order missing"
      and orders_after_buy() == [("order", "SELL", "0.00592")])

# H. Binance rejects the OCO right after the buy
fake.reset()
fake.fail_oco = True
tid = live.enter(SIG, fake.price)
t = trade(tid)
check("H  OCO rejected -> position sold immediately", t.exit_reason == "Protection failed"
      and orders_after_buy() == [("order", "SELL", "0.00592")] and fake.bal["BTC"] < 0.00001,
      f"P&L {t.pnl} (two fees)")

# I. Cap too small for Binance's minimum order
fake.reset()
live.MAX_CAPITAL_USDT = 3.0
check("I  3 USDT cap -> no order at all", live.enter(SIG, fake.price) is None and not fake.log)
live.MAX_CAPITAL_USDT = 500.0

# J. The target fills in the same moment the bot cancels for the time exit
fake.reset()
tid = live.enter(SIG, fake.price)
backdate(tid, timedelta(hours=23))
fake.fill_on_cancel = int(trade(tid).exit_order_id)
live.check_exits(fake.price)
t = trade(tid)
check("J  fill races the cancel -> recorded as Take profit, no extra sell",
      t.exit_reason == "Take profit" and not orders_after_buy())

# K. Crash between the buy and the OCO: open trade with no protection
fake.reset()
buy = fake.private_post_order({"symbol": "BTCUSDT", "side": "BUY", "type": "MARKET", "quantity": "0.00593"})
fake.log.clear()
tid = open_trade("BTC/USDT", "LONG", 80_000.0, 0.00592, 79_550.0, 80_750.0, "crash test", mode="live",
                 entry_cost=474.40, entry_order_id=str(buy["orderId"]))
live.check_exits(fake.price)
t = trade(tid)
check("K  unprotected trade after a crash -> sold on the next check",
      t.exit_reason == "Stop-loss order missing" and fake.log == [("order", "SELL", "0.00592")])

# L. Scheduler in live mode: a locked gate blocks buys but still manages exits
scheduler.PAPER_MODE, scheduler.TRADE_MODE = False, "live"
real_generate = signals.generate_signal
signals.generate_signal = lambda df: Signal("LONG", "forced test", atr=real_generate(df).atr or 300.0)
import data.fetcher as fetcher
fake.reset(price=float(fetcher.fetch_ticker()["last"]))
bot_state["gate"] = {"passed": False, "sharpe": -1.2, "trades": 30}
scheduler.run_pipeline()
check("L  gate locked -> buy signal skipped, no order", not fake.log and "locked" in bot_state["last_signal_reason"],
      bot_state["last_signal_reason"][-60:])
bot_state["gate"] = {"passed": True, "sharpe": 1.4, "trades": 30}
scheduler.run_pipeline()
check("L  gate passed -> live buy + OCO placed", [e[0] for e in fake.log] == ["order", "oco"],
      f"{len(fake.log)} Binance calls: {[e[0] for e in fake.log]}")
signals.generate_signal = real_generate

print(f"\n{sum(results)}/{len(results)} checks passed")
sys.exit(0 if all(results) else 1)
