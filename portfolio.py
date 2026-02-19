"""Portfolio - Positions, holdings, funds from Upstox"""
import upstox_client
from upstox_client.rest import ApiException


class Portfolio:
    def __init__(self, token: str):
        cfg = upstox_client.Configuration()
        cfg.access_token = token
        client = upstox_client.ApiClient(cfg)
        self._pf = upstox_client.PortfolioApi(client)
        self._user = upstox_client.UserApi(client)
    
    def get_positions(self) -> list:
        try:
            r = self._pf.get_positions(api_version='2.0')
            return r.data if r.status == 'success' and r.data else []
        except ApiException:
            return []
    
    def get_holdings(self) -> list:
        try:
            r = self._pf.get_holdings(api_version='2.0')
            return r.data if r.status == 'success' and r.data else []
        except ApiException:
            return []
    
    def get_funds(self) -> dict:
        try:
            r = self._user.get_user_fund_margin(segment='SEC', api_version='2.0')
            if r.status == 'success' and r.data:
                eq = r.data['equity']
                return {"available": getattr(eq, 'available_margin', 0) or 0,
                        "blocked": getattr(eq, 'used_margin', 0) or 0}
        except ApiException:
            pass
        return {"available": 0.0, "blocked": 0.0}
    
    def get_overview(self) -> dict:
        f = self.get_funds()
        return {"positions": self.get_positions(), "holdings": self.get_holdings(),
                "available_fund": f["available"], "blocked_fund": f["blocked"]}


def format_overview(d: dict) -> str:
    """Format portfolio for display"""
    def table(title, icon, items, cols):
        lines = [f"\n{icon} {title} ({len(items)}):"]
        if not items: return "\n".join(lines)
        lines.append("   " + "".join(f"{c[0]:<{c[2]}}" if c[3]=='l' else f"{c[0]:>{c[2]}}" for c in cols))
        lines.append("   " + "-" * sum(c[2] for c in cols))
        for i in items:
            row = "   "
            for _, a, w, al in cols:
                v = getattr(i, a, 'N/A')
                row += f"{str(v)[:w-1]:<{w}}" if al=='l' else (f"{v:>{w}}" if isinstance(v,int) else f"{v:>{w}.2f}")
            lines.append(row)
        return "\n".join(lines)
    
    pc = [("Symbol","trading_symbol",25,'l'),("Qty","quantity",8,'r'),("Avg","average_price",12,'r'),("LTP","last_price",12,'r')]
    hc = [("Company","company_name",25,'l'),("Qty","quantity",8,'r'),("Avg","average_price",12,'r'),("LTP","last_price",12,'r')]
    
    return "\n".join([
        "\n===== PORTFOLIO =====",
        table("POSITIONS","📊",d['positions'],pc),
        table("HOLDINGS","💼",d['holdings'],hc),
        f"\n💰 Available: ₹{d['available_fund']:,.2f} | Blocked: ₹{d['blocked_fund']:,.2f}"
    ])