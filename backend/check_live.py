"""
Live-trading readiness check. After putting your Binance API key, secret and MAX_CAPITAL_USDT in
backend/.env, run it from the TradBot folder:

    python backend/check_live.py

It reads your account and asks Binance to validate (not execute) a sample buy. It never places
an order and never prints your keys.
"""
import sys

import ccxt

from config.settings import BINANCE_API_KEY, BINANCE_SECRET, MAX_CAPITAL_USDT, PAPER_MODE, SYMBOL
from data.fetcher import build_exchange


def main() -> int:
    problems = 0

    def report(ok: bool, text: str) -> None:
        nonlocal problems
        problems += 0 if ok else 1
        print(f"  [{'OK' if ok else '!!'}] {text}")

    print("TradBot live-trading check (read-only: no orders are placed)\n")
    has_keys = bool(BINANCE_API_KEY and BINANCE_SECRET)
    report(has_keys, "API key and secret are set in backend/.env" if has_keys
           else "BINANCE_API_KEY / BINANCE_SECRET missing from backend/.env")
    report(MAX_CAPITAL_USDT > 0, f"Spending cap MAX_CAPITAL_USDT = {MAX_CAPITAL_USDT:,.2f} USDT" if MAX_CAPITAL_USDT > 0
           else "MAX_CAPITAL_USDT missing from backend/.env (the most USDT the bot may use)")
    if not has_keys:
        return 1

    ex = build_exchange(with_keys=True)
    try:
        ex.load_markets()
        m = ex.market(SYMBOL)
        account = ex.private_get_account()
    except (ccxt.AuthenticationError, ccxt.PermissionDenied) as e:
        report(False, f"Binance rejected the key: {e}")
        return 1
    except ccxt.BaseError as e:
        report(False, f"Couldn't reach Binance: {e}")
        return 1
    report(bool(account.get("canTrade")), "Account can trade spot")
    free = {b["asset"]: float(b["free"]) for b in account["balances"]}
    usdt, btc = free.get(m["quoteId"], 0.0), free.get(m["baseId"], 0.0)
    capital = min(MAX_CAPITAL_USDT, usdt)
    report(capital >= m["limits"]["cost"]["min"],
           f"Free balance {usdt:,.2f} USDT and {btc:.8f} BTC; the bot can use up to {capital:,.2f} USDT")

    try:
        rules = ex.sapi_get_account_apirestrictions()
        report(bool(rules.get("enableSpotAndMarginTrading")), "Key allows Spot & Margin Trading")
        report(not rules.get("enableWithdrawals"), "Key has withdrawals turned off")
        print(f"       IP restriction: {'on' if rules.get('ipRestrict') else 'off (restricting the key to your IP is safer)'}")
    except ccxt.BaseError as e:
        print(f"  [??] Couldn't read the key's permissions: {e}")

    types = m["info"].get("orderTypes", [])
    report(bool(m["info"].get("ocoAllowed")) and "LIMIT_MAKER" in types,
           f"{SYMBOL} allows the stop-loss/take-profit pair (OCO); stop type "
           f"{'STOP_LOSS (market)' if 'STOP_LOSS' in types else 'STOP_LOSS_LIMIT'}")

    price = ex.fetch_ticker(SYMBOL)["last"]
    amount = ex.amount_to_precision(SYMBOL, m["limits"]["cost"]["min"] * 2 / price)
    try:
        ex.private_post_order_test({"symbol": m["id"], "side": "BUY", "type": "MARKET", "quantity": amount})
        report(True, f"Binance accepted a test buy of {amount} BTC (validated only, nothing bought)")
    except ccxt.BaseError as e:
        report(False, f"Binance rejected a test buy of {amount} BTC: {e}")

    from backtest.gate import evaluate_gate
    print("       Running the strategy gate (365-day backtest)...")
    gate = evaluate_gate()
    report(gate["passed"], f"Strategy gate: Sharpe {gate['sharpe']} over {gate['trades']} trades "
                           f"(needs a {gate['rule']})")

    print()
    if problems:
        print(f"Not ready: {problems} item(s) marked !! above. Live trading stays locked until they pass.")
    elif PAPER_MODE:
        print("Ready. Set PAPER_MODE=false in backend/.env and restart the bot to trade live.")
    else:
        print("Ready: the bot trades live the next time you start it.")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
