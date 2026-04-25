import sys
import os
import asyncio
import yfinance as yf
import pandas as pd
from datetime import datetime

sys.path.insert(0, '/home/dps/stock_ai')
from modules.kis_api import KISApi
from modules.ai_analyzer import AIAnalyzer

class RealtimeMonitor:
    def __init__(self, alert_callback, monitor, regime):
        self.alert_callback = alert_callback
        self.monitor        = monitor
        self.regime         = regime
        self.alert_history  = {}
        self.running        = False
        self.kis            = KISApi()
        self.ai             = AIAnalyzer()

        self.watch_kr = {
            "삼성전자":           "005930",
            "SK하이닉스":         "000660",
            "한화에어로스페이스":  "012450",
            "현대차":             "005380",
            "LG에너지솔루션":     "373220",
            "카카오":             "035720",
            "NAVER":              "035420",
            "셀트리온":           "068270",
            "기아":               "000270",
            "삼성바이오로직스":   "207940",
            "에코프로비엠":       "247540",
            "포스코퓨처엠":       "003670",
            "한국항공우주":       "047810",
            "현대로템":           "064350",
            "두산에너빌리티":     "034020",
        }
        self.watch_us = {
            "NVIDIA":    ("NVDA", "NAS"),
            "Apple":     ("AAPL", "NAS"),
            "Tesla":     ("TSLA", "NAS"),
            "Microsoft": ("MSFT", "NAS"),
            "AMD":       ("AMD",  "NAS"),
            "META":      ("META", "NAS"),
            "Google":    ("GOOGL","NAS"),
            "TSMC":      ("TSM",  "NYS"),
            "Amazon":    ("AMZN", "NAS"),
        }
        self.prev_prices = {}

    def _can_alert(self, key, cooldown_min=30):
        if key in self.alert_history:
            diff = (datetime.now() - self.alert_history[key]).total_seconds() / 60
            if diff < cooldown_min:
                return False
        self.alert_history[key] = datetime.now()
        return True

    def _calc_trade_levels(self, current_price, change_pct, signal_type, is_kr=True):
        """매수가/목표가/손절가 자동 계산"""
        # 급등 중인 경우 눌림목 기다리는 전략
        if change_pct >= 8:
            # 상한가 근접 → 눌림목 대기
            buy1       = round(current_price * 0.97, -2 if is_kr else 0)
            buy2       = round(current_price * 0.94, -2 if is_kr else 0)
            target1    = round(current_price * 1.05, -2 if is_kr else 0)
            target2    = round(current_price * 1.12, -2 if is_kr else 0)
            stop_loss  = round(current_price * 0.93, -2 if is_kr else 0)
            strategy   = "눌림목 대기 후 진입"
            timing     = "지금 바로 매수 금지 → 3~5% 눌림목 후 진입"
        elif change_pct >= 5:
            buy1       = round(current_price * 0.98, -2 if is_kr else 0)
            buy2       = round(current_price * 0.95, -2 if is_kr else 0)
            target1    = round(current_price * 1.05, -2 if is_kr else 0)
            target2    = round(current_price * 1.10, -2 if is_kr else 0)
            stop_loss  = round(current_price * 0.94, -2 if is_kr else 0)
            strategy   = "소량 진입 + 눌림목 추가 매수"
            timing     = "지금 소량(30%) 진입 → 눌림목에 추가(70%)"
        elif change_pct >= 2:
            buy1       = round(current_price * 0.99, -2 if is_kr else 0)
            buy2       = round(current_price * 0.96, -2 if is_kr else 0)
            target1    = round(current_price * 1.05, -2 if is_kr else 0)
            target2    = round(current_price * 1.10, -2 if is_kr else 0)
            stop_loss  = round(current_price * 0.95, -2 if is_kr else 0)
            strategy   = "분할 매수 진입"
            timing     = "지금 50% 진입 → 눌림목에 나머지 50%"
        else:
            # 저점 신호
            buy1       = round(current_price, -2 if is_kr else 0)
            buy2       = round(current_price * 0.97, -2 if is_kr else 0)
            target1    = round(current_price * 1.07, -2 if is_kr else 0)
            target2    = round(current_price * 1.15, -2 if is_kr else 0)
            stop_loss  = round(current_price * 0.93, -2 if is_kr else 0)
            strategy   = "저점 분할 매수"
            timing     = "지금 바로 1차 진입 가능"

        return {
            "buy1":      buy1,
            "buy2":      buy2,
            "target1":   target1,
            "target2":   target2,
            "stop_loss": stop_loss,
            "strategy":  strategy,
            "timing":    timing,
            "target1_pct": round(((target1 - current_price) / current_price) * 100, 1),
            "target2_pct": round(((target2 - current_price) / current_price) * 100, 1),
            "stop_pct":    round(((stop_loss - current_price) / current_price) * 100, 1),
        }

    def _get_ai_recommendation(self, name, ticker, current_price, change_pct, volume, signals, regime_type):
        """AI 매수 추천 점수 계산"""
        score = 0

        # 장세 반영
        if regime_type == '강세':
            score += 2
        elif regime_type == '중립':
            score += 1
        elif regime_type in ['약세초입', '약세']:
            score -= 2

        # 급등 신호
        if 5 <= change_pct <= 15:
            score += 2
        elif change_pct > 20:
            score += 1  # 너무 많이 오르면 리스크
        elif change_pct < 0:
            score -= 1

        # 거래량
        if volume > 500000:
            score += 2
        elif volume > 200000:
            score += 1

        # 신호 수
        score += min(len(signals), 3)

        # 별점 변환
        if score >= 8:
            stars      = "★★★★★"
            action     = "강력 매수 추천"
            confidence = "높음"
        elif score >= 6:
            stars      = "★★★★☆"
            action     = "매수 추천"
            confidence = "중상"
        elif score >= 4:
            stars      = "★★★☆☆"
            action     = "소량 진입 고려"
            confidence = "중간"
        elif score >= 2:
            stars      = "★★☆☆☆"
            action     = "관망 추천"
            confidence = "낮음"
        else:
            stars      = "★☆☆☆☆"
            action     = "보류"
            confidence = "매우 낮음"

        return {
            "stars":      stars,
            "action":     action,
            "confidence": confidence,
            "score":      score
        }

    async def _check_kr_signals(self, name, code, regime_type):
        data = self.kis.get_kr_price(code)
        if not data:
            return

        current    = data['price']
        change_pct = data['change_pct']
        volume     = data['volume']
        signals    = []
        urgency    = 0
        alert_key  = None

        prev_key    = f"prev_{code}"
        min5_change = 0
        if prev_key in self.prev_prices:
            prev        = self.prev_prices[prev_key]
            min5_change = ((current - prev) / prev) * 100
        self.prev_prices[prev_key] = current

        # 신호 감지
        if min5_change >= 3:
            signals.append(f"🔥 5분 급등 {min5_change:+.1f}%")
            urgency   += 3
            alert_key = f"{code}_급등_5m"

        if change_pct >= 8:
            signals.append(f"🚀 당일 {change_pct:+.1f}% 급등 (상한가 접근)")
            urgency   += 4
            alert_key = alert_key or f"{code}_급등_일"
        elif change_pct >= 5:
            signals.append(f"📈 당일 {change_pct:+.1f}% 강세")
            urgency   += 3
            alert_key = alert_key or f"{code}_급등_일"

        if change_pct >= 28:
            signals.append("🏆 상한가 도달")
            urgency   += 3

        if volume >= 1000000:
            signals.append(f"💥 거래량 {volume:,} (폭발적)")
            urgency   += 2
        elif volume >= 500000:
            signals.append(f"📊 거래량 {volume:,} (강세)")
            urgency   += 1

        # 급락 경고
        if min5_change <= -3:
            signals.append(f"🔴 5분 급락 {min5_change:+.1f}%")
            urgency   += 3
            alert_key = f"{code}_급락_5m"
        if change_pct <= -5:
            signals.append(f"🚨 당일 {change_pct:+.1f}% 급락")
            urgency   += 3
            alert_key = f"{code}_급락_일"

        if urgency >= 3 and alert_key and signals:
            cooldown = 10 if urgency >= 6 else 20 if urgency >= 4 else 30
            if self._can_alert(alert_key, cooldown_min=cooldown):
                await self._send_kr_alert(
                    name, code, data, signals, urgency,
                    min5_change, regime_type
                )

    async def _send_kr_alert(self, name, code, data, signals, urgency, min5_change, regime_type):
        current    = data['price']
        change_pct = data['change_pct']
        volume     = data['volume']
        is_drop    = change_pct <= -5 or min5_change <= -3

        # 급락이면 다른 메시지
        if is_drop:
            arrow = "▼"
            msg   = f"""🚨 <b>[급락 경고] {name}</b> ({code})

💰 현재가: {current:,}원
{arrow} 당일: {change_pct:+.2f}%
⚡ 5분: {min5_change:+.1f}%

⚠️ <b>보유 중이라면:</b>
📉 손절 고려선: {round(current * 0.95, -2):,}원
🤔 판단 기준:
  • 거래량 많으면 → 손절 고려
  • 거래량 적으면 → 세력 털기 가능성
  • 공시 확인 필수

⏰ {data['timestamp']}
💡 <i>MTS에서 공시/뉴스 먼저 확인하세요</i>"""
            await self.alert_callback(msg)
            return

        # 급등 신호 → 매수 가이드 포함
        levels = self._calc_trade_levels(current, change_pct, "급등", is_kr=True)
        rec    = self._get_ai_recommendation(
            name, code, current, change_pct, volume, signals, regime_type
        )

        if urgency >= 6:
            header = "🚨 <b>[긴급]"
        elif urgency >= 4:
            header = "⚡ <b>[중요]"
        else:
            header = "🔔 <b>[알림]"

        regime_emoji = {"강세": "🚀", "중립": "➡️", "약세초입": "⚠️", "약세": "🔴"}.get(regime_type, "")
        signals_text = "\n".join(signals)

        msg = f"""{header} {name}</b> ({code}) {regime_emoji}

💰 현재가: {current:,}원
▲ 당일: {change_pct:+.2f}% | ⚡5분: {min5_change:+.1f}%
📦 거래량: {volume:,}

📊 <b>감지 신호:</b>
{signals_text}

━━━━━━━━━━━━━━━━━━━
🤖 <b>AI 판단: {rec['action']} {rec['stars']}</b>
━━━━━━━━━━━━━━━━━━━

⏱ <b>진입 전략: {levels['strategy']}</b>
💡 {levels['timing']}

💚 <b>매수가</b>
  1차: {levels['buy1']:,}원
  2차: {levels['buy2']:,}원 (눌림목)

🎯 <b>목표가</b>
  1차: {levels['target1']:,}원 ({levels['target1_pct']:+.1f}%) → 절반 익절
  2차: {levels['target2']:,}원 ({levels['target2_pct']:+.1f}%) → 나머지 익절

🛑 <b>손절가: {levels['stop_loss']:,}원 ({levels['stop_pct']:+.1f}%)</b>
  → 이 가격 깨지면 미련없이 손절

⏰ {data['timestamp']}
💡 <i>최종 판단은 본인이 하세요</i>"""

        await self.alert_callback(msg)
        print(f"  📱 실시간 알림: {name} {rec['action']}")

    async def _check_us_signals(self, name, ticker, exchange, regime_type):
        data = self.kis.get_us_price(ticker, exchange)
        if not data or data['price'] == 0:
            return

        current    = data['price']
        change_pct = data['change_pct']
        signals    = []
        urgency    = 0
        alert_key  = None

        prev_key    = f"prev_us_{ticker}"
        min5_change = 0
        if prev_key in self.prev_prices:
            prev        = self.prev_prices[prev_key]
            min5_change = ((current - prev) / prev) * 100
        self.prev_prices[prev_key] = current

        if min5_change >= 2:
            signals.append(f"🔥 5분 급등 {min5_change:+.1f}%")
            urgency   += 3
            alert_key = f"{ticker}_급등_5m"

        if change_pct >= 4:
            signals.append(f"🚀 당일 {change_pct:+.1f}% 급등")
            urgency   += 3
            alert_key = alert_key or f"{ticker}_급등"

        if change_pct <= -4:
            signals.append(f"🚨 당일 {change_pct:+.1f}% 급락")
            urgency   += 3
            alert_key = f"{ticker}_급락"

        if urgency >= 3 and alert_key and signals:
            cooldown = 15 if urgency >= 5 else 30
            if self._can_alert(alert_key, cooldown_min=cooldown):
                is_drop = change_pct <= -4
                levels  = self._calc_trade_levels(current, change_pct, "급등", is_kr=False)
                rec     = self._get_ai_recommendation(
                    name, ticker, current, change_pct,
                    data.get('volume', 0), signals, regime_type
                )
                signals_text = "\n".join(signals)
                arrow        = "▼" if change_pct < 0 else "▲"

                if is_drop:
                    ai_action = "홀딩"
                    ai_reason = ""
                    ai_stop   = levels['stop_loss']
                    ai_recov  = round(current * 1.03, 2)
                    try:
                        # 포트폴리오 보유 여부 확인
                        import json as _json2, os as _os2
                        _pf_file = '/home/dps/stock_ai/data/portfolio.json'
                        _is_holding = False
                        _buy_price  = 0
                        if _os2.path.exists(_pf_file):
                            with open(_pf_file, 'r') as _f:
                                _pf = _json2.load(_f)
                            if ticker in _pf:
                                _is_holding = True
                                _buy_price  = _pf[ticker].get('buy_price', 0)

                        from anthropic import Anthropic
                        import os, re, json
                        _client = Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))
                        _holding_text = f"보유 중 (매수가: ${_buy_price})" if _is_holding else "미보유"
                        _action_guide = "손절/홀딩/추가매수 중 하나로 답하세요" if _is_holding else "진입기회/관망 중 하나로 답하세요"
                        _res = _client.messages.create(
                            model="claude-sonnet-4-5",
                            max_tokens=300,
                            messages=[{"role": "user", "content": f"""미국 주식 급락을 분석해주세요.

종목: {name} ({ticker})
현재가: ${current}
당일등락: {change_pct:+.1f}%
보유여부: {_holding_text}

{_action_guide}

반드시 JSON 형식으로만 답하세요:
{{"action": "진입기회 또는 관망", "reason": "구체적인 이유를 한줄로", "stop_loss": {round(current*0.93,2)}, "recovery_price": {round(current*1.05,2)}}}"""}]
                        )
                        _text = re.sub(r'```json|```', '', _res.content[0].text).strip()
                        _m = re.search(r'\{{.*\}}', _text, re.DOTALL)
                        if _m:
                            _ai = json.loads(_m.group())
                            ai_action = _ai.get('action', '홀딩')
                            ai_reason = _ai.get('reason', '')
                            ai_stop   = _ai.get('stop_loss', levels['stop_loss'])
                            ai_recov  = _ai.get('recovery_price', round(current * 1.03, 2))
                    except:
                        pass
                    action_emoji = {"손절": "🛑", "홀딩": "⏳", "추가매수": "✅", "진입기회": "🎯", "관망": "👀"}.get(ai_action, "⚠️")
                    holding_text = f"💼 보유 중 (매수가: ${_buy_price})" if _is_holding else "💼 미보유"
                    msg = f"""🚨 <b>[급락 경고] {name}</b> ({ticker})
💰 현재가: ${current}
▼ 당일: {change_pct:+.2f}% | ⚡5분: {min5_change:+.1f}%
{holding_text}

{action_emoji} <b>AI 판단: {ai_action}</b>
💡 {ai_reason}

🛑 손절선: ${ai_stop}
🔄 회복시 재진입: ${ai_recov}
⏰ {data['timestamp']}"""
                else:
                    msg = f"""⚡ <b>[미국장 알림] {name}</b> ({ticker})

💰 현재가: ${current:,}
{arrow} 당일: {change_pct:+.2f}% | ⚡5분: {min5_change:+.1f}%

📊 신호:
{signals_text}

━━━━━━━━━━━━━━━━━━━
🤖 <b>AI 판단: {rec['action']} {rec['stars']}</b>
━━━━━━━━━━━━━━━━━━━

⏱ <b>{levels['strategy']}</b>
💡 {levels['timing']}

💚 매수가: ${levels['buy1']:,} / ${levels['buy2']:,}
🎯 목표가: ${levels['target1']:,} ({levels['target1_pct']:+.1f}%) / ${levels['target2']:,} ({levels['target2_pct']:+.1f}%)
🛑 손절가: ${levels['stop_loss']:,} ({levels['stop_pct']:+.1f}%)

⏰ {data['timestamp']}
💡 <i>최종 판단은 본인이 하세요</i>"""

                await self.alert_callback(msg)
                print(f"  📱 미국 알림: {name} {rec['action']}")

    async def scan_once(self):
        r           = self.regime.current_regime
        regime_type = r.get('regime', '중립')
        hour        = datetime.now().hour

        if 9 <= hour < 16:
            print(f"[{datetime.now().strftime('%H:%M')}] ⚡ 한국장 실시간 스캔")
            for name, code in self.watch_kr.items():
                await self._check_kr_signals(name, code, regime_type)
                await asyncio.sleep(0.3)

        if hour >= 21 or hour < 4:
            print(f"[{datetime.now().strftime('%H:%M')}] ⚡ 미국장 실시간 스캔")
            for name, (ticker, exchange) in self.watch_us.items():
                await self._check_us_signals(name, ticker, exchange, regime_type)
                await asyncio.sleep(0.3)

    async def run_forever(self, interval_sec=300):
        self.running = True
        print(f"✅ 실시간 모니터 시작 (매 {interval_sec//60}분)")
        while self.running:
            try:
                hour    = datetime.now().hour
                kr_open = (9 <= hour < 16)
                us_open = (hour >= 21 or hour < 4)
                if kr_open or us_open:
                    await self.scan_once()
                else:
                    print(f"[{datetime.now().strftime('%H:%M')}] 💤 장 마감 대기 중")
            except Exception as e:
                print(f"❌ 실시간 스캔 오류: {e}")
            await asyncio.sleep(interval_sec)

    def stop(self):
        self.running = False
