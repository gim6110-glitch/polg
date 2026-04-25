import sys
import os
import json
import yfinance as yf
import pandas as pd
from datetime import datetime

sys.path.insert(0, '/home/dps/stock_ai')


class MarketRegime:
    """
    시장 국면 자동 감지 및 전략 전환
    한국(코스피) + 미국(나스닥) 각각 독립 판단
    """

    def __init__(self):
        self.regime_file         = "/home/dps/stock_ai/data/market_regime.json"
        self.regime_history_file = "/home/dps/stock_ai/data/regime_history.json"
        self.current_regime      = self._load_regime()

    def _load_regime(self):
        if os.path.exists(self.regime_file):
            with open(self.regime_file, "r") as f:
                return json.load(f)
        return {
            "regime":        "중립",
            "kr_regime":     "중립",
            "us_regime":     "중립",
            "score":         0,
            "kr_score":      0,
            "us_score":      0,
            "updated":       datetime.now().isoformat(),
            "consecutive_days": 0,
            "strategy":      "중립_전략"
        }

    def _save_regime(self):
        os.makedirs("/home/dps/stock_ai/data", exist_ok=True)
        with open(self.regime_file, "w") as f:
            json.dump(self.current_regime, f, ensure_ascii=False, indent=2)

    def _save_history(self, regime_data):
        history = []
        if os.path.exists(self.regime_history_file):
            with open(self.regime_history_file, "r") as f:
                history = json.load(f)
        history.append(regime_data)
        history = history[-60:]
        with open(self.regime_history_file, "w") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)

    # ── 한국 장세 분석 ─────────────────────────────

    def _analyze_kr(self):
        """코스피 기반 한국 장세 분석"""
        try:
            score   = 0
            details = []

            kospi = yf.Ticker("^KS11")
            df    = kospi.history(period="3mo").dropna()
            if len(df) < 20:
                return 0, [], {}

            close   = df['Close']
            current = close.iloc[-1]
            ma5     = close.rolling(5).mean().iloc[-1]
            ma20    = close.rolling(20).mean().iloc[-1]
            ma60    = close.rolling(60).mean().iloc[-1]

            # 이동평균 정배열
            if current > ma5 > ma20:
                score += 2
                details.append("✅ 코스피 단기 정배열")
            if ma5 > ma20 > ma60:
                score += 2
                details.append("✅ 코스피 장기 정배열")

            # 20일선
            if current > ma20:
                score += 1
                details.append("✅ 코스피 20일선 위")
            else:
                score -= 1
                details.append("❌ 코스피 20일선 아래")

            # 최근 5일
            week_change = ((close.iloc[-1] - close.iloc[-5]) / close.iloc[-5]) * 100
            if week_change >= 2:
                score += 2
                details.append(f"✅ 최근 5일 {week_change:+.1f}% 상승")
            elif week_change <= -2:
                score -= 2
                details.append(f"❌ 최근 5일 {week_change:+.1f}% 하락")

            # 최근 20일
            month_change = ((close.iloc[-1] - close.iloc[-20]) / close.iloc[-20]) * 100
            if month_change >= 5:
                score += 2
                details.append(f"✅ 최근 20일 {month_change:+.1f}% 상승")
            elif month_change <= -5:
                score -= 2
                details.append(f"❌ 최근 20일 {month_change:+.1f}% 하락")

            # VIX
            try:
                vix_df  = yf.Ticker("^VIX").history(period="5d").dropna()
                vix_val = vix_df['Close'].iloc[-1] if not vix_df.empty else 20
                if vix_val < 20:
                    score += 1
                    details.append(f"✅ VIX 낮음 ({vix_val:.1f}) → 안정")
                elif vix_val > 30:
                    score -= 2
                    details.append(f"❌ VIX 높음 ({vix_val:.1f}) → 공포")
            except:
                vix_val = 20

            # 거래량
            avg_vol    = df['Volume'].rolling(20).mean().iloc[-1]
            recent_vol = df['Volume'].iloc[-3:].mean()
            if recent_vol > avg_vol * 1.2:
                score += 1
                details.append("✅ 거래량 증가")
            elif recent_vol < avg_vol * 0.8:
                score -= 1
                details.append("⚠️ 거래량 감소")

            # 고점 대비
            high_3m  = close.max()
            drawdown = ((current - high_3m) / high_3m) * 100
            if drawdown <= -10:
                score -= 3
                details.append(f"❌ 고점 대비 {drawdown:.1f}% 하락")
            elif drawdown <= -5:
                score -= 1
                details.append(f"⚠️ 고점 대비 {drawdown:.1f}% 하락")
            else:
                details.append(f"✅ 고점 대비 {drawdown:.1f}% (건강한 상승)")

            data = {
                "current":      round(current, 2),
                "ma20":         round(ma20, 2),
                "drawdown":     round(drawdown, 1),
                "week_change":  round(week_change, 2),
                "month_change": round(month_change, 2),
                "vix":          round(vix_val, 1),
            }
            return score, details, data

        except Exception as e:
            print(f"❌ 한국 장세 분석 실패: {e}")
            return 0, [], {}

    # ── 미국 장세 분석 ─────────────────────────────

    def _analyze_us(self):
        """나스닥 기반 미국 장세 분석"""
        try:
            score   = 0
            details = []

            nas = yf.Ticker("^IXIC")
            df  = nas.history(period="3mo").dropna()
            if len(df) < 20:
                return 0, [], {}

            close   = df['Close']
            current = close.iloc[-1]
            ma5     = close.rolling(5).mean().iloc[-1]
            ma20    = close.rolling(20).mean().iloc[-1]
            ma60    = close.rolling(60).mean().iloc[-1]

            # 이동평균 정배열
            if current > ma5 > ma20:
                score += 2
                details.append("✅ 나스닥 단기 정배열")
            if ma5 > ma20 > ma60:
                score += 2
                details.append("✅ 나스닥 장기 정배열")

            # 20일선
            if current > ma20:
                score += 1
                details.append("✅ 나스닥 20일선 위")
            else:
                score -= 1
                details.append("❌ 나스닥 20일선 아래")

            # 최근 5일
            week_change = ((close.iloc[-1] - close.iloc[-5]) / close.iloc[-5]) * 100
            if week_change >= 2:
                score += 2
                details.append(f"✅ 최근 5일 {week_change:+.1f}% 상승")
            elif week_change <= -2:
                score -= 2
                details.append(f"❌ 최근 5일 {week_change:+.1f}% 하락")

            # 최근 20일
            month_change = ((close.iloc[-1] - close.iloc[-20]) / close.iloc[-20]) * 100
            if month_change >= 5:
                score += 2
                details.append(f"✅ 최근 20일 {month_change:+.1f}% 상승")
            elif month_change <= -5:
                score -= 2
                details.append(f"❌ 최근 20일 {month_change:+.1f}% 하락")

            # S&P500 동반 확인
            try:
                sp  = yf.Ticker("^GSPC")
                sp_df = sp.history(period="5d").dropna()
                if len(sp_df) >= 2:
                    sp_change = ((sp_df['Close'].iloc[-1] - sp_df['Close'].iloc[-2]) / sp_df['Close'].iloc[-2]) * 100
                    if sp_change > 0:
                        score += 1
                        details.append(f"✅ S&P500 동반 상승 ({sp_change:+.1f}%)")
                    else:
                        details.append(f"⚠️ S&P500 하락 ({sp_change:+.1f}%)")
                    sp_current = round(sp_df['Close'].iloc[-1], 2)
                    sp_chg     = round(sp_change, 2)
                else:
                    sp_current = 0
                    sp_chg     = 0
            except:
                sp_current = 0
                sp_chg     = 0

            # VIX
            try:
                vix_df  = yf.Ticker("^VIX").history(period="5d").dropna()
                vix_val = vix_df['Close'].iloc[-1] if not vix_df.empty else 20
                if vix_val < 20:
                    score += 1
                    details.append(f"✅ VIX 낮음 ({vix_val:.1f})")
                elif vix_val > 30:
                    score -= 2
                    details.append(f"❌ VIX 높음 ({vix_val:.1f})")
            except:
                vix_val = 20

            # 고점 대비
            high_3m  = close.max()
            drawdown = ((current - high_3m) / high_3m) * 100
            if drawdown <= -10:
                score -= 3
                details.append(f"❌ 고점 대비 {drawdown:.1f}% 하락")
            elif drawdown <= -5:
                score -= 1
                details.append(f"⚠️ 고점 대비 {drawdown:.1f}% 하락")
            else:
                details.append(f"✅ 고점 대비 {drawdown:.1f}% (건강)")

            # 금리 영향 (10년물)
            try:
                tnx    = yf.Ticker("^TNX")
                tnx_df = tnx.history(period="5d").dropna()
                if not tnx_df.empty:
                    tnx_val = tnx_df['Close'].iloc[-1]
                    if tnx_val > 4.5:
                        score -= 1
                        details.append(f"⚠️ 미국 금리 높음 ({tnx_val:.2f}%)")
                    else:
                        details.append(f"✅ 미국 금리 ({tnx_val:.2f}%)")
            except:
                tnx_val = 0

            day_change = ((close.iloc[-1] - close.iloc[-2]) / close.iloc[-2]) * 100

            data = {
                "current":      round(current, 2),
                "ma20":         round(ma20, 2),
                "drawdown":     round(drawdown, 1),
                "week_change":  round(week_change, 2),
                "month_change": round(month_change, 2),
                "day_change":   round(day_change, 2),
                "sp_current":   sp_current,
                "sp_change":    sp_chg,
            }
            return score, details, data

        except Exception as e:
            print(f"❌ 미국 장세 분석 실패: {e}")
            return 0, [], {}

    # ── 종합 장세 판단 ─────────────────────────────

    def _score_to_regime(self, score):
        if score >= 6:
            return "강세"
        elif score >= 2:
            return "중립"
        elif score >= -2:
            return "약세초입"
        else:
            return "약세"

    def analyze_regime(self):
        """한국 + 미국 각각 분석 후 종합"""
        try:
            prev_regime = self.current_regime.get("regime", "중립")

            # 한국 분석
            kr_score, kr_details, kr_data = self._analyze_kr()
            kr_regime = self._score_to_regime(kr_score)

            # 미국 분석
            us_score, us_details, us_data = self._analyze_us()
            us_regime = self._score_to_regime(us_score)

            # 종합 점수 (한국 60% + 미국 40%)
            total_score   = round(kr_score * 0.6 + us_score * 0.4)
            total_regime  = self._score_to_regime(total_score)

            # 연속 일수
            consecutive = self.current_regime.get("consecutive_days", 0)
            if total_regime == prev_regime:
                consecutive += 1
            else:
                consecutive = 1

            result = {
                # 종합
                "regime":           total_regime,
                "score":            total_score,
                "consecutive_days": consecutive,
                "prev_regime":      prev_regime,
                "regime_changed":   total_regime != prev_regime,
                "strategy":         f"{total_regime}_전략",

                # 한국
                "kr_regime":        kr_regime,
                "kr_score":         kr_score,
                "kr_details":       kr_details,
                "kospi_current":    kr_data.get("current", 0),
                "kospi_ma20":       kr_data.get("ma20", 0),
                "kospi_drawdown":   kr_data.get("drawdown", 0),
                "kr_week_change":   kr_data.get("week_change", 0),
                "kr_month_change":  kr_data.get("month_change", 0),
                "vix":              kr_data.get("vix", 20),

                # 미국
                "us_regime":        us_regime,
                "us_score":         us_score,
                "us_details":       us_details,
                "nas_current":      us_data.get("current", 0),
                "nas_ma20":         us_data.get("ma20", 0),
                "nas_drawdown":     us_data.get("drawdown", 0),
                "nas_day_change":   us_data.get("day_change", 0),
                "nas_week_change":  us_data.get("week_change", 0),
                "nas_month_change": us_data.get("month_change", 0),
                "sp_current":       us_data.get("sp_current", 0),
                "sp_change":        us_data.get("sp_change", 0),

                "updated": datetime.now().isoformat()
            }

            self.current_regime = result
            self._save_regime()
            self._save_history(result)
            return result

        except Exception as e:
            print(f"❌ 장세 분석 실패: {e}")
            return self.current_regime

    def get_strategy_params(self):
        """현재 국면에 맞는 전략 파라미터"""
        regime = self.current_regime.get("regime", "중립")
        params = {
            "강세": {
                "rsi_buy_min":  50, "rsi_buy_max": 72, "rsi_sell": 80,
                "pullback_pct": -3, "volume_min": 1.2,
                "use_breakout": True, "use_pullback": True, "use_oversold": False,
                "stop_loss_atr": 1.5,
                "description": "추세 추종 + 눌림목 매수 + 신고가 돌파"
            },
            "중립": {
                "rsi_buy_min":  35, "rsi_buy_max": 65, "rsi_sell": 70,
                "pullback_pct": -5, "volume_min": 1.3,
                "use_breakout": True, "use_pullback": True, "use_oversold": True,
                "stop_loss_atr": 1.5,
                "description": "혼합 전략 (돌파 + 저점)"
            },
            "약세초입": {
                "rsi_buy_min":  25, "rsi_buy_max": 45, "rsi_sell": 60,
                "pullback_pct": -7, "volume_min": 1.5,
                "use_breakout": False, "use_pullback": False, "use_oversold": True,
                "stop_loss_atr": 1.2,
                "description": "방어적 저점 매수 위주"
            },
            "약세": {
                "rsi_buy_min":  20, "rsi_buy_max": 35, "rsi_sell": 55,
                "pullback_pct": -10, "volume_min": 2.0,
                "use_breakout": False, "use_pullback": False, "use_oversold": True,
                "stop_loss_atr": 1.0,
                "description": "극단적 저점만 매수, 현금 비중 확대"
            }
        }
        return params.get(regime, params["중립"])

    def get_regime_emoji(self):
        regime = self.current_regime.get("regime", "중립")
        return {"강세": "🚀", "중립": "➡️", "약세초입": "⚠️", "약세": "🔴"}.get(regime, "➡️")

    def get_kr_regime_emoji(self):
        regime = self.current_regime.get("kr_regime", "중립")
        return {"강세": "🚀", "중립": "➡️", "약세초입": "⚠️", "약세": "🔴"}.get(regime, "➡️")

    def get_us_regime_emoji(self):
        regime = self.current_regime.get("us_regime", "중립")
        return {"강세": "🚀", "중립": "➡️", "약세초입": "⚠️", "약세": "🔴"}.get(regime, "➡️")

    def get_status_text(self):
        r       = self.current_regime
        p       = self.get_strategy_params()
        em      = self.get_regime_emoji()
        kr_em   = self.get_kr_regime_emoji()
        us_em   = self.get_us_regime_emoji()

        kr_details_text = "\n".join(r.get("kr_details", []))
        us_details_text = "\n".join(r.get("us_details", []))

        changed_text = ""
        if r.get("regime_changed"):
            changed_text = f"\n🔄 <b>전략 전환!</b> {r.get('prev_regime')} → {r.get('regime')}\n"

        return f"""{em} <b>종합 시장 국면: {r.get('regime')}장</b> (점수: {r.get('score')})
{changed_text}
🗓 연속 {r.get('consecutive_days')}일째
⚔️ 전략: {p['description']}

━━━━━━━━━━━━━━━━━━━
🇰🇷 <b>한국 ({r.get('kr_regime')}장)</b> {kr_em} 점수: {r.get('kr_score')}

📊 코스피: {r.get('kospi_current'):,}
📈 20일선: {r.get('kospi_ma20'):,}
📉 고점 대비: {r.get('kospi_drawdown')}%
📅 주간: {r.get('kr_week_change', 0):+.1f}% | 월간: {r.get('kr_month_change', 0):+.1f}%
😨 VIX: {r.get('vix', 20)}

📋 판단 근거:
{kr_details_text}

━━━━━━━━━━━━━━━━━━━
🇺🇸 <b>미국 ({r.get('us_regime')}장)</b> {us_em} 점수: {r.get('us_score')}

📊 나스닥: {r.get('nas_current'):,} ({r.get('nas_day_change', 0):+.2f}%)
📊 S&P500: {r.get('sp_current'):,} ({r.get('sp_change', 0):+.2f}%)
📈 20일선: {r.get('nas_ma20'):,}
📉 고점 대비: {r.get('nas_drawdown')}%
📅 주간: {r.get('nas_week_change', 0):+.1f}% | 월간: {r.get('nas_month_change', 0):+.1f}%

📋 판단 근거:
{us_details_text}"""


if __name__ == "__main__":
    mr = MarketRegime()
    print("=" * 50)
    print("📊 시장 국면 분석 테스트")
    print("=" * 50)
    result = mr.analyze_regime()
    print(mr.get_status_text())
