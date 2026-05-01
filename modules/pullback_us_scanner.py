from datetime import datetime

import yfinance as yf


class PullbackUSScanner:
    """23:30 US 눌림목 스캐너 (경량)"""

    WATCH = ["NVDA", "AVGO", "GOOGL", "MSFT", "IONQ", "RKLB", "OKLO", "ASTS", "RGTI"]

    def scan(self):
        picks = []
        for t in self.WATCH:
            try:
                h = yf.Ticker(t).history(period="2mo").dropna()
                if len(h) < 25:
                    continue
                c = float(h["Close"].iloc[-1]); o = float(h["Open"].iloc[-1]); hi = float(h["High"].iloc[-1])
                chg = ((c - o) / o) * 100 if o else 0
                draw = ((c - hi) / hi) * 100 if hi else 0
                vol = h["Volume"].iloc[-1] / max(h["Volume"].rolling(20).mean().iloc[-1], 1)
                # 대형주/고변동 단순 분기
                is_volatile = t in ["IONQ", "RKLB", "OKLO", "ASTS", "RGTI"]
                lo, hi_dd = (-10, -5) if is_volatile else (-5, -2)
                if 5 <= chg < 10 and lo <= draw <= hi_dd and vol <= 0.5:
                    picks.append((t, chg, draw, vol))
            except Exception:
                continue
        if not picks:
            return "📉 US 눌림목 후보 없음"
        lines = [f"📉 <b>US 눌림목 스캔</b> {datetime.now().strftime('%m/%d %H:%M')}"]
        for t, chg, draw, vol in picks[:5]:
            lines.append(f"- {t} 등락 {chg:+.1f}% | 고점대비 {draw:+.1f}% | 거래량 {vol:.1f}배")
        return "\n".join(lines)
