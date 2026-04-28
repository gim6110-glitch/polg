import os
import sys
import json
import time
from datetime import datetime
from dotenv import load_dotenv

sys.path.insert(0, '/media/dps/T7/stock_ai')
load_dotenv('/media/dps/T7/stock_ai/.env')


class SmartRecommender:
    """
    레이어 2: 수급 기반 스마트 추천 (전면 개편)
    - AI 선정 섹터 내 종목만 스캔
    - 수급 스코어링 (외국인/기관/거래량/기술적)
    - 07:30 vs 14:30 완전히 다른 로직
    - backtest 자동 기록
    """

    def __init__(self):
        from modules.kis_api import KISApi
        self.kis = KISApi()

    # ── 섹터 내 종목 수집 ──────────────────────────

    def _get_sector_stocks(self, sector_names):
        """선정된 섹터의 종목 목록 추출 — 유연한 매칭"""
        from modules.sector_db import SECTOR_DB
        stocks = {}

        # 매칭 키워드 확장 (레이어1이 다양한 이름으로 섹터 반환)
        keywords = set()
        for s in sector_names:
            keywords.add(s.lower())
            # 부분 키워드 분리 (예: "반도체 소부장" → "반도체", "소부장")
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
                # 소부장이 중첩 딕셔너리인 경우 처리
                if tier == '소부장' and isinstance(tier_data, dict):
                    for sub in tier_data.values():
                        if isinstance(sub, dict):
                            for name, ticker in sub.items():
                                stocks[ticker] = {"name": name, "sector": sector_name, "tier": tier}
                        else:
                            continue
                else:
                    for name, ticker in tier_data.items():
                        stocks[ticker] = {"name": name, "sector": sector_name, "tier": tier}

        print(f"  📋 섹터 매칭: {sector_names} → {len(stocks)}개 종목")
        return stocks

    # ── 수급 스코어링 ──────────────────────────────

    def _score_stock(self, ticker, info, supply_data=None):
        """
        종목 수급 스코어링
        1순위: 외국인/기관 수급
        2순위: 거래량 패턴
        3순위: 가격 지표
        """
        import yfinance as yf

        score   = 0
        signals = []

        try:
            # KIS 실시간 가격
            kis_data = self.kis.get_kr_price(ticker)
            if not kis_data:
                return None

            price  = kis_data['price']
            change = kis_data['change_pct']
            volume = kis_data.get('volume', 0)

            # yfinance 기술적 데이터
            hist = yf.Ticker(f"{ticker}.KS").history(period="20d").dropna()
            if len(hist) < 10:
                return None

            close     = hist['Close']
            vol_hist  = hist['Volume']
            avg_vol   = vol_hist.mean()
            vol_ratio = round(volume / avg_vol, 1) if avg_vol > 0 else 1

            # VWAP 계산
            vwap = (hist['Close'] * hist['Volume']).sum() / hist['Volume'].sum()

            # RSI
            delta = close.diff()
            gain  = delta.clip(lower=0).rolling(14).mean()
            loss  = (-delta.clip(upper=0)).rolling(14).mean()
            rs    = gain / loss
            rsi   = round((100 - (100 / (1 + rs))).iloc[-1], 1)

            # OBV 방향
            obv       = (vol_hist * close.diff().apply(lambda x: 1 if x > 0 else -1)).cumsum()
            obv_trend = "상승" if obv.iloc[-1] > obv.iloc[-5] else "하락"

            # 5일선
            ma5     = close.rolling(5).mean().iloc[-1]
            ma20    = close.rolling(20).mean().iloc[-1]
            above_ma5 = price > ma5

            # ── 수급 스코어링 (1순위) ──
            if supply_data:
                foreign_cons = supply_data.get('foreign_consecutive', 0)
                organ_cons   = supply_data.get('organ_consecutive', 0)
                foreign      = supply_data.get('foreign', 0)
                organ        = supply_data.get('organ', 0)

                if foreign_cons >= 3:
                    score += 5
                    signals.append(f"🌍 외국인 {foreign_cons}일 연속 순매수")
                elif foreign_cons >= 2:
                    score += 3
                    signals.append(f"🌍 외국인 {foreign_cons}일 연속 순매수")
                elif foreign > 0:
                    score += 1
                    signals.append(f"🌍 외국인 순매수")

                if organ_cons >= 3:
                    score += 5
                    signals.append(f"🏦 기관 {organ_cons}일 연속 순매수")
                elif organ_cons >= 2:
                    score += 3
                    signals.append(f"🏦 기관 {organ_cons}일 연속 순매수")
                elif organ > 0:
                    score += 1
                    signals.append(f"🏦 기관 순매수")

                if foreign > 0 and organ > 0:
                    score += 2
                    signals.append("💪 외국인+기관 동시 매수")

            # ── 거래량 스코어링 (2순위) ──
            if vol_ratio >= 2:
                score += 3
                signals.append(f"📦 거래량 {vol_ratio}배 급증")
            elif vol_ratio >= 1.5:
                score += 2
                signals.append(f"📦 거래량 {vol_ratio}배 증가")

            # OBV 상승
            if obv_trend == "상승":
                score += 2
                signals.append("📈 OBV 상승 (매집 신호)")

            # ── 가격 지표 (3순위) ──
            # VWAP 위
            if price > vwap:
                score += 1
                signals.append(f"✅ VWAP 위 ({vwap:,.0f})")

            # 5일선 돌파
            if above_ma5:
                score += 1
                signals.append("✅ 5일선 위")

            # RSI 적정 구간
            if 40 <= rsi <= 65:
                score += 1
                signals.append(f"✅ RSI {rsi} 적정")
            elif rsi > 75:
                score -= 1
                signals.append(f"⚠️ RSI {rsi} 과열")

            # 등락률
            if 1 <= change <= 5:
                score += 1
                signals.append(f"✅ 당일 {change:+.1f}% 상승")
            elif change > 8:
                signals.append(f"⚠️ 당일 {change:+.1f}% 과열")

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
                "vwap":      round(vwap, 0),
                "above_ma5": above_ma5,
                "score":     score,
                "signals":   signals,
            }

        except Exception as e:
            return None

    # ── 07:30 단기 추천 ────────────────────────────

    async def recommend_morning(self, sector_names, regime_type, macro_context=None):
        """
        07:30 장전 단기 추천
        → NXT 08:00 진입용
        → 오늘 오를 종목 (당일 모멘텀 + 수급)
        """
        print(f"[{datetime.now().strftime('%H:%M')}] 🟡 07:30 단기 추천 시작")

        stocks      = self._get_sector_stocks(sector_names)

        # ── 재무 필터 (적자 종목 제외) ──
        try:
            from modules.financial_filter import FinancialFilter
            ff     = FinancialFilter()
            stocks, removed = ff.filter_profitable(stocks, market="KR")
            if removed:
                print(f"  🚫 적자 제외: {', '.join(removed[:3])}")
        except Exception as e:
            print(f"  ⚠️ 재무 필터 실패 (전체 통과): {e}")

        supply_dict = {info["name"]: ticker for ticker, info in list(stocks.items())[:20]}

        # 수급 데이터 수집
        supply_results = {}
        try:
            from modules.supply_demand import SupplyDemand
            sd      = SupplyDemand()
            results = sd.scan_supply(supply_dict)
            for r in results:
                supply_results[r['code']] = r
        except Exception as e:
            print(f"  ⚠️ 수급 수집 실패: {e}")

        # 장세별 임계값 — dynamic_strategy.json에서 로드 (AI가 매일 자동 조정)
        try:
            from modules.market_regime import MarketRegime
            strategy = MarketRegime().load_strategy()
            score_threshold = strategy.get("kr_score_threshold", 3)
            print(f"  📊 동적 임계값: {score_threshold} (사이클:{strategy.get('cycle_stage','?')} 조정확률:{strategy.get('correction_prob','?')}%)")
        except:
            score_threshold = {"강세": 2, "중립": 3, "약세": 4}.get(regime_type, 3)

        # 스코어링
        candidates = []
        for ticker, info in stocks.items():
            supply_data = supply_results.get(ticker)
            data        = self._score_stock(ticker, info, supply_data)
            if data and data['score'] >= score_threshold:
                candidates.append(data)
            time.sleep(0.15)

        candidates.sort(key=lambda x: x['score'], reverse=True)
        top10 = candidates[:10]

        if not top10:
            return None

        # AI 최종 판단
        result = await self._ai_analyze(
            top10, regime_type, "07:30단기",
            "NXT 08:00 진입용 당일 단기 추천",
            macro_context
        )

        # backtest 기록
        if result:
            self._record_backtest(result, "07:30단기", regime_type)

        return result

    # ── 14:30 선점 추천 ────────────────────────────

    async def recommend_afternoon(self, sector_names, regime_type, macro_context=None):
        """
        14:30 내일 선점 추천 (07:30과 완전히 다른 로직)
        → 오늘 거래량 급증했는데 주가 안 오른 종목 (매집 신호)
        → 오늘 강세 섹터 2등주/소부장
        → 내일 갭상승 노림
        """
        print(f"[{datetime.now().strftime('%H:%M')}] 🕑 14:30 선점 추천 시작")

        stocks     = self._get_sector_stocks(sector_names)

        # ── 재무 필터 (적자 종목 제외) ──
        try:
            from modules.financial_filter import FinancialFilter
            ff     = FinancialFilter()
            stocks, removed = ff.filter_profitable(stocks, market="KR")
            if removed:
                print(f"  🚫 적자 제외: {', '.join(removed[:3])}")
        except Exception as e:
            print(f"  ⚠️ 재무 필터 실패 (전체 통과): {e}")

        candidates = []

        for ticker, info in stocks.items():
            try:
                import yfinance as yf
                kis_data = self.kis.get_kr_price(ticker)
                if not kis_data:
                    continue

                price  = kis_data['price']
                change = kis_data['change_pct']
                volume = kis_data.get('volume', 0)

                hist    = yf.Ticker(f"{ticker}.KS").history(period="10d").dropna()
                if len(hist) < 5:
                    continue

                avg_vol   = hist['Volume'].mean()
                vol_ratio = round(volume / avg_vol, 1) if avg_vol > 0 else 1

                score   = 0
                signals = []

                # 핵심: 거래량 급증 + 주가 소폭 상승 = 매집 신호
                if vol_ratio >= 2 and 0 <= change <= 3:
                    score += 5
                    signals.append(f"🔍 매집 신호: 거래량 {vol_ratio}배↑ 주가 소폭({change:+.1f}%)")

                # 오늘 강세 섹터 2등주/소부장
                if info['tier'] in ['2등주', '소부장'] and change >= 0:
                    score += 3
                    signals.append(f"📈 강세 섹터 {info['tier']} 파급 효과 기대")

                # 대장주 오른 후 아직 안 따라온 경우
                if info['tier'] == '2등주' and 0 <= change <= 2:
                    score += 2
                    signals.append("⏳ 대장주 상승 후 아직 미반응")

                # 거래량 급증
                if vol_ratio >= 1.5:
                    score += 1
                    signals.append(f"📦 거래량 {vol_ratio}배")

                if score >= 3:  # 강세장 기준 완화
                    candidates.append({
                        "name":      info["name"],
                        "ticker":    ticker,
                        "sector":    info["sector"],
                        "tier":      info["tier"],
                        "price":     price,
                        "change":    change,
                        "vol_ratio": vol_ratio,
                        "score":     score,
                        "signals":   signals,
                    })

            except:
                pass
            time.sleep(0.15)

        # 장세별 임계값 유동화
        score_threshold = {"강세": 3, "중립": 4, "약세": 5}.get(regime_type, 4)

        candidates.sort(key=lambda x: x['score'], reverse=True)
        top10 = candidates[:10]

        if not top10:
            return None

        # AI 최종 판단
        result = await self._ai_analyze(
            top10, regime_type, "14:30선점",
            "내일 NXT/장후 진입용 선점 추천 (오늘 매집 신호 + 파급 효과 종목)",
            macro_context
        )

        # backtest 기록
        if result:
            self._record_backtest(result, "14:30선점", regime_type)

        return result

    # ── AI 최종 판단 ───────────────────────────────

    async def _ai_analyze(self, candidates, regime_type, source, description, macro_context=None):
        """AI 최종 종목 판단"""
        from anthropic import Anthropic
        import re

        client = Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))

        cand_text = ""
        for c in candidates:
            sig_text  = " | ".join(c.get('signals', [])[:3])
            cand_text += (
                f"{c['name']}({c['ticker']}) {c['sector']}/{c.get('tier','')} "
                f"현재가:{c['price']:,} 등락:{c.get('change',0):+.1f}% "
                f"거래량:{c.get('vol_ratio',1)}배 점수:{c['score']} "
                f"신호:{sig_text}\n"
            )

        macro_text = ""
        if macro_context:
            ai_result = macro_context.get("ai_result", {})
            macro_text = f"""
시장전망: {ai_result.get('market_outlook', '')}
장세신뢰도: {ai_result.get('regime_confidence', '')}
과열섹터: {', '.join(ai_result.get('overheated_sectors', []))}
"""

        prompt = f"""한국 주식 전문 트레이더로서 종목을 추천해주세요.

=== 추천 목적 ===
{description}

=== 장세 ===
{regime_type}장

=== 시장 컨텍스트 ===
{macro_text}

=== 후보 종목 (수급 스코어링 결과) ===
{cand_text}

분석 기준:
1. 수급 점수 높은 종목 우선
2. 이미 많이 오른 종목은 추격주의 표시
3. {regime_type}장 전략에 맞게 선택
4. 직장인이라 정규장 09:00 진입 불가

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
      "reason": "추천 이유 한줄",
      "current_price": 000000,
      "buy_price": 000000,
      "buy_timing": "NXT 08:00 / 14:30 장마감전 / 퇴근후 NXT",
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
            text = res.content[0].text.strip()
            text = re.sub(r'```json|```', '', text).strip()
            m    = re.search(r'\{.*\}', text, re.DOTALL)
            if m:
                result         = json.loads(m.group())
                result['source'] = source
                return result
        except Exception as e:
            print(f"  ❌ AI 판단 실패: {e}")
        return None

    # ── backtest 기록 ──────────────────────────────

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
                bt.record(
                    ticker       = r['ticker'],
                    name         = r['name'],
                    entry_price  = r.get('buy_price', r.get('current_price', 0)),
                    target_price = r.get('target1', 0),
                    stop_loss    = r.get('stop_loss', 0),
                    market       = "KR",
                    hold_type    = "단기",
                    source       = source,
                    regime       = regime_type,
                    grade        = grade
                )
            print(f"  📝 backtest 기록 완료 ({len(result.get('recommendations', []))}개)")
        except Exception as e:
            print(f"  ⚠️ backtest 기록 실패: {e}")

    # ── 메시지 생성 ────────────────────────────────

    def build_message(self, result, time_slot="07:30"):
        """추천 메시지 생성"""
        if not result:
            return "❌ 추천 분석 실패"

        slot_info = {
            "07:30단기": ("🌅", "장전 단기 추천", "NXT 08:00 진입"),
            "14:30선점": ("🕑", "내일 선점 추천", "NXT/장후 진입"),
            "20:30":     ("🌙", "미국장 추천",    "오늘 밤 진입"),
        }
        emoji, title, timing = slot_info.get(
            result.get('source', time_slot),
            ("📊", "추천", "")
        )

        msg  = f"{emoji} <b>{title}</b> {datetime.now().strftime('%m/%d %H:%M')}\n"
        msg += f"<i>{timing}</i>\n\n"
        msg += f"📊 {result.get('market_summary', '')}\n"
        msg += f"⚔️ {result.get('strategy', '')}\n\n"
        msg += "━━━━━━━━━━━━━━━━━━━\n"

        for r in result.get('recommendations', [])[:5]:
            strategy_emoji = {
                "선점형":  "🎯",
                "모멘텀형": "🚀",
                "눌림목형": "📉",
                "매집형":  "🔍",
            }.get(r.get('strategy_type', ''), "📊")

            caution      = r.get('caution', '없음')
            caution_text = f"\n   ⚠️ {caution}" if caution and caution != "없음" else ""

            def fmt(val):
                try:
                    return f"{int(val):,}원"
                except:
                    return "?"

            msg += f"{strategy_emoji} <b>{r['name']}</b> ({r['ticker']})\n"
            msg += f"   {r['sector']} / {r.get('tier','')}\n"
            msg += f"   {r.get('reason', '')}{caution_text}\n\n"
            msg += f"   💰 현재가: {fmt(r.get('current_price', 0))}\n"
            msg += f"   🟢 매수가: {fmt(r.get('buy_price', 0))}\n"
            msg += f"   ⏱ 진입:   {r.get('buy_timing', '')}\n"
            msg += f"   🎯 목표1: {fmt(r.get('target1', 0))}\n"
            msg += f"   🎯 목표2: {fmt(r.get('target2', 0))}\n"
            msg += f"   🛑 손절:  {fmt(r.get('stop_loss', 0))}\n"
            msg += f"   ⚖️ 리스크: {r.get('risk_reward', '')}\n"
            msg += "━━━━━━━━━━━━━━━━━━━\n"

        msg += f"\n⚠️ 최종 판단은 본인이 하세요.\n"
        msg += f"📝 모의 backtest 자동 기록됨\n"
        msg += f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        return msg
