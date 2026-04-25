import os
import sys
import json
import time
from datetime import datetime
from dotenv import load_dotenv

sys.path.insert(0, '/home/dps/stock_ai')
load_dotenv('/home/dps/stock_ai/.env')

# 미국 섹터 ETF
SECTOR_ETFS = {
    "기술":   "XLK",
    "반도체": "SMH",
    "에너지": "XLE",
    "금융":   "XLF",
    "헬스케어": "XLV",
    "유틸리티": "XLU",
    "산업재": "XLI",
    "혁신성장": "ARKK",
}

# 섹터 ETF → 한국 연관 섹터 매핑
ETF_KR_MAPPING = {
    "XLK":  ["AI반도체", "소프트웨어", "IT서비스"],
    "SMH":  ["AI반도체", "반도체소부장"],
    "XLE":  ["에너지", "정유화학"],
    "XLF":  ["금융", "은행"],
    "XLV":  ["바이오", "헬스케어"],
    "XLU":  ["전력", "원전", "유틸리티"],
    "XLI":  ["방산", "조선", "산업재"],
    "ARKK": ["양자컴퓨터", "우주항공", "AI신약"],
}


class MarketTemperature:
    """
    레이어 1: 시장 온도 체크 + AI 섹터 선정
    - 글로벌 매크로 수집
    - 미국 섹터 ETF 흐름 분석
    - 한국 시장 온도 체크
    - AI가 오늘 주력 섹터 3개 선정
    """

    def __init__(self):
        self._context = None  # 캐시

    # ── 데이터 수집 ────────────────────────────────

    def get_global_macro(self):
        """글로벌 매크로 데이터 수집"""
        import yfinance as yf
        macro = {}

        tickers = {
            "나스닥":    "^IXIC",
            "S&P500":   "^GSPC",
            "나스닥선물": "NQ=F",
            "VIX":      "^VIX",
            "달러인덱스": "DX-Y.NYB",
            "미국10년채권": "^TNX",
            "금":       "GC=F",
            "WTI원유":  "CL=F",
            "코스피":   "^KS11",
            "코스닥":   "^KQ11",
        }

        for name, ticker in tickers.items():
            try:
                hist = yf.Ticker(ticker).history(period="5d").dropna()
                if len(hist) >= 2:
                    curr   = hist['Close'].iloc[-1]
                    prev   = hist['Close'].iloc[-2]
                    change = ((curr - prev) / prev) * 100
                    macro[name] = {
                        "current": round(curr, 2),
                        "change":  round(change, 2)
                    }
                time.sleep(0.1)
            except:
                pass

        return macro

    def get_sector_etf_flow(self):
        """미국 섹터 ETF 자금 흐름 분석"""
        import yfinance as yf
        etf_data = {}

        for sector, ticker in SECTOR_ETFS.items():
            try:
                hist = yf.Ticker(ticker).history(period="5d").dropna()
                if len(hist) >= 2:
                    curr      = hist['Close'].iloc[-1]
                    prev      = hist['Close'].iloc[-2]
                    change    = ((curr - prev) / prev) * 100
                    week_change = ((curr - hist['Close'].iloc[0]) / hist['Close'].iloc[0]) * 100

                    # 거래량 추세
                    avg_vol   = hist['Volume'].mean()
                    curr_vol  = hist['Volume'].iloc[-1]
                    vol_ratio = round(curr_vol / avg_vol, 1) if avg_vol > 0 else 1

                    etf_data[sector] = {
                        "ticker":      ticker,
                        "change":      round(change, 2),
                        "week_change": round(week_change, 2),
                        "vol_ratio":   vol_ratio,
                        "inflow":      change > 0 and vol_ratio >= 1.2,  # 자금 유입 신호
                    }
                time.sleep(0.1)
            except:
                pass

        return etf_data

    def get_kr_market_temperature(self):
        """한국 시장 온도 체크"""
        try:
            from modules.kis_api import KISApi
            import yfinance as yf
            kis  = KISApi()
            temp = {}

            # 코스피 선물 방향
            try:
                fut  = yf.Ticker("^KS11").history(period="2d").dropna()
                if len(fut) >= 2:
                    temp['kospi_change'] = round(
                        ((fut['Close'].iloc[-1] - fut['Close'].iloc[-2]) / fut['Close'].iloc[-2]) * 100, 2
                    )
                    temp['kospi'] = round(fut['Close'].iloc[-1], 2)
            except:
                pass

            # 외국인 전체 순매수 방향 (삼성전자로 대리 판단)
            try:
                from modules.supply_demand import SupplyDemand
                sd   = SupplyDemand()
                data = sd.analyze_supply("005930", "삼성전자")
                if data:
                    temp['foreign_direction'] = "매수" if data['foreign'] > 0 else "매도"
                    temp['foreign_consecutive'] = data['foreign_consecutive']
            except:
                temp['foreign_direction'] = "불명"

            # VIX
            try:
                vix = yf.Ticker("^VIX").history(period="2d").dropna()
                if not vix.empty:
                    temp['vix'] = round(vix['Close'].iloc[-1], 1)
            except:
                pass

            return temp
        except Exception as e:
            print(f"  ⚠️ 시장 온도 수집 실패: {e}")
            return {}

    # ── AI 섹터 선정 ───────────────────────────────

    async def select_sectors(self, regime_type="강세"):
        """AI가 오늘 주력 섹터 3개 선정"""
        from anthropic import Anthropic
        import re

        print(f"[{datetime.now().strftime('%H:%M')}] 🌡️ 시장 온도 체크 + 섹터 선정")

        # 데이터 수집
        macro    = self.get_global_macro()
        etf_flow = self.get_sector_etf_flow()
        kr_temp  = self.get_kr_market_temperature()

        # 매크로 텍스트
        macro_text = ""
        for name, data in macro.items():
            arrow = "▲" if data['change'] > 0 else "▼"
            macro_text += f"{name}: {arrow}{data['change']:+.2f}%\n"

        # ETF 흐름 텍스트
        etf_text = ""
        for sector, data in etf_flow.items():
            inflow = "💰유입" if data['inflow'] else ""
            etf_text += f"{sector}({data['ticker']}): {data['change']:+.2f}% 주간:{data['week_change']:+.2f}% 거래량:{data['vol_ratio']}배 {inflow}\n"

        # 한국 시장 온도
        kr_text = f"""
코스피: {kr_temp.get('kospi_change', 0):+.2f}%
외국인: {kr_temp.get('foreign_direction', '불명')} ({kr_temp.get('foreign_consecutive', 0)}일 연속)
VIX: {kr_temp.get('vix', 20)}
"""

        # 섹터 순환 사이클 컨텍스트
        cycle_context = """
한국 섹터 순환 패턴 (참고):
- 반도체 강세 → 반도체 소부장 → AI서버/전력 → 2차전지
- 정책 발표 → 관련 대장주 → 소부장 순서
- 외국인 매수 시작 → 대형주 → 중형주 → 소부장 2~3주 시차

미국 AI 사이클 (현재 진행 중):
- AI인프라(반도체) → 전력/데이터센터 → AI응용소프트웨어 → AI수혜산업
"""

        prompt = f"""오늘 한국 주식시장에서 주력 섹터를 선정해주세요.

=== 글로벌 매크로 ===
{macro_text}

=== 미국 섹터 ETF 흐름 ===
{etf_text}

=== 한국 시장 온도 ===
{kr_text}

=== 섹터 순환 사이클 ===
{cycle_context}

=== 현재 장세 ===
{regime_type}장

판단 기준:
1. ETF 자금 유입 섹터 우선
2. 섹터 순환 사이클상 다음 차례 섹터
3. 과열 섹터는 제외 (ETF 주간 +5% 이상 + 거래량 급증)
4. {regime_type}장에 맞는 섹터

JSON으로만:
{{
  "selected_sectors": [
    {{
      "kr_sector": "한국 섹터명",
      "etf": "연관 ETF",
      "reason": "선정 이유 한줄",
      "momentum": "강함/보통/약함",
      "caution": "주의사항 또는 없음"
    }}
  ],
  "market_outlook": "오늘 시장 한줄 전망",
  "overheated_sectors": ["과열 섹터1", "과열 섹터2"],
  "regime_confidence": "높음/보통/낮음"
}}"""

        try:
            client = Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))
            res    = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=800,
                messages=[{"role": "user", "content": prompt}]
            )
            text = res.content[0].text.strip()
            text = __import__('re').sub(r'```json|```', '', text).strip()
            m    = __import__('re').search(r'\{.*\}', text, __import__('re').DOTALL)
            if m:
                result = json.loads(m.group())
                # 캐시 저장
                self._context = {
                    "macro":        macro,
                    "etf_flow":     etf_flow,
                    "kr_temp":      kr_temp,
                    "ai_result":    result,
                    "regime":       regime_type,
                    "updated_at":   datetime.now().isoformat(),
                }
                print(f"  ✅ 섹터 선정 완료: {[s['kr_sector'] for s in result.get('selected_sectors', [])]}")
                return self._context
        except Exception as e:
            print(f"  ❌ 섹터 선정 실패: {e}")

        return None

    def get_current_context(self):
        """캐시된 컨텍스트 반환"""
        return self._context

    def get_selected_sector_names(self):
        """선정된 섹터 이름 목록"""
        if not self._context:
            return []
        result = self._context.get("ai_result", {})
        return [s["kr_sector"] for s in result.get("selected_sectors", [])]

    def get_overheated_sectors(self):
        """과열 섹터 목록"""
        if not self._context:
            return []
        result = self._context.get("ai_result", {})
        return result.get("overheated_sectors", [])

    def build_briefing_message(self):
        """시장 온도 + 섹터 선정 결과 메시지"""
        if not self._context:
            return "❌ 시장 분석 데이터 없음"

        macro     = self._context.get("macro", {})
        etf_flow  = self._context.get("etf_flow", {})
        kr_temp   = self._context.get("kr_temp", {})
        ai_result = self._context.get("ai_result", {})
        regime    = self._context.get("regime", "?")

        msg  = f"🌡️ <b>시장 온도 + 오늘 섹터</b> {datetime.now().strftime('%m/%d %H:%M')}\n\n"

        # 글로벌 매크로
        msg += "🌍 <b>글로벌 매크로</b>\n"
        for name in ["나스닥", "S&P500", "VIX", "달러인덱스", "미국10년채권"]:
            if name in macro:
                arrow = "▲" if macro[name]['change'] > 0 else "▼"
                msg  += f"  {arrow} {name}: {macro[name]['change']:+.2f}%\n"

        # ETF 흐름 (유입 섹터만)
        inflow_etfs = [(s, d) for s, d in etf_flow.items() if d['inflow']]
        if inflow_etfs:
            msg += "\n💰 <b>자금 유입 ETF</b>\n"
            for sector, data in inflow_etfs:
                msg += f"  ▲ {sector}({data['ticker']}): {data['change']:+.2f}%\n"

        # 한국 시장
        msg += f"\n🇰🇷 <b>한국 시장</b>\n"
        msg += f"  코스피: {kr_temp.get('kospi_change', 0):+.2f}%\n"
        msg += f"  외국인: {kr_temp.get('foreign_direction', '불명')} ({kr_temp.get('foreign_consecutive', 0)}일 연속)\n"
        msg += f"  VIX: {kr_temp.get('vix', 20)}\n"

        # AI 섹터 선정
        selected = ai_result.get("selected_sectors", [])
        if selected:
            msg += f"\n🎯 <b>오늘 주력 섹터</b>\n"
            for s in selected:
                momentum_emoji = {"강함": "🔥", "보통": "✅", "약함": "⚠️"}.get(s.get("momentum", "보통"), "✅")
                msg += f"  {momentum_emoji} <b>{s['kr_sector']}</b> — {s['reason']}\n"
                if s.get("caution") and s["caution"] != "없음":
                    msg += f"     ⚠️ {s['caution']}\n"

        # 과열 섹터
        overheated = ai_result.get("overheated_sectors", [])
        if overheated:
            msg += f"\n🌡️ <b>과열 주의</b> (신규 진입 금지)\n"
            for s in overheated:
                msg += f"  ❌ {s}\n"

        # 전망
        msg += f"\n💡 {ai_result.get('market_outlook', '')}\n"
        msg += f"📊 장세 신뢰도: {ai_result.get('regime_confidence', '?')}\n"
        msg += f"\n⏰ {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        return msg
