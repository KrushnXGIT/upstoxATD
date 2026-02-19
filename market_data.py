"""Market Data - LTP, candles, batch operations"""
import csv
from pathlib import Path
from datetime import datetime, timedelta

import upstox_client
from upstox_client.rest import ApiException

# Stock name cache
_STOCKS = {}
_CSV = Path(__file__).parent / "stkData.csv"

def get_stock_name(isin: str) -> str:
    global _STOCKS
    if not _STOCKS:
        with open(_CSV, 'r', encoding='utf-8') as f:
            for r in csv.DictReader(f):
                if r.get('isin'): _STOCKS[r['isin'].strip()] = r.get('name','').strip()
    return _STOCKS.get(isin, "Unknown")


class MarketData:
    def __init__(self, token: str):
        cfg = upstox_client.Configuration()
        cfg.access_token = token
        client = upstox_client.ApiClient(cfg)
        self._quote = upstox_client.MarketQuoteApi(client)
        self._hist = upstox_client.HistoryApi(client)
    
    def get_ltp(self, key: str) -> float:
        try:
            r = self._quote.ltp(key, api_version='2.0')
            return list(r.data.values())[0].last_price or 0.0 if r.status=='success' and r.data else 0.0
        except: return 0.0
    
    def get_candles(self, key: str, days: int = 365) -> list:
        try:
            r = self._hist.get_historical_candle_data1(
                instrument_key=key, interval='day',
                to_date=datetime.now().strftime('%Y-%m-%d'),
                from_date=(datetime.now()-timedelta(days=days)).strftime('%Y-%m-%d'),
                api_version='2.0')
            return r.data.candles if r.status=='success' and r.data and r.data.candles else []
        except: return []
    
    def batch_ltp(self, keys: list) -> dict:
        if not keys: return {}
        result = {k: 0.0 for k in keys}
        try:
            r = self._quote.ltp(",".join(keys), api_version='2.0')
            if r.status=='success' and r.data:
                for rk, d in r.data.items():
                    for k in keys:
                        isin = k.split("|")[1] if "|" in k else k
                        if d.instrument_token and isin in str(d.instrument_token):
                            result[k] = d.last_price or 0.0
                            break
        except: pass
        return result
    
    def batch_info(self, isins: list, cache=None) -> list:
        """Get [{name, isin, ltp, rsi}, ...] for multiple ISINs"""
        import talib, numpy as np
        if not isins: return []
        
        keys = [f"NSE_EQ|{i}" for i in isins]
        ltps = self.batch_ltp(keys)
        
        results = []
        for isin in isins:
            ltp = ltps.get(f"NSE_EQ|{isin}", 0.0)
            rsi = 0.0
            if cache:
                closes = cache.get_closes(isin)
                if closes and len(closes) >= 14:
                    if ltp > 0: closes = closes + [ltp]
                    r = talib.RSI(np.array(closes, dtype=float), 14)
                    rsi = round(float(r[-1]), 2) if not np.isnan(r[-1]) else 0.0
            results.append({"name": get_stock_name(isin), "isin": isin, "ltp": ltp, "rsi": rsi})
        return results
