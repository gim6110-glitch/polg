import sys
import os
import json
import time
import asyncio
from datetime import datetime
from dotenv import load_dotenv

sys.path.insert(0, '/home/dps/stock_ai')
from modules.kis_api import KISApi

load_dotenv('/home/dps/stock_ai/.env')

class LeverageMonitor:
    """
    레버리지 ETF 감시
    강세장에서 수익 극대화 핵심 도구
    """
    def __init__(self):
        self.kis          = KISApi()
        self.alert_file   = "/home/dps/stock_ai/data/leverage_alerts.json"
        self.alert_history = self._load_alerts()

        # 한국 레버리지/섹터 ETF
        self.kr_leverage = {
            # 시장 레버리지
            "KODEX 레버리지":          "122630",  # 코스피 2배
            "TIGER 레버리지":          "123320",  # 코스피 2배
            "KODEX 코스닥150레버리지": "233740",  # 코스닥 2배
            # 섹터 ETF
            "KODEX 반도체":            "091160",  # 반도체
            "KODEX AI전력인프라":      "475050",  # AI전력
            "TIGER 방산":              "329200",  # 방산
            "HANARO 방산":             "448280",  # 방산
            "KODEX 원자력":            "456600",  # 원전
            "KODEX 조선":              "474220",  # 조선
            "KODEX 바이오":            "244580",  # 바이오
            "KODEX 2차전지산업":       "305720",  # 2차전지
            "HANARO 로봇":             "401470",  # 로봇
        }

        # 미국 레버리지 ETF
        self.us_leverage = {
            "TQQQ":  ("TQQQ", "NAS"),   # 나스닥 3배
            "UPRO":  ("UPRO", "AMS"),   # S&P500 3배
            "SOXL":  ("SOXL", "AMS"),   # 반도체 3배
            "TECL":  ("TECL", "AMS"),   # 기술주 3배
            "FNGU":  ("FNGU", "AMS"),   # FAANG 3배
            "LABU":  ("LABU", "AMS"),   # 바이오 3배
            "BOIL":  ("BOIL", "AMS"),   # 천연가스 2배
            "URA":   ("URA",  "AMS"),   # 우라늄 ETF
        }

        # ETF 섹터 매핑 (해석용)
        self.etf_sector_map = {
            "KODEX 레버리지":          "코스피 전체",
            "TIGER 레버리지":          "코스피 전체",
            "KODEX 코스닥150레버리지": "코스닥 전체",
            "KODEX 반도체":            "AI반도체",
            "KODEX AI전력인프라":      "AI인프라/전력",
            "TIGER 방산":              "방산",
            "HANARO 방산":             "방산",
            "KODEX 원자력":            "원전",
            "KODEX 조선":              "조선",
            "KODEX 바이오":            "바이오",
            "KODEX 2차전지산업":       "2차전지",
            "HANARO 로봇":             "로봇",
            "TQQQ":                    "미국 나스닥",
            "UPRO":                    "미국 S&P500",
            "SOXL":                    "미국 반도체",
            "TECL":                    "미국 기술주",
            "FNGU":                    "미국 빅테크",
            "LABU":                    "미국 바이오",
            "BOIL":                    "천연가스",
            "URA":                     "우라늄/원전",
        }

    def _load_alerts(self):
        if os.path.exists(self.alert_file):
            with open(self.alert_file, "r") as f:
                return json.load(f)
        return {}

    def _save_alerts(self):
        with open(self.alert_file, "w") as f:
            json.dump(self.alert_history, f, ensure_ascii=False, indent=2)

    def _can_alert(self, key, cooldown_min=60):
        if key in self.alert_history:
            last = datetime.fromisoformat(self.alert_history[key])
            diff = (datetime.now() - last).total_seconds() / 60
            if diff < cooldown_min:
                return False
        self.alert_history[key] = datetime.now().isoformat()
        self._save_alerts()
        return True

    def _calc_entry_strategy(self, name, current, change_pct, is_kr=True):
        """레버리지 ETF 진입 전략 계산"""
        currency = "₩" if is_kr else "$"

        # 레버리지 ETF는 일반주보다 보수적으로
        if change_pct >= 5:
            strategy = "눌림목 대기"
            buy1     = round(current * 0.96, 0 if is_kr else 2)
            buy2     = round(current * 0.93, 0 if is_kr else 2)
            target1  = round(current * 1.10, 0 if is_kr else 2)
            target2  = round(current * 1.20, 0 if is_kr else 2)
            stop     = round(current * 0.90, 0 if is_kr else 2)
            timing   = "지금 금지 → 3~5% 눌림목 후 진입"
        elif change_pct >= 2:
            strategy = "소량 선진입"
            buy1     = round(current * 0.99, 0 if is_kr else 2)
            buy2     = round(current * 0.96, 0 if is_kr else 2)
            target1  = round(current * 1.08, 0 if is_kr else 2)
            target2  = round(current * 1.15, 0 if is_kr else 2)
            stop     = round(current * 0.93, 0 if is_kr else 2)
            timing   = "지금 30% 진입 → 눌림목에 70%"
        else:
            strategy = "적극 매수"
            buy1     = round(current, 0 if is_kr else 2)
            buy2     = round(current * 0.97, 0 if is_kr else 2)
            target1  = round(current * 1.08, 0 if is_kr else 2)
            target2  = round(current * 1.15, 0 if is_kr else 2)
            stop     = round(current * 0.93, 0 if is_kr else 2)
            timing   = "지금 바로 분할 진입 가능"

        return {
            "strategy": strategy,
            "timing":   timing,
            "buy1":     buy1,
            "buy2":     buy2,
            "target1":  target1,
            "target2":  target2,
            "stop":     stop,
            "target1_pct": round(((target1 - current) / current) * 100, 1),
            "target2_pct": round(((target2 - current) / current) * 100, 1),
            "stop_pct":    round(((stop - current) / current) * 100, 1),
            "currency":    currency,
        }

    def get_kr_leverage_status(self):
        """한국 레버리지 ETF 현황"""
        results = []
        for name, code in self.kr_leverage.items():
            data = self.kis.get_kr_price(code)
            if data:
                results.append({
                    "name":       name,
                    "code":       code,
                    "price":      data['price'],
                    "change_pct": data['change_pct'],
                    "volume":     data['volume'],
                    "market":     "KR"
                })
            time.sleep(0.2)
        return results

    def get_us_leverage_status(self):
        """미국 레버리지 ETF 현황"""
        results = []
        for name, (ticker, excd) in self.us_leverage.items():
            data = self.kis.get_us_price(ticker, excd)
            if data and data['price'] > 0:
                results.append({
                    "name":       name,
                    "ticker":     ticker,
                    "price":      data['price'],
                    "change_pct": data['change_pct'],
                    "market":     "US"
                })
            time.sleep(0.2)
        return results

    async def check_leverage_signals(self, regime_type, send_func):
        """레버리지 ETF 매수 신호 감지"""
        hour = datetime.now().hour

        # 한국장 (09:00~15:30)
        if 9 <= hour < 16:
            results = self.get_kr_leverage_status()
            for r in results:
                change = r['change_pct']
                name   = r['name']
                price  = r['price']
                code   = r['code']

                signals  = []
                urgency  = 0
                alert_key = None

                # 강세장 신호
                if regime_type in ['강세', '중립']:
                    if change >= 3:
                        signals.append(f"🚀 강세장 레버리지 급등 {change:+.1f}%")
                        urgency   += 3
                        alert_key = f"lev_{code}_급등"
                    elif change >= 1.5:
                        signals.append(f"📈 레버리지 상승 {change:+.1f}%")
                        urgency   += 2
                        alert_key = f"lev_{code}_상승"

                # 레버리지 하락 = 역레버리지 기회
                if change <= -3:
                    signals.append(f"📉 레버리지 급락 {change:+.1f}% → 역레버리지 고려")
                    urgency   += 2
                    alert_key = f"lev_{code}_급락"

                if urgency >= 2 and alert_key and signals:
                    if self._can_alert(alert_key, cooldown_min=60):
                        entry  = self._calc_entry_strategy(name, price, change, is_kr=True)
                        signal_text = "\n".join(signals)
                        msg = f"""⚡ <b>[레버리지 ETF]</b> {name}

💰 현재가: {entry['currency']}{price:,}
📊 등락: {change:+.2f}%

{signal_text}

━━━━━━━━━━━━━━━━━━━
🤖 <b>전략: {entry['strategy']}</b>
💡 {entry['timing']}

💚 매수가
  1차: {entry['currency']}{entry['buy1']:,}
  2차: {entry['currency']}{entry['buy2']:,}

🎯 목표가
  1차: {entry['currency']}{entry['target1']:,} ({entry['target1_pct']:+.1f}%)
  2차: {entry['currency']}{entry['target2']:,} ({entry['target2_pct']:+.1f}%)

🛑 손절가: {entry['currency']}{entry['stop']:,} ({entry['stop_pct']:+.1f}%)

⚠️ 레버리지는 손실도 2배!
⏰ {datetime.now().strftime('%H:%M:%S')}"""
                        await send_func(msg)
                        print(f"  📱 레버리지 알림: {name}")

        # 미국장 (21:30~04:00)
        if hour >= 21 or hour < 4:
            results = self.get_us_leverage_status()
            for r in results:
                change = r['change_pct']
                name   = r['name']
                price  = r['price']
                ticker = r['ticker']

                signals   = []
                urgency   = 0
                alert_key = None

                if change >= 4:
                    signals.append(f"🚀 미국 레버리지 급등 {change:+.1f}%")
                    urgency   += 3
                    alert_key = f"lev_{ticker}_급등"
                elif change >= 2:
                    signals.append(f"📈 미국 레버리지 상승 {change:+.1f}%")
                    urgency   += 2
                    alert_key = f"lev_{ticker}_상승"

                if change <= -4:
                    signals.append(f"📉 미국 레버리지 급락 {change:+.1f}%")
                    urgency   += 2
                    alert_key = f"lev_{ticker}_급락"

                if urgency >= 2 and alert_key and signals:
                    if self._can_alert(alert_key, cooldown_min=60):
                        entry       = self._calc_entry_strategy(name, price, change, is_kr=False)
                        signal_text = "\n".join(signals)
                        msg = f"""⚡ <b>[미국 레버리지]</b> {name} ({ticker})

💰 현재가: {entry['currency']}{price:,}
📊 등락: {change:+.2f}%

{signal_text}

━━━━━━━━━━━━━━━━━━━
🤖 <b>전략: {entry['strategy']}</b>
💡 {entry['timing']}

💚 매수가: {entry['currency']}{entry['buy1']:,} / {entry['currency']}{entry['buy2']:,}
🎯 목표가: {entry['currency']}{entry['target1']:,} ({entry['target1_pct']:+.1f}%) / {entry['currency']}{entry['target2']:,} ({entry['target2_pct']:+.1f}%)
🛑 손절가: {entry['currency']}{entry['stop']:,} ({entry['stop_pct']:+.1f}%)

⚠️ 레버리지는 손실도 3배!
⏰ {datetime.now().strftime('%H:%M:%S')}"""
                        await send_func(msg)
                        print(f"  📱 미국 레버리지 알림: {name}")

    def build_leverage_status_message(self):
        """레버리지 ETF 현황 + AI 판단 메시지"""
        from anthropic import Anthropic
        from dotenv import load_dotenv
        import os, re, json as _json
        load_dotenv('/home/dps/stock_ai/.env')
        client = Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))

        kr   = self.get_kr_leverage_status()
        hour = datetime.now().hour
        us   = self.get_us_leverage_status() if (hour >= 21 or hour < 4) else []

        kr_text = ""
        for r in sorted(kr, key=lambda x: x['change_pct'], reverse=True):
            sector = self.etf_sector_map.get(r['name'], '')
            kr_text += f"{r['name']}({sector}): {r['change_pct']:+.1f}%\n"

        us_text = ""
        for r in sorted(us, key=lambda x: x['change_pct'], reverse=True):
            sector = self.etf_sector_map.get(r['name'], '')
            us_text += f"{r['name']}({sector}): {r['change_pct']:+.1f}%\n"

        ai_result = None
        try:
            prompt = f"""레버리지 ETF 현황을 보고 투자 판단을 해주세요.

한국 ETF:
{kr_text}

미국 ETF:
{us_text if us_text else "장 마감"}

JSON으로만:
{{
  "strong_sectors": ["섹터1", "섹터2"],
  "weak_sectors": ["섹터1"],
  "tomorrow_strategy": "내일 전략 한줄",
  "buy_etf": [
    {{
      "name": "ETF명",
      "reason": "이유 한줄",
      "timing": "지금/눌림목 후",
      "risk_reward": "1:2"
    }}
  ],
  "caution_etf": ["주의 ETF명"],
  "summary": "한줄 총평"
}}"""

            res  = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=500,
                messages=[{"role": "user", "content": prompt}]
            )
            text = re.sub(r'```json|```', '', res.content[0].text.strip()).strip()
            m    = re.search(r'\{.*\}', text, re.DOTALL)
            ai_result = _json.loads(m.group()) if m else None
        except Exception as e:
            print(f"  ❌ AI 분석 실패: {e}")

        msg = f"⚡ <b>레버리지 ETF 현황</b> {datetime.now().strftime('%m/%d %H:%M')}\n\n"

        if ai_result:
            msg += f"💡 <b>{ai_result.get('summary', '')}</b>\n"
            strong = ai_result.get('strong_sectors', [])
            weak   = ai_result.get('weak_sectors', [])
            if strong:
                msg += f"🔥 강한 섹터: {', '.join(strong)}\n"
            if weak:
                msg += f"❄️ 약한 섹터: {', '.join(weak)}\n"
            msg += f"📋 {ai_result.get('tomorrow_strategy', '')}\n\n"

        msg += "🇰🇷 <b>한국 ETF</b>\n"
        for r in sorted(kr, key=lambda x: x['change_pct'], reverse=True):
            arrow  = "▲" if r['change_pct'] > 0 else "▼"
            emoji  = "🔴" if r['change_pct'] >= 3 else "🟡" if r['change_pct'] >= 1 else "⚪"
            sector = self.etf_sector_map.get(r['name'], '')
            msg   += f"{emoji} {r['name']}: {r['price']:,}원 {arrow}{r['change_pct']:+.1f}% [{sector}]\n"

        if us:
            msg += "\n🇺🇸 <b>미국 ETF</b>\n"
            for r in sorted(us, key=lambda x: x['change_pct'], reverse=True):
                arrow  = "▲" if r['change_pct'] > 0 else "▼"
                emoji  = "🔴" if r['change_pct'] >= 4 else "🟡" if r['change_pct'] >= 2 else "⚪"
                sector = self.etf_sector_map.get(r['name'], '')
                msg   += f"{emoji} {r['name']}: ${r['price']} {arrow}{r['change_pct']:+.1f}% [{sector}]\n"
        else:
            msg += "\n🇺🇸 미국장 마감 중\n"

        if ai_result:
            buy_etfs = ai_result.get('buy_etf', [])
            if buy_etfs:
                msg += "\n━━━━━━━━━━━━━━━━━━━\n"
                msg += "🎯 <b>ETF 매수 추천</b>\n"
                for e in buy_etfs[:2]:
                    msg += f"  ✅ <b>{e.get('name', '')}</b>\n"
                    msg += f"     {e.get('reason', '')}\n"
                    msg += f"     진입: {e.get('timing', '')} | R/R: {e.get('risk_reward', '')}\n"

            caution = ai_result.get('caution_etf', [])
            if caution:
                msg += f"\n⚠️ 주의: {', '.join(caution)}\n"

        msg += f"\n⏰ {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        return msg


if __name__ == "__main__":
    print("=" * 50)
    print("⚡ 레버리지 ETF 테스트")
    print("=" * 50)
    lm  = LeverageMonitor()
    msg = lm.build_leverage_status_message()
    print(msg)
