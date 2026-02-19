"""Main - Trading Bot with Auto Buy/Sell"""
import logging
import time
from datetime import datetime
from pathlib import Path

import upstox_client
from upstox_client.rest import ApiException

from config import Config
from portfolio import Portfolio
from market_data import MarketData
from sm import CandleCache
from om import OrderManager

# ==================== LOGGING ====================

LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

# Setup logging with UTF-8 encoding
import sys
log = logging.getLogger("bot")
log.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s | %(levelname)s | %(message)s')

# File handler with UTF-8
fh = logging.FileHandler(LOG_DIR / "bot.log", encoding='utf-8')
fh.setFormatter(formatter)
log.addHandler(fh)

# Stream handler with UTF-8
sh = logging.StreamHandler(sys.stdout)
sh.setFormatter(formatter)
sh.setStream(open(sys.stdout.fileno(), mode='w', encoding='utf-8', buffering=1))
log.addHandler(sh)


# ==================== WATCHLIST ====================

WATCHLIST = [
    "INE176A01028",  # BATA
    "INE081A01020",  # Tata Steel
    "INE002A01018",  # Reliance
    # Add more ISINs here
]


# ==================== INITIALIZE ====================

Config.validate()
portfolio = Portfolio(Config.ACCESS_TOKEN)
market = MarketData(Config.ACCESS_TOKEN)
cache = CandleCache(market)
orders = OrderManager(Config.ACCESS_TOKEN, portfolio, market, cache)


# ==================== MARKET STATUS ====================

def is_market_open() -> tuple[bool, str]:
    """Check if market is open using Upstox API."""
    try:
        cfg = upstox_client.Configuration()
        cfg.access_token = Config.ACCESS_TOKEN
        api = upstox_client.MarketHolidaysAndTimingsApi(upstox_client.ApiClient(cfg))
        
        resp = api.get_market_status('NSE')
        if resp.status == 'success' and resp.data:
            status = getattr(resp.data, 'status', '').upper()
            # NORMAL_OPEN, PRE_OPEN, CLOSING_END, etc.
            if 'OPEN' in status:
                return True, f"Market {status}"
            else:
                return False, f"Market {status}"
        return False, "Unknown status"
    except ApiException as e:
        log.warning(f"Market status API error: {e}")
        # Fallback: check time manually
        now = datetime.now()
        if now.weekday() >= 5:
            return False, "Weekend"
        if now.hour < 9 or (now.hour == 9 and now.minute < 15):
            return False, "Pre-market"
        if now.hour >= 15 and now.minute > 30:
            return False, "Post-market"
        if now.hour >= 16:
            return False, "Market closed"
        return True, "Assumed open (API failed)"


# ==================== BOT ====================

def run_bot(interval_min: int = 3):
    """
    Main trading bot loop.
    - Checks market status
    - Scans holdings for sell (profit >= 4%)
    - Scans watchlist for buy (RSI < 25)
    - Loops every interval_min minutes
    """
    log.info("=" * 50)
    log.info("🤖 TRADING BOT STARTED")
    log.info(f"Watchlist: {len(WATCHLIST)} stocks")
    log.info(f"Interval: {interval_min} minutes")
    log.info("=" * 50)
    
    while True:
        try:
            # Check market status
            is_open, status = is_market_open()
            
            if not is_open:
                log.info(f"⏸️  {status} - Waiting...")
                time.sleep(60)  # Check every minute when closed
                continue
            
            log.info(f"✅  {status}")
            
            # Sync trades
            log.info("Syncing trades...")
            orders.sync_trades()
            
            # SELL: Scan holdings for profit >= 4%
            log.info("📤 Scanning for SELL signals...")
            orders.scan_and_sell()
            
            # BUY: Scan watchlist for RSI < 25
            log.info("📥 Scanning for BUY signals...")
            bought = orders.scan_and_buy(WATCHLIST)
            log.info(f"Bought: {bought} stocks")
            
            # Wait for next cycle
            log.info(f"💤 Sleeping {interval_min} minutes...")
            time.sleep(interval_min * 60)
            
        except KeyboardInterrupt:
            log.info("🛑 Bot stopped by user")
            break
        except Exception as e:
            log.error(f"Error: {e}")
            time.sleep(60)  # Wait a minute on error


# ==================== ENTRY POINT ====================

if __name__ == "__main__":
    run_bot()