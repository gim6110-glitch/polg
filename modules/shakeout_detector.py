import os
import sys
import json
import time
from datetime import datetime, timedelta
from dotenv import load_dotenv

sys.path.insert(0, '/home/dps/stock_ai')
load_dotenv('/home/dps/stock_ai/.env')

SHAKEOUT_FILE = "/home/dps/stock_ai/data/shakeout_alerts.json"


class ShakeoutDetector:
    """
    세력 흔들기 감지
    - ATR 기반 하락 감지
    - 거래량 패턴으로 흔들기 vs 진짜 하락 구분
    - 매수 후 3거래일 이내는 진입 실패 가능성 알림
    - 매수 후 4거래일 이상은 세력 흔들기 판단
    - 쿨다운 4시간
    """

    def __init__(self):
        self.alert_history = self._load_alerts()

    def _load_alerts(self):
        if os.path.exists(SHAKEOUT_FILE):
            with open(SHAKEOUT_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}

    def _save_alerts(self):
        os.makedirs(os.path.dirname(SHAKEOUT_FILE), exist_ok=True)
        with open(SHAKEOUT_FILE, "w", encoding="utf-8") as f:
            json.dump(self.alert_history, f, ensure_ascii=False, indent=2)

    def _can_alert(self, key, cooldown_hours=4):
        if key in self.alert_history:
            last = datetime.fromisoformat(self.alert_history[key])
            diff = (datetime.now() - last).total_seconds() / 3600
            if diff < cooldown_hours:
                return False
        self.alert_history[key] = datetime.now().isoformat()
        self._save_alerts()
        return True

    # ── 데이터 수집 ────────────────────────────────

    def _get_stock_data(self, ticker, market):
        """기술적 데이터 수집"""
        try:
            import yfinance as yf
            yf_ticker = f"{ticker}.KS" if market == "KR" else ticker
            hist      = yf.Ticker(yf_ticker).history(period="30d").dropna()

            if len(hist) < 10:
                return None

            close  = hist['Close']
            volume = hist['Volume']
            high   = hist['High']
            low    = hist['Low']

            # ATR 계산 (14일)
            tr_list = []
            for i in range(1, len(hist)):
                tr = max(
                    high.iloc[i] - low.iloc[i],
                    abs(high.iloc[i] - close.iloc[i-1]),
                    abs(low.iloc[i] - close.iloc[i-1])
                )
                tr_list.append(tr)
            atr = sum(tr_list[-14:]) / 14 if len(tr_list) >= 14 else sum(tr_list) / len(tr_list)

            # 현재 거래량 vs 평균
            avg_vol   = volume.iloc[:-1].mean()
            curr_vol  = volume.iloc[-1]
            vol_ratio = round(curr_vol / avg_vol, 2) if avg_vol > 0 else 1

            # 5일 주가 흐름
            price_5d = close.tail(5).tolist()

            # 52주 위치
            high_52w      = close.max()
            low_52w       = close.min()
            curr_price    = close.iloc[-1]
            position_52w  = round(((curr_price - low_52w) / (high_52w - low_52w)) * 100, 1) if high_52w != low_52w else 50

            # 당일 하락률
            prev_close  = close.iloc[-2]
            day_change  = ((curr_price - prev_close) / prev_close) * 100

            # ATR 대비 하락 비율
            atr_ratio = abs(curr_price - prev_close) / atr if atr > 0 else 0

            return {
                "current_price": round(curr_price, 2),
                "prev_close":    round(prev_close, 2),
                "day_change":    round(day_change, 2),
                "atr":           round(atr, 2),
                "atr_ratio":     round(atr_ratio, 2),
                "vol_ratio":     vol_ratio,
                "avg_vol":       round(avg_vol, 0),
                "curr_vol":      round(curr_vol, 0),
                "price_5d":      [round(p, 2) for p in price_5d],
                "position_52w":  position_52w,
                "high_52w":      round(high_52w, 2),
                "low_52w":       round(low_52w, 2),
            }
        except Exception as e:
            print(f"  ⚠️ {ticker} 데이터 수집 실패: {e}")
            return None

    def _get_supply_data(self, ticker, market):
        """수급 데이터 수집"""
        if market != "KR":
            return None
        try:
            from modules.supply_demand import SupplyDemand
            sd   = SupplyDemand()
            data = sd.analyze_supply(ticker, ticker)
            return data
        except:
            return None

    def _get_sector_stocks_change(self, sector):
        """섹터 내 다른 종목들 등락 확인 (동반 하락 여부)"""
        try:
            from modules.sector_db import SECTOR_DB
            import yfinance as yf

            changes = []
            for sector_name, sector_data in SECTOR_DB.items():
                if sector.lower() not in sector_name.lower():
                    continue
                for tier in ['대장주', '2등주']:
                    for name, ticker in list(sector_data.get(tier, {}).items())[:3]:
                        try:
                            hist = yf.Ticker(f"{ticker}.KS").history(period="2d").dropna()
                            if len(hist) >= 2:
                                change = ((hist['Close'].iloc[-1] - hist['Close'].iloc[-2]) / hist['Close'].iloc[-2]) * 100
                                changes.append(change)
                        except:
                            pass
                        time.sleep(0.1)
                break

            if changes:
                avg_change = sum(changes) / len(changes)
                return round(avg_change, 2)
        except:
            pass
        return None

    def _get_days_since_buy(self, buy_date_str):
        """매수 후 경과 거래일 수"""
        try:
            buy_date = datetime.strptime(buy_date_str, "%Y-%m-%d")
            delta    = datetime.now() - buy_date
            return delta.days
        except:
            return 999

    # ── 핵심 감지 로직 ─────────────────────────────

    def detect(self, ticker, stock_info):
        """
        세력 흔들기 감지 메인 함수
        returns: None (감지 없음) or dict (감지 결과)
        """
        market    = stock_info.get('market', 'KR')
        hold_type = stock_info.get('hold_type', '장기')
        buy_date  = stock_info.get('buy_date', '')
        name      = stock_info.get('name', ticker)

        # 도박/초장기는 손절 없으니 흔들기 감지 불필요
        if hold_type in ['초장기', '도박']:
            return None

        # 데이터 수집
        data = self._get_stock_data(ticker, market)
        if not data:
            return None

        day_change = data['day_change']
        atr_ratio  = data['atr_ratio']
        vol_ratio  = data['vol_ratio']

        # 하락이 아니면 감지 불필요
        if day_change >= 0:
            return None

        # ATR 1.5배 이상 하락만 감지
        if atr_ratio < 1.5:
            return None

        # 쿨다운 체크
        key = f"shakeout_{ticker}"
        if not self._can_alert(key, cooldown_hours=4):
            return None

        # 매수 후 경과일 확인
        days_since_buy = self._get_days_since_buy(buy_date)

        # 즉시 손절 조건 (거래량 150% 이상 + 하락)
        if vol_ratio >= 1.5:
            return {
                "type":           "즉시손절",
                "ticker":         ticker,
                "name":           name,
                "market":         market,
                "day_change":     day_change,
                "vol_ratio":      vol_ratio,
                "atr_ratio":      atr_ratio,
                "data":           data,
                "days_since_buy": days_since_buy,
                "needs_ai":       False,
            }

        # 매수 후 3거래일 이내 → 진입 실패 가능성
        if days_since_buy <= 3:
            return {
                "type":           "진입실패가능성",
                "ticker":         ticker,
                "name":           name,
                "market":         market,
                "day_change":     day_change,
                "vol_ratio":      vol_ratio,
                "atr_ratio":      atr_ratio,
                "data":           data,
                "days_since_buy": days_since_buy,
                "needs_ai":       False,
            }

        # 거래량 70% 이하 + 하락 → AI 판단 요청
        if vol_ratio <= 0.7:
            return {
                "type":           "AI판단요청",
                "ticker":         ticker,
                "name":           name,
                "market":         market,
                "day_change":     day_change,
                "vol_ratio":      vol_ratio,
                "atr_ratio":      atr_ratio,
                "data":           data,
                "days_since_buy": days_since_buy,
                "needs_ai":       True,
            }

        return None

    # ── AI 판단 ────────────────────────────────────

    async def ai_judge(self, detection, stock_info, news_list=None):
        """AI한테 흔들기 vs 진짜 하락 판단 요청"""
        from anthropic import Anthropic

        ticker  = detection['ticker']
        name    = detection['name']
        market  = detection['market']
        data    = detection['data']

        # 수급 데이터
        supply_text = "수급 데이터 없음"
        supply      = self._get_supply_data(ticker, market)
        if supply:
            supply_text = f"외국인 {supply['foreign_consecutive']}일 연속 {'순매수' if supply['foreign'] > 0 else '순매도'}, 기관 {supply['organ_consecutive']}일 연속 {'순매수' if supply['organ'] > 0 else '순매도'}"

        # 섹터 동반 하락 여부
        sector       = stock_info.get('sector', '')
        sector_change = self._get_sector_stocks_change(sector)
        sector_text  = f"섹터 평균 {sector_change:+.1f}%" if sector_change is not None else "섹터 데이터 없음"

        # 5일 주가 흐름
        price_5d    = data.get('price_5d', [])
        price_trend = "하락 추세" if len(price_5d) >= 3 and price_5d[-1] < price_5d[-3] else "상승/횡보 추세"

        # 뉴스
        news_text = "뉴스 없음"
        if news_list:
            relevant = [n for n in news_list if name in n.get('title', '') or ticker in n.get('title', '')]
            if relevant:
                news_text = "\n".join([f"- {n['title'][:60]}" for n in relevant[:3]])

        prompt = f"""보유 종목의 하락이 세력 흔들기인지 진짜 하락인지 판단해주세요.

=== 종목 정보 ===
종목: {name} ({ticker})
매수 후 {detection['days_since_buy']}일 경과

=== 오늘 하락 데이터 ===
당일 등락: {data['day_change']:+.2f}%
ATR 대비: {data['atr_ratio']:.1f}배 하락 (평소보다 {data['atr_ratio']:.1f}배 큰 하락)
거래량: 평균 대비 {data['vol_ratio']:.1f}배 (적은 거래량)
52주 위치: {data['position_52w']}% (0%=52주저점, 100%=52주고점)

=== 5일 주가 흐름 ===
{price_5d}
흐름: {price_trend}

=== 수급 ===
{supply_text}

=== 섹터 동반 하락 ===
{sector_text}

=== 관련 뉴스 ===
{news_text}

판단 기준:
- 흔들기: 거래량 적음 + 섹터 혼자 빠짐 + 수급 양호 + 뉴스 없음
- 진짜 하락: 섹터 동반 하락 or 악재 뉴스 or 수급 악화 or 추세적 하락

JSON으로만:
{{
  "judgment": "흔들기 or 진짜하락",
  "confidence": "높음 or 보통 or 낮음",
  "reason": "판단 이유 한줄",
  "action": "홀딩 or 손절고려 or 추가매수기회",
  "risk": "낮음 or 보통 or 높음"
}}"""

        try:
            client = Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))
            res    = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=300,
                messages=[{"role": "user", "content": prompt}]
            )
            import re, json as _json
            text = re.sub(r'```json|```', '', res.content[0].text.strip()).strip()
            m    = re.search(r'\{.*\}', text, re.DOTALL)
            if m:
                return _json.loads(m.group())
        except Exception as e:
            print(f"  ❌ AI 판단 실패: {e}")
        return None

    # ── 메시지 생성 ────────────────────────────────

    def build_alert_message(self, detection, ai_result=None):
        """세력 흔들기 알림 메시지"""
        name      = detection['name']
        ticker    = detection['ticker']
        market    = detection['market']
        currency  = "$" if market == "US" else "₩"
        data      = detection['data']
        det_type  = detection['type']

        if det_type == "즉시손절":
            msg  = f"🚨 <b>[즉시 손절 신호] {name}</b> ({ticker})\n\n"
            msg += f"💰 현재가: {currency}{data['current_price']:,}\n"
            msg += f"📉 당일: {data['day_change']:+.2f}%\n"
            msg += f"📦 거래량: 평균 대비 {data['vol_ratio']}배 급증\n"
            msg += f"⚡ ATR {data['atr_ratio']:.1f}배 하락\n\n"
            msg += f"⚠️ 거래량 폭발하며 하락 → 즉시 손절 고려\n"

        elif det_type == "진입실패가능성":
            msg  = f"⚠️ <b>[진입 실패 가능성] {name}</b> ({ticker})\n\n"
            msg += f"💰 현재가: {currency}{data['current_price']:,}\n"
            msg += f"📉 당일: {data['day_change']:+.2f}%\n"
            msg += f"📅 매수 후 {detection['days_since_buy']}일 (진입 초기)\n\n"
            msg += f"💡 매수 초기 하락 → 진입 타이밍 재점검 필요\n"
            msg += f"   손절선 재확인 후 판단하세요\n"

        else:  # AI판단요청
            if ai_result:
                judgment  = ai_result.get('judgment', '?')
                action    = ai_result.get('action', '?')
                reason    = ai_result.get('reason', '')
                confidence = ai_result.get('confidence', '')
                risk      = ai_result.get('risk', '')

                if judgment == "흔들기":
                    emoji = "💪"
                    title = "세력 흔들기 감지"
                else:
                    emoji = "⚠️"
                    title = "진짜 하락 가능성"

                msg  = f"{emoji} <b>[{title}] {name}</b> ({ticker})\n\n"
                msg += f"💰 현재가: {currency}{data['current_price']:,}\n"
                msg += f"📉 당일: {data['day_change']:+.2f}%\n"
                msg += f"📦 거래량: 평균 대비 {data['vol_ratio']}배 (적음)\n"
                msg += f"⚡ ATR {data['atr_ratio']:.1f}배 하락\n\n"
                msg += f"🤖 <b>AI 판단: {judgment}</b> (신뢰도: {confidence})\n"
                msg += f"💡 {reason}\n"
                msg += f"📌 행동: {action} | 리스크: {risk}\n"
            else:
                msg  = f"⚠️ <b>[하락 감지] {name}</b> ({ticker})\n\n"
                msg += f"💰 현재가: {currency}{data['current_price']:,}\n"
                msg += f"📉 당일: {data['day_change']:+.2f}%\n"
                msg += f"📦 거래량: 평균 대비 {data['vol_ratio']}배\n"
                msg += f"💡 거래량 적은 하락 → 관망 권고\n"

        msg += f"\n⏰ {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        return msg

    # ── 전체 포트폴리오 스캔 ───────────────────────

    async def scan_portfolio(self, portfolio, news_list=None):
        """포트폴리오 전체 세력 흔들기 스캔"""
        results = []

        for ticker, stock in portfolio.items():
            if not isinstance(stock, dict):
                continue
            if stock.get('hold_type') in ['초장기', '도박']:
                continue

            detection = self.detect(ticker, stock)
            if not detection:
                continue

            print(f"  🔍 {stock['name']} 하락 감지: {detection['type']}")

            # AI 판단 필요한 경우
            ai_result = None
            if detection['needs_ai']:
                ai_result = await self.ai_judge(detection, stock, news_list)

            results.append({
                "detection": detection,
                "ai_result": ai_result,
            })
            time.sleep(0.2)

        return results
