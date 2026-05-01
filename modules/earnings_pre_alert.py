from datetime import datetime, timedelta

import yfinance as yf


class EarningsPreAlert:
    """미국 보유 종목 어닝 사전 알림 (AI 호출 없음)"""

    def _get_next_earnings(self, ticker):
        try:
            tk = yf.Ticker(ticker)
            cal = tk.calendar
            if not cal or "Earnings Date" not in cal:
                return None
            dates = cal["Earnings Date"]
            if not dates:
                return None
            from datetime import date
            today = date.today()
            future = [d for d in dates if d >= today]
            if not future:
                return None
            d = future[0]
            return {
                "date": datetime.combine(d, datetime.min.time()),
                "eps_est": cal.get("Earnings Average"),
                "eps_high": cal.get("Earnings High"),
                "eps_low": cal.get("Earnings Low"),
                "surprise": None,
            }
        except Exception:
            return None

    def build_alert(self, portfolio, days_ahead=1):
        targets = []
        now = datetime.now()
        for ticker, s in portfolio.items():
            if not isinstance(s, dict) or s.get("market") != "US":
                continue
            e = self._get_next_earnings(ticker)
            if not e:
                continue
            d = e["date"].replace(tzinfo=None) if getattr(e["date"], "tzinfo", None) else e["date"]
            days = (d.date() - now.date()).days
            if 0 <= days <= days_ahead:
                targets.append((s.get("name", ticker), ticker, d, e))

        if not targets:
            return None
        lines = [f"📅 <b>어닝 사전 알림</b> {now.strftime('%m/%d %H:%M')}", ""]
        for name, t, d, e in targets[:10]:
            lines.append(
                f"- {name}({t}) | 발표: {d.strftime('%m/%d %H:%M')} | "
                f"EPS예상 {e.get('eps_est','-')} / 최근서프 {e.get('surprise','-')}"
            )
        lines.append("\n💡 오늘 밤 발표 종목은 포지션(익절/홀딩) 사전 점검 권장")
        return "\n".join(lines)
