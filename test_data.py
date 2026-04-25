import sys
sys.path.append('/home/dps/stock_ai')

from modules.news_collector import NewsCollector
from modules.price_collector import PriceCollector
from modules.market_indicators import MarketIndicators

print("=" * 50)
print("📡 데이터 수집 테스트 시작")
print("=" * 50)

print("\n[1/3] 뉴스 수집")
nc = NewsCollector()
news = nc.collect_news(max_per_feed=3)
print(f"→ 총 {len(news)}개 뉴스 수집")

print("\n[2/3] 주가 데이터 수집")
pc = PriceCollector()
prices = pc.get_all_prices()

print("\n[3/3] 시장 지표 수집")
mi = MarketIndicators()
indicators = mi.get_all_indicators()

print("\n" + "=" * 50)
print("✅ 모든 데이터 수집 완료!")
print("=" * 50)
