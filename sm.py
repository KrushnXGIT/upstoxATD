"""Stock Manager - Cache and RSI"""
import json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

import talib
import numpy as np

CACHE_DIR = Path(__file__).parent / "cache"
CACHE_DIR.mkdir(exist_ok=True)


class CandleCache:
    def __init__(self, market):
        self.m = market
    
    def _path(self, isin): return CACHE_DIR / f"{isin}.json"
    def _load(self, isin): 
        p = self._path(isin)
        return json.loads(p.read_text()) if p.exists() else None
    def _save(self, isin, candles):
        self._path(isin).write_text(json.dumps({"candles": candles}))
    
    def get_closes(self, isin: str, refresh: bool = False) -> list:
        key = f"NSE_EQ|{isin}"
        c = self._load(isin)
        
        if refresh or not c:
            candles = self.m.get_candles(key, 365)
            if candles:
                self._save(isin, candles)
                return [x[4] for x in reversed(candles)]
            return []
        
        # Check for new day
        if c["candles"]:
            latest = self.m.get_candles(key, 1)
            if latest and latest[0][0][:10] != c["candles"][0][0][:10]:
                candles = self.m.get_candles(key, 365)
                if candles:
                    self._save(isin, candles)
                    return [x[4] for x in reversed(candles)]
        
        return [x[4] for x in reversed(c["candles"])]
    
    def refresh_parallel(self, isins: list, workers: int = 10):
        def _r(i):
            try: self.get_closes(i, True); return i, True
            except: return i, False
        
        ok = fail = 0
        with ThreadPoolExecutor(max_workers=workers) as ex:
            for i, s in ex.map(_r, isins):
                if s: ok += 1; print(f"✓ {i}")
                else: fail += 1; print(f"✗ {i}")
        print(f"\nDone: {ok} ok, {fail} fail")


def get_rsi(isin: str, cache, live: bool = True) -> float:
    closes = cache.get_closes(isin)
    if not closes or len(closes) < 14: return 0.0
    if live:
        ltp = cache.m.get_ltp(f"NSE_EQ|{isin}")
        if ltp > 0: closes = closes + [ltp]
    r = talib.RSI(np.array(closes, dtype=float), 14)
    return round(float(r[-1]), 2) if not np.isnan(r[-1]) else 0.0
