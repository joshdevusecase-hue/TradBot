"""A ccxt.binance with Binance's real public market rules but simulated private (account/order)
endpoints, so live-trading code can be exercised without any real order or real key."""
import ccxt


class FakeBinance(ccxt.binance):
    FEE = 0.001

    def __init__(self):
        super().__init__({"enableRateLimit": True, "options": {
            "defaultType": "spot", "fetchCurrencies": False,
            "fetchMarkets": {"types": ["spot"]}, "fetchMargins": False}})
        self.load_markets()
        self.reset()

    def reset(self, usdt=1000.0, price=80_000.0):
        self.price = price
        self.bal = {"USDT": usdt, "BTC": 0.0}
        self.orders, self.fills, self.lists = {}, {}, {}
        self.seq = 1000
        self.fail_oco = False
        self.fill_on_cancel = None
        self.log = []

    def _new_id(self):
        self.seq += 1
        return self.seq

    # ── private endpoints the bot calls ────────────────────────────────────
    def private_get_account(self, params={}):
        return {"canTrade": True,
                "balances": [{"asset": a, "free": f"{v:.8f}", "locked": "0"} for a, v in self.bal.items()]}

    def sapi_get_account_apirestrictions(self, params={}):
        return {"ipRestrict": False, "enableSpotAndMarginTrading": True, "enableWithdrawals": False}

    def private_post_order_test(self, params):
        self.log.append(("test-order", params))
        return {}

    def private_post_order(self, params):
        self.log.append(("order", params["side"], params["quantity"]))
        qty, px, oid = float(params["quantity"]), self.price, self._new_id()
        if params["side"] == "BUY":
            if qty * px > self.bal["USDT"] + 1e-9:
                raise ccxt.InsufficientFunds("binance Account has insufficient balance for requested action.")
            fee, asset = qty * self.FEE, "BTC"
            self.bal["USDT"] -= qty * px
            self.bal["BTC"] += qty - fee
        else:
            if qty > self.bal["BTC"] + 1e-12:
                raise ccxt.InsufficientFunds("binance Account has insufficient balance for requested action.")
            fee, asset = qty * px * self.FEE, "USDT"
            self.bal["BTC"] -= qty
            self.bal["USDT"] += qty * px - fee
        fills = [{"price": f"{px:.2f}", "qty": f"{qty:.8f}", "commission": f"{fee:.8f}", "commissionAsset": asset}]
        order = {"orderId": oid, "status": "FILLED", "type": "MARKET", "side": params["side"],
                 "origQty": params["quantity"], "executedQty": f"{qty:.8f}",
                 "cummulativeQuoteQty": f"{qty * px:.8f}", "fills": fills}
        self.orders[oid], self.fills[oid] = order, fills
        return order

    def private_post_orderlist_oco(self, params):
        self.log.append(("oco", params))
        if self.fail_oco:
            raise ccxt.InvalidOrder('binance {"code":-2010,"msg":"Order would trigger immediately."}')
        qty = float(params["quantity"])
        if qty > self.bal["BTC"] + 1e-12:
            raise ccxt.InsufficientFunds("binance Account has insufficient balance for requested action.")
        self.bal["BTC"] -= qty  # both legs share one locked quantity
        tp, sl, lid = self._new_id(), self._new_id(), self._new_id()
        base = {"side": "SELL", "origQty": params["quantity"], "executedQty": "0",
                "cummulativeQuoteQty": "0", "status": "NEW"}
        self.orders[tp] = {**base, "orderId": tp, "type": params["aboveType"], "price": params["abovePrice"]}
        self.orders[sl] = {**base, "orderId": sl, "type": params["belowType"], "stopPrice": params["belowStopPrice"]}
        self.lists[lid] = (tp, sl)
        return {"orderListId": lid, "listOrderStatus": "EXECUTING", "orders": [{"orderId": tp}, {"orderId": sl}]}

    def private_get_orderlist(self, params):
        tp, sl = self.lists[int(params["orderListId"])]
        return {"orderListId": int(params["orderListId"]), "orders": [{"orderId": tp}, {"orderId": sl}]}

    def private_get_order(self, params):
        return dict(self.orders[int(params["orderId"])])

    def private_get_mytrades(self, params):
        return list(self.fills.get(int(params["orderId"]), []))

    def private_delete_order(self, params):
        self.log.append(("cancel", params["orderId"]))
        oid = int(params["orderId"])
        lid = next(l for l, ids in self.lists.items() if oid in ids)
        if self.fill_on_cancel == lid:  # the target fills a moment before the cancel arrives
            self.fill_leg(lid, "tp")
            self.fill_on_cancel = None
        if self.orders[oid]["status"] not in ("NEW", "PARTIALLY_FILLED"):
            raise ccxt.OrderNotFound('binance {"code":-2011,"msg":"Unknown order sent."}')
        self.cancel_list(lid)
        return {}

    # ── what Binance does on its own (test controls) ───────────────────────
    def fill_leg(self, lid, which, fraction=1.0):
        tp, sl = self.lists[lid]
        leg, other = (self.orders[tp], self.orders[sl]) if which == "tp" else (self.orders[sl], self.orders[tp])
        qty = float(leg["origQty"]) * fraction
        px = float(leg.get("price") or leg["stopPrice"])
        fee = qty * px * self.FEE
        leg.update(executedQty=f"{qty:.8f}", cummulativeQuoteQty=f"{qty * px:.8f}",
                   status="FILLED" if fraction >= 1 else "PARTIALLY_FILLED")
        self.bal["USDT"] += qty * px - fee
        self.fills[leg["orderId"]] = [{"price": f"{px:.2f}", "qty": f"{qty:.8f}",
                                       "commission": f"{fee:.8f}", "commissionAsset": "USDT"}]
        if other["status"] == "NEW":
            other["status"] = "CANCELED"  # OCO: a fill on one leg cancels the other

    def cancel_list(self, lid):
        legs = [self.orders[i] for i in self.lists[lid]]
        working = [leg for leg in legs if leg["status"] in ("NEW", "PARTIALLY_FILLED")]
        self.bal["BTC"] += max((float(leg["origQty"]) - float(leg["executedQty"]) for leg in working), default=0.0)
        for leg in working:
            leg["status"] = "CANCELED"
