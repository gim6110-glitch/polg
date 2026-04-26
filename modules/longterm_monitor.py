import sys
import os
import json
import time
import asyncio
from datetime import datetime, timedelta
from dotenv import load_dotenv

sys.path.insert(0, '/home/dps/stock_ai')
from modules.kis_api import KISApi

load_dotenv('/home/dps/stock_ai/.env')

class LongtermMonitor:
    """
    중장기 + 도박 매수 타이밍 모니터
    유망 테마 종목 매수 시점만 알림
    평소엔 조용히 지켜봄
    """
    def __init__(self):
        self.kis        = KISApi()
        self.alert_file = "/home/dps/stock_ai/data/longterm_alerts.json"
        self.alerts     = self._load_alerts()

        # ── 중장기 테마 ──
        self.themes = {
            "AI반도체": {
                "KR": {"삼성전자": "005930", "SK하이닉스": "000660", "한미반도체": "042700", "HPSP": "403870"},
                "US": {"NVDA": "NVDA", "AMD": "AMD", "AVGO": "AVGO", "ASML": "ASML"}
            },
            "로봇": {
                "KR": {"두산로보틱스": "454910", "레인보우로보틱스": "277810", "에스피지": "058610"},
                "US": {}
            },
            "원전/에너지": {
                "KR": {"두산에너빌리티": "034020", "한전기술": "052690", "한전KPS": "051600"},
                "US": {"VST": "VST", "CEG": "CEG", "NEE": "NEE"}
            },
            "양자컴퓨터": {
                "KR": {},
                "US": {"IONQ": "IONQ", "RGTI": "RGTI", "QUBT": "QUBT"}
            },
            "바이오/AI신약": {
                "KR": {"삼성바이오로직스": "207940", "셀트리온": "068270", "에스티팜": "237690"},
                "US": {"LLY": "LLY"}
            },
            "우주항공": {
                "KR": {"한국항공우주": "047810"},
                "US": {"LUNR": "LUNR"}
            },
            "방산": {
                "KR": {"한화에어로스페이스": "012450", "LIG넥스원": "079550", "한국항공우주": "047810"},
                "US": {"LMT": "LMT", "RTX": "RTX", "NOC": "NOC"}
            },
            "AI인프라": {
                "KR": {},
                "US": {"NVDA": "NVDA", "AVGO": "AVGO", "MSFT": "MSFT", "GOOGL": "GOOGL"}
            },
        }

        # ── 도박 watchlist (감시만, 신호 오면 알림) ──
        # 조건: 혁신 기술 + 아직 저평가 + 미래 산업 핵심
        self.gamble_watchlist = {
            "APLD":  {"name": "어플라이드디지털",  "market": "US", "theme": "AI데이터센터",  "memo": "AI GPU 데이터센터 인프라, 전력/냉각 병목 수혜"},
            "AMPX":  {"name": "암프리우스",        "market": "US", "theme": "혁신배터리",    "memo": "실리콘 음극 배터리, 기존 대비 에너지밀도 500%, 드론/방산"},
            "IONQ":  {"name": "아이온큐",          "market": "US", "theme": "양자컴퓨터",    "memo": "양자컴 순수 플레이 1위, 엔비디아 협력"},
            "RGTI":  {"name": "리게티컴퓨팅",      "market": "US", "theme": "양자컴퓨터",    "memo": "양자컴 2위, IONQ보다 저렴, 고위험"},
        }

    def _load_alerts(self):
        if os.path.exists(self.alert_file):
            with open(self.alert_file, "r") as f:
                return json.load(f)
        return {}

    def _save_alerts(self):
        with open(self.alert_file, "w") as f:
            json.dump(self.alerts, f, ensure_ascii=False, indent=2)

    def _can_alert(self, key, cooldown_hours=24):
        if key in self.alerts:
            last = datetime.fromisoformat(self.alerts[key])
            diff = (datetime.now() - last).total_seconds() / 3600
            if diff < cooldown_hours:
                return False
        self.alerts[key] = datetime.now().isoformat()
        self._save_alerts()
        return True

    def _analyze_stock(self, name, ticker, market="KR"):
        """종목 매수 타이밍 분석"""
        try:
            import yfinance as yf

            yf_ticker = f"{ticker}.KS" if market == "KR" else ticker
            hist      = yf.Ticker(yf_ticker).history(period="3mo").dropna()

            if len(hist) < 20:
                return None

            close  = hist['Close']
            volume = hist['Volume']

            current   = close.iloc[-1]
            high_3m   = close.max()
            low_3m    = close.min()
            avg_vol   = volume.mean()
            curr_vol  = volume.iloc[-1]
            vol_ratio = curr_vol / avg_vol if avg_vol > 0 else 1

            # 52주 저점 대비
            hist_1y  = yf.Ticker(yf_ticker).history(period="1y").dropna()
            low_52w  = hist_1y['Close'].min() if len(hist_1y) > 0 else low_3m
            from_low = ((current - low_52w) / low_52w) * 100

            # 고점 대비 하락률
            drawdown = ((current - high_3m) / high_3m) * 100

            # RSI
            delta = close.diff()
            gain  = delta.clip(lower=0).rolling(14).mean()
            loss  = (-delta.clip(upper=0)).rolling(14).mean()
            rs    = gain / loss
            rsi   = (100 - (100 / (1 + rs))).iloc[-1]

            # 5일 거래량 추세
            vol_5d    = volume.tail(5).mean()
            vol_trend = vol_5d / avg_vol

            # 5일선 돌파 여부
            ma5        = close.rolling(5).mean()
            above_ma5  = close.iloc[-1] > ma5.iloc[-1]

            # KIS 실시간 가격
            if market == "KR":
                kis_data = self.kis.get_kr_price(ticker)
            else:
                kis_data = None
                for excd in ["NAS", "NYS"]:
                    kis_data = self.kis.get_us_price(ticker, excd)
                    if kis_data and kis_data.get('price', 0) > 0:
                        break

            if kis_data:
                current = kis_data['price']

            return {
                "name":       name,
                "ticker":     ticker,
                "market":     market,
                "price":      current,
                "high_3m":    high_3m,
                "low_3m":     low_3m,
                "low_52w":    low_52w,
                "from_low":   round(from_low, 1),
                "drawdown":   round(drawdown, 1),
                "rsi":        round(rsi, 1),
                "vol_ratio":  round(vol_ratio, 1),
                "vol_trend":  round(vol_trend, 2),
                "above_ma5":  above_ma5,
            }
        except Exception as e:
            return None

    def _is_buy_timing(self, data, is_gamble=False):
        """
        매수 타이밍 판단
        is_gamble=True 면 도박 종목 기준 (더 엄격)
        """
        signals = []
        score   = 0

        drawdown  = data.get('drawdown', 0)
        rsi       = data.get('rsi', 50)
        vol_ratio = data.get('vol_ratio', 1)
        vol_trend = data.get('vol_trend', 1)
        from_low  = data.get('from_low', 100)
        above_ma5 = data.get('above_ma5', False)

        if is_gamble:
            # 도박 종목 — 52주 저점 근처 + 반등 시작 조건
            if from_low <= 20:
                score += 3
                signals.append(f"📉 52주 저점 근처 (저점 대비 +{from_low:.0f}%)")
            elif from_low <= 40:
                score += 1
                signals.append(f"📉 52주 저점 대비 +{from_low:.0f}% (아직 저평가)")

            if rsi <= 35:
                score += 3
                signals.append(f"✅ RSI {rsi:.0f} 과매도 → 반등 가능")
            elif rsi <= 45:
                score += 2
                signals.append(f"✅ RSI {rsi:.0f} 매수 구간")

            if above_ma5:
                score += 2
                signals.append("📈 5일선 돌파 → 반등 시작 신호")

            if vol_ratio >= 2:
                score += 3
                signals.append(f"💥 거래량 {vol_ratio:.1f}배 급증 → 세력 유입 가능성")
            elif vol_ratio >= 1.5:
                score += 1
                signals.append(f"📦 거래량 {vol_ratio:.1f}배 증가")

            # 도박 기준: 5점 이상 (중장기보다 높게)
            return score, signals

        else:
            # 중장기 종목 기준
            if -30 <= drawdown <= -10:
                score += 3
                signals.append(f"📉 고점 대비 {drawdown:.1f}% 눌림목")
            elif -10 < drawdown <= -5:
                score += 1
                signals.append(f"📉 고점 대비 {drawdown:.1f}% 소폭 조정")

            if 35 <= rsi <= 55:
                score += 3
                signals.append(f"✅ RSI {rsi:.0f} 매수 적정 구간")
            elif 55 < rsi <= 65:
                score += 1
                signals.append(f"⚠️ RSI {rsi:.0f} 다소 높음")

            if vol_trend >= 1.3:
                score += 2
                signals.append(f"📦 거래량 증가 추세 ({vol_trend:.1f}배)")
            elif vol_trend >= 1.1:
                score += 1
                signals.append(f"📦 거래량 소폭 증가")

            if vol_ratio >= 2:
                score += 2
                signals.append(f"💥 당일 거래량 {vol_ratio:.1f}배 급증")

            if above_ma5:
                score += 1
                signals.append("📈 5일선 위 → 단기 상승 추세")

            return score, signals

    async def scan_all_themes(self, news_list=None):
        """전체 테마 + 도박 watchlist 스캔"""
        print(f"[{datetime.now().strftime('%H:%M')}] 🔍 중장기+도박 테마 스캔")

        # 동적 테마 추가
        try:
            from modules.dynamic_sectors import DynamicSectors
            ds      = DynamicSectors()
            dynamic = ds.dynamic.get('themes', {})
            for theme_name, theme_data in dynamic.items():
                if theme_name not in self.themes:
                    self.themes[theme_name] = {
                        "KR": theme_data.get('stocks', {}),
                        "US": {}
                    }
        except:
            pass

        buy_signals  = []
        gamble_signals = []

        # ── 중장기 테마 스캔 ──
        for theme_name, markets in self.themes.items():
            for market, stocks in markets.items():
                for name, ticker in stocks.items():
                    data = self._analyze_stock(name, ticker, market)
                    if not data:
                        continue

                    score, signals = self._is_buy_timing(data, is_gamble=False)

                    if score >= 5:
                        alert_key = f"longterm_{ticker}_{market}"
                        if not self._can_alert(alert_key, cooldown_hours=24):
                            continue
                        data['theme']      = theme_name
                        data['score']      = score
                        data['signals']    = signals
                        data['type']       = '중장기'
                        buy_signals.append(data)
                        print(f"  🔔 중장기 타이밍: {name} (점수:{score})")

                    time.sleep(0.2)

        # ── 도박 watchlist 스캔 ──
        for ticker, info in self.gamble_watchlist.items():
            data = self._analyze_stock(info['name'], ticker, info['market'])
            if not data:
                continue

            score, signals = self._is_buy_timing(data, is_gamble=True)

            if score >= 5:
                alert_key = f"gamble_{ticker}"
                if not self._can_alert(alert_key, cooldown_hours=24):
                    continue
                data['theme']   = info['theme']
                data['score']   = score
                data['signals'] = signals
                data['memo']    = info['memo']
                data['type']    = '도박'
                gamble_signals.append(data)
                print(f"  🎰 도박 타이밍: {info['name']} (점수:{score})")

            time.sleep(0.2)

        all_signals = buy_signals + gamble_signals

        # AI 최종 판단
        if all_signals and news_list:
            all_signals = await self._ai_filter(all_signals, news_list)

        return all_signals

    async def _ai_filter(self, candidates, news_list):
        """AI가 매수 타이밍 최종 검증"""
        from anthropic import Anthropic
        client = Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))

        news_text = "\n".join([f"- {n['title']}" for n in news_list[:10]])
        cand_text = ""
        for c in candidates:
            cand_text += (
                f"{c['name']}({c['ticker']}) "
                f"유형:{c['type']} 테마:{c['theme']} "
                f"RSI:{c['rsi']} 눌림목:{c['drawdown']}% "
                f"거래량:{c['vol_ratio']}배 점수:{c['score']}\n"
            )

        prompt = f"""투자 전문가로서 매수 타이밍을 검증해주세요.
중장기는 3~12개월, 도박은 1~5년 관점으로 판단해주세요.
마크다운 금지.

=== 오늘 뉴스 ===
{news_text}

=== 매수 타이밍 후보 ===
{cand_text}

JSON으로만 답변:
{{
  "verified": [
    {{
      "ticker": "티커",
      "buy_now": true,
      "target": 0,
      "stop_loss": 0,
      "reason": "이유 한줄",
      "timeframe": "3개월"
    }}
  ]
}}"""

        try:
            res  = client.messages.create(
                model      = "claude-sonnet-4-6",
                max_tokens = 800,
                messages   = [{"role": "user", "content": prompt}]
            )
            import re
            text = res.content[0].text.strip()
            text = re.sub(r'```json|```', '', text).strip()
            m    = re.search(r'\{.*\}', text, re.DOTALL)
            if m:
                try:
                    data = json.loads(m.group())
                except json.JSONDecodeError:
                    clean = re.sub(r',\s*}', '}', m.group())
                    clean = re.sub(r',\s*]', ']', clean)
                    data  = json.loads(clean)
                verified = {v['ticker']: v for v in data.get('verified', []) if v.get('buy_now')}
                result   = []
                for c in candidates:
                    if c['ticker'] in verified:
                        c.update(verified[c['ticker']])
                        result.append(c)
                return result
        except Exception as e:
            print(f"  ❌ AI 검증 실패: {e}")
        return candidates

    def build_alert_message(self, signals):
        """중장기 + 도박 매수 타이밍 알림 (분리)"""
        if not signals:
            return None

        middle  = [s for s in signals if s.get('type') == '중장기']
        gambles = [s for s in signals if s.get('type') == '도박']

        msg = f"🔔 <b>매수 타이밍 알림</b> {datetime.now().strftime('%m/%d %H:%M')}\n\n"

        if middle:
            msg += "📊 <b>중장기 타이밍</b>\n"
            msg += "━━━━━━━━━━━━━━━━━━━\n"
            for s in middle[:3]:
                market   = s.get('market', 'KR')
                currency = "$" if market == "US" else "₩"
                price    = s.get('price', 0)
                target   = s.get('target', round(price * 1.20, 0))
                stop     = s.get('stop_loss', round(price * 0.88, 0))
                profit   = ((target - price) / price) * 100
                sigs     = "\n".join([f"   {sg}" for sg in s.get('signals', [])[:3]])

                msg += f"""🎯 <b>{s['name']}</b> ({s['ticker']}) [{s['theme']}]

{sigs}

💡 {s.get('reason', '')}
💰 현재가: {currency}{price:,.2f}
🎯 목표가: {currency}{target:,.2f} (+{profit:.0f}%, {s.get('timeframe', '3개월')})
🛑 손절가: {currency}{stop:,.2f}

"""

        if gambles:
            msg += "🎰 <b>도박 타이밍</b> (소액만!)\n"
            msg += "━━━━━━━━━━━━━━━━━━━\n"
            for s in gambles[:3]:
                market   = s.get('market', 'US')
                currency = "$" if market == "US" else "₩"
                price    = s.get('price', 0)
                target   = s.get('target', round(price * 3.0, 0))
                stop     = s.get('stop_loss', round(price * 0.80, 0))
                sigs     = "\n".join([f"   {sg}" for sg in s.get('signals', [])[:3]])

                msg += f"""🎲 <b>{s['name']}</b> ({s['ticker']}) [{s['theme']}]

{sigs}

💡 {s.get('reason', s.get('memo', ''))}
💰 현재가: {currency}{price:,.2f}
🎯 목표: {currency}{target:,.2f} (장기 3~5배)
🛑 손절: {currency}{stop:,.2f}
⚠️ 총자산 2% 이하 소액만!

"""

        msg += f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        return msg


if __name__ == "__main__":
    async def test():
        print("=" * 50)
        print("🔔 중장기+도박 매수 타이밍 테스트")
        print("=" * 50)
        from modules.news_collector import NewsCollector
        nc      = NewsCollector()
        news    = nc.collect_news(max_per_feed=3)
        lm      = LongtermMonitor()
        signals = await lm.scan_all_themes(news)
        print(f"\n매수 타이밍 {len(signals)}개 발견")
        msg = lm.build_alert_message(signals)
        if msg:
            print(msg)
        else:
            print("현재 매수 타이밍 없음")

    asyncio.run(test())
