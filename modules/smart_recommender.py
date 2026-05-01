import os
import sys
import json
import time
from datetime import datetime
from dotenv import load_dotenv
from modules.gap_filter import classify_gap

sys.path.insert(0, '/media/dps/T7/stock_ai')
load_dotenv('/media/dps/T7/stock_ai/.env')


# ── 장세별 전략 파라미터 ────────────────────────────────────────────
#
# 장세       | 이평선 중심           | RSI 역할        | 임계값
# ───────────┼─────────────────────┼────────────────┼───────
# 강세/가속   | 정배열+신고가 우선    | 85이상만 감점   | 낮음(2)
# 과열경계    | 눌림목 필수           | 75이상 감점     | 보통(3)
# 조정초입    | 60일선 지지 필수      | 35이하 가산     | 보통(3)
# 조정중      | 60일선+RSI30이하     | 30이하 강가산   | 높음(4)
# ──────────────────────────────────────────────────────────────────

REGIME_PARAMS = {
    "강세":    {"ma_weight": 3, "rsi_sell": 85, "rsi_buy": 0,  "threshold": 2, "pullback_req": False},
    "상승가속": {"ma_weight": 3, "rsi_sell": 85, "rsi_buy": 0,  "threshold": 2, "pullback_req": False},
    "과열경계": {"ma_weight": 2, "rsi_sell": 75, "rsi_buy": 0,  "threshold": 3, "pullback_req": True},
    "과열":    {"ma_weight": 2, "rsi_sell": 75, "rsi_buy": 0,  "threshold": 4, "pullback_req": True},
    "조정초입": {"ma_weight": 2, "rsi_sell": 0,  "rsi_buy": 35, "threshold": 3, "pullback_req": False},
    "조정중":  {"ma_weight": 1, "rsi_sell": 0,  "rsi_buy": 30, "threshold": 4, "pullback_req": False},
    "중립":    {"ma_weight": 2, "rsi_sell": 75, "rsi_buy": 35, "threshold": 3, "pullback_req": False},
    "약세":    {"ma_weight": 1, "rsi_sell": 0,  "rsi_buy": 30, "threshold": 5, "pullback_req": False},
}


class SmartRecommender:
    """
    수급 기반 스마트 추천 (전면 개편)
    ─────────────────────────────────
    scoring 우선순위:
      1) 수급    — 외국인/기관 연속 매수 (가장 선행)
      2) 이평선  — 정배열/눌림목/60일선 지지 (장세별)
      3) 거래량  — 매집 vs 이탈 판단
      4) 테마/섹터 모멘텀 — 대장주 올랐는데 2등주 미반응
      5) RSI    — 보조 지표 (장세별 가중치 변화)
      6) 재무   — 최소 필터 (적자 제외)

    슬롯:
      07:30단기    — KR 오늘 오를 것, 수급+이평선 중심
      09:40확신    — 정규장 초반 방향 확인 후, 임계값 +1 높게
      14:30선점    — 내일 NXT용, 오늘 안 오른 매집 종목
      16:30NXT선점 — 오후 NXT용, 14:30과 동일 로직
      20:30        — US 장전, 미국 종목
      23:30단기    — US 개장 초반 방향 확인 후
    """

    def __init__(self):
        from modules.kis_api import KISApi
        self.kis = KISApi()

    # ────────────────────────────────────────────────
    # 내부 헬퍼
    # ────────────────────────────────────────────────

    def _get_params(self, regime_type: str) -> dict:
        """장세별 파라미터 반환 (없으면 중립 기본값)"""
        return REGIME_PARAMS.get(regime_type, REGIME_PARAMS["중립"])

    def _get_dynamic_threshold(self, regime_type: str, base_extra: int = 0) -> int:
        """
        dynamic_strategy.json → kr_score_threshold 우선 사용
        없으면 REGIME_PARAMS 기본값 + base_extra
        """
        try:
            strategy_path = '/media/dps/T7/stock_ai/dynamic_strategy.json'
            with open(strategy_path, encoding='utf-8') as f:
                strategy = json.load(f)
            threshold = strategy.get('kr_score_threshold',
                                     self._get_params(regime_type)['threshold'])
        except Exception:
            threshold = self._get_params(regime_type)['threshold']
        return int(threshold) + base_extra

    def _get_sector_stocks(self, sector_names):
        """선정된 섹터 종목 추출 — 유연한 키워드 매칭, 부족하면 전체 DB 폴백"""
        from modules.sector_db import SECTOR_DB
        stocks = {}

        keywords = set()
        for s in sector_names:
            keywords.add(s.lower())
            for word in s.split():
                if len(word) >= 2:
                    keywords.add(word.lower())

        for sector_name, sector_data in SECTOR_DB.items():
            if sector_data.get('market', 'KR') != 'KR':
                continue
            sn_lower = sector_name.lower()
            matched  = any(kw in sn_lower or sn_lower in kw for kw in keywords)
            if not matched:
                continue
            for tier in ['대장주', '2등주', '소부장']:
                tier_data = sector_data.get(tier, {})
                if tier == '소부장' and isinstance(tier_data, dict):
                    for sub in tier_data.values():
                        if isinstance(sub, dict):
                            for name, ticker in sub.items():
                                stocks[ticker] = {"name": name, "sector": sector_name, "tier": tier}
                else:
                    for name, ticker in tier_data.items():
                        stocks[ticker] = {"name": name, "sector": sector_name, "tier": tier}

        print(f"  📋 섹터 매칭: {sector_names} → {len(stocks)}개 종목")

        # 매칭 부족 시 전체 DB 폴백 (이게 "후보 없음"의 원인이었음)
        if len(stocks) < 5:
            print("  ⚠️ 섹터 매칭 부족 → KR 전체 DB 폴백")
            stocks = self._get_all_kr_stocks()

        return stocks

    def _get_all_kr_stocks(self):
        """KR 전체 종목 반환"""
        from modules.sector_db import SECTOR_DB
        stocks = {}
        for sector_name, sector_data in SECTOR_DB.items():
            if sector_data.get('market', 'KR') != 'KR':
                continue
            for tier in ['대장주', '2등주', '소부장']:
                tier_data = sector_data.get(tier, {})
                if tier == '소부장' and isinstance(tier_data, dict):
                    for sub in tier_data.values():
                        if isinstance(sub, dict):
                            for name, ticker in sub.items():
                                stocks[ticker] = {"name": name, "sector": sector_name, "tier": tier}
                else:
                    for name, ticker in tier_data.items():
                        stocks[ticker] = {"name": name, "sector": sector_name, "tier": tier}
        print(f"  📋 전체 KR DB: {len(stocks)}개 종목")
        return stocks

    def _get_all_us_stocks(self):
        """US 전체 종목 반환"""
        from modules.sector_db import SECTOR_DB
        stocks = {}
        for sector_name, sector_data in SECTOR_DB.items():
            if sector_data.get('market') != 'US':
                continue
            for tier in ['대장주', '2등주']:
                for name, ticker in sector_data.get(tier, {}).items():
                    stocks[ticker] = {"name": name, "sector": sector_name, "tier": tier}
        return stocks

    def _apply_financial_filter(self, stocks):
        """적자 종목 제외"""
        try:
            from modules.financial_filter import FinancialFilter
            ff = FinancialFilter()
            stocks, removed = ff.filter_profitable(stocks, market="KR")
            if removed:
                print(f"  🚫 적자 제외: {', '.join(removed[:3])}")
        except Exception as e:
            print(f"  ⚠️ 재무 필터 실패 (전체 통과): {e}")
        return stocks

    def _collect_supply(self, stocks):
        """수급 데이터 수집 (상위 20개 종목 대상)"""
        supply_results = {}
        try:
            from modules.supply_demand import SupplyDemand
            sd = SupplyDemand()
            supply_dict = {info["name"]: ticker for ticker, info in list(stocks.items())[:20]}
            results = sd.scan_supply(supply_dict)
            for r in results:
                supply_results[r['code']] = r
        except Exception as e:
            print(f"  ⚠️ 수급 수집 실패: {e}")
        return supply_results

    def _get_today_sector_changes(self, stocks):
        """오늘 섹터별 대장주 평균 등락률 계산 (오후 선점용)"""
        sector_changes = {}
        sector_counts  = {}
        for ticker, info in stocks.items():
            if info['tier'] != '대장주':
                continue
            try:
                d = self.kis.get_kr_price(ticker)
                if not d:
                    continue
                s = info['sector']
                sector_changes[s] = sector_changes.get(s, 0) + d.get('change_pct', 0)
                sector_counts[s]  = sector_counts.get(s, 0) + 1
                time.sleep(0.1)
            except Exception:
                pass
        return {s: sector_changes[s] / sector_counts[s]
                for s in sector_changes if sector_counts.get(s, 0) > 0}

    # ────────────────────────────────────────────────
    # 스코어링 — 아침/확신 (오늘 오를 것)
    # ────────────────────────────────────────────────

    def _score_morning(self, ticker, info, regime_type, supply_data=None):
        """
        아침/확신 추천 스코어링
        우선순위: 수급 > 이평선 배열 > 거래량 > 섹터 티어 > RSI(보조)
        """
        import yfinance as yf

        score   = 0
        signals = []
        params  = self._get_params(regime_type)

        try:
            kis_data = self.kis.get_kr_price(ticker)
            if not kis_data:
                return None

            price  = kis_data['price']
            change = kis_data['change_pct']
            volume = kis_data.get('volume', 0)

            # KIS 일봉 (yfinance KR 사용 안 함)
            indicators = self.kis.calc_indicators_kr(ticker, days=80)
            if not indicators:
                return None

            import pandas as pd
            rows = self.kis.get_kr_ohlcv(ticker, days=80)
            if not rows or len(rows) < 20:
                return None
            df       = pd.DataFrame(rows)
            close    = df['close'].astype(float)
            vol_hist = df['volume'].astype(float)
            avg_vol  = vol_hist.mean()
            vol_ratio = round(volume / avg_vol, 1) if avg_vol > 0 else 1

            ma5      = indicators['ma5']
            ma20     = indicators['ma20']
            ma60     = indicators['ma60']
            rsi      = indicators['rsi']
            obv_trend = indicators['obv_trend']
            drawdown  = indicators['drawdown']
            high_52w  = indicators['high_52w']
            macd = indicators.get('macd', 0)
            macd_signal = indicators.get('macd_signal', 0)
            macd_cross = indicators.get('macd_cross', 'none')

            # ── 1) 수급 (가장 선행, 최고 가중) ─────────
            if supply_data:
                foreign_cons = supply_data.get('foreign_consecutive', 0)
                organ_cons   = supply_data.get('organ_consecutive', 0)
                foreign      = supply_data.get('foreign', 0)
                organ        = supply_data.get('organ', 0)

                if foreign_cons >= 3:
                    score += 5; signals.append(f"외국인 {foreign_cons}일 연속 순매수")
                elif foreign_cons >= 2:
                    score += 3; signals.append(f"외국인 {foreign_cons}일 연속 순매수")
                elif foreign > 0:
                    score += 1; signals.append("외국인 순매수")

                if organ_cons >= 3:
                    score += 5; signals.append(f"기관 {organ_cons}일 연속 순매수")
                elif organ_cons >= 2:
                    score += 3; signals.append(f"기관 {organ_cons}일 연속 순매수")
                elif organ > 0:
                    score += 1; signals.append("기관 순매수")

                if foreign > 0 and organ > 0:
                    score += 2; signals.append("외국인+기관 동시 매수")

            # ── 2) 이평선 배열 (장세별 핵심) ────────────
            w = params['ma_weight']

            if regime_type in ('강세', '상승가속'):
                # 정배열: 5>20>60 = 추세 확인, 가장 안전한 진입
                if ma5 > ma20 > ma60:
                    score += w; signals.append("정배열(5>20>60)")
                # 5일선 눌림 후 막 회복 = 최적 진입 타이밍
                if ma20 > ma5 * 0.98 and price > ma5:
                    score += 2; signals.append("5일선 눌림 반등")
                # 신고가 근접 (52주 고점 5% 이내)
                if drawdown >= -5:
                    score += 1; signals.append(f"52주 신고가 근접({drawdown}%)")

            elif regime_type in ('과열경계', '과열'):
                # 눌림목 필수: 오늘 0~-5% 구간
                if -5 <= change <= 0:
                    score += w; signals.append(f"과열장 눌림목({change:+.1f}%)")
                elif change > 5:
                    score -= 2; signals.append(f"추격주의({change:+.1f}% 급등)")
                # 5일선이 20일선보다 10% 이상 위 = 단기 과열, 진입 자제
                if ma5 > ma20 * 1.10:
                    score -= 2; signals.append("단기 과열 이격")

            elif regime_type in ('조정초입', '조정중'):
                # 60일선 지지 필수
                if price >= ma60 * 0.98:
                    score += w; signals.append("60일선 지지")
                else:
                    score -= 2; signals.append("60일선 하회(위험)")
                if ma5 < ma20:
                    score -= 1  # 역배열 감점

            else:  # 중립
                if ma5 > ma20:
                    score += 1; signals.append("단기 정배열")

            # ── 3) 거래량 패턴 ───────────────────────────
            if vol_ratio >= 2.0:
                score += 3; signals.append(f"거래량 {vol_ratio}배 급증")
            elif vol_ratio >= 1.5:
                score += 2; signals.append(f"거래량 {vol_ratio}배 증가")
            elif vol_ratio >= 1.2:
                score += 1; signals.append(f"거래량 {vol_ratio}배")

            # OBV 상승 = 매집 신호
            if obv_trend == "상승":
                score += 1; signals.append("OBV 상승(매집)")

            # ── 4) 섹터 티어 보정 ───────────────────────
            if info['tier'] == '대장주':
                score += 1   # 신뢰도 높음
            elif info['tier'] == '소부장':
                score -= 1   # 단기 변동성 높음

            # ── 5) RSI (보조, 장세별 가중) ───────────────
            rsi_sell = params['rsi_sell']
            rsi_buy  = params['rsi_buy']

            if rsi_sell and rsi >= rsi_sell:
                score -= 2; signals.append(f"RSI {rsi:.0f} 과열(진입주의)")
            if rsi_buy and rsi <= rsi_buy:
                score += 2; signals.append(f"RSI {rsi:.0f} 과매도(반등기대)")
            elif 45 <= rsi <= 65:
                score += 1; signals.append(f"RSI {rsi:.0f} 적정")

            # ── 6) MACD 보조 ─────────────────────────────
            if macd_cross == "golden":
                score += 2; signals.append("MACD 골든크로스")
            elif macd_cross == "dead":
                score -= 2; signals.append("MACD 데드크로스")

            if macd > 0 and macd > macd_signal:
                score += 1; signals.append("MACD 양수+상승")
            elif macd < 0:
                score -= 1; signals.append("MACD 음수")

            return {
                "name":      info["name"],
                "ticker":    ticker,
                "sector":    info["sector"],
                "tier":      info["tier"],
                "price":     price,
                "change":    change,
                "vol_ratio": vol_ratio,
                "rsi":       rsi,
                "obv_trend": obv_trend,
                "ma5":       round(ma5, 0),
                "ma20":      round(ma20, 0),
                "ma60":      round(ma60, 0),
                "drawdown":  drawdown,
                "score":     score,
                "signals":   signals,
            }

        except Exception:
            return None

    # ────────────────────────────────────────────────
    # 스코어링 — 오후 선점 (내일 오를 것)
    # ────────────────────────────────────────────────

    def _score_afternoon(self, ticker, info, regime_type, today_sector_changes=None):
        """
        오후/NXT 선점 스코어링
        핵심: 오늘 거래량 터졌는데 주가 안 오름 = 세력이 조용히 쌓는 중
              오늘 강한 섹터의 아직 안 오른 2등주/소부장
        RSI는 여기서도 보조만
        """
        import yfinance as yf

        score   = 0
        signals = []
        params  = self._get_params(regime_type)

        try:
            kis_data = self.kis.get_kr_price(ticker)
            if not kis_data:
                return None

            price  = kis_data['price']
            change = kis_data['change_pct']
            volume = kis_data.get('volume', 0)

            # KIS 일봉 (yfinance KR 사용 안 함)
            indicators = self.kis.calc_indicators_kr(ticker, days=80)
            if not indicators:
                return None

            import pandas as pd
            rows = self.kis.get_kr_ohlcv(ticker, days=80)
            if not rows or len(rows) < 10:
                return None
            df       = pd.DataFrame(rows)
            vol_hist = df['volume'].astype(float)
            avg_vol  = vol_hist.mean()
            vol_ratio = round(volume / avg_vol, 1) if avg_vol > 0 else 1

            ma5  = indicators['ma5']
            ma20 = indicators['ma20']
            ma60 = indicators['ma60']
            rsi  = indicators['rsi']
            macd = indicators.get('macd', 0)
            macd_signal = indicators.get('macd_signal', 0)
            macd_cross = indicators.get('macd_cross', 'none')

            # ── 1) 핵심: 매집 신호 ──────────────────────
            # 거래량 터졌는데 주가 안 오름 = 세력 조용히 매집 중
            if vol_ratio >= 2.0 and -2 <= change <= 2:
                score += 6; signals.append(f"핵심매집: 거래량{vol_ratio}배↑ 주가보합({change:+.1f}%)")
            elif vol_ratio >= 1.5 and change <= 1:
                score += 3; signals.append(f"매집신호: 거래량{vol_ratio}배 주가소폭")

            # ── 2) 섹터 파급 효과 (오늘 안 오른 2등주) ──
            if info['tier'] in ('2등주', '소부장') and -1 <= change <= 1:
                score += 3; signals.append(f"섹터 {info['tier']} 미반응(내일 파급 기대)")

            # 오늘 강한 섹터의 아직 안 오른 종목
            if today_sector_changes:
                sc = today_sector_changes.get(info['sector'], 0)
                if sc >= 2 and change <= 1:
                    score += 3; signals.append(f"대장주 {sc:+.1f}% 섹터, 본 종목 미반응")
                elif sc >= 1 and change <= 0:
                    score += 2; signals.append(f"섹터 강세인데 보합")

            # ── 3) 이평선 — 진입 위치 확인 ──────────────
            if regime_type in ('강세', '상승가속'):
                # 정배열이면서 5일선으로 눌림 = NXT 최적 진입점
                if ma5 > ma20 > ma60 and -3 <= change <= 0:
                    score += 3; signals.append("정배열 5일선 눌림(NXT 최적)")
                elif ma5 > ma20:
                    score += 1; signals.append("단기 정배열")

            elif regime_type in ('과열경계', '과열'):
                # 과열장: -5~0% 눌림목만
                if -5 <= change <= 0 and ma5 < ma20 * 1.05:
                    score += 2; signals.append(f"과열장 눌림목({change:+.1f}%)")
                elif change > 3:
                    # 오늘 이미 많이 오른 종목은 내일 추가 상승 어려움
                    score -= 3; signals.append("오늘 급등(내일 추가상승 어려움)")

            elif regime_type in ('조정초입', '조정중'):
                if price >= ma60 * 0.97:
                    score += 2; signals.append("60일선 근접 지지")

            # ── 4) 거래량 추가 체크 ──────────────────────
            if vol_ratio >= 3.0:
                score += 2; signals.append(f"거래량 {vol_ratio}배 폭발")

            # ── 5) RSI 보조 ──────────────────────────────
            rsi_buy = params['rsi_buy']
            if rsi_buy and rsi <= rsi_buy:
                score += 2; signals.append(f"RSI {rsi:.0f} 과매도")
            elif rsi >= 80:
                score -= 2; signals.append(f"RSI {rsi:.0f} 이미 과열")

            if macd_cross == "golden":
                score += 2; signals.append("MACD 골든크로스")
            elif macd_cross == "dead":
                score -= 2; signals.append("MACD 데드크로스")
            if macd > 0 and macd > macd_signal:
                score += 1; signals.append("MACD 양수+상승")
            elif macd < 0:
                score -= 1; signals.append("MACD 음수")

            # 오늘 이미 급등한 종목은 오후 선점 부적합
            if change >= 5:
                score -= 4; signals.append(f"오늘 {change:+.1f}% 급등(오후 진입 부적합)")

            return {
                "name":      info["name"],
                "ticker":    ticker,
                "sector":    info["sector"],
                "tier":      info["tier"],
                "price":     price,
                "change":    change,
                "vol_ratio": vol_ratio,
                "rsi":       rsi,
                "ma5":       round(ma5, 0),
                "ma20":      round(ma20, 0),
                "ma60":      round(ma60, 0),
                "score":     score,
                "signals":   signals,
            }

        except Exception:
            return None

    # ────────────────────────────────────────────────
    # 공개 API — KR 추천
    # ────────────────────────────────────────────────

    async def recommend_morning(self, sector_names, regime_type, macro_context=None):
        """
        07:30 장전 단기 추천 → NXT 08:00 / 정규장 초반 진입
        오늘 오를 것: 수급 + 이평선 배열 + 거래량 중심
        """
        print(f"[{datetime.now().strftime('%H:%M')}] 🟡 단기 추천 시작 (장세:{regime_type})")

        stocks = self._get_sector_stocks(sector_names)
        stocks = self._apply_financial_filter(stocks)
        supply_results = self._collect_supply(stocks)

        threshold = self._get_dynamic_threshold(regime_type)
        print(f"  📊 임계값: {threshold} (장세:{regime_type})")

        candidates = []
        for ticker, info in stocks.items():
            supply_data = supply_results.get(ticker)
            data = self._score_morning(ticker, info, regime_type, supply_data)
            if data and data['score'] >= threshold:
                candidates.append(data)
            time.sleep(0.15)

        candidates.sort(key=lambda x: x['score'], reverse=True)
        top10 = candidates[:10]

        # 임계값 낮춰서 재시도 (완전 빈손 방지)
        if not top10:
            lower = max(1, threshold - 1)
            print(f"  ⚠️ 임계값 {threshold} 충족 없음 → {lower} 재시도")
            candidates = []
            for ticker, info in stocks.items():
                supply_data = supply_results.get(ticker)
                data = self._score_morning(ticker, info, regime_type, supply_data)
                if data and data['score'] >= lower:
                    candidates.append(data)
                time.sleep(0.10)
            candidates.sort(key=lambda x: x['score'], reverse=True)
            top10 = candidates[:10]

        if not top10:
            return None

        result = await self._ai_analyze(
            top10, regime_type, "07:30단기",
            "NXT 08:00 / 정규장 초반 진입용 단기 추천. 오늘 오를 것.",
            macro_context
        )
        if result:
            self._record_backtest(result, "07:30단기", regime_type)
        return result

    async def recommend_conviction(self, sector_names, regime_type, macro_context=None):
        """
        09:40 확신 추천 — 정규장 초반 방향 확인 후
        임계값 +1로 더 엄격하게 선별
        """
        print(f"[{datetime.now().strftime('%H:%M')}] 🎯 확신 추천 시작 (장세:{regime_type})")

        stocks = self._get_sector_stocks(sector_names)
        stocks = self._apply_financial_filter(stocks)
        supply_results = self._collect_supply(stocks)

        threshold = self._get_dynamic_threshold(regime_type, base_extra=1)
        print(f"  📊 확신 임계값: {threshold}")

        candidates = []
        for ticker, info in stocks.items():
            supply_data = supply_results.get(ticker)
            data = self._score_morning(ticker, info, regime_type, supply_data)
            if data and data['score'] >= threshold:
                candidates.append(data)
            time.sleep(0.15)

        candidates.sort(key=lambda x: x['score'], reverse=True)
        top5 = candidates[:5]

        # 장이 강한데도 후보가 0개면 임계값을 1단계 완화해 재시도
        # (09:40은 원래 엄격하지만, 완전 공백 메시지는 실전에서 신뢰를 떨어뜨림)
        if not top5:
            lower = max(1, threshold - 1)
            print(f"  ⚠️ 확신 후보 없음 → 임계값 {lower} 재시도")
            for ticker, info in stocks.items():
                supply_data = supply_results.get(ticker)
                data = self._score_morning(ticker, info, regime_type, supply_data)
                if data and data['score'] >= lower:
                    candidates.append(data)
                time.sleep(0.10)
            candidates.sort(key=lambda x: x['score'], reverse=True)
            top5 = candidates[:5]
        
        if not top5:
            return None

        result = await self._ai_analyze(
            top5, regime_type, "09:40확신",
            "정규장 초반 방향 확인 후 확신 추천. 점수 높은 종목만.",
            macro_context
        )
        if result:
            self._record_backtest(result, "09:40확신", regime_type)
        return result

    async def recommend_afternoon(self, sector_names, regime_type, macro_context=None):
        """
        14:30 / 16:30 오후 선점 추천 → 내일 NXT 진입
        핵심: KR 전체 DB 스캔 (섹터 제한 없음)
              오늘 안 오른 종목 중 매집 신호 + 섹터 파급 효과
        """
        print(f"[{datetime.now().strftime('%H:%M')}] 🕑 오후 선점 추천 시작 (장세:{regime_type})")

        # 오후는 아침 선정 섹터에 갇히지 않고 전체 DB 스캔
        # 이유: 아침에 올랐던 섹터는 이미 끝난 것
        #       오후엔 아직 안 오른 섹터에서 내일 주인공을 찾아야 함
        stocks = self._get_all_kr_stocks()
        stocks = self._apply_financial_filter(stocks)

        print("  📊 섹터별 오늘 대장주 등락률 수집 중...")
        top_stocks = dict(list(stocks.items())[:40])
        today_sector_changes = self._get_today_sector_changes(top_stocks)

        threshold = self._get_dynamic_threshold(regime_type)
        print(f"  📊 임계값: {threshold}")

        candidates = []
        for ticker, info in stocks.items():
            data = self._score_afternoon(ticker, info, regime_type, today_sector_changes)
            if data and data['score'] >= threshold:
                candidates.append(data)
            time.sleep(0.15)

        candidates.sort(key=lambda x: x['score'], reverse=True)
        top10 = candidates[:10]

        if not top10:
            lower = max(1, threshold - 1)
            print(f"  ⚠️ 후보 없음 → 임계값 {lower} 재시도")
            candidates = []
            for ticker, info in stocks.items():
                data = self._score_afternoon(ticker, info, regime_type, today_sector_changes)
                if data and data['score'] >= lower:
                    candidates.append(data)
                time.sleep(0.10)
            candidates.sort(key=lambda x: x['score'], reverse=True)
            top10 = candidates[:10]

        if not top10:
            return None

        result = await self._ai_analyze(
            top10, regime_type, "14:30선점",
            "내일 NXT/장후 진입용 선점. 오늘 거래량 매집 신호 + 섹터 파급 효과 종목.",
            macro_context
        )
        if result:
            self._record_backtest(result, "14:30선점", regime_type)
        return result

    # ────────────────────────────────────────────────
    # 공개 API — US 추천 (20:30 / 23:30)
    # ────────────────────────────────────────────────

    async def analyze_and_recommend(self, news, regime_type, time_slot, macro_context=None):
        """
        US 추천 (20:30 브리핑 / 23:30 단기)
        수급 데이터 없어서 이평선 배열 + 눌림목 + 거래량 중심
        """
        import yfinance as yf

        print(f"[{datetime.now().strftime('%H:%M')}] 🌙 US 추천 시작 ({time_slot})")

        us_stocks  = self._get_all_us_stocks()
        candidates = []
        params     = self._get_params(regime_type)

        for ticker, info in list(us_stocks.items())[:60]:
            try:
                hist = yf.Ticker(ticker).history(period="60d").dropna()
                if len(hist) < 20:
                    continue

                close    = hist['Close']
                vol_hist = hist['Volume']
                curr     = close.iloc[-1]
                prev     = close.iloc[-2]
                change   = (curr - prev) / prev * 100

                avg_vol   = vol_hist.mean()
                vol_ratio = round(vol_hist.iloc[-1] / avg_vol, 1) if avg_vol > 0 else 1

                ma5  = close.rolling(5).mean().iloc[-1]
                ma20 = close.rolling(20).mean().iloc[-1]
                ma60 = close.rolling(60).mean().iloc[-1] if len(hist) >= 60 else ma20

                delta = close.diff()
                gain  = delta.clip(lower=0).rolling(14).mean()
                loss  = (-delta.clip(upper=0)).rolling(14).mean()
                rs    = gain / (loss.replace(0, 0.0001))
                rsi   = round((100 - 100 / (1 + rs)).iloc[-1], 1)

                high_52w = close.max()
                drawdown = round((curr - high_52w) / high_52w * 100, 1)

                score   = 0
                signals = []

                # 이평선 배열
                if ma5 > ma20 > ma60:
                    score += 3; signals.append("정배열")
                elif ma5 > ma20:
                    score += 1; signals.append("단기 정배열")

                # 눌림목 (오늘 -5~-1% = 내일 반등 기대)
                if -5 <= change <= -1:
                    score += 2; signals.append(f"눌림목({change:+.1f}%)")
                elif 0 < change <= 3:
                    score += 1; signals.append(f"소폭 상승({change:+.1f}%)")
                elif change > 5:
                    score -= 1; signals.append("급등 추격주의")

                # 거래량
                if vol_ratio >= 1.5:
                    score += 2; signals.append(f"거래량{vol_ratio}배")

                # RSI (장세별)
                rsi_sell = params['rsi_sell']
                rsi_buy  = params['rsi_buy']
                if rsi_sell and rsi >= rsi_sell:
                    score -= 2
                if rsi_buy and rsi <= rsi_buy:
                    score += 2; signals.append(f"RSI{rsi:.0f} 과매도")
                elif 40 <= rsi <= 65:
                    score += 1

                # 52주 고점 대비 조정 구간
                if -15 <= drawdown <= -5:
                    score += 1; signals.append(f"고점대비 {drawdown}% 조정")

                if score >= 3:
                    candidates.append({
                        "name":      info["name"],
                        "ticker":    ticker,
                        "sector":    info["sector"],
                        "tier":      info["tier"],
                        "price":     round(curr, 2),
                        "change":    round(change, 2),
                        "vol_ratio": vol_ratio,
                        "rsi":       rsi,
                        "ma5":       round(ma5, 2),
                        "ma20":      round(ma20, 2),
                        "ma60":      round(ma60, 2),
                        "drawdown":  drawdown,
                        "score":     score,
                        "signals":   signals,
                    })

                time.sleep(0.5)
            except Exception as e:
                print(f"  warning {ticker} 조회 실패: {e}")
                continue

        candidates.sort(key=lambda x: x['score'], reverse=True)
        top10 = candidates[:10]

        if not top10:
            return {"market_summary": "조건 충족 US 종목 없음",
                    "strategy": "관망",
                    "recommendations": [],
                    "source": time_slot}

        source = "23:30단기" if "23" in str(time_slot) else "20:30"
        result = await self._ai_analyze(
            top10, regime_type, source,
            f"미국 주식 {time_slot} 추천. 이평선 배열 + 눌림목 + 거래량 기반.",
            macro_context
        )
        if result:
            self._record_backtest(result, source, regime_type)
        return result

    # ────────────────────────────────────────────────
    # AI 최종 판단
    # ────────────────────────────────────────────────

    async def _ai_analyze(self, candidates, regime_type, source, description, macro_context=None):
        """규칙 기반으로 좁혀진 후보 → AI가 최종 5개 선별 및 진입가/목표가 산출"""
        from anthropic import Anthropic
        import re

        client = Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))

        cand_text = ""
        for c in candidates:
            sig_text = " | ".join(c.get('signals', [])[:4])
            ma_text  = (f"5일:{c.get('ma5',0):,.0f} 20일:{c.get('ma20',0):,.0f} "
                        f"60일:{c.get('ma60',0):,.0f}") if c.get('ma5') else ""
            cand_text += (
                f"{c['name']}({c['ticker']}) {c['sector']}/{c.get('tier','')}\n"
                f"  현재가:{c['price']:,} 등락:{c.get('change',0):+.1f}%"
                f" 거래량:{c.get('vol_ratio',1)}배\n"
                f"  {ma_text}\n"
                f"  RSI:{c.get('rsi','?')} 점수:{c['score']} 신호:{sig_text}\n\n"
            )

        macro_text = ""
        if macro_context:
            ai_r = macro_context.get("ai_result", {})
            macro_text = (
                f"시장전망: {ai_r.get('market_outlook','')}\n"
                f"장세신뢰도: {ai_r.get('regime_confidence','')}\n"
                f"과열섹터: {', '.join(ai_r.get('overheated_sectors',[]))}"
            )

        prompt = f"""한국 주식 전문 트레이더로서 종목을 추천해주세요.
마크다운 금지. JSON으로만.

=== 추천 목적 ===
{description}

=== 장세 ===
{regime_type}장

=== 시장 컨텍스트 ===
{macro_text}

=== 후보 종목 (수급+이평선+거래량 스코어링 결과) ===
{cand_text}

추천 기준:
1. 수급 점수 높은 종목 우선 (외국인/기관 연속 매수가 가장 중요)
2. 이평선 배열 확인 (정배열 진입이 가장 안전)
3. 이미 많이 오른 종목은 추격주의 표시
4. {regime_type}장 전략에 맞게 선택
5. 직장인이라 정규장 09:00 진입 불가 (NXT 또는 퇴근 후 NXT 활용)

추천 5개, JSON으로만:
{{
  "market_summary": "시장 한줄 요약",
  "strategy": "오늘 전략 한줄",
  "recommendations": [
    {{
      "name": "종목명",
      "ticker": "티커",
      "sector": "섹터",
      "tier": "대장주/2등주/소부장",
      "reason": "추천 이유 한줄 (수급/이평선/거래량 근거 명시)",
      "current_price": 000000,
      "buy_price": 000000,
      "buy_timing": "NXT 08:00 / 정규장 초반 / 퇴근후 NXT / 오늘밤",
      "target1": 000000,
      "target2": 000000,
      "stop_loss": 000000,
      "risk_reward": "1:2",
      "caution": "추격주의 또는 없음",
      "strategy_type": "선점형/모멘텀형/눌림목형/매집형"
    }}
  ]
}}"""

        try:
            print("  🧠 AI 최종 판단 중...")
            res  = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=1500,
                messages=[{"role": "user", "content": prompt}]
            )
            text = re.sub(r'```json|```', '', res.content[0].text.strip()).strip()
            m    = re.search(r'\{.*\}', text, re.DOTALL)
            if m:
                result           = json.loads(m.group())
                result['source'] = source
                return result
        except Exception as e:
            print(f"  ❌ AI 판단 실패: {e}")
        return None

    # ────────────────────────────────────────────────
    # backtest 기록
    # ────────────────────────────────────────────────

    def _record_backtest(self, result, source, regime_type):
        try:
            from modules.backtest import BacktestSystem
            bt = BacktestSystem()
            for r in result.get('recommendations', [])[:5]:
                score = r.get('score', 3)
                if score >= 5:   grade = "A"
                elif score >= 4: grade = "B"
                elif score >= 3: grade = "C"
                else:            grade = "D"
                # US 티커 판별: 영문자만 + 5자 이하
                is_us = r['ticker'].isalpha() and len(r['ticker']) <= 5
                bt.record(
                    ticker       = r['ticker'],
                    name         = r['name'],
                    entry_price  = r.get('buy_price', r.get('current_price', 0)),
                    target_price = r.get('target1', 0),
                    stop_loss    = r.get('stop_loss', 0),
                    market       = "US" if is_us else "KR",
                    hold_type    = "단기",
                    source       = source,
                    regime       = regime_type,
                    grade        = grade
                )
            print(f"  📝 backtest 기록 완료 ({len(result.get('recommendations',[]))}개)")
        except Exception as e:
            print(f"  ⚠️ backtest 기록 실패: {e}")

    # ────────────────────────────────────────────────
    # 메시지 생성
    # ────────────────────────────────────────────────

    def build_message(self, result, time_slot="07:30단기"):
        if not result:
            return "❌ 추천 분석 실패"

        slot_info = {
            "07:30단기":    ("🌅", "장전 단기 추천",      "NXT 08:00 진입"),
            "09:40확신":    ("🎯", "확신 추천",           "정규장 초반 진입"),
            "14:30선점":    ("🕑", "내일 선점 추천",      "NXT/장후 진입"),
            "16:30NXT선점": ("🌆", "오후 NXT 선점",       "NXT 진입"),
            "20:30":        ("🌙", "미국장 추천",          "오늘 밤 진입"),
            "23:30단기":    ("🌙", "미국 단기 추천",       "개장 초반 확인 후"),
        }
        source = result.get('source', time_slot)
        emoji, title, timing = slot_info.get(source, ("📊", "추천", ""))

        msg  = f"{emoji} <b>{title}</b> {datetime.now().strftime('%m/%d %H:%M')}\n"
        msg += f"<i>{timing}</i>\n\n"
        msg += f"📊 {result.get('market_summary', '')}\n"
        msg += f"⚔️ {result.get('strategy', '')}\n\n"
        msg += "━━━━━━━━━━━━━━━━━━━\n"

        strategy_emojis = {
            "선점형": "🎯", "모멘텀형": "🚀",
            "눌림목형": "📉", "매집형": "🔍",
        }

        def fmt(val):
            try:    return f"{int(val):,}원"
            except: return "?"

        for r in result.get('recommendations', [])[:5]:
            se = strategy_emojis.get(r.get('strategy_type', ''), "📊")
            caution = r.get('caution', '없음')
            caution_text = f"\n   ⚠️ {caution}" if caution and caution != "없음" else ""

            msg += f"{se} <b>{r['name']}</b> ({r['ticker']})\n"
            msg += f"   {r['sector']} / {r.get('tier','')}\n"
            msg += f"   {r.get('reason','')}{caution_text}\n\n"
            msg += f"   💰 현재가: {fmt(r.get('current_price', 0))}\n"
            msg += f"   🟢 매수가: {fmt(r.get('buy_price', 0))}\n"
            gap_pct = float(r.get('change_pct', 0) or 0)
            market = "US" if str(r.get("ticker", "")).isalpha() else "KR"
            msg += f"   🏷 갭업:   {classify_gap(market, gap_pct)} ({gap_pct:+.1f}%)\n"
            msg += f"   ⏱ 진입:   {r.get('buy_timing','')}\n"
            msg += f"   🎯 목표1:  {fmt(r.get('target1', 0))}\n"
            msg += f"   🎯 목표2:  {fmt(r.get('target2', 0))}\n"
            msg += f"   🛑 손절:   {fmt(r.get('stop_loss', 0))}\n"
            msg += f"   ⚖️ 리스크: {r.get('risk_reward','')}\n"
            msg += "━━━━━━━━━━━━━━━━━━━\n"

        msg += f"\n⚠️ 최종 판단은 본인이 하세요.\n"
        msg += f"📝 모의 backtest 자동 기록됨\n"
        msg += f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        return msg
