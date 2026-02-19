"""Trading Dashboard - Textual TUI (Advanced, Lightweight, Production)"""
from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import (
    Header, Footer, DataTable, Static, TabbedContent, TabPane, RichLog,
)
from textual import work
from rich.text import Text


# ==================== DATA LAYER ====================

from main import portfolio, market, orders, cache, is_market_open, WATCHLIST
from market_data import get_stock_name
from sm import get_rsi
from om import load_trades, PROFIT_TARGET

LOG_FILE = Path(__file__).parent / "logs" / "bot.log"
_last_log_size = 0  # Track log file size for incremental reads


def fetch_holdings_data() -> tuple[list[tuple], float, float]:
    """Fetch holdings + totals. Runs in background thread."""
    rows = []
    total_inv = total_cur = 0.0
    try:
        for h in portfolio.get_holdings():
            name = str(getattr(h, "company_name", "?"))[:20]
            qty = int(getattr(h, "quantity", 0))
            avg = float(getattr(h, "average_price", 0))
            ltp = float(getattr(h, "last_price", 0))
            inv = avg * qty
            cur = ltp * qty
            pl = cur - inv
            pct = (pl / inv * 100) if inv > 0 else 0
            total_inv += inv
            total_cur += cur

            # Profit progress toward 4% target
            target_pct = PROFIT_TARGET * 100
            progress = min(pct / target_pct, 1.0) if target_pct > 0 else 0
            bar_len = 8
            filled = int(progress * bar_len)
            if pct >= target_pct:
                bar = Text(f"{'█' * bar_len} ✓", style="bold green")
            elif pct > 0:
                bar = Text("█" * filled + "░" * (bar_len - filled), style="yellow")
            else:
                bar = Text("░" * bar_len, style="red")

            pl_text = Text(f"{pl:+,.0f}", style="green" if pl >= 0 else "red")
            pct_text = Text(f"{pct:+.2f}%", style="bold green" if pct >= 0 else "bold red")
            rows.append((name, str(qty), f"{avg:,.2f}", f"{ltp:,.2f}", pl_text, pct_text, bar))
    except Exception:
        pass
    return rows, total_inv, total_cur


def fetch_watchlist_data() -> tuple[list[tuple], list[str]]:
    """Fetch watchlist + alert messages. Runs in background thread."""
    rows = []
    alerts = []
    for isin in WATCHLIST[:8]:
        try:
            name = str(get_stock_name(isin))[:16]
            rsi = float(get_rsi(isin, cache))
            rsi_str = f"{rsi:.2f}"
            if rsi < 25:
                signal = Text(" BUY ", style="bold white on green")
                rsi_text = Text(rsi_str, style="bold green")
                alerts.append(f"🟢 {name}: RSI {rsi_str} — BUY SIGNAL!")
            elif rsi < 30:
                signal = Text("WATCH", style="bold yellow")
                rsi_text = Text(rsi_str, style="green")
            elif rsi > 70:
                signal = Text(" SELL ", style="bold white on red")
                rsi_text = Text(rsi_str, style="bold red")
                alerts.append(f"🔴 {name}: RSI {rsi_str} — SELL SIGNAL!")
            elif rsi > 60:
                signal = Text("CAUTION", style="bold yellow")
                rsi_text = Text(rsi_str, style="yellow")
            else:
                signal = Text("HOLD", style="dim")
                rsi_text = Text(rsi_str, style="white")
            rows.append((name, rsi_text, signal))
        except Exception:
            rows.append((isin[:14], Text("-"), Text("ERR", style="red")))
    return rows, alerts


def fetch_trades_data() -> list[tuple]:
    """Fetch active trades. Runs in background thread."""
    rows = []
    trades = load_trades()
    for isin, data in list(trades.items())[:6]:
        name = str(data.get("name", isin))[:16]
        buys = data.get("buys", [])
        count = len(buys)
        last = buys[-1]["date"] if buys else "-"
        total_qty = sum(b["qty"] for b in buys)
        if count >= 3:
            ct = Text(f"{count}/3", style="bold red")
        elif count >= 2:
            ct = Text(f"{count}/3", style="yellow")
        else:
            ct = Text(f"{count}/3", style="green")
        rows.append((name, ct, last, str(total_qty)))
    return rows


def fetch_funds_data() -> tuple[float, float]:
    """Fetch funds. Runs in background thread."""
    try:
        f = portfolio.get_funds()
        return float(f.get("available", 0)), float(f.get("blocked", 0))
    except Exception:
        return 0.0, 0.0


def fetch_day_summary() -> dict:
    """Compute today's summary. Runs in background thread."""
    summary = {"orders_today": 0, "buys": 0, "sells": 0}
    try:
        ob = orders.get_order_book()
        today = datetime.now().strftime("%Y-%m-%d")
        for o in ob:
            summary["orders_today"] += 1
            txn = getattr(o, "transaction_type", "").upper()
            if txn == "BUY":
                summary["buys"] += 1
            elif txn == "SELL":
                summary["sells"] += 1
    except Exception:
        pass
    return summary


def read_new_log_lines() -> str:
    """Read only new lines from bot.log (incremental). Runs in thread."""
    global _last_log_size
    if not LOG_FILE.exists():
        return ""
    size = LOG_FILE.stat().st_size
    if size <= _last_log_size:
        return ""
    with open(LOG_FILE, "r", encoding="utf-8", errors="replace") as f:
        f.seek(_last_log_size)
        new_content = f.read()
    _last_log_size = size
    return new_content


# ==================== APP ====================

class TradingDashboard(App):
    """Trading Bot Dashboard — Advanced Textual TUI"""

    CSS_PATH = "dashboard.tcss"
    TITLE = "Trading Bot"

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("r", "refresh", "Refresh"),
        ("d", "toggle_dark", "Theme"),
        ("1", "tab_overview", "Overview"),
        ("2", "tab_log", "Log"),
    ]

    _refresh_countdown: int = 10
    _refresh_interval: int = 10

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Static("⏳ Loading...", id="status-bar")

        with TabbedContent(id="tabs"):
            # Tab 1: Overview
            with TabPane("Overview", id="tab-overview"):
                # Day summary
                yield Static("", id="day-summary")
                # Main grid
                with Horizontal(id="main-grid"):
                    with Vertical(id="holdings-box"):
                        yield Static("💼 HOLDINGS")
                        yield DataTable(id="holdings-table", cursor_type="row")
                    with Vertical(id="right-col"):
                        with Vertical(id="watchlist-box"):
                            yield Static("📡 WATCHLIST")
                            yield DataTable(id="watchlist-table", cursor_type="row")
                        with Vertical(id="trades-box"):
                            yield Static("📊 ACTIVE TRADES")
                            yield DataTable(id="trades-table", cursor_type="row")

            # Tab 2: Bot Log
            with TabPane("Bot Log", id="tab-log"):
                yield RichLog(id="log-viewer", highlight=True, markup=True)

        yield Static("💰 Loading...", id="funds-bar")
        yield Footer()

    def on_mount(self) -> None:
        """Initialize tables and start timers."""
        # Holdings columns (with progress bar)
        ht = self.query_one("#holdings-table", DataTable)
        ht.add_columns("Stock", "Qty", "Avg", "LTP", "P/L", "P/L %", "→4%")

        # Watchlist columns
        wt = self.query_one("#watchlist-table", DataTable)
        wt.add_columns("Stock", "RSI", "Signal")

        # Trades columns
        tt = self.query_one("#trades-table", DataTable)
        tt.add_columns("Stock", "Buys", "Last Date", "Qty")

        # Load initial log
        self._load_initial_log()

        # First data fetch
        self.refresh_all()

        # Auto-refresh every 10 seconds
        self.set_interval(self._refresh_interval, self.refresh_all)

        # Countdown tick every second
        self._refresh_countdown = self._refresh_interval
        self.set_interval(1, self._tick_countdown)

    # ==================== ACTIONS ====================

    def action_refresh(self) -> None:
        self._refresh_countdown = self._refresh_interval
        self.refresh_all()
        self.notify("🔄 Refreshed!", timeout=2)

    def action_toggle_dark(self) -> None:
        self.theme = "textual-light" if self.theme == "textual-dark" else "textual-dark"

    def action_tab_overview(self) -> None:
        self.query_one("#tabs", TabbedContent).active = "tab-overview"

    def action_tab_log(self) -> None:
        self.query_one("#tabs", TabbedContent).active = "tab-log"

    # ==================== COUNTDOWN ====================

    def _tick_countdown(self) -> None:
        self._refresh_countdown -= 1
        if self._refresh_countdown < 0:
            self._refresh_countdown = self._refresh_interval
        self._update_status_timer()

    def _update_status_timer(self) -> None:
        try:
            bar = self.query_one("#status-bar", Static)
            # Get current content and append countdown
            # We'll rebuild in _update_status to include timer
            pass
        except Exception:
            pass

    # ==================== WORKERS ====================

    def refresh_all(self) -> None:
        self._refresh_countdown = self._refresh_interval
        self._fetch_status()
        self._fetch_holdings()
        self._fetch_watchlist()
        self._fetch_trades()
        self._fetch_funds()
        self._fetch_summary()
        self._fetch_new_logs()

    @work(thread=True, exclusive=True, group="status")
    def _fetch_status(self) -> None:
        is_open, status = is_market_open()
        now = datetime.now()
        # Compute market close countdown
        close_info = ""
        if "OPEN" in status.upper():
            close_h = 15
            close_m = 30
            mins_left = (close_h * 60 + close_m) - (now.hour * 60 + now.minute)
            if mins_left > 0:
                close_info = f"  │  Closes in {mins_left // 60}h {mins_left % 60}m"
        self.call_from_thread(self._update_status, status, now.strftime("%H:%M:%S"), close_info)

    def _update_status(self, status: str, time_str: str, close_info: str) -> None:
        text = Text()
        if "OPEN" in status.upper():
            text.append(f" 🟢 {status}", style="bold green")
        else:
            text.append(f" 🔴 {status}", style="bold red")
        text.append(f"  │  {time_str}", style="dim")
        text.append(close_info, style="cyan")
        text.append(f"  │  Next: {self._refresh_countdown}s", style="dim italic")
        self.query_one("#status-bar", Static).update(text)

    @work(thread=True, exclusive=True, group="holdings")
    def _fetch_holdings(self) -> None:
        rows, total_inv, total_cur = fetch_holdings_data()
        self.call_from_thread(self._update_holdings, rows, total_inv, total_cur)

    def _update_holdings(self, rows: list, total_inv: float, total_cur: float) -> None:
        ht = self.query_one("#holdings-table", DataTable)
        ht.clear()
        for row in rows:
            ht.add_row(*row)
        if rows:
            total_pl = total_cur - total_inv
            total_pct = (total_pl / total_inv * 100) if total_inv > 0 else 0
            style = "bold green" if total_pl >= 0 else "bold red"
            ht.add_row(
                Text("TOTAL", style="bold"), "", Text(f"{total_inv:,.0f}", style="dim"),
                Text(f"{total_cur:,.0f}", style="yellow"),
                Text(f"{total_pl:+,.0f}", style=style),
                Text(f"{total_pct:+.2f}%", style=style),
                Text("", style="dim"),
            )

    @work(thread=True, exclusive=True, group="watchlist")
    def _fetch_watchlist(self) -> None:
        rows, alerts = fetch_watchlist_data()
        self.call_from_thread(self._update_watchlist, rows, alerts)

    def _update_watchlist(self, rows: list, alerts: list) -> None:
        wt = self.query_one("#watchlist-table", DataTable)
        wt.clear()
        for row in rows:
            wt.add_row(*row)
        # Toast alerts for signals
        for msg in alerts:
            self.notify(msg, timeout=5, severity="warning")

    @work(thread=True, exclusive=True, group="trades")
    def _fetch_trades(self) -> None:
        rows = fetch_trades_data()
        self.call_from_thread(self._update_trades, rows)

    def _update_trades(self, rows: list) -> None:
        tt = self.query_one("#trades-table", DataTable)
        tt.clear()
        for row in rows:
            tt.add_row(*row)
        if not rows:
            tt.add_row("No active trades", "-", "-", "-")

    @work(thread=True, exclusive=True, group="funds")
    def _fetch_funds(self) -> None:
        avail, blocked = fetch_funds_data()
        self.call_from_thread(self._update_funds, avail, blocked)

    def _update_funds(self, avail: float, blocked: float) -> None:
        total = avail + blocked
        text = Text()
        text.append(" 💰 Available: ", style="dim")
        text.append(f"₹{avail:,.2f}", style="bold green")
        text.append("  │  Blocked: ", style="dim")
        text.append(f"₹{blocked:,.2f}", style="bold yellow")
        text.append("  │  Total: ", style="dim")
        text.append(f"₹{total:,.2f}", style="bold white")
        self.query_one("#funds-bar", Static).update(text)

    @work(thread=True, exclusive=True, group="summary")
    def _fetch_summary(self) -> None:
        s = fetch_day_summary()
        self.call_from_thread(self._update_summary, s)

    def _update_summary(self, s: dict) -> None:
        text = Text()
        text.append("  📋 Today: ", style="bold")
        text.append(f"{s['orders_today']} orders", style="cyan")
        text.append("  │  ", style="dim")
        text.append(f"↑ {s['buys']} buys", style="green")
        text.append("  │  ", style="dim")
        text.append(f"↓ {s['sells']} sells", style="red")
        text.append(f"  │  Target: {PROFIT_TARGET*100:.0f}%", style="yellow")
        self.query_one("#day-summary", Static).update(text)

    # ==================== LOG VIEWER ====================

    def _load_initial_log(self) -> None:
        """Load last 50 lines of bot.log on startup."""
        global _last_log_size
        log_view = self.query_one("#log-viewer", RichLog)
        if LOG_FILE.exists():
            try:
                lines = LOG_FILE.read_text(encoding="utf-8", errors="replace").splitlines()
                _last_log_size = LOG_FILE.stat().st_size
                for line in lines[-50:]:
                    log_view.write(line)
            except Exception:
                log_view.write("[red]Could not read log file[/]")
        else:
            log_view.write("[dim]No log file found. Start the bot with: python main.py[/]")

    @work(thread=True, exclusive=True, group="logs")
    def _fetch_new_logs(self) -> None:
        new = read_new_log_lines()
        if new.strip():
            self.call_from_thread(self._append_logs, new)

    def _append_logs(self, content: str) -> None:
        log_view = self.query_one("#log-viewer", RichLog)
        for line in content.strip().splitlines():
            log_view.write(line)


# ==================== ENTRY ====================

if __name__ == "__main__":
    TradingDashboard().run()
