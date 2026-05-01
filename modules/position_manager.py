from datetime import datetime

import yfinance as yf


class PositionManager:
    def _ret5(self, ticker):
        try:
            h = yf.Ticker(ticker).history(period="7d").dropna()
            if len(h) < 5:
                return 0
            return ((h["Close"].iloc[-1] - h["Close"].iloc[-5]) / h["Close"].iloc[-5]) * 100
        except Exception:
            return 0

    def score(self):
        kr = self._ret5("^KS11")
        us = self._ret5("^GSPC")
        try:
            vix = yf.Ticker("^VIX").history(period="2d").dropna()
            vix_down = (vix["Close"].iloc[-1] < vix["Close"].iloc[-2]) if len(vix) >= 2 else False
        except Exception:
            vix_down = False
        kr_score = max(0, min(100, 50 + kr * 5))
        us_score = max(0, min(100, 50 + us * 5 + (5 if vix_down else -5)))
        return kr_score, us_score

    def build_message(self, portfolio):
        kr_score, us_score = self.score()
        cash_krw = portfolio.get("_cash", 0)
        cash_usd = portfolio.get("_cash_usd", 0)
        diff = abs(kr_score - us_score)
        if diff < 15:
            act = "현재 비중 유지"
        elif diff < 30:
            act = "약한 쪽 수익종목 익절 후보 1~2개 검토"
        else:
            act = "강한 쪽 비중 확대 권고"
        stronger = "KR" if kr_score > us_score else "US"
        return (
            f"⚖️ <b>07:00 장세 비중 분석</b> {datetime.now().strftime('%m/%d %H:%M')}\n"
            f"KR 점수: {kr_score:.1f} / US 점수: {us_score:.1f}\n"
            f"예수금: KRW {cash_krw:,.0f} / USD {cash_usd:,.2f}\n"
            f"권고: {act} (강한 시장: {stronger})"
        )
