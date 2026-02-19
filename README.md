# 🤖 UpstoxATD — Upstox API Terminal Dashboard

An automated trading bot + live terminal dashboard for the Indian stock market, built on the [Upstox API](https://upstox.com/developer/api/).

> **Buy low (RSI < 25) → Scale in (up to 3x) → Sell at 4% profit → Repeat.**

---

## ✨ Features

### Trading Bot (`main.py`)
- 🔄 **Auto buy/sell** — RSI-based buy signals, profit-based sell triggers
- 📈 **Scale-in strategy** — Up to 3 buys per stock with 7-day gap
- 🛡️ **Portfolio-aware** — Checks actual holdings/positions before trading
- 🔁 **Trade sync** — Validates orders against broker's order book
- 📝 **Logging** — Full activity log to `logs/bot.log`

### Live Dashboard (`dashboard_tui.py`)
- 💼 **Holdings** — Real-time P/L with color coding + progress toward 4% target
- 📡 **Watchlist** — Live RSI values with BUY/SELL/HOLD signals
- 📊 **Active Trades** — Scale-in count, last buy date
- 📜 **Bot Log** — Live scrollable log viewer (Tab 2)
- 🔔 **Toast Alerts** — Pop-up notifications on signal triggers
- ⏱️ **Auto-refresh** — Every 10 seconds with countdown timer
- 🎨 **Dark/Light mode** — Toggle with `d`

---

## 📁 Project Structure

```
upstoxATD/
├── main.py            # Bot entry point — run this
├── om.py              # Order Manager (buy/sell/strategy)
├── sm.py              # Stock Manager (cache/RSI)
├── market_data.py     # Market data API (LTP/candles)
├── portfolio.py       # Portfolio API (holdings/funds)
├── config.py          # Config from .env
├── dashboard_tui.py   # Terminal dashboard (Textual)
├── dashboard.tcss     # Dashboard styling
├── stkData.csv        # Stock ISIN → Name mapping
├── trades.json        # Trade history
├── requirements.txt   # Dependencies
├── .env.example       # Environment template
└── LICENSE            # MIT
```

---

## 🚀 Quick Start

### 1. Clone
```bash
git clone https://github.com/YOUR_USERNAME/upstoxATD.git
cd upstoxATD
```

### 2. Install Dependencies

**Python 3.11+** required.

```bash
python -m venv venv
source venv/bin/activate   # Linux/Mac
venv\Scripts\activate      # Windows

pip install -r requirements.txt
```

> ⚠️ **TA-Lib** requires a C library. See [TA-Lib installation guide](https://github.com/TA-Lib/ta-lib-python#dependencies).

### 3. Configure
```bash
cp .env.example .env
```
Edit `.env` and add your Upstox access token:
```
ACCESS_TOKEN=your_token_here
API_KEY=your_api_key
API_SECRET=your_api_secret
```

### 4. Add Stocks to Watchlist
Edit `main.py` and add ISINs to the `WATCHLIST`:
```python
WATCHLIST = [
    "INE176A01028",  # BATA
    "INE081A01020",  # Tata Steel
    "INE002A01018",  # Reliance
]
```

### 5. Run

**Bot:**
```bash
python main.py
```

**Dashboard:**
```bash
python dashboard_tui.py
```

---

## 🎮 Dashboard Controls

| Key | Action |
|-----|--------|
| `q` | Quit |
| `r` | Force refresh |
| `d` | Toggle dark/light mode |
| `1` | Overview tab |
| `2` | Bot log tab |
| `↑↓` | Navigate table rows |

---

## ⚙️ Strategy Configuration

All constants are in `om.py`:

```python
MAX_BUYS = 3           # Max scale-in buys per stock
DAYS_GAP = 7           # Min days between buys
RSI_THRESHOLD = 25     # Buy when RSI < this
FUND_PERCENT = 0.10    # 10% of available funds per buy
PROFIT_TARGET = 0.04   # Sell when profit >= 4%
```

---

## 🖥️ Deploy on AWS EC2

```bash
# Install TA-Lib on Ubuntu
sudo apt install build-essential wget -y
wget http://prdownloads.sourceforge.net/ta-lib/ta-lib-0.4.0-src.tar.gz
tar -xzf ta-lib-0.4.0-src.tar.gz
cd ta-lib && ./configure --prefix=/usr && make && sudo make install

# Setup
cd upstoxATD
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env && nano .env

# Run bot in background
nohup python main.py > /dev/null 2>&1 &

# View dashboard over SSH
python dashboard_tui.py
```

---

## ⚠️ Disclaimer

This software is for **educational purposes only**. Trading in the stock market involves risk. The authors are not responsible for any financial losses. Use at your own risk.

---

## 📄 License

[BSL 1.1](LICENSE)
