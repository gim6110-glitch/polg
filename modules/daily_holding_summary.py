from datetime import datetime

import yfinance as yf


class DailyHoldingSummary:
    """보유 종목 일일 상태 요약 (AI 호출 없음)"""

    def _prev_close(self, ticker, market):
        try:
            tk = ticker if market == "US" else f"{ticker}.KS"
            h = yf.Ticker(tk).history(period="5d").dropna()
            if len(h) < 2:
                return None
            return float(h["Close"].iloc[-2])
        except Exception:
            return None

    def build(self, portfolio, kis_api):
        lines = [f"🧾 <b>보유 종목 일일 상태 요약</b> {datetime.now().strftime('%m/%d %H:%M')}", ""]
        for ticker, s in portfolio.items():
            if not isinstance(s, dict):
                continue
            name = s.get("name", ticker)
            market = s.get("market", "KR")
            buy = float(s.get("buy_price", 0) or 0)
            t1 = float(s.get("target1") or 0)
            sl = float(s.get("stop_loss") or 0)
            if market == "KR":
                d = kis_api.get_kr_price(ticker)
            else:
                d = kis_api.get_us_price(ticker)
            if not d:
                continue
            px = float(d.get("price", 0) or 0)
            if px <= 0 or buy <= 0:
                continue
            profit = ((px - buy) / buy) * 100
            to_t1 = (((t1 - px) / px) * 100) if t1 > 0 else None
            to_sl = (((px - sl) / px) * 100) if sl > 0 else None
            prev = self._prev_close(ticker, market)
            day = (((px - prev) / prev) * 100) if prev else 0
            lines.append(
                f"- {name}({ticker}) | 수익률 {profit:+.1f}% | 전일대비 {day:+.1f}% | "
                f"목표까지 {to_t1:+.1f}% | 손절여유 {to_sl:+.1f}%"
            )
        if len(lines) == 2:
            return "🧾 보유 종목 요약: 데이터 없음"
        return "\n".join(lines)
