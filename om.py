"""Order Manager (om.py) - Buy/Sell strategy, order placement, trade tracking"""
import json
from pathlib import Path
from datetime import datetime

import upstox_client
from upstox_client.rest import ApiException


# ==================== CONFIGURATION ====================

TRADES_FILE = Path(__file__).parent / "trades.json"
MAX_BUYS = 3
DAYS_GAP = 7
RSI_THRESHOLD = 25
FUND_PERCENT = 0.10
PROFIT_TARGET = 0.04  # 4% profit to sell


# ==================== TRADE STORAGE ====================

def load_trades() -> dict:
    return json.loads(TRADES_FILE.read_text()) if TRADES_FILE.exists() else {}

def save_trades(trades: dict):
    TRADES_FILE.write_text(json.dumps(trades, indent=2))


class OrderManager:
    """Manages orders, trades, and strategy execution"""
    
    def __init__(self, access_token: str, portfolio, market, cache):
        self.token = access_token
        self.portfolio = portfolio
        self.market = market
        self.cache = cache
        self._api = None
    
    @property
    def api(self):
        if not self._api:
            cfg = upstox_client.Configuration()
            cfg.access_token = self.token
            self._api = upstox_client.OrderApi(upstox_client.ApiClient(cfg))
        return self._api
    
    # -------------------- Sync --------------------
    
    def sync_trades(self):
        """Sync trades.json with order book + portfolio. Remove invalid orders."""
        t = load_trades()
        if not t: return
        
        try:
            # Get order statuses
            resp = self.api.get_order_book(api_version='2.0')
            orders = {o.order_id: o.status.lower() for o in resp.data} if resp.status=='success' and resp.data else {}
            
            # Get owned stocks
            owned = {getattr(h,'isin','') for h in self.portfolio.get_holdings()}
            owned |= {getattr(p,'isin','') for p in self.portfolio.get_positions()}
            
            invalid = ["cancelled", "rejected", "failed", "open", "pending"]
            changed = False
            
            for isin in list(t.keys()):
                valid = []
                for b in t[isin]["buys"]:
                    status = orders.get(b.get("order_id",""), "")
                    if any(kw in status for kw in invalid):
                        print(f"⚠️ Removing '{status}' order for {t[isin]['name']}")
                        changed = True
                    elif b.get("order_id") and not status and isin not in owned:
                        print(f"⚠️ Removing stale order for {t[isin]['name']}")
                        changed = True
                    else:
                        valid.append(b)
                
                if valid: t[isin]["buys"] = valid
                else: del t[isin]
            
            if changed: save_trades(t); print("✅ Synced")
        except ApiException: pass
    
    # -------------------- Orders --------------------
    
    def place_buy(self, isin: str, qty: int) -> str:
        """Place market buy order. Returns order_id or empty string."""
        try:
            req = upstox_client.PlaceOrderRequest(
                quantity=qty, product="D", validity="DAY", price=0,
                instrument_token=f"NSE_EQ|{isin}", order_type="MARKET",
                transaction_type="BUY", disclosed_quantity=0, trigger_price=0, is_amo=False
            )
            r = self.api.place_order(req, api_version='2.0')
            return r.data.order_id if r.status=='success' and r.data else ""
        except ApiException as e:
            print(f"Order failed: {e}")
            return ""
    
    def place_sell(self, isin: str, qty: int) -> str:
        """Place market sell order. Returns order_id or empty string."""
        try:
            req = upstox_client.PlaceOrderRequest(
                quantity=qty, product="D", validity="DAY", price=0,
                instrument_token=f"NSE_EQ|{isin}", order_type="MARKET",
                transaction_type="SELL", disclosed_quantity=0, trigger_price=0, is_amo=False
            )
            r = self.api.place_order(req, api_version='2.0')
            return r.data.order_id if r.status=='success' and r.data else ""
        except ApiException as e:
            print(f"Sell failed: {e}")
            return ""
    
    def record_buy(self, isin: str, name: str, qty: int, price: float, order_id: str):
        """Record buy in trades.json"""
        t = load_trades()
        if isin not in t: t[isin] = {"name": name, "buys": []}
        t[isin]["buys"].append({
            "date": datetime.now().strftime("%Y-%m-%d"),
            "qty": qty, "price": price, "order_id": order_id
        })
        save_trades(t)
    
    # -------------------- Strategy --------------------
    
    def can_buy(self, isin: str) -> tuple[bool, str]:
        """Check if we can buy. Returns (can_buy, reason)."""
        t = load_trades()
        if isin not in t: return True, "First buy"
        
        buys = t[isin]["buys"]
        if len(buys) >= MAX_BUYS: return False, f"Max {MAX_BUYS} buys"
        
        days = (datetime.now() - datetime.strptime(buys[-1]["date"], "%Y-%m-%d")).days
        if days < DAYS_GAP: return False, f"Wait {DAYS_GAP-days} more days"
        
        return True, f"Scale-in #{len(buys)+1}"
    
    def calc_qty(self, ltp: float) -> int:
        """Calculate quantity based on available funds."""
        avail = self.portfolio.get_funds()["available"]
        return max(int(avail * FUND_PERCENT / ltp), 1)
    
    def get_rsi(self, isin: str) -> float:
        """Get RSI for stock."""
        from sm import get_rsi
        return get_rsi(isin, self.cache)
    
    def check_and_buy(self, isin: str):
        """Main buy strategy: Check RSI < 25 and place order."""
        self.sync_trades()
        
        rsi = self.get_rsi(isin)
        print(f"RSI: {rsi}")
        
        if rsi >= RSI_THRESHOLD:
            print(f"RSI >= {RSI_THRESHOLD}, skip")
            return
        
        ok, reason = self.can_buy(isin)
        if not ok:
            print(f"Cannot buy: {reason}")
            return
        
        ltp = self.market.get_ltp(f"NSE_EQ|{isin}")
        qty = self.calc_qty(ltp)
        print(f"BUY {qty} @ ₹{ltp} ({reason})")
        
        oid = self.place_buy(isin, qty)
        if oid:
            from market_data import get_stock_name
            self.record_buy(isin, get_stock_name(isin), qty, ltp, oid)
            print(f"✅ Order: {oid}")
            return True
        else:
            print("❌ Failed")
            return False
    
    def scan_and_buy(self, watchlist: list) -> int:
        """Scan watchlist for buy signals. Returns count of orders placed."""
        self.sync_trades()
        bought = 0
        
        for isin in watchlist:
            rsi = self.get_rsi(isin)
            
            if rsi >= RSI_THRESHOLD:
                continue
            
            ok, reason = self.can_buy(isin)
            if not ok:
                continue
            
            ltp = self.market.get_ltp(f"NSE_EQ|{isin}")
            qty = self.calc_qty(ltp)
            
            from market_data import get_stock_name
            name = get_stock_name(isin)
            print(f"🟢 {name}: RSI={rsi}, BUY {qty} @ ₹{ltp}")
            
            oid = self.place_buy(isin, qty)
            if oid:
                self.record_buy(isin, name, qty, ltp, oid)
                print(f"   ✅ Order: {oid}")
                bought += 1
            else:
                print(f"   ❌ Failed")
        
        return bought
    
    def get_stock_profit(self, isin: str) -> dict:
        """Calculate profit using holdings/positions + trades.json for avg price."""
        # Check actual holdings
        holdings = self.portfolio.get_holdings()
        holding = next((h for h in holdings if getattr(h, 'isin', '') == isin), None)
        
        # Check positions (intraday)
        positions = self.portfolio.get_positions()
        position = next((p for p in positions if getattr(p, 'isin', '') == isin), None)
        
        # Get actual qty from portfolio
        actual_qty = 0
        avg_price = 0
        
        if holding:
            actual_qty = getattr(holding, 'quantity', 0)
            avg_price = getattr(holding, 'average_price', 0)
        elif position:
            actual_qty = getattr(position, 'quantity', 0)
            avg_price = getattr(position, 'average_price', 0)
        
        if actual_qty == 0:
            return {"invested": 0, "current": 0, "profit_pct": 0, "qty": 0, "ltp": 0, "in_portfolio": False}
        
        # Use trades.json avg price if available (more accurate for scale-in)
        t = load_trades()
        if isin in t and t[isin]["buys"]:
            buys = t[isin]["buys"]
            total_cost = sum(b["qty"] * b["price"] for b in buys)
            total_qty = sum(b["qty"] for b in buys)
            if total_qty > 0:
                avg_price = total_cost / total_qty
        
        ltp = self.market.get_ltp(f"NSE_EQ|{isin}")
        invested = avg_price * actual_qty
        current = ltp * actual_qty
        profit_pct = ((current - invested) / invested * 100) if invested > 0 else 0
        
        return {
            "invested": round(invested, 2),
            "current": round(current, 2),
            "profit_pct": round(profit_pct, 2),
            "qty": actual_qty,
            "avg_price": round(avg_price, 2),
            "ltp": ltp,
            "in_portfolio": True
        }
    
    def check_and_sell(self, isin: str):
        """Sell strategy: Sell when profit >= 4%. Checks actual holdings."""
        self.sync_trades()
        
        p = self.get_stock_profit(isin)
        
        if not p["in_portfolio"]:
            print(f"❌ {isin} not in holdings/positions")
            return
        
        print(f"Qty: {p['qty']} | Avg: ₹{p['avg_price']} | LTP: ₹{p['ltp']}")
        print(f"Invested: ₹{p['invested']} | Current: ₹{p['current']} | Profit: {p['profit_pct']}%")
        
        if p["profit_pct"] < PROFIT_TARGET * 100:
            print(f"Profit {p['profit_pct']}% < {PROFIT_TARGET*100}%, holding")
            return
        
        print(f"🎯 SELL {p['qty']} @ ₹{p['ltp']} (Profit: {p['profit_pct']}%)")
        
        oid = self.place_sell(isin, p["qty"])
        if oid:
            # Remove from trades.json after sell
            t = load_trades()
            if isin in t: del t[isin]
            save_trades(t)
            print(f"✅ Sold! Order: {oid}")
        else:
            print("❌ Sell failed")
    
    def scan_and_sell(self):
        """Scan ALL holdings/positions and sell any with profit >= 4%."""
        self.sync_trades()
        
        # Get all ISINs from holdings + positions
        holdings = self.portfolio.get_holdings()
        positions = self.portfolio.get_positions()
        
        all_isins = set()
        for h in holdings:
            isin = getattr(h, 'isin', '')
            if isin: all_isins.add(isin)
        for p in positions:
            isin = getattr(p, 'isin', '')
            if isin: all_isins.add(isin)
        
        if not all_isins:
            print("No stocks in portfolio")
            return
        
        print(f"Scanning {len(all_isins)} stocks...")
        sold = 0
        
        for isin in all_isins:
            p = self.get_stock_profit(isin)
            if not p["in_portfolio"]:
                continue
            
            name = getattr(next((h for h in holdings if getattr(h,'isin','')==isin), None), 'company_name', isin[:10])
            
            if p["profit_pct"] >= PROFIT_TARGET * 100:
                print(f"\n🎯 {name}: +{p['profit_pct']}%")
                print(f"   Qty: {p['qty']} | Avg: ₹{p['avg_price']} | LTP: ₹{p['ltp']}")
                
                oid = self.place_sell(isin, p["qty"])
                if oid:
                    t = load_trades()
                    if isin in t: del t[isin]
                    save_trades(t)
                    print(f"   ✅ Sold! Order: {oid}")
                    sold += 1
                else:
                    print(f"   ❌ Sell failed")
            else:
                print(f"· {name}: {p['profit_pct']}% (holding)")
        
        print(f"\n{'='*30}\nSold {sold} stocks")
    
    # -------------------- Info --------------------
    
    def get_trades(self) -> dict:
        """Get all trades."""
        return load_trades()
    
    def get_order_book(self) -> list:
        """Get today's orders."""
        try:
            r = self.api.get_order_book(api_version='2.0')
            return r.data if r.status=='success' and r.data else []
        except: return []
