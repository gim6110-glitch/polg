import yfinance as yf
import pandas as pd
from datetime import datetime

class PriceCollector:
    def __init__(self):
        self.kr_stocks = {
            "삼성전자": "005930.KS",
            "SK하이닉스": "000660.KS",
            "한화에어로스페이스": "012450.KS",
            "LG에너지솔루션": "373220.KS",
            "카카오": "035720.KS",
        }
        self.us_stocks = {
            "NVIDIA": "NVDA",
            "Apple": "AAPL",
            "Tesla": "TSLA",
            "Microsoft": "MSFT",
            "AMD": "AMD",
        }
        self.indices = {
            "코스피": "^KS11",
            "코스닥": "^KQ11",
            "나스닥": "^IXIC",
            "S&P500": "^GSPC",
            "VIX": "^VIX",
        }

    def get_stock_data(self, ticker, period="3mo"):
        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(period=period)
            hist = hist.dropna()
            if len(hist) < 2:
                return None
            current = hist['Close'].iloc[-1]
            prev = hist['Close'].iloc[-2]
            change_pct = ((current - prev) / prev) * 100
            volume = hist['Volume'].iloc[-1]
            avg_volume = hist['Volume'].replace(0, float('nan')).mean()
            if pd.isna(avg_volume) or avg_volume == 0:
                vol_ratio = 1.0
            else:
                vol_ratio = round(volume / avg_volume, 2)
            return {
                "ticker": ticker,
                "current_price": round(current, 2),
                "change_pct": round(change_pct, 2),
                "volume": int(volume),
                "avg_volume": int(avg_volume) if not pd.isna(avg_volume) else 0,
                "volume_ratio": vol_ratio,
                "week_52_high": round(hist['Close'].max(), 2),
                "week_52_low": round(hist['Close'].min(), 2),
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
            }
        except Exception as e:
            print(f"❌ {ticker} 데이터 수집 실패: {e}")
            return None

    def get_all_prices(self):
        results = {"한국주식": {}, "미국주식": {}, "지수": {}}
        print("📊 한국 주식 수집 중...")
        for name, ticker in self.kr_stocks.items():
            data = self.get_stock_data(ticker)
            if data:
                results["한국주식"][name] = data
                print(f"  ✅ {name}: {data['current_price']} ({data['change_pct']:+.2f}%)")
        print("📊 미국 주식 수집 중...")
        for name, ticker in self.us_stocks.items():
            data = self.get_stock_data(ticker)
            if data:
                results["미국주식"][name] = data
                print(f"  ✅ {name}: ${data['current_price']} ({data['change_pct']:+.2f}%)")
        print("📊 지수 수집 중...")
        for name, ticker in self.indices.items():
            data = self.get_stock_data(ticker)
            if data:
                results["지수"][name] = data
                print(f"  ✅ {name}: {data['current_price']} ({data['change_pct']:+.2f}%)")
        return results

if __name__ == "__main__":
    collector = PriceCollector()
    prices = collector.get_all_prices()
