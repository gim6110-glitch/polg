import sys
sys.path.append('/home/dps/stock_ai')

from modules.news_collector import NewsCollector
from modules.price_collector import PriceCollector
from modules.market_indicators import MarketIndicators
from modules.claude_analyzer import ClaudeAnalyzer

print("=" * 50)
print("🧠 Claude 파급 추론 테스트")
print("=" * 50)

print("\n📡 데이터 수집 중...")
news = NewsCollector().collect_news(max_per_feed=5)
prices = PriceCollector().get_all_prices()
indicators = MarketIndicators().get_all_indicators()

print("\n🧠 Claude 분석 중... (10~20초 소요)")
analyzer = ClaudeAnalyzer()
result = analyzer.analyze_market(news, prices, indicators)

if result:
    print("\n" + "=" * 50)
    print("📊 Claude 분석 결과")
    print("=" * 50)
    print(result)
    print("\n✅ 3단계 완료!")
else:
    print("❌ 분석 실패")
