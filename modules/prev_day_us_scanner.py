from datetime import datetime

import yfinance as yf


class PrevDayUSScanner:
    """07:00 미국 전날 선점 스캐너 (경량 버전)"""

    ETF_LINK = {
        "SOXX": "KR 반도체(HBM) 연동 체크",
        "XAR": "KR 방산 연동 체크",
        "XBI": "KR 바이오 연동 체크",
        "ARKK": "혁신기술/고변동 연동 체크",
    }

    GAMBLE = ["RXRX", "IONQ", "RKLB", "OKLO", "ASTS", "RGTI", "APLD", "AMPX"]
    CORE_US = ["NVDA", "AVGO", "GOOGL", "MSFT", "NEE", "KMI", "VST"]

    def _chg(self, ticker):
        try:
            h = yf.Ticker(ticker).history(period="2d").dropna()
            if len(h) < 2:
                return None
            return ((h["Close"].iloc[-1] - h["Close"].iloc[-2]) / h["Close"].iloc[-2]) * 100
        except Exception:
            return None

    def scan(self):
        lines = [f"🇺🇸 <b>US 전날 선점 스캔</b> {datetime.now().strftime('%m/%d %H:%M')}", ""]

        # 1) ETF 연동
        lines.append("📡 <b>섹터 ETF 연동</b>")
        for etf, note in self.ETF_LINK.items():
            chg = self._chg(etf)
            if chg is None:
                continue
            if (etf in ["SOXX", "XAR"] and chg >= 3) or (etf in ["XBI", "ARKK"] and chg >= 5):
                lines.append(f"- {etf} {chg:+.2f}% → {note}")

        # 2) 도박 조건(간이)
        hits = []
        for t in self.GAMBLE:
            try:
                h = yf.Ticker(t).history(period="3mo").dropna()
                if len(h) < 30:
                    continue
                c = h["Close"].iloc[-1]
                low52 = h["Low"].min()
                rsi_base = h["Close"].diff()
                up = rsi_base.clip(lower=0).rolling(14).mean().iloc[-1]
                down = (-rsi_base.clip(upper=0)).rolling(14).mean().iloc[-1]
                rsi = 100 - (100 / (1 + (up / down))) if down and down > 0 else 50
                vol_ratio = h["Volume"].iloc[-1] / max(h["Volume"].rolling(20).mean().iloc[-1], 1)
                if c <= low52 * 1.2 and rsi <= 35 and vol_ratio >= 2:
                    hits.append((t, rsi, vol_ratio))
            except Exception:
                continue
        if hits:
            lines.append("\n🎰 <b>도박 조건 충족(총자산 2% 이내)</b>")
            for t, rsi, vr in hits[:5]:
                lines.append(f"- {t}: RSI {rsi:.1f}, 거래량 {vr:.1f}배")

        # 3) 코어 미국 점검(변동 큰 종목만)
        warns = []
        for t in self.CORE_US:
            chg = self._chg(t)
            if chg is not None and abs(chg) >= 3:
                warns.append((t, chg))
        if warns:
            lines.append("\n📊 <b>중장기 코어 변동 경보</b>")
            for t, chg in warns:
                lines.append(f"- {t}: {chg:+.2f}%")

        if len(lines) <= 3:
            return "🇺🇸 US 전날 선점 특이 신호 없음"
        return "\n".join(lines)
