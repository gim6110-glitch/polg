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
                "KR": {
                    # 대장주
                    "삼성전자": "005930", "SK하이닉스": "000660",
                    # 2등주
                    "한미반도체": "042700", "HPSP": "403870",
                    # 소부장
                    "원익IPS": "240810", "피에스케이": "319660",
                    "이수페타시스": "097950", "후성": "093370",
                },
                "US": {"NVDA": "NVDA", "AMD": "AMD", "AVGO": "AVGO", "ASML": "ASML"}
            },
            "로봇": {
                "KR": {
                    "두산로보틱스": "454910", "레인보우로보틱스": "277810",
                    "에스피지": "058610", "스맥": "099440",
                },
                "US": {"ISRG": "ISRG", "ABB": "ABB"}
            },
            "원전/에너지": {
                "KR": {
                    # 대장주
                    "두산에너빌리티": "034020",
                    # 2등주
                    "한전기술": "052690", "한전KPS": "051600",
                    # 소부장
                    "일진파워": "094820", "비에이치아이": "083650",
                },
                "US": {"VST": "VST", "CEG": "CEG", "NEE": "NEE", "KMI": "KMI"}
            },
            "양자컴퓨터": {
                "KR": {},
                "US": {"IONQ": "IONQ", "RGTI": "RGTI", "QUBT": "QUBT", "QBTS": "QBTS"}
            },
            "바이오/AI신약": {
                "KR": {
                    "삼성바이오로직스": "207940", "셀트리온": "068270",
                    "에스티팜": "237690", "JW중외제약": "001060",
                },
                "US": {"LLY": "LLY", "RXRX": "RXRX", "MRNA": "MRNA"}
            },
            "우주항공": {
                "KR": {"한국항공우주": "047810"},
                "US": {"RKLB": "RKLB", "LUNR": "LUNR", "ASTS": "ASTS"}
            },
            "방산": {
                "KR": {
                    "한화에어로스페이스": "012450", "LIG넥스원": "079550",
                    "한국항공우주": "047810", "빅텍": "065450",
                },
                "US": {"LMT": "LMT", "RTX": "RTX", "NOC": "NOC"}
            },
            "AI인프라/빅테크": {
                "KR": {},
                "US": {"NVDA": "NVDA", "AVGO": "AVGO", "MSFT": "MSFT",
                       "GOOGL": "GOOGL", "META": "META", "AAPL": "AAPL"}
            },
            "전력/전력기기": {
                "KR": {
                    "LS ELECTRIC": "010120", "HD현대일렉트릭": "267260",
                    "효성중공업": "298040", "일진전기": "103590",
                },
                "US": {}
            },
            "2차전지": {
                "KR": {
                    "에코프로비엠": "247540", "삼성SDI": "006400",
                    "엘앤에프": "066970", "포스코퓨처엠": "003670",
                },
                "US": {}
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
        """종목 분석 — 이동평균선 + 주봉 중심"""
        try:
            import yfinance as yf

            yf_ticker = f"{ticker}.KS" if market == "KR" else ticker
            hist      = yf.Ticker(yf_ticker).history(period="6mo").dropna()

            if len(hist) < 20:
                return None

            close  = hist['Close']
            volume = hist['Volume']

            current  = close.iloc[-1]
            avg_vol  = volume.mean()
            curr_vol = volume.iloc[-1]
            vol_ratio = curr_vol / avg_vol if avg_vol > 0 else 1

            # ── 이동평균선 ──
            ma5   = close.rolling(5).mean()
            ma20  = close.rolling(20).mean()
            ma60  = close.rolling(60).mean() if len(close) >= 60 else ma20

            ma5_val  = ma5.iloc[-1]
            ma20_val = ma20.iloc[-1]
            ma60_val = ma60.iloc[-1]

            # 정배열 (5 > 20 > 60)
            is_bullish_array = ma5_val > ma20_val > ma60_val

            # 5일선 위/아래
            above_ma5  = current > ma5_val
            above_ma20 = current > ma20_val
            above_ma60 = current > ma60_val

            # 5일선 눌림 (현재가가 5일선 아래지만 전일 위였던 경우)
            ma5_prev   = ma5.iloc[-2] if len(ma5) >= 2 else ma5_val
            ma5_touch  = not above_ma5 and (close.iloc[-2] > ma5_prev if len(close) >= 2 else False)

            # 20일선 대비 위치
            ma20_gap = ((current - ma20_val) / ma20_val) * 100

            # 고점 대비 하락률 (3개월)
            high_3m  = close.max()
            drawdown = ((current - high_3m) / high_3m) * 100

            # 52주 데이터
            hist_1y = yf.Ticker(yf_ticker).history(period="1y").dropna()
            high_52w = hist_1y['Close'].max() if len(hist_1y) > 0 else high_3m
            low_52w  = hist_1y['Close'].min() if len(hist_1y) > 0 else current
            from_low = ((current - low_52w) / low_52w) * 100
            ath_prox = (current / high_52w) * 100  # 신고가 근접도

            # 거래량 패턴
            vol_5d    = volume.tail(5).mean()
            vol_trend = vol_5d / avg_vol if avg_vol > 0 else 1

            # 하락 시 거래량 감소 + 반등 시 증가 (건강한 눌림)
            recent_down_days  = close.diff().iloc[-5:] < 0
            recent_down_vols  = volume.iloc[-5:][recent_down_days].mean() if recent_down_days.any() else avg_vol
            recent_up_days    = close.diff().iloc[-5:] > 0
            recent_up_vols    = volume.iloc[-5:][recent_up_days].mean() if recent_up_days.any() else avg_vol
            healthy_pullback  = recent_up_vols > recent_down_vols  # 상승 거래량 > 하락 거래량

            # 주봉 데이터
            try:
                weekly = yf.Ticker(yf_ticker).history(period="6mo", interval="1wk").dropna()
                wma5   = weekly['Close'].rolling(5).mean().iloc[-1] if len(weekly) >= 5 else ma20_val
                wma20  = weekly['Close'].rolling(20).mean().iloc[-1] if len(weekly) >= 20 else ma60_val
                above_wma5  = current > wma5
                above_wma20 = current > wma20
            except:
                above_wma5  = above_ma20
                above_wma20 = above_ma60

            # RSI (보조 지표로만)
            delta = close.diff()
            gain  = delta.clip(lower=0).rolling(14).mean()
            loss  = (-delta.clip(upper=0)).rolling(14).mean()
            rs    = gain / loss
            rsi   = round((100 - (100 / (1 + rs))).iloc[-1], 1)

            # KIS 실시간 가격
            if market == "KR":
                kis_data = self.kis.get_kr_price(ticker)
            else:
                kis_data = None
                for excd in ["NAS", "NYS"]:
                    kis_data = self.kis.get_us_price(ticker, excd)
                    if kis_data and kis_data.get('price', 0) > 0:
                        break

            if kis_data and kis_data.get('price', 0) > 0:
                current = kis_data['price']

            return {
                "name":            name,
                "ticker":          ticker,
                "market":          market,
                "price":           current,
                "ma5":             round(ma5_val, 2),
                "ma20":            round(ma20_val, 2),
                "ma60":            round(ma60_val, 2),
                "above_ma5":       above_ma5,
                "above_ma20":      above_ma20,
                "above_ma60":      above_ma60,
                "is_bullish_array": is_bullish_array,
                "ma5_touch":       ma5_touch,
                "ma20_gap":        round(ma20_gap, 1),
                "above_wma5":      above_wma5,
                "above_wma20":     above_wma20,
                "healthy_pullback": healthy_pullback,
                "high_3m":         high_3m,
                "high_52w":        high_52w,
                "low_52w":         low_52w,
                "from_low":        round(from_low, 1),
                "drawdown":        round(drawdown, 1),
                "ath_prox":        round(ath_prox, 1),
                "rsi":             rsi,
                "vol_ratio":       round(vol_ratio, 1),
                "vol_trend":       round(vol_trend, 2),
                "healthy_pullback": healthy_pullback,
            }
        except Exception as e:
            return None

    def _is_buy_timing(self, data, is_gamble=False):
        """
        매수 타이밍 판단 — 장세 연동 + 이동평균선 중심
        RSI는 극단값만 참조
        """
        signals = []
        score   = 0

        # ── 장세 로드 ──
        cycle_stage = "상승중"
        try:
            from modules.market_regime import MarketRegime
            strategy    = MarketRegime().load_strategy()
            cycle_stage = strategy.get("cycle_stage", "상승중")
        except:
            pass

        drawdown       = data.get('drawdown', 0)
        rsi            = data.get('rsi', 50)
        vol_ratio      = data.get('vol_ratio', 1)
        vol_trend      = data.get('vol_trend', 1)
        from_low       = data.get('from_low', 100)
        above_ma5      = data.get('above_ma5', False)
        above_ma20     = data.get('above_ma20', False)
        above_ma60     = data.get('above_ma60', False)
        is_bull_array  = data.get('is_bullish_array', False)
        ma5_touch      = data.get('ma5_touch', False)
        ma20_gap       = data.get('ma20_gap', 0)
        above_wma5     = data.get('above_wma5', False)
        above_wma20    = data.get('above_wma20', False)
        ath_prox       = data.get('ath_prox', 90)
        healthy_pb     = data.get('healthy_pullback', False)

        if is_gamble:
            # 도박: 52주 저점 근처 + 반등 시작
            if from_low <= 20:
                score += 3
                signals.append(f"📉 52주 저점 근처 (+{from_low:.0f}%)")
            elif from_low <= 40:
                score += 1
                signals.append(f"📉 저점 대비 +{from_low:.0f}%")
            if above_ma5:
                score += 2
                signals.append("📈 5일선 돌파 → 반등 시작")
            if vol_ratio >= 2:
                score += 3
                signals.append(f"💥 거래량 {vol_ratio:.1f}배 급증")
            elif vol_ratio >= 1.5:
                score += 1
                signals.append(f"📦 거래량 {vol_ratio:.1f}배")
            if rsi <= 35:
                score += 2
                signals.append(f"✅ RSI {rsi:.0f} 과매도")
            return score, signals

        # ── 중장기: 장세별 차등 적용 ──

        if cycle_stage in ["초입", "상승중", "가속"]:
            # 강세장 — 신고가 = 매수 신호, 이평선 정배열 중심

            # 1. 정배열 확인 (핵심)
            if is_bull_array:
                score += 3
                signals.append("✅ 5>20>60일 정배열 (강세 추세)")
            elif above_ma20:
                score += 1
                signals.append("✅ 20일선 위 유지")

            # 2. 주봉 강세 확인
            if above_wma5 and above_wma20:
                score += 2
                signals.append("✅ 주봉 강세 (5주>20주선 위)")
            elif above_wma5:
                score += 1
                signals.append("✅ 주봉 5주선 위")

            # 3. 신고가 근접 = 강세장에선 매수 신호
            if ath_prox >= 97:
                score += 2
                signals.append(f"🏔 52주 신고가 근접 ({ath_prox:.1f}%)")
            elif ath_prox >= 90:
                score += 1
                signals.append(f"📊 신고가 대비 -{100-ath_prox:.1f}%")

            # 4. 5일선 눌림 = 진입 기회
            if ma5_touch:
                score += 2
                signals.append("📉 5일선 눌림 → 진입 기회")
            elif -3 <= ma20_gap <= 3:
                score += 1
                signals.append(f"📊 20일선 근처 ({ma20_gap:+.1f}%)")

            # 5. 거래량 패턴
            if healthy_pb:
                score += 2
                signals.append("📦 건강한 눌림 (상승 거래량 > 하락 거래량)")
            elif vol_trend >= 1.3:
                score += 1
                signals.append(f"📦 거래량 증가 ({vol_trend:.1f}배)")

            # 6. RSI — 극단값만
            if rsi >= 90:
                score -= 2
                signals.append(f"🌡️ RSI {rsi:.0f} 극과열 주의")
            elif rsi >= 80:
                score -= 1
                signals.append(f"⚠️ RSI {rsi:.0f} 과열")

        elif cycle_stage in ["과열경계", "과열"]:
            # 과열 구간 — 더 엄격, 눌림목 확인 필수

            # 1. 눌림목 필수
            if -15 <= drawdown <= -5:
                score += 3
                signals.append(f"📉 고점 대비 {drawdown:.1f}% 눌림 (진입 기회)")
            elif -5 < drawdown <= -2:
                score += 1
                signals.append(f"📉 소폭 조정 {drawdown:.1f}%")
            elif drawdown > -2:
                score -= 1  # 과열 구간에서 신고가 = 위험
                signals.append(f"⚠️ 과열 구간 신고가 근처 — 추격 금지")

            # 2. 20일선 위 + 정배열
            if is_bull_array and above_ma20:
                score += 2
                signals.append("✅ 정배열 유지")

            # 3. 주봉 지지 확인
            if above_wma5:
                score += 1
                signals.append("✅ 주봉 5주선 지지")

            # 4. 거래량
            if healthy_pb:
                score += 2
                signals.append("📦 건강한 눌림")

            # 5. RSI
            if rsi >= 80:
                score -= 2
                signals.append(f"🌡️ RSI {rsi:.0f} 과열 — 비중 축소")
            elif rsi >= 70:
                score -= 1
                signals.append(f"⚠️ RSI {rsi:.0f} 다소 과열")

        else:
            # 조정초입/조정중 — 보수적, 60일선 지지 확인

            # 1. 60일선 위 + 반등
            if above_ma60 and above_ma20:
                score += 2
                signals.append("✅ 60/20일선 위 (하락 방어)")
            elif above_ma60:
                score += 1
                signals.append("✅ 60일선 지지")

            # 2. 큰 눌림목
            if -30 <= drawdown <= -15:
                score += 3
                signals.append(f"📉 {drawdown:.1f}% 대폭 조정 (분할 매수)")
            elif -15 < drawdown <= -8:
                score += 1
                signals.append(f"📉 {drawdown:.1f}% 조정")

            # 3. 주봉 20주선 위 = 장기 강세 유지
            if above_wma20:
                score += 2
                signals.append("✅ 주봉 20주선 위 (장기 강세)")

            # 4. RSI 과매도
            if rsi <= 30:
                score += 3
                signals.append(f"✅ RSI {rsi:.0f} 과매도 → 반등")
            elif rsi <= 40:
                score += 1
                signals.append(f"✅ RSI {rsi:.0f} 매수 구간")

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

        # 동적 임계값 로드
        try:
            from modules.market_regime import MarketRegime
            strategy      = MarketRegime().load_strategy()
            lt_threshold  = strategy.get("kr_lt_threshold", 4)
            avoid_sectors = strategy.get("avoid_sectors", [])
            print(f"  📊 중장기 임계값: {lt_threshold} 회피섹터: {avoid_sectors}")
        except:
            lt_threshold  = 4
            avoid_sectors = []

        buy_signals    = []
        gamble_signals = []

        # ── sector_db 전체 종목 스캔 (동적 발굴) ──
        try:
            from modules.financial_filter import FinancialFilter
            ff = FinancialFilter()
        except Exception:
            ff = None

        from modules.sector_db import SECTOR_DB

        seen_tickers = set()  # 중복 방지

        for sector_name, sector_data in SECTOR_DB.items():
            market = sector_data.get('market', 'KR')

            # 회피 섹터 제외
            if any(av.lower() in sector_name.lower() for av in avoid_sectors):
                continue

            all_stocks = {}
            all_stocks.update(sector_data.get('대장주', {}))
            all_stocks.update(sector_data.get('2등주', {}))
            # 소부장 처리
            for sub in sector_data.get('소부장', {}).values():
                if isinstance(sub, dict):
                    all_stocks.update(sub)

            for name, ticker in all_stocks.items():
                if ticker in seen_tickers:
                    continue
                seen_tickers.add(ticker)

                # 재무 필터
                if ff:
                    try:
                        if not ff.is_profitable(ticker, market):
                            print(f"  🚫 적자 제외: {name}")
                            time.sleep(0.1)
                            continue
                    except Exception:
                        pass

                data = self._analyze_stock(name, ticker, market)
                if not data:
                    continue

                score, signals = self._is_buy_timing(data, is_gamble=False)

                if score >= lt_threshold:
                    alert_key = f"longterm_{ticker}"
                    if not self._can_alert(alert_key, cooldown_hours=24):
                        continue
                    data['theme']   = sector_name
                    data['score']   = score
                    data['signals'] = signals
                    data['type']    = '중장기'
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
                max_tokens = 1500,
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
        """중장기 매수 타이밍 알림 — 한국/미국 분리, 간결"""
        if not signals:
            return None

        middle  = [s for s in signals if s.get('type') == '중장기']
        gambles = [s for s in signals if s.get('type') == '도박']

        def priority_score(s):
            """진입가 근접 + 목표가 빠른 달성 예상 순"""
            price  = s.get('price', 1)
            rsi    = s.get('rsi', 50)
            draw   = abs(s.get('drawdown', 0))
            score  = s.get('score', 0)
            # RSI 낮을수록 + 눌림목 클수록 + 점수 높을수록 우선
            return -(score * 10 + draw + (70 - rsi))

        # 한국/미국 분리 + 우선순위 정렬
        kr_signals = sorted([s for s in middle if s.get('market') == 'KR'], key=priority_score)
        us_signals = sorted([s for s in middle if s.get('market') == 'US'], key=priority_score)

        msg = f"🔔 <b>중장기 매수 타이밍</b> {datetime.now().strftime('%m/%d %H:%M')}\n\n"

        def fmt_stock(s):
            market   = s.get('market', 'KR')
            currency = "$" if market == "US" else "₩"
            price    = s.get('price', 0)
            rsi      = s.get('rsi', 50)
            drawdown = s.get('drawdown', 0)

            # 목표가 — AI 검증 결과 또는 기본값
            target = s.get('target', 0)
            stop   = s.get('stop_loss', 0)
            if not target or target <= price:
                # 점수/RSI 기반 동적 목표가
                if s.get('score', 0) >= 6:
                    target = round(price * 1.30, 0) if market == "KR" else round(price * 1.30, 2)
                elif rsi < 40:
                    target = round(price * 1.25, 0) if market == "KR" else round(price * 1.25, 2)
                else:
                    target = round(price * 1.20, 0) if market == "KR" else round(price * 1.20, 2)
            if not stop or stop >= price:
                stop = round(price * 0.88, 0) if market == "KR" else round(price * 0.88, 2)

            # 매수 타이밍 + 매수가
            if rsi <= 40 or drawdown <= -10:
                timing = "🟢 지금 바로"
                buy1   = round(price * 0.99, 0) if market == "KR" else round(price * 0.99, 2)
                buy2   = round(price * 0.97, 0) if market == "KR" else round(price * 0.97, 2)
            elif rsi <= 55:
                timing = "🟡 조정 시"
                buy1   = round(price * 0.98, 0) if market == "KR" else round(price * 0.98, 2)
                buy2   = round(price * 0.95, 0) if market == "KR" else round(price * 0.95, 2)
            else:
                timing = "🔴 눌림목 후"
                buy1   = round(price * 0.97, 0) if market == "KR" else round(price * 0.97, 2)
                buy2   = round(price * 0.94, 0) if market == "KR" else round(price * 0.94, 2)

            profit = ((target - price) / price * 100) if price > 0 else 0
            entry  = "NXT/장전" if market == "KR" else "프리마켓"
            fmt    = lambda v: f"{int(v):,}" if market == "KR" else f"{v:.2f}"

            return (
                f"🎯 <b>{s['name']}</b> ({s['ticker']}) [{s['theme']}]\n"
                f"{timing} | 현재가: {currency}{fmt(price)}\n"
                f"1차: {currency}{fmt(buy1)} ({entry})\n"
                f"2차: {currency}{fmt(buy2)}\n"
                f"목표: {currency}{fmt(target)} (+{profit:.0f}%) | 손절: {currency}{fmt(stop)}\n"
            )

        if kr_signals:
            msg += "🇰🇷 <b>한국</b>\n━━━━━━━━━━━━━━━\n"
            for s in kr_signals[:3]:
                msg += fmt_stock(s) + "\n"

        if us_signals:
            msg += "🇺🇸 <b>미국</b>\n━━━━━━━━━━━━━━━\n"
            for s in us_signals[:3]:
                msg += fmt_stock(s) + "\n"

        if gambles:
            msg += "🎰 <b>도박</b> (총자산 2% 이하)\n━━━━━━━━━━━━━━━\n"
            for s in gambles[:3]:
                market   = s.get('market', 'US')
                currency = "$" if market == "US" else "₩"
                price    = s.get('price', 0)
                target   = round(price * 3.0, 2)
                stop     = round(price * 0.80, 2)
                buy1     = round(price * 0.99, 2)
                fmt      = lambda v: f"{int(v):,}" if market == "KR" else f"{v:.2f}"
                msg += (
                    f"🎲 <b>{s['name']}</b> ({s['ticker']}) [{s['theme']}]\n"
                    f"현재가: {currency}{fmt(price)} | 매수: {currency}{fmt(buy1)}\n"
                    f"목표: {currency}{fmt(target)} (3~5배) | 손절: {currency}{fmt(stop)}\n\n"
                )

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
