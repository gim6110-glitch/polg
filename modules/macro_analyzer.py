import sys
import os
import json
import time
import yfinance as yf
from datetime import datetime
from dotenv import load_dotenv

sys.path.insert(0, '/home/dps/stock_ai')
load_dotenv('/home/dps/stock_ai/.env')

class MacroAnalyzer:
    """
    매크로 상황 자동 파악
    AI가 뉴스/지표 보고 스스로 판단
    → 전략 자동 조정
    """
    def __init__(self):
        self.macro_file = "/home/dps/stock_ai/data/macro_context.json"
        self.context    = self._load_context()

    def _load_context(self):
        if os.path.exists(self.macro_file):
            with open(self.macro_file, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}

    def _save_context(self, context):
        os.makedirs("/home/dps/stock_ai/data", exist_ok=True)
        with open(self.macro_file, "w", encoding="utf-8") as f:
            json.dump(context, f, ensure_ascii=False, indent=2)

    def get_market_indicators(self):
        """핵심 시장 지표 수집"""
        indicators = {}

        tickers = {
            "나스닥":    "^IXIC",
            "S&P500":   "^GSPC",
            "코스피":    "^KS11",
            "VIX":       "^VIX",
            "달러인덱스": "DX-Y.NYB",
            "금":        "GC=F",
            "유가":      "CL=F",
            "나스닥선물": "NQ=F",
            "SP선물":    "ES=F",
            "국채10년":  "^TNX",
        }

        for name, ticker in tickers.items():
            try:
                hist = yf.Ticker(ticker).history(period="5d").dropna()
                if len(hist) >= 2:
                    current    = hist['Close'].iloc[-1]
                    prev       = hist['Close'].iloc[-2]
                    change_pct = ((current - prev) / prev) * 100
                    week_change = ((current - hist['Close'].iloc[0]) / hist['Close'].iloc[0]) * 100
                    indicators[name] = {
                        "value":        round(current, 2),
                        "change_pct":   round(change_pct, 2),
                        "week_change":  round(week_change, 2),
                    }
            except:
                pass
            time.sleep(0.1)

        return indicators

    async def analyze_macro_context(self, news_list):
        """
        AI가 뉴스 + 지표 보고
        현재 매크로 상황 스스로 파악
        → 투자 전략 자동 조정
        """
        from anthropic import Anthropic
        client = Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))

        # 시장 지표 수집
        indicators = self.get_market_indicators()

        indicators_text = ""
        for name, data in indicators.items():
            arrow = "▲" if data['change_pct'] > 0 else "▼"
            indicators_text += f"{name}: {data['value']} ({arrow}{data['change_pct']:+.2f}% / 주간{data['week_change']:+.2f}%)\n"

        # 뉴스 텍스트
        news_text = ""
        for i, n in enumerate(news_list[:20]):
            importance = n.get('importance', '')
            emoji      = "🔴" if importance == "high" else "🟡"
            news_text += f"{emoji} {n['title']}\n"

        prompt = f"""당신은 글로벌 매크로 전략가입니다.
오늘 시장 지표와 뉴스를 분석해서 현재 상황을 파악하고 투자 전략을 제시해주세요.

=== 시장 지표 ===
{indicators_text}

=== 오늘 주요 뉴스 ===
{news_text}

다음을 분석해주세요:

1. 현재 글로벌 매크로 상황
   (지금 세계에서 무슨 일이 일어나고 있는지 핵심 파악)

2. 시장에 가장 큰 영향을 주는 요인 TOP3
   (금리/전쟁/환율/원자재 등 중 현재 가장 중요한 것)

3. 이 상황에서 유리한 섹터/자산
4. 이 상황에서 불리한 섹터/자산
5. 한국 투자자 전략 (공격적/중립/방어적)
6. 단기 리스크 요인
7. 오늘 핵심 한줄 요약

JSON으로만 답변:
{{
  "situation": "현재 상황 두줄 요약",
  "top_factors": ["요인1", "요인2", "요인3"],
  "favorable_sectors": ["섹터1", "섹터2", "섹터3"],
  "unfavorable_sectors": ["섹터1", "섹터2"],
  "strategy": "공격적/중립/방어적",
  "strategy_reason": "전략 이유 한줄",
  "risk_factors": ["리스크1", "리스크2"],
  "summary": "오늘 핵심 한줄",
  "us_strategy": "미국장 전략 한줄",
  "kr_strategy": "한국장 전략 한줄"
}}"""

        try:
            res  = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=1000,
                messages=[{"role": "user", "content": prompt}]
            )
            text = res.content[0].text.strip()
            import re
            text = re.sub(r'```json|```', '', text).strip()
            m    = re.search(r'\{.*\}', text, re.DOTALL)
            if m:
                context = json.loads(m.group())
                context['indicators']  = indicators
                context['updated']     = datetime.now().isoformat()
                self._save_context(context)
                self.context = context
                print(f"  ✅ 매크로 상황 파악 완료: {context.get('summary', '')}")
                return context
        except Exception as e:
            print(f"  ❌ 매크로 분석 실패: {e}")

        return self.context

    def get_current_context(self):
        """현재 저장된 매크로 컨텍스트"""
        return self.context

    def build_briefing_message(self, context):
        """아침 브리핑용 매크로 메시지"""
        if not context:
            return "⚠️ 매크로 데이터 없음"

        strategy    = context.get('strategy', '중립')
        strategy_emoji = {
            "공격적": "🚀",
            "중립":   "➡️",
            "방어적": "🛡️"
        }.get(strategy, "➡️")

        favorable   = context.get('favorable_sectors', [])
        unfavorable = context.get('unfavorable_sectors', [])
        factors     = context.get('top_factors', [])
        risks       = context.get('risk_factors', [])
        indicators  = context.get('indicators', {})

        msg  = f"🌍 <b>오늘의 매크로 상황</b> {datetime.now().strftime('%m/%d %H:%M')}\n\n"
        msg += f"📋 <b>현재 상황</b>\n{context.get('situation', '')}\n\n"

        msg += f"⚡ <b>핵심 변수 TOP3</b>\n"
        for f in factors:
            msg += f"  • {f}\n"

        msg += f"\n{strategy_emoji} <b>오늘 전략: {strategy}</b>\n"
        msg += f"  {context.get('strategy_reason', '')}\n\n"

        msg += f"🇰🇷 <b>한국장</b>: {context.get('kr_strategy', '')}\n"
        msg += f"🇺🇸 <b>미국장</b>: {context.get('us_strategy', '')}\n\n"

        if indicators:
            msg += "📊 <b>핵심 지표</b>\n"
            key_indicators = ['나스닥선물', 'VIX', '달러인덱스', '금', '유가', '국채10년']
            for name in key_indicators:
                if name in indicators:
                    d     = indicators[name]
                    arrow = "▲" if d['change_pct'] > 0 else "▼"
                    msg  += f"  {name}: {d['value']} {arrow}{d['change_pct']:+.2f}%\n"

        if favorable:
            msg += f"\n✅ <b>유리한 섹터</b>: {' / '.join(favorable)}\n"
        if unfavorable:
            msg += f"❌ <b>불리한 섹터</b>: {' / '.join(unfavorable)}\n"

        if risks:
            msg += f"\n⚠️ <b>리스크</b>\n"
            for r in risks:
                msg += f"  • {r}\n"

        msg += f"\n💡 <b>오늘 핵심</b>: {context.get('summary', '')}"
        msg += f"\n⏰ {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        return msg

if __name__ == "__main__":
    import asyncio
    from modules.news_collector import NewsCollector

    async def test():
        print("=" * 50)
        print("🌍 매크로 분석 테스트")
        print("=" * 50)
        nc       = NewsCollector()
        news     = nc.collect_news(max_per_feed=5)
        filtered = nc.filter_by_importance(news)
        ma       = MacroAnalyzer()
        context  = await ma.analyze_macro_context(filtered)
        msg      = ma.build_briefing_message(context)
        print(msg)

    asyncio.run(test())
