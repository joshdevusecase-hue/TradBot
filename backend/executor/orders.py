"""
Live trading on the user's real Binance spot account (PAPER_MODE=false only). main.py keeps it
locked until the cap, keys, account and strategy gate check out.

Each trade is a market buy sized within MAX_CAPITAL_USDT, followed at once by an OCO sell that
Binance holds (take-profit limit above, stop-loss below), so the position stays protected while
the PC is off. The hourly check records what those orders did, sells anything left without a
working stop, and makes the 23-hour exit. Same interface as executor/paper.py.
"""
import logging

import ccxt

from strategy.signals import Signal
from tracker.trades import open_trade, close_trade, get_open_trade, set_exit_order
from risk.manager import size_position, stop_loss_price, take_profit_price, should_time_exit
from data.fetcher import get_exchange
from config.settings import SYMBOL, MAX_CAPITAL_USDT

logger = logging.getLogger("tradbot.live")

MODE = "live"
_WORKING = ("NEW", "PARTIALLY_FILLED")
_STOP_TYPES = ("STOP_LOSS", "STOP_LOSS_LIMIT")
# Only for markets without market-stop orders: a limit 0.5% under the stop still fills in a fast drop.
_STOP_LIMIT_BUFFER = 0.005


def _market() -> tuple[ccxt.binance, dict]:
    ex = get_exchange()
    ex.load_markets()
    return ex, ex.market(SYMBOL)


def _step(ex: ccxt.binance, qty: float) -> str | None:
    """qty truncated to Binance's lot step, or None when that leaves nothing."""
    try:
        return ex.amount_to_precision(SYMBOL, qty)
    except ccxt.InvalidOrder:
        return None


def _price(ex: ccxt.binance, price: float) -> str:
    return ex.price_to_precision(SYMBOL, price)


def _min_cost(m: dict) -> float:
    return m["limits"]["cost"]["min"] or 0.0


def _fees(fills: list[dict]) -> dict[str, float]:
    """Commission per asset from an order's fills or its account trades."""
    out: dict[str, float] = {}
    for f in fills:
        out[f["commissionAsset"]] = out.get(f["commissionAsset"], 0.0) + float(f["commission"])
    return out


def free_balance(ex: ccxt.binance, asset: str) -> float:
    for b in ex.private_get_account()["balances"]:
        if b["asset"] == asset:
            return float(b["free"])
    return 0.0


def account_problem() -> str | None:
    """Why this account can't trade spot right now, or None."""
    ex, _ = _market()
    try:
        account = ex.private_get_account()
    except (ccxt.AuthenticationError, ccxt.PermissionDenied) as e:
        return f"Binance rejected the API key ({e})"
    if not account.get("canTrade"):
        return "the account or API key isn't allowed to trade spot (enable Spot & Margin Trading on the key)"
    return None


def _sell_market(ex: ccxt.binance, m: dict, qty: float, price: float) -> tuple[float, float]:
    """Market-sell qty. Returns (BTC sold, USDT received net of USDT fees); (0, 0) for dust under Binance's minimum."""
    amount = _step(ex, qty)
    if amount is None or float(amount) * price < _min_cost(m):
        return 0.0, 0.0
    resp = ex.private_post_order({"symbol": m["id"], "side": "SELL", "type": "MARKET",
                                  "quantity": amount, "newOrderRespType": "FULL"})
    fees = _fees(resp.get("fills", []))
    return float(resp["executedQty"]), float(resp["cummulativeQuoteQty"]) - fees.get(m["quoteId"], 0.0)


def _place_oco(ex: ccxt.binance, m: dict, qty: str, sl: float, tp: float) -> dict:
    """Sell qty at the take-profit (resting limit) or the stop-loss, whichever Binance reaches first."""
    if "STOP_LOSS" in m["info"].get("orderTypes", []):
        below = {"belowType": "STOP_LOSS", "belowStopPrice": _price(ex, sl)}
    else:
        below = {"belowType": "STOP_LOSS_LIMIT", "belowStopPrice": _price(ex, sl),
                 "belowPrice": _price(ex, sl * (1 - _STOP_LIMIT_BUFFER)), "belowTimeInForce": "GTC"}
    return ex.private_post_orderlist_oco({
        "symbol": m["id"], "side": "SELL", "quantity": qty,
        "aboveType": "LIMIT_MAKER", "abovePrice": _price(ex, tp),
        **below,
    })


def enter(signal: Signal, current_price: float) -> int | None:
    """Buy with at most MAX_CAPITAL_USDT, then protect the position with an OCO sell on Binance."""
    ex, m = _market()
    capital = min(MAX_CAPITAL_USDT, free_balance(ex, m["quoteId"]))
    amount = _step(ex, size_position(current_price, signal.atr, capital))
    if amount is None or float(amount) * current_price < _min_cost(m):
        logger.warning(f"[LIVE] Buy skipped: {capital:,.2f} USDT available under the cap is below Binance's minimum order")
        return None

    buy = ex.private_post_order({"symbol": m["id"], "side": "BUY", "type": "MARKET",
                                 "quantity": amount, "newOrderRespType": "FULL"})
    filled, spent = float(buy["executedQty"]), float(buy["cummulativeQuoteQty"])
    if filled <= 0:
        logger.error(f"[LIVE] Market buy {buy.get('orderId')} filled nothing (status {buy.get('status')})")
        return None
    fees = _fees(buy.get("fills", []))
    # Binance takes the buy fee out of the BTC received unless fees are paid in BNB.
    held = _step(ex, filled - fees.get(m["baseId"], 0.0))
    avg = spent / filled
    sl = float(_price(ex, stop_loss_price(avg, signal.atr, "LONG")))
    tp = float(_price(ex, take_profit_price(avg, signal.atr, "LONG")))

    # Record the position before placing its protection, so a crash in between still leaves a
    # trade the hourly check will find (and sell, since it has no stop).
    trade_id = open_trade(
        symbol=SYMBOL, direction="LONG", entry_price=avg, quantity=float(held or 0), sl_price=sl,
        tp_price=tp, signal_reason=signal.reason, mode=MODE,
        entry_cost=spent + fees.get(m["quoteId"], 0.0), entry_order_id=str(buy["orderId"]),
    )
    logger.info(f"[LIVE] Bought {filled} BTC at {avg:,.2f} for {spent:,.2f} USDT (order {buy['orderId']}), trade #{trade_id}")

    try:
        oco = _place_oco(ex, m, held, sl, tp)
    except Exception:
        logger.exception(f"[LIVE] Couldn't place the stop-loss/take-profit for trade #{trade_id}; selling at market")
        _settle(ex, m, get_open_trade(SYMBOL, MODE), current_price, [], "Protection failed")
        return trade_id
    set_exit_order(trade_id, str(oco["orderListId"]))
    logger.info(f"[LIVE] Trade #{trade_id} protected on Binance: stop {sl:,.2f}, target {tp:,.2f} (OCO {oco['orderListId']})")
    return trade_id


def _legs(ex: ccxt.binance, m: dict, list_id: str | None) -> list[dict]:
    """Current state of the trade's OCO orders on Binance."""
    if not list_id:
        return []
    order_list = ex.private_get_orderlist({"orderListId": list_id})
    return [ex.private_get_order({"symbol": m["id"], "orderId": o["orderId"]}) for o in order_list["orders"]]


def _received(ex: ccxt.binance, m: dict, legs: list[dict]) -> tuple[float, float]:
    """(BTC sold, USDT received net of USDT fees) across the legs that traded."""
    sold = received = 0.0
    for leg in legs:
        qty = float(leg["executedQty"])
        if qty > 0:
            fees = _fees(ex.private_get_mytrades({"symbol": m["id"], "orderId": leg["orderId"]}))
            sold += qty
            received += float(leg["cummulativeQuoteQty"]) - fees.get(m["quoteId"], 0.0)
    return sold, received


def _leg_reason(legs: list[dict]) -> str:
    traded = [leg for leg in legs if float(leg["executedQty"]) > 0]
    if not traded:
        return "Stop-loss order missing"
    top = max(traded, key=lambda leg: float(leg["executedQty"]))
    return "Take profit" if top["type"] == "LIMIT_MAKER" else "Stop loss"


def check_exits(current_price: float) -> bool:
    """Record what Binance's orders did for the open live trade, and sell what's left once it has
    no working stop or its time is up. Returns True if the trade closed."""
    trade = get_open_trade(SYMBOL, MODE)
    if trade is None:
        return False
    ex, m = _market()
    legs = _legs(ex, m, trade.exit_order_id)
    sold = sum(float(leg["executedQty"]) for leg in legs)
    protected = any(leg["status"] in _WORKING and leg["type"] in _STOP_TYPES for leg in legs)
    time_up = should_time_exit(trade.entry_time)
    if _step(ex, trade.quantity - sold) is not None and protected and not time_up:
        return False  # Binance still holds the stop and target

    reason = "Time exit" if time_up else ("Take profit (partial)" if sold > 0 else "Stop-loss order missing")
    _settle(ex, m, trade, current_price, legs, reason)
    return True


def _settle(ex: ccxt.binance, m: dict, trade, price: float, legs: list[dict], reason: str) -> None:
    """Cancel any working exit orders, market-sell what the bot still holds, and record the trade."""
    working = [leg for leg in legs if leg["status"] in _WORKING]
    for leg in working:  # cancelling one leg of an OCO cancels the pair
        try:
            ex.private_delete_order({"symbol": m["id"], "orderId": leg["orderId"]})
        except ccxt.BaseError as e:
            logger.warning(f"[LIVE] Cancel of order {leg['orderId']} failed ({e}); it may have just filled")
    if working:
        legs = _legs(ex, m, trade.exit_order_id)

    sold, received = _received(ex, m, legs)
    if _step(ex, trade.quantity - sold) is None:
        reason = _leg_reason(legs)  # the exchange orders finished the job after all
    else:
        more_sold, more_received = _sell_market(ex, m, trade.quantity - sold, price)
        sold, received = sold + more_sold, received + more_received

    unsold = max(trade.quantity - sold, 0.0)  # dust under Binance's minimum order stays in the account
    close_trade(trade.id, received / sold if sold else price, reason, proceeds=received + unsold * price)
    logger.info(f"[LIVE] Closed trade #{trade.id} ({reason}): sold {sold} BTC for {received:,.2f} USDT")
