import anthropic
import os
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

class ClaudeAnalyzer:
    def __init__(self):
        self.client = anthropic.Anthropic(
            api_key=os.getenv('ANTHROPIC_API_KEY')
        )
        self.model = "claude-sonnet-4-5"
        self.daily_call_count = 0
        self.max_daily_calls = 30  # 하루 최대 호출 횟수 제한

    def _check_limit(self):
        if self.daily_call_count >= self.max_daily_calls:
            print("⚠️ 일일 Claude 호출 한도 도달")
            return False
        return True

    def analyze_market(self, news_list, prices, indicators):
        if not self._check_limit():
            return None

        # 뉴스 요약 (상위 10개)
        news_text = ""
        for i, news in enumerate(news_list[:10]):
            news_text += f"{i+1}. [{news['source']}] {news['title']}\n"

        # 주요 지수 요약
        indices_text = ""
        if prices.get("지수"):
            for name, data in prices["지수"].items():
                indices_text += f"- {name}: {data['current_price']} ({data['change_pct']:+.2f}%)\n"

        # 시장 지표 요약
        fg = indicators.get("fear_greed", {})
        fg_text = f"공포탐욕지수: {fg.get('score', 'N/A')} ({fg.get('signal', 'N/A')})" if fg else ""

        forex = indicators.get("forex_commodities", {})
        forex_text = ""
        for name, data in forex.items():
            forex_text += f"- {name}: {data['price']} ({data['change_pct']:+.2f}%)\n"

        prompt = f"""
당신은 전문 주식 애널리스트입니다.
오늘의 시장 데이터를 분석하고 투자 기회를 찾아주세요.

=== 오늘의 주요 뉴스 ===
{news_text}

=== 주요 지수 ===
{indices_text}

=== 시장 지표 ===
{fg_text}
{forex_text}

다음 형식으로 분석해주세요:

1. 오늘의 시장 핵심 이슈 (2~3줄 요약)

2. 2차 파급 효과 분석
- 뉴스 A → 수혜 섹터/종목 (한국/미국 각각)
- 뉴스 B → 수혜 섹터/종목
(최대 3개 뉴스)

3. 단기 추천 종목 (3~5개)
- 종목명 (티커): 추천 이유, 진입 전략
- 신뢰도: ★★★★☆ 형식

4. 오늘 주의해야 할 리스크

5. 전체 시장 방향성 (상승/중립/하락 + 이유)

한국어로 답변해주세요.
"""

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=1500,
                messages=[{"role": "user", "content": prompt}]
            )
            self.daily_call_count += 1
            return response.content[0].text
        except Exception as e:
            print(f"❌ Claude 분석 실패: {e}")
            return None

    def analyze_buy_signal(self, stock_name, ticker, signal_data):
        if not self._check_limit():
            return None

        prompt = f"""
주식 매수 신호 분석을 해주세요.

종목: {stock_name} ({ticker})
현재가: {signal_data.get('current_price')}
등락률: {signal_data.get('change_pct')}%
거래량 비율: 평소 대비 {signal_data.get('volume_ratio')}배
RSI: {signal_data.get('rsi', 'N/A')}
52주 최고가: {signal_data.get('week_52_high')}
52주 최저가: {signal_data.get('week_52_low')}
신호 유형: {signal_data.get('signal_type')}

다음을 간단히 분석해주세요 (5줄 이내):
1. 매수 신호 신뢰도 (★ 1~5개)
2. 진입 추천 여부와 이유
3. 목표가와 손절가 제안
4. 주의사항

한국어로 답변해주세요.
"""

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=500,
                messages=[{"role": "user", "content": prompt}]
            )
            self.daily_call_count += 1
            return response.content[0].text
        except Exception as e:
            print(f"❌ Claude 신호 분석 실패: {e}")
            return None

if __name__ == "__main__":
    analyzer = ClaudeAnalyzer()
    print("✅ Claude 분석 엔진 로드 완료")
