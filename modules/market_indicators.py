import requests
import yfinance as yf
from datetime import datetime

class MarketIndicators:
    def get_fear_greed(self):
        try:
            url = "https://api.alternative.me/fng/"
            res = requests.get(url, timeout=10)
            data = res.json()
            score = float(data['data'][0]['value'])
            rating = data['data'][0]['value_classification']
            if score <= 25:
                signal = "극단적 공포 → 매수 기회"
            elif score <= 45:
                signal = "공포 → 매수 고려"
            elif score <= 55:
                signal = "중립"
            elif score <= 75:
                signal = "탐욕 → 주의"
            else:
                signal = "극단적 탐욕 → 과열 경고"
            return {"score": score, "rating": rating, "signal": signal}
        except Exception as e:
            print(f"❌ 공포탐욕지수 수집 실패: {e}")
            return None

    def get_forex_commodities(self):
        tickers = {
            "달러/원": "KRW=X",
            "금": "GC=F",
            "유가(WTI)": "CL=F",
            "달러인덱스": "DX-Y.NYB",
        }
        results = {}
        for name, ticker in tickers.items():
            try:
                data = yf.Ticker(ticker)
                hist = data.history(period="5d")
                hist = hist.dropna()
                if len(hist) >= 2:
                    current = hist['Close'].iloc[-1]
                    prev = hist['Close'].iloc[-2]
                    change_pct = ((current - prev) / prev) * 100
                    results[name] = {
                        "price": round(current, 2),
                        "change_pct": round(change_pct, 2)
                    }
                    print(f"  ✅ {name}: {current:.2f} ({change_pct:+.2f}%)")
                else:
                    print(f"  ⚠️ {name}: 데이터 부족")
            except Exception as e:
                print(f"  ❌ {name} 실패: {e}")
        return results

    def get_all_indicators(self):
        print("🌍 시장 지표 수집 중...")
        fg = self.get_fear_greed()
        if fg:
            print(f"  ✅ 공포탐욕지수: {fg['score']} ({fg['signal']})")
        forex = self.get_forex_commodities()
        return {
            "fear_greed": fg,
            "forex_commodities": forex,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M")
        }

if __name__ == "__main__":
    mi = MarketIndicators()
    indicators = mi.get_all_indicators()
