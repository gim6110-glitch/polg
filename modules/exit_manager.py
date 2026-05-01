from datetime import datetime

import yfinance as yf


class ExitManager:
    def _atr(self, ticker, market="US"):
        try:
            tk = f"{ticker}.KS" if market == "KR" and "." not in ticker else ticker
            h = yf.Ticker(tk).history(period="2mo").dropna()
            if len(h) < 20:
                return None, None
            tr = (h["High"] - h["Low"]).rolling(14).mean().iloc[-1]
            return float(tr), h
        except Exception:
            return None, None

    def scan(self, portfolio):
        alerts = []
        for ticker, s in portfolio.items():
            if not isinstance(s, dict):
                continue
            market = s.get("market", "KR")
            atr, h = self._atr(ticker, market)
            if atr is None:
                continue
            close = float(h["Close"].iloc[-1]); high20 = float(h["High"].tail(20).max())
            buy = float(s.get("buy_price", 0) or 0)
            if buy <= 0:
                continue
            profit = ((close - buy) / buy) * 100
            target1 = float(s.get("target1") or 0)
            hold_type = s.get("hold_type", "장기")
            mult = 1.5 if hold_type == "단기" else 3.0 if "도박" in hold_type else 2.5

            if target1 > 0 and close >= (buy + (target1 - buy) * 0.5):
                alerts.append(f"💸 익절 알림 {s['name']}({ticker}) 수익률 {profit:+.1f}% | 30~50% 부분익절 검토")

            trailing = high20 - atr * mult
            min_profit = 5.0 if hold_type == "단기" else 10.0
            if close < trailing and profit >= min_profit:
                alerts.append(f"🚨 트레일링 이탈 {s['name']}({ticker}) | 수익 {profit:+.1f}% | 잔여 익절 검토")
            ma5 = h["Close"].rolling(5).mean().iloc[-1]
            ma20 = h["Close"].rolling(20).mean().iloc[-1]
            if hold_type == "단기":
                down3 = len(h) >= 4 and all(h["Close"].iloc[-i] < h["Close"].iloc[-i-1] for i in [1,2,3])
                if down3 and close < ma5:
                    alerts.append(f"⚠️ 추세 꺾임 {s['name']}({ticker}) 3일하락+5일선이탈 | 익절 검토")
            else:
                down5 = len(h) >= 6 and all(h["Close"].iloc[-i] < h["Close"].iloc[-i-1] for i in [1,2,3,4,5])
                if down5 and close < ma20:
                    alerts.append(f"⚠️ 추세 꺾임 {s['name']}({ticker}) 5일하락+20일선이탈 | 중장기 익절 검토")
        return alerts
