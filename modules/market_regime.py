import sys
import os
import json
import time
import requests
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta

sys.path.insert(0, '/media/dps/T7/stock_ai')


class MarketRegime:
    """
    동적 시장 전략 엔진 v2.0
    - 사이클 7단계 판단
    - 역사적 신고가 영역 감지
    - VIX 이상 신호 감지
    - 미국→한국 선행 효과
    - 조정 확률 계산
    - AI 종합 판단 + 전략 자동 생성
    """

    def __init__(self):
        self.regime_file         = "/media/dps/T7/stock_ai/data/market_regime.json"
        self.regime_history_file = "/media/dps/T7/stock_ai/data/regime_history.json"
        self.strategy_file       = "/media/dps/T7/stock_ai/data/dynamic_strategy.json"
        self.current_regime      = self._load_regime()

    # ── 파일 I/O ──────────────────────────────────

    def _load_regime(self):
        if os.path.exists(self.regime_file):
            with open(self.regime_file, "r") as f:
                return json.load(f)
        return {
            "regime": "중립", "kr_regime": "중립", "us_regime": "중립",
            "cycle_stage": "상승중", "score": 0,
            "kr_score": 0, "us_score": 0,
            "consecutive_days": 0, "strategy": "중립_전략",
            "correction_prob": 30, "confidence": 50,
            "kr_score_threshold": 3, "kr_lt_threshold": 4,
            "us_score_threshold": 3, "position_size": 100,
            "updated": datetime.now().isoformat()
        }

    def _save_regime(self):
        os.makedirs("/media/dps/T7/stock_ai/data", exist_ok=True)
        with open(self.regime_file, "w") as f:
            json.dump(self.current_regime, f, ensure_ascii=False, indent=2)

    def _save_history(self, regime_data):
        history = []
        if os.path.exists(self.regime_history_file):
            with open(self.regime_history_file, "r") as f:
                history = json.load(f)
        history.append({
            "date":            datetime.now().strftime("%Y-%m-%d"),
            "cycle_stage":     regime_data.get("cycle_stage"),
            "kr_regime":       regime_data.get("kr_regime"),
            "us_regime":       regime_data.get("us_regime"),
            "correction_prob": regime_data.get("correction_prob"),
            "ai_strategy":     regime_data.get("ai_strategy", ""),
            "kospi":           regime_data.get("kospi_current", 0),
            "nasdaq":          regime_data.get("nas_current", 0),
        })
        history = history[-90:]
        with open(self.regime_history_file, "w") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)

    def _save_strategy(self, strategy):
        os.makedirs("/media/dps/T7/stock_ai/data", exist_ok=True)
        with open(self.strategy_file, "w") as f:
            json.dump(strategy, f, ensure_ascii=False, indent=2)

    def load_strategy(self):
        if os.path.exists(self.strategy_file):
            with open(self.strategy_file, "r") as f:
                return json.load(f)
        return {}

    # ── 데이터 수집 ────────────────────────────────

    def _get_fear_greed(self):
        try:
            res  = requests.get("https://api.alternative.me/fng/", timeout=5)
            data = res.json()['data'][0]
            return int(data['value']), data['value_classification']
        except:
            return 50, "Neutral"

    def _get_dollar_index(self):
        try:
            dxy = yf.Ticker("DX-Y.NYB").history(period="5d").dropna()
            if len(dxy) >= 2:
                change = (dxy['Close'].iloc[-1] - dxy['Close'].iloc[-2]) / dxy['Close'].iloc[-2] * 100
                return round(dxy['Close'].iloc[-1], 2), round(change, 2)
        except:
            pass
        return 0, 0

    def _get_oil_gold(self):
        result = {}
        for name, ticker in [('oil', 'CL=F'), ('gold', 'GC=F')]:
            try:
                df = yf.Ticker(ticker).history(period="5d").dropna()
                if len(df) >= 2:
                    result[name] = round((df['Close'].iloc[-1] - df['Close'].iloc[-2]) / df['Close'].iloc[-2] * 100, 2)
                time.sleep(0.1)
            except:
                result[name] = 0
        return result

    def _get_sector_etfs(self):
        etfs = {
            "반도체": "SMH", "빅테크": "QQQ", "AI": "BOTZ",
            "에너지": "XLE", "금융": "XLF", "유틸리티": "XLU",
            "헬스": "XLV", "소비재": "XLY"
        }
        result = {}
        for name, ticker in etfs.items():
            try:
                df = yf.Ticker(ticker).history(period="5d").dropna()
                if len(df) >= 2:
                    d1 = round((df['Close'].iloc[-1] - df['Close'].iloc[-2]) / df['Close'].iloc[-2] * 100, 2)
                    w1 = round((df['Close'].iloc[-1] - df['Close'].iloc[0]) / df['Close'].iloc[0] * 100, 2)
                    result[name] = {"day": d1, "week": w1, "ticker": ticker}
                time.sleep(0.1)
            except:
                pass
        return result

    def _get_vix_signal(self):
        """VIX 이상 신호: VIX↑ + 주가↑ 동시 = 내부 불안"""
        try:
            vix = yf.Ticker("^VIX").history(period="5d").dropna()
            sp  = yf.Ticker("^GSPC").history(period="5d").dropna()
            if len(vix) >= 2 and len(sp) >= 2:
                vix_change = vix['Close'].iloc[-1] - vix['Close'].iloc[-2]
                sp_change  = sp['Close'].iloc[-1] - sp['Close'].iloc[-2]
                vix_val    = round(vix['Close'].iloc[-1], 1)
                if vix_change > 0 and sp_change > 0:
                    signal = "이상신호"
                elif vix_change < 0 and sp_change > 0:
                    signal = "건강"
                elif vix_change > 0 and sp_change < 0:
                    signal = "공포"
                else:
                    signal = "중립"
                return vix_val, signal, round(vix_change, 2)
        except:
            pass
        return 20, "중립", 0

    # ── 한국 장세 분석 ─────────────────────────────

    def _analyze_kr(self, sector_etfs=None):
        try:
            score   = 0
            details = []
            signals = {}

            kospi = yf.Ticker("^KS11").history(period="6mo").dropna()
            if len(kospi) < 20:
                return 0, [], {}, {}

            close    = kospi['Close']
            volume   = kospi['Volume']
            current  = close.iloc[-1]
            high_all = close.max()
            ma5      = close.rolling(5).mean().iloc[-1]
            ma20     = close.rolling(20).mean().iloc[-1]
            ma60     = close.rolling(60).mean().iloc[-1] if len(close) >= 60 else ma20
            drawdown = (current - high_all) / high_all * 100

            # 1. 역사적 신고가 영역
            ath_prox = current / high_all * 100
            if ath_prox >= 99:
                signals['ath'] = True
                score += 3
                details.append(f"🏔 역사적 신고가 영역 ({current:,.0f})")
            elif ath_prox >= 97:
                signals['near_ath'] = True
                score += 1
                details.append(f"🏔 신고가 근접 ({ath_prox:.1f}%)")

            # 2. 이동평균 정배열
            if current > ma5 > ma20:
                score += 2
                details.append("✅ 단기 정배열")
            if ma5 > ma20 > ma60:
                score += 2
                details.append("✅ 장기 정배열")

            # 3. 수익률
            r5  = (close.iloc[-1] - close.iloc[-5])  / close.iloc[-5]  * 100
            r20 = (close.iloc[-1] - close.iloc[-20]) / close.iloc[-20] * 100
            r60 = (close.iloc[-1] - close.iloc[-60]) / close.iloc[-60] * 100 if len(close) >= 60 else 0

            if r5 >= 3:
                score += 2; details.append(f"✅ 5일 {r5:+.1f}%")
            elif r5 >= 1:
                score += 1; details.append(f"✅ 5일 {r5:+.1f}%")
            elif r5 <= -3:
                score -= 2; details.append(f"❌ 5일 {r5:+.1f}%")

            if r20 >= 5:
                score += 2; details.append(f"✅ 20일 {r20:+.1f}%")
            elif r20 <= -5:
                score -= 2; details.append(f"❌ 20일 {r20:+.1f}%")

            # 4. 거래량 Divergence
            avg_vol20  = volume.rolling(20).mean().iloc[-1]
            recent_vol = volume.iloc[-3:].mean()
            vol_ratio  = recent_vol / avg_vol20 if avg_vol20 > 0 else 1

            if r5 > 0 and vol_ratio < 0.8:
                signals['vol_divergence'] = True
                score -= 2
                details.append(f"⚠️ 거래량 Divergence (주가↑ 거래량↓)")
            elif vol_ratio >= 1.3:
                score += 1; details.append(f"✅ 거래량 증가 ({vol_ratio:.1f}배)")

            # 5. 코스닥 동반
            try:
                kq = yf.Ticker("^KQ11").history(period="5d").dropna()
                if len(kq) >= 2:
                    kq_chg = (kq['Close'].iloc[-1] - kq['Close'].iloc[-2]) / kq['Close'].iloc[-2] * 100
                    if kq_chg > 0:
                        score += 1; details.append(f"✅ 코스닥 동반 ({kq_chg:+.1f}%)")
                    else:
                        details.append(f"⚠️ 코스닥 약세 ({kq_chg:+.1f}%)")
                    signals['kosdaq_change']  = round(kq_chg, 2)
                    signals['kosdaq_current'] = round(kq['Close'].iloc[-1], 2)
            except:
                pass

            # 6. 미국 반도체 선행 지표
            if sector_etfs:
                smh = sector_etfs.get("반도체", {})
                if smh.get("day", 0) >= 3:
                    score += 2; details.append(f"✅ 미국 SMH {smh['day']:+.1f}% → 한국 반도체 선행")
                elif smh.get("day", 0) <= -3:
                    score -= 1; details.append(f"⚠️ 미국 SMH {smh['day']:+.1f}%")

            data = {
                "current": round(current, 2), "ma5": round(ma5, 2), "ma20": round(ma20, 2),
                "drawdown": round(drawdown, 1), "ath_proximity": round(ath_prox, 1),
                "r5": round(r5, 2), "r20": round(r20, 2), "r60": round(r60, 2),
                "vol_ratio": round(vol_ratio, 2),
                "kosdaq_current": signals.get('kosdaq_current', 0),
                "kosdaq_change":  signals.get('kosdaq_change', 0),
            }
            return score, details, data, signals

        except Exception as e:
            print(f"❌ 한국 장세 분석 실패: {e}")
            return 0, [], {}, {}

    # ── 미국 장세 분석 ─────────────────────────────

    def _analyze_us(self, vix_val, vix_signal, fg_score, dxy_change, oil_gold):
        try:
            score   = 0
            details = []
            signals = {}

            nas = yf.Ticker("^IXIC").history(period="6mo").dropna()
            sp  = yf.Ticker("^GSPC").history(period="6mo").dropna()
            if len(nas) < 20:
                return 0, [], {}, {}

            n_close   = nas['Close']
            n_current = n_close.iloc[-1]
            n_high    = n_close.max()
            n_ma5     = n_close.rolling(5).mean().iloc[-1]
            n_ma20    = n_close.rolling(20).mean().iloc[-1]
            n_ma60    = n_close.rolling(60).mean().iloc[-1] if len(n_close) >= 60 else n_ma20
            n_ath     = n_current / n_high * 100
            n_r5      = (n_close.iloc[-1] - n_close.iloc[-5])  / n_close.iloc[-5]  * 100
            n_r20     = (n_close.iloc[-1] - n_close.iloc[-20]) / n_close.iloc[-20] * 100
            n_r60     = (n_close.iloc[-1] - n_close.iloc[-60]) / n_close.iloc[-60] * 100 if len(n_close) >= 60 else 0
            n_day     = (n_close.iloc[-1] - n_close.iloc[-2])  / n_close.iloc[-2]  * 100

            s_close   = sp['Close']
            s_current = s_close.iloc[-1]
            s_high    = s_close.max()
            s_ath     = s_current / s_high * 100
            s_r5      = (s_close.iloc[-1] - s_close.iloc[-5]) / s_close.iloc[-5] * 100
            s_day     = (s_close.iloc[-1] - s_close.iloc[-2]) / s_close.iloc[-2] * 100

            # 1. 신고가 영역
            if n_ath >= 99 and s_ath >= 99:
                signals['ath'] = True; score += 3
                details.append("🏔 나스닥+S&P 동시 신고가")
            elif n_ath >= 97:
                score += 1; details.append(f"🏔 나스닥 신고가 근접 ({n_ath:.1f}%)")

            # 2. 이동평균
            if n_current > n_ma5 > n_ma20:
                score += 2; details.append("✅ 나스닥 단기 정배열")
            if n_ma5 > n_ma20 > n_ma60:
                score += 2; details.append("✅ 나스닥 장기 정배열")

            # 3. 수익률
            if n_r5 >= 3:
                score += 2; details.append(f"✅ 나스닥 5일 {n_r5:+.1f}%")
            elif n_r5 <= -3:
                score -= 2; details.append(f"❌ 나스닥 5일 {n_r5:+.1f}%")
            if n_r20 >= 5:
                score += 2; details.append(f"✅ 나스닥 20일 {n_r20:+.1f}%")
            elif n_r20 <= -5:
                score -= 2; details.append(f"❌ 나스닥 20일 {n_r20:+.1f}%")

            # 4. VIX 이상 신호
            if vix_signal == "이상신호":
                signals['vix_anomaly'] = True; score -= 2
                details.append(f"⚠️ VIX 이상신호! VIX↑({vix_val}) + 주가↑ (내부 불안)")
            elif vix_signal == "건강":
                score += 2; details.append(f"✅ VIX {vix_val} 하락 (건강한 상승)")
            elif vix_signal == "공포":
                score -= 3; details.append(f"❌ VIX 공포 ({vix_val})")

            if vix_val > 30:
                score -= 2; details.append(f"❌ VIX {vix_val} 과공포")
            elif vix_val < 15:
                score += 1; details.append(f"✅ VIX {vix_val} 극안정")
            elif vix_val < 20:
                score += 1; details.append(f"✅ VIX {vix_val} 안정")

            # 5. 공포탐욕
            if fg_score >= 75:
                signals['extreme_greed'] = True; score -= 2
                details.append(f"⚠️ 공포탐욕 {fg_score} 극탐욕 (과열)")
            elif fg_score >= 60:
                score += 1; details.append(f"✅ 공포탐욕 {fg_score} 탐욕")
            elif fg_score <= 25:
                score += 2; details.append(f"✅ 공포탐욕 {fg_score} 극공포 (기회)")
            elif fg_score <= 40:
                score += 1; details.append(f"✅ 공포탐욕 {fg_score} 공포")

            # 6. 달러
            if dxy_change <= -0.3:
                score += 1; details.append(f"✅ 달러 약세 {dxy_change:+.2f}%")
            elif dxy_change >= 0.5:
                score -= 1; details.append(f"⚠️ 달러 강세 {dxy_change:+.2f}%")

            # 7. 금/원유
            gold_chg = oil_gold.get('gold', 0)
            oil_chg  = oil_gold.get('oil', 0)
            if gold_chg >= 1:
                signals['gold_up'] = True; score -= 1
                details.append(f"⚠️ 금 강세 {gold_chg:+.1f}% (안전자산 수요)")
            if oil_chg >= 3:
                signals['oil_spike'] = True; score -= 1
                details.append(f"⚠️ 원유 급등 {oil_chg:+.1f}% (지정학)")

            # 8. 나스닥/S&P 동반
            if n_day > 0 and s_day > 0:
                score += 1; details.append("✅ 나스닥/S&P 동반 상승")
            elif n_day < 0 and s_day < 0:
                score -= 1; details.append("⚠️ 나스닥/S&P 동반 하락")

            data = {
                "current": round(n_current, 2), "ma5": round(n_ma5, 2), "ma20": round(n_ma20, 2),
                "ath_proximity": round(n_ath, 1),
                "r5": round(n_r5, 2), "r20": round(n_r20, 2), "r60": round(n_r60, 2),
                "day_change": round(n_day, 2),
                "sp_current": round(s_current, 2), "sp_day": round(s_day, 2), "sp_r5": round(s_r5, 2),
                "vix": vix_val, "fg_score": fg_score,
            }
            return score, details, data, signals

        except Exception as e:
            print(f"❌ 미국 장세 분석 실패: {e}")
            return 0, [], {}, {}

    # ── 조정 확률 계산 ─────────────────────────────

    def _calc_correction_prob(self, kr_data, us_data, kr_signals, us_signals,
                               vix_val, vix_signal, fg_score):
        prob = 20
        if vix_signal == "이상신호":   prob += 15
        elif vix_signal == "공포":     prob += 10
        if fg_score >= 80:             prob += 20
        elif fg_score >= 70:           prob += 10
        if kr_signals.get('ath') and us_signals.get('ath'): prob += 10
        elif kr_signals.get('ath') or us_signals.get('ath'): prob += 5
        if kr_signals.get('vol_divergence'): prob += 10
        if us_signals.get('extreme_greed'): prob += 10
        if us_signals.get('oil_spike'):     prob += 5
        if us_signals.get('gold_up'):       prob += 5
        if kr_data.get('r20', 0) >= 10 or us_data.get('r20', 0) >= 10: prob += 10
        return min(prob, 95)

    # ── 사이클 단계 ────────────────────────────────

    def _determine_cycle_stage(self, kr_data, us_data, kr_signals, us_signals,
                                correction_prob, total_score):
        if correction_prob >= 70:   return "과열"
        elif correction_prob >= 50: return "과열경계"
        elif kr_signals.get('ath') and us_signals.get('ath'): return "과열경계"
        elif total_score >= 10 and kr_data.get('r20', 0) >= 5: return "가속"
        elif total_score >= 6:  return "상승중"
        elif total_score >= 2:  return "초입"
        elif total_score >= -2: return "조정초입"
        else:                   return "조정중"

    # ── AI 종합 판단 ───────────────────────────────

    async def _ai_strategy(self, kr_data, us_data, kr_details, us_details,
                            kr_signals, us_signals, sector_etfs,
                            correction_prob, cycle_stage, history):
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))

            etf_text = ""
            for name, data in sector_etfs.items():
                etf_text += f"{name}: 당일{data['day']:+.1f}% 주간{data['week']:+.1f}%\n"

            history_text = ""
            for h in history[-5:]:
                history_text += f"{h['date']}: {h.get('cycle_stage','')} 조정확률{h.get('correction_prob','')}% {h.get('ai_strategy','')[:40]}\n"

            anomalies = []
            if kr_signals.get('vol_divergence'): anomalies.append("한국 거래량 Divergence")
            if us_signals.get('vix_anomaly'):    anomalies.append("미국 VIX 이상신호")
            if us_signals.get('extreme_greed'): anomalies.append(f"극탐욕({us_data.get('fg_score')})")
            if us_signals.get('oil_spike'):      anomalies.append("원유 급등")
            if us_signals.get('gold_up'):        anomalies.append("금 강세")

            prompt = f"""최고 수준의 퀀트 트레이더로서 시장 전략을 만들어주세요.
마크다운 금지. JSON으로만 답변.

=== 한국 ===
코스피: {kr_data.get('current'):,.0f} | 코스닥: {kr_data.get('kosdaq_current',0):,.0f}
5일: {kr_data.get('r5'):+.1f}% | 20일: {kr_data.get('r20'):+.1f}% | 60일: {kr_data.get('r60'):+.1f}%
신고가 근접도: {kr_data.get('ath_proximity'):.1f}%
거래량: {kr_data.get('vol_ratio'):.1f}배
근거: {' | '.join(kr_details[:5])}

=== 미국 ===
나스닥: {us_data.get('current'):,.0f} ({us_data.get('day_change'):+.2f}%)
S&P500: {us_data.get('sp_current'):,.0f} ({us_data.get('sp_day'):+.2f}%)
5일: {us_data.get('r5'):+.1f}% | 20일: {us_data.get('r20'):+.1f}%
신고가 근접도: {us_data.get('ath_proximity'):.1f}%
VIX: {us_data.get('vix')} | 공포탐욕: {us_data.get('fg_score')}
근거: {' | '.join(us_details[:5])}

=== 섹터 ETF ===
{etf_text}

=== 이상 신호 ===
{chr(10).join(anomalies) if anomalies else '없음'}

=== 현재 사이클 ===
{cycle_stage} | 조정확률: {correction_prob}%

=== 최근 5일 판단 ===
{history_text if history_text else '없음'}

JSON:
{{
  "cycle_analysis": "현재 사이클 정확한 분석 (2줄)",
  "kr_strategy": "한국장 전략 (공격/유지/분할매도준비/관망/적극매수 + 이유)",
  "us_strategy": "미국장 전략 + 이유",
  "correction_timing": "조정 타이밍 예측 (구체적으로)",
  "key_risk": "오늘 핵심 리스크",
  "opportunity": "오늘 최고 기회",
  "kr_score_threshold": 3,
  "kr_lt_threshold": 4,
  "us_score_threshold": 3,
  "position_size": 100,
  "tomorrow_outlook": "내일 장 전망 한줄",
  "watch_sectors": ["주목 섹터1", "섹터2"],
  "avoid_sectors": ["회피 섹터"]
}}

score_threshold: 단기 추천 최소 점수 (강세장 2, 보통 3, 조정임박 5)
position_size: 100=정상, 70=축소, 130=확대"""

            res  = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=800,
                messages=[{"role": "user", "content": prompt}]
            )
            import re
            text = re.sub(r'```json|```', '', res.content[0].text.strip()).strip()
            m    = re.search(r'\{.*\}', text, re.DOTALL)
            if m:
                return json.loads(m.group())
        except Exception as e:
            print(f"  ⚠️ AI 전략 실패: {e}")

        # 기본값
        defaults = {
            "과열":     {"kr_score_threshold": 5, "kr_lt_threshold": 6, "position_size": 70},
            "과열경계": {"kr_score_threshold": 4, "kr_lt_threshold": 5, "position_size": 80},
            "가속":     {"kr_score_threshold": 2, "kr_lt_threshold": 3, "position_size": 110},
            "상승중":   {"kr_score_threshold": 3, "kr_lt_threshold": 4, "position_size": 100},
            "초입":     {"kr_score_threshold": 2, "kr_lt_threshold": 3, "position_size": 90},
            "조정초입": {"kr_score_threshold": 5, "kr_lt_threshold": 5, "position_size": 70},
            "조정중":   {"kr_score_threshold": 6, "kr_lt_threshold": 6, "position_size": 50},
        }
        d = defaults.get(cycle_stage, defaults["상승중"])
        return {
            "kr_strategy": "AI 판단 불가 — 규칙 기반",
            "us_strategy": "AI 판단 불가", "cycle_analysis": "",
            "correction_timing": "미확인", "key_risk": "데이터 부족",
            "opportunity": "미확인", "tomorrow_outlook": "미확인",
            "watch_sectors": [], "avoid_sectors": [],
            "us_score_threshold": d["kr_score_threshold"], **d
        }

    # ── 종합 분석 (async) ──────────────────────────

    async def analyze_regime(self):
        try:
            print(f"[{datetime.now().strftime('%H:%M')}] 📊 동적 전략 엔진 v2.0")
            prev_regime = self.current_regime.get("regime", "중립")

            print("  📡 글로벌 데이터 수집...")
            vix_val, vix_signal, vix_change = self._get_vix_signal()
            fg_score, fg_class              = self._get_fear_greed()
            dxy_val, dxy_change             = self._get_dollar_index()
            oil_gold                        = self._get_oil_gold()
            sector_etfs                     = self._get_sector_etfs()

            print("  🇰🇷 한국 분석...")
            kr_score, kr_details, kr_data, kr_signals = self._analyze_kr(sector_etfs)

            print("  🇺🇸 미국 분석...")
            us_score, us_details, us_data, us_signals = self._analyze_us(
                vix_val, vix_signal, fg_score, dxy_change, oil_gold
            )

            correction_prob = self._calc_correction_prob(
                kr_data, us_data, kr_signals, us_signals, vix_val, vix_signal, fg_score
            )
            total_score  = round(kr_score * 0.6 + us_score * 0.4)
            cycle_stage  = self._determine_cycle_stage(
                kr_data, us_data, kr_signals, us_signals, correction_prob, total_score
            )
            kr_regime    = self._score_to_regime(kr_score)
            us_regime    = self._score_to_regime(us_score)
            total_regime = self._score_to_regime(total_score)

            consecutive = self.current_regime.get("consecutive_days", 0)
            consecutive = consecutive + 1 if total_regime == prev_regime else 1

            print("  🤖 AI 전략 생성...")
            history = []
            if os.path.exists(self.regime_history_file):
                with open(self.regime_history_file, "r") as f:
                    history = json.load(f)

            ai = await self._ai_strategy(
                kr_data, us_data, kr_details, us_details,
                kr_signals, us_signals, sector_etfs,
                correction_prob, cycle_stage, history
            )

            result = {
                "regime": total_regime, "score": total_score,
                "consecutive_days": consecutive,
                "prev_regime": prev_regime,
                "regime_changed": total_regime != prev_regime,
                "cycle_stage": cycle_stage,
                "correction_prob": correction_prob,
                "confidence": min(100, abs(total_score) * 10 + 30),
                "kr_regime": kr_regime, "kr_score": kr_score,
                "kr_details": kr_details, "kr_signals": kr_signals,
                "kospi_current": kr_data.get("current", 0),
                "kospi_ma20": kr_data.get("ma20", 0),
                "kospi_drawdown": kr_data.get("drawdown", 0),
                "kr_r5": kr_data.get("r5", 0), "kr_r20": kr_data.get("r20", 0),
                "kr_r60": kr_data.get("r60", 0),
                "kr_ath_proximity": kr_data.get("ath_proximity", 0),
                "kr_vol_ratio": kr_data.get("vol_ratio", 1),
                "kosdaq_current": kr_data.get("kosdaq_current", 0),
                "kosdaq_change": kr_data.get("kosdaq_change", 0),
                "us_regime": us_regime, "us_score": us_score,
                "us_details": us_details, "us_signals": us_signals,
                "nas_current": us_data.get("current", 0),
                "nas_ma20": us_data.get("ma20", 0),
                "nas_day_change": us_data.get("day_change", 0),
                "nas_r5": us_data.get("r5", 0), "nas_r20": us_data.get("r20", 0),
                "nas_r60": us_data.get("r60", 0),
                "nas_ath_proximity": us_data.get("ath_proximity", 0),
                "sp_current": us_data.get("sp_current", 0),
                "sp_change": us_data.get("sp_day", 0),
                "vix": vix_val, "vix_signal": vix_signal,
                "fg_score": fg_score, "fg_class": fg_class,
                "dxy_change": dxy_change,
                "oil_change": oil_gold.get("oil", 0),
                "gold_change": oil_gold.get("gold", 0),
                "sector_etfs": sector_etfs,
                "ai_strategy": ai.get("kr_strategy", ""),
                "ai_us_strategy": ai.get("us_strategy", ""),
                "cycle_analysis": ai.get("cycle_analysis", ""),
                "correction_timing": ai.get("correction_timing", ""),
                "key_risk": ai.get("key_risk", ""),
                "opportunity": ai.get("opportunity", ""),
                "tomorrow_outlook": ai.get("tomorrow_outlook", ""),
                "watch_sectors": ai.get("watch_sectors", []),
                "avoid_sectors": ai.get("avoid_sectors", []),
                "kr_score_threshold": ai.get("kr_score_threshold", 3),
                "kr_lt_threshold": ai.get("kr_lt_threshold", 4),
                "us_score_threshold": ai.get("us_score_threshold", 3),
                "position_size": ai.get("position_size", 100),
                "updated": datetime.now().isoformat()
            }

            self.current_regime = result
            self._save_regime()
            self._save_history(result)
            self._save_strategy({
                "kr_score_threshold": result["kr_score_threshold"],
                "kr_lt_threshold":    result["kr_lt_threshold"],
                "us_score_threshold": result["us_score_threshold"],
                "position_size":      result["position_size"],
                "cycle_stage":        result["cycle_stage"],
                "correction_prob":    result["correction_prob"],
                "watch_sectors":      result["watch_sectors"],
                "avoid_sectors":      result["avoid_sectors"],
                "updated":            result["updated"],
            })

            print(f"  ✅ {cycle_stage} | 조정확률:{correction_prob}% | 임계값:{result['kr_score_threshold']}")
            return result

        except Exception as e:
            print(f"❌ 장세 분석 실패: {e}")
            return self.current_regime

    # ── 하위 호환 (동기 버전) ──────────────────────

    def analyze_regime_sync(self):
        """기존 동기 코드 호환용 - 저장된 값 즉시 반환"""
        return self.current_regime

    # ── 전략 파라미터 ──────────────────────────────

    def get_strategy_params(self):
        cycle = self.current_regime.get("cycle_stage", "상승중")
        prob  = self.current_regime.get("correction_prob", 30)
        params_map = {
            "초입":     {"rsi_buy_min": 45, "rsi_buy_max": 70,
                         "use_breakout": True,  "stop_loss_atr": 1.5,
                         "description": "초입 — 대장주 선취매"},
            "상승중":   {"rsi_buy_min": 50, "rsi_buy_max": 72,
                         "use_breakout": True,  "stop_loss_atr": 1.5,
                         "description": "상승중 — 추세 추종 + 눌림목"},
            "가속":     {"rsi_buy_min": 55, "rsi_buy_max": 75,
                         "use_breakout": True,  "stop_loss_atr": 1.3,
                         "description": "가속 — 모멘텀 + 신고가 돌파"},
            "과열경계": {"rsi_buy_min": 40, "rsi_buy_max": 65,
                         "use_breakout": False, "stop_loss_atr": 1.2,
                         "description": "과열경계 — 비중 축소, 분할 매도 준비"},
            "과열":     {"rsi_buy_min": 30, "rsi_buy_max": 50,
                         "use_breakout": False, "stop_loss_atr": 1.0,
                         "description": "과열 — 관망, 수익 실현"},
            "조정초입": {"rsi_buy_min": 30, "rsi_buy_max": 50,
                         "use_breakout": False, "stop_loss_atr": 1.0,
                         "description": "조정초입 — 손절 타이트, 현금 확보"},
            "조정중":   {"rsi_buy_min": 20, "rsi_buy_max": 35,
                         "use_breakout": False, "stop_loss_atr": 0.8,
                         "description": "조정중 — 현금 최대화"},
        }
        base = params_map.get(cycle, params_map["상승중"])
        if prob >= 60:
            base['description'] += f" ⚠️ 조정확률{prob}%"
        return base

    def _score_to_regime(self, score):
        if score >= 7:    return "강세"
        elif score >= 3:  return "중립"
        elif score >= -1: return "약세초입"
        else:             return "약세"

    def get_regime_emoji(self):
        stage = self.current_regime.get("cycle_stage", "상승중")
        return {
            "초입": "🌱", "상승중": "📈", "가속": "🚀",
            "과열경계": "⚠️", "과열": "🔥",
            "조정초입": "📉", "조정중": "🔴"
        }.get(stage, "➡️")

    def get_kr_regime_emoji(self):
        return {"강세": "🚀", "중립": "➡️", "약세초입": "⚠️", "약세": "🔴"}.get(
            self.current_regime.get("kr_regime", "중립"), "➡️")

    def get_us_regime_emoji(self):
        return {"강세": "🚀", "중립": "➡️", "약세초입": "⚠️", "약세": "🔴"}.get(
            self.current_regime.get("us_regime", "중립"), "➡️")

    def get_status_text(self):
        r    = self.current_regime
        p    = self.get_strategy_params()
        em   = self.get_regime_emoji()
        prob = r.get("correction_prob", 30)
        prob_bar = "🟩" * (prob // 20) + "⬜" * (5 - prob // 20)

        anomalies = []
        if r.get("us_signals", {}).get("vix_anomaly"):    anomalies.append("⚠️ VIX 이상신호")
        if r.get("kr_signals", {}).get("vol_divergence"): anomalies.append("⚠️ 거래량 Divergence")
        if r.get("us_signals", {}).get("extreme_greed"):  anomalies.append("⚠️ 극탐욕")
        if r.get("us_signals", {}).get("oil_spike"):      anomalies.append("⚠️ 원유 급등")

        etf_text = ""
        for name, data in r.get("sector_etfs", {}).items():
            arrow = "▲" if data['day'] > 0 else "▼"
            etf_text += f"  {arrow} {name}: {data['day']:+.1f}% (주간{data['week']:+.1f}%)\n"

        watch = ", ".join(r.get("watch_sectors", []))
        avoid = ", ".join(r.get("avoid_sectors", []))

        return f"""{em} <b>시장 사이클: {r.get('cycle_stage')}</b> ({r.get('consecutive_days')}일째)
⚔️ {p['description']}

🇰🇷 코스피: {r.get('kospi_current', 0):,.0f} | 코스닥: {r.get('kosdaq_current', 0):,.0f}
   5일: {r.get('kr_r5', 0):+.1f}% | 20일: {r.get('kr_r20', 0):+.1f}% | 신고가: {r.get('kr_ath_proximity', 0):.1f}%
🇺🇸 나스닥: {r.get('nas_current', 0):,.0f} ({r.get('nas_day_change', 0):+.2f}%)
   S&P500: {r.get('sp_current', 0):,.0f} | 5일: {r.get('nas_r5', 0):+.1f}% | 신고가: {r.get('nas_ath_proximity', 0):.1f}%
😨 VIX: {r.get('vix')} ({r.get('vix_signal')}) | 공포탐욕: {r.get('fg_score')} {r.get('fg_class')}

📊 <b>조정 확률: {prob}%</b> {prob_bar}
{chr(10).join(anomalies) if anomalies else '✅ 이상 신호 없음'}

📈 <b>섹터 ETF</b>
{etf_text}
🤖 <b>AI 전략</b>
🇰🇷 {r.get('ai_strategy', '')}
🇺🇸 {r.get('ai_us_strategy', '')}

🔮 조정 타이밍: {r.get('correction_timing', '')}
⚡ 기회: {r.get('opportunity', '')}
🚨 리스크: {r.get('key_risk', '')}
📅 내일: {r.get('tomorrow_outlook', '')}

🎯 주목: {watch if watch else '없음'}
🚫 회피: {avoid if avoid else '없음'}
💡 임계값 — 단기:{r.get('kr_score_threshold')} 중장기:{r.get('kr_lt_threshold')} 포지션:{r.get('position_size')}%
⏰ {datetime.now().strftime('%Y-%m-%d %H:%M')}"""


if __name__ == "__main__":
    import asyncio

    async def test():
        print("=" * 50)
        print("📊 동적 전략 엔진 v2.0 테스트")
        print("=" * 50)
        mr     = MarketRegime()
        result = await mr.analyze_regime()
        print(mr.get_status_text())

    asyncio.run(test())
