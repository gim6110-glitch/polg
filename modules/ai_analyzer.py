import os
import sys
from anthropic import Anthropic
from dotenv import load_dotenv
from datetime import datetime

load_dotenv('/home/dps/stock_ai/.env')

# 텔레그램 메시지 제한 고려한 최대 글자수
MAX_RESPONSE_CHARS = 1500

class AIAnalyzer:
    def __init__(self):
        self.client           = Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))
        self.model            = "claude-sonnet-4-6"
        self.daily_call_count = 0
        self.max_daily_calls  = 50

    def _check_limit(self):
        if self.daily_call_count >= self.max_daily_calls:
            print("⚠️ 일일 AI 호출 한도 도달")
            return False
        return True

    def _clean_response(self, text):
        """마크다운 제거 + 글자수 제한"""
        # 마크다운 헤더 제거
        import re
        text = re.sub(r'#{1,6}\s+', '', text)
        # 볼드 제거
        text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)
        # 이탤릭 제거
        text = re.sub(r'\*(.*?)\*', r'\1', text)
        # 구분선 제거
        text = re.sub(r'---+', '─────────', text)
        # 연속 빈 줄 정리
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text.strip()

    def analyze_market(self, news_list, prices, indicators):
        if not self._check_limit():
            return None

        news_text = ""
        for i, news in enumerate(news_list[:10]):
            news_text += f"{i+1}. [{news['source']}] {news['title']}\n"

        indices_text = ""
        if prices.get("지수"):
            for name, data in prices["지수"].items():
                indices_text += f"- {name}: {data['current_price']} ({data['change_pct']:+.2f}%)\n"

        fg    = indicators.get("fear_greed", {})
        fg_text = f"공포탐욕지수: {fg.get('score', 'N/A')} ({fg.get('signal', 'N/A')})" if fg else ""

        forex      = indicators.get("forex_commodities", {})
        forex_text = ""
        for name, data in forex.items():
            forex_text += f"- {name}: {data['price']} ({data['change_pct']:+.2f}%)\n"

        prompt = f"""전문 주식 애널리스트로서 오늘 시장을 분석해주세요.
마크다운(##, **, --, ###) 절대 금지. 이모지와 줄바꿈만 사용.
각 항목은 2줄 이내로 간결하게.

=== 뉴스 ===
{news_text}

=== 지수 ===
{indices_text}

=== 지표 ===
{fg_text}
{forex_text}

아래 형식으로만 답변:
1️⃣ 핵심 이슈: (2줄 이내)
2️⃣ 수혜 종목: (한국/미국 각 2개씩)
3️⃣ 단기 추천: (3개, 이유 한 줄씩)
4️⃣ 리스크: (1줄)
5️⃣ 방향성: (상승/중립/하락 + 이유 1줄)

한국어로 답변."""

        try:
            response = self.client.messages.create(
                model      = self.model,
                max_tokens = 800,
                messages   = [{"role": "user", "content": prompt}]
            )
            self.daily_call_count += 1
            return self._clean_response(response.content[0].text)
        except Exception as e:
            print(f"❌ AI 분석 실패: {e}")
            return None

    def analyze_sector_trend(self, news_list):
        if not self._check_limit():
            return None

        news_text = ""
        for i, news in enumerate(news_list[:15]):
            news_text += f"{i+1}. [{news['source']}] {news['title']}\n"

        prompt = f"""주식 섹터 분석 전문가로서 분석해주세요.
마크다운(##, **, --, ###) 절대 금지. 이모지와 줄바꿈만 사용.
각 항목은 2줄 이내로 간결하게.

=== 뉴스 ===
{news_text}

아래 형식으로만 답변:
🔥 핫한 섹터 TOP3:
1. 섹터명: 이유(1줄) / 대표종목: 한국1,2 / 미국1,2
2. 섹터명: 이유(1줄) / 대표종목: 한국1,2 / 미국1,2
3. 섹터명: 이유(1줄) / 대표종목: 한국1,2 / 미국1,2

📈 다음 올 섹터 TOP3:
1. 섹터명: 근거(1줄) / 선점종목: 한국1,2 / 미국1,2
2. 섹터명: 근거(1줄) / 선점종목: 한국1,2 / 미국1,2
3. 섹터명: 근거(1줄) / 선점종목: 한국1,2 / 미국1,2

⚠️ 피할 섹터:
1. 섹터명: 이유(1줄)
2. 섹터명: 이유(1줄)

한국어로 답변."""

        try:
            response = self.client.messages.create(
                model      = self.model,
                max_tokens = 600,
                messages   = [{"role": "user", "content": prompt}]
            )
            self.daily_call_count += 1
            return self._clean_response(response.content[0].text)
        except Exception as e:
            print(f"❌ 섹터 분석 실패: {e}")
            return None

    def analyze_buy_signal(self, stock_name, ticker, signal_data):
        if not self._check_limit():
            return None

        prompt = f"""주식 매수 신호를 분석해주세요.
마크다운 금지. 이모지와 줄바꿈만 사용.

종목: {stock_name} ({ticker})
현재가: {signal_data.get('current_price')}
등락률: {signal_data.get('change_pct')}%
거래량: 평소 대비 {signal_data.get('volume_ratio')}배
RSI: {signal_data.get('rsi')}
볼린저밴드: {signal_data.get('bb_position')}
52주 신고가 대비: {signal_data.get('high_52w_proximity')}%
ATR 손절선: {signal_data.get('stop_loss')} ({signal_data.get('stop_loss_pct')}%)
감지된 신호: {signal_data.get('signals')}

아래 형식으로만 답변:
⭐ 신뢰도: ★★★★☆
✅ 진입: (추천여부 + 이유 1줄)
🎯 목표가: / 🛑 손절가:
⚠️ 주의: (1줄)"""

        try:
            response = self.client.messages.create(
                model      = self.model,
                max_tokens = 300,
                messages   = [{"role": "user", "content": prompt}]
            )
            self.daily_call_count += 1
            return self._clean_response(response.content[0].text)
        except Exception as e:
            print(f"❌ 신호 분석 실패: {e}")
            return None

    def predict_next_trend(self, news_list, current_hot_sectors):
        if not self._check_limit():
            return None

        news_text = ""
        for i, news in enumerate(news_list[:10]):
            news_text += f"{i+1}. [{news['source']}] {news['title']}\n"

        prompt = f"""주식 트렌드 예측 전문가로서 분석해주세요.
마크다운(##, **, --, ###) 절대 금지. 이모지와 줄바꿈만 사용.
각 항목은 2줄 이내로 간결하게.

=== 뉴스 ===
{news_text}

=== 현재 핫한 섹터 ===
{current_hot_sectors}

아래 형식으로만 답변:
📌 덜 오른 2등주 TOP3: (티커포함, 이유 1줄씩)
📅 3개월 후 뜰 섹터: (2개, 근거 1줄씩)
🚀 지금 선점 TOP5: (티커포함, 한국/미국 혼합)

한국어로 답변."""

        try:
            response = self.client.messages.create(
                model      = self.model,
                max_tokens = 500,
                messages   = [{"role": "user", "content": prompt}]
            )
            self.daily_call_count += 1
            return self._clean_response(response.content[0].text)
        except Exception as e:
            print(f"❌ 트렌드 예측 실패: {e}")
            return None


if __name__ == "__main__":
    analyzer = AIAnalyzer()
    print("=" * 50)
    print("🧠 Claude API 연결 테스트")
    print("=" * 50)
    try:
        response = analyzer.client.messages.create(
            model      = "claude-sonnet-4-6",
            max_tokens = 100,
            messages   = [{"role": "user", "content": "안녕하세요. 주식 AI 에이전트 테스트입니다. 한 줄로 응답해주세요."}]
        )
        print(f"✅ Claude API 연결 성공!")
        print(f"응답: {response.content[0].text}")
    except Exception as e:
        print(f"❌ 연결 실패: {e}")
