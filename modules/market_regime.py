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
    강세장 / 약세장 / 중립장 자동 판단
    """
    def __init__(self):
        self.regime_file = "/home/dps/stock_ai/data/market_regime.json"
        self.regime_history_file = "/home/dps/stock_ai/data/regime_history.json"
        self.current_regime = self._load_regime()

    def _load_regime(self):
        if os.path.exists(self.regime_file):
            with open(self.regime_file, "r") as f:
                return json.load(f)
        return {
            "regime": "중립",
            "score": 0,
            "updated": datetime.now().isoformat(),
            "consecutive_days": 0,
            "strategy": "중립_전략"
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
        # 최근 60일만 보관
        history = history[-60:]
        with open(self.regime_history_file, "w") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)

    def analyze_regime(self):
        """코스피 + 코스닥 + VIX 종합해서 시장 국면 판단"""
        try:
            score = 0
            details = []

            # 코스피 분석
            kospi = yf.Ticker("^KS11")
            df    = kospi.history(period="3mo").dropna()
            if len(df) < 20:
                return self.current_regime

            close   = df['Close']
            current = close.iloc[-1]
            ma5     = close.rolling(5).mean().iloc[-1]
            ma20    = close.rolling(20).mean().iloc[-1]
            ma60    = close.rolling(60).mean().iloc[-1]

            # 1. 이동평균 정배열
            if current > ma5 > ma20:
                score += 2
                details.append("✅ 코스피 단기 정배열")
            if ma5 > ma20 > ma60:
                score += 2
                details.append("✅ 코스피 장기 정배열")

            # 2. 20일선 위에 있는지
            if current > ma20:
                score += 1
                details.append("✅ 코스피 20일선 위")
            else:
                score -= 1
                details.append("❌ 코스피 20일선 아래")

            # 3. 최근 5일 방향성
            week_change = ((close.iloc[-1] - close.iloc[-5]) / close.iloc[-5]) * 100
            if week_change >= 2:
                score += 2
                details.append(f"✅ 최근 5일 {week_change:+.1f}% 상승")
            elif week_change <= -2:
                score -= 2
                details.append(f"❌ 최근 5일 {week_change:+.1f}% 하락")

            # 4. 최근 20일 추세
            month_change = ((close.iloc[-1] - close.iloc[-20]) / close.iloc[-20]) * 100
            if month_change >= 5:
                score += 2
                details.append(f"✅ 최근 20일 {month_change:+.1f}% 상승")
            elif month_change <= -5:
                score -= 2
                details.append(f"❌ 최근 20일 {month_change:+.1f}% 하락")

            # 5. VIX (공포지수) 확인
            try:
                vix    = yf.Ticker("^VIX")
                vix_df = vix.history(period="5d").dropna()
                if not vix_df.empty:
                    vix_val = vix_df['Close'].iloc[-1]
                    if vix_val < 20:
                        score += 1
                        details.append(f"✅ VIX 낮음 ({vix_val:.1f}) → 안정")
                    elif vix_val > 30:
                        score -= 2
                        details.append(f"❌ VIX 높음 ({vix_val:.1f}) → 공포")
            except:
                pass

            # 6. 거래량 추세
            avg_vol    = df['Volume'].rolling(20).mean().iloc[-1]
            recent_vol = df['Volume'].iloc[-3:].mean()
            if recent_vol > avg_vol * 1.2:
                score += 1
                details.append("✅ 거래량 증가 → 상승 에너지")
            elif recent_vol < avg_vol * 0.8:
                score -= 1
                details.append("⚠️ 거래량 감소 → 에너지 약화")

            # 7. 고점 대비 하락폭 (조정 감지)
            high_3m = close.max()
            drawdown = ((current - high_3m) / high_3m) * 100
            if drawdown <= -10:
                score -= 3
                details.append(f"❌ 고점 대비 {drawdown:.1f}% 하락 (조정)")
            elif drawdown <= -5:
                score -= 1
                details.append(f"⚠️ 고점 대비 {drawdown:.1f}% 하락")
            else:
                details.append(f"✅ 고점 대비 {drawdown:.1f}% (건강한 상승)")

            # 국면 판단
            prev_regime = self.current_regime.get("regime", "중립")
            if score >= 6:
                regime   = "강세"
                strategy = "강세장_전략"
            elif score >= 2:
                regime   = "중립"
                strategy = "중립_전략"
            elif score >= -2:
                regime   = "약세초입"
                strategy = "방어_전략"
            else:
                regime   = "약세"
                strategy = "약세장_전략"

            # 연속 일수 계산
            consecutive = self.current_regime.get("consecutive_days", 0)
            if regime == prev_regime:
                consecutive += 1
            else:
                consecutive = 1

            result = {
                "regime": regime,
                "score": score,
                "strategy": strategy,
                "kospi_current": round(current, 2),
                "kospi_ma20": round(ma20, 2),
                "kospi_drawdown": round(drawdown, 1),
                "week_change": round(week_change, 2),
                "month_change": round(month_change, 2),
                "consecutive_days": consecutive,
                "details": details,
                "prev_regime": prev_regime,
                "regime_changed": regime != prev_regime,
                "updated": datetime.now().isoformat()
            }

            self.current_regime = result
            self._save_regime()
            self._save_history(result)
            return result

        except Exception as e:
            print(f"❌ 시장 국면 분석 실패: {e}")
            return self.current_regime

    def get_strategy_params(self):
        """현재 국면에 맞는 전략 파라미터 반환"""
        regime = self.current_regime.get("regime", "중립")
        params = {
            "강세": {
                "rsi_buy_min": 50,
                "rsi_buy_max": 72,
                "rsi_sell":    80,
                "pullback_pct": -3,
                "volume_min":   1.2,
                "use_breakout": True,
                "use_pullback": True,
                "use_oversold": False,
                "stop_loss_atr": 1.5,
                "description": "추세 추종 + 눌림목 매수 + 신고가 돌파"
            },
            "중립": {
                "rsi_buy_min": 35,
                "rsi_buy_max": 65,
                "rsi_sell":    70,
                "pullback_pct": -5,
                "volume_min":   1.3,
                "use_breakout": True,
                "use_pullback": True,
                "use_oversold": True,
                "stop_loss_atr": 1.5,
                "description": "혼합 전략 (돌파 + 저점)"
            },
            "약세초입": {
                "rsi_buy_min": 25,
                "rsi_buy_max": 45,
                "rsi_sell":    60,
                "pullback_pct": -7,
                "volume_min":   1.5,
                "use_breakout": False,
                "use_pullback": False,
                "use_oversold": True,
                "stop_loss_atr": 1.2,
                "description": "방어적 저점 매수 위주"
            },
            "약세": {
                "rsi_buy_min": 20,
                "rsi_buy_max": 35,
                "rsi_sell":    55,
                "pullback_pct": -10,
                "volume_min":   2.0,
                "use_breakout": False,
                "use_pullback": False,
                "use_oversold": True,
                "stop_loss_atr": 1.0,
                "description": "극단적 저점만 매수, 현금 비중 확대"
            }
        }
        return params.get(regime, params["중립"])

    def get_regime_emoji(self):
        regime = self.current_regime.get("regime", "중립")
        return {"강세": "🚀", "중립": "➡️", "약세초입": "⚠️", "약세": "🔴"}.get(regime, "➡️")

    def get_status_text(self):
        r  = self.current_regime
        p  = self.get_strategy_params()
        em = self.get_regime_emoji()
        details_text = "\n".join(r.get("details", []))
        changed_text = ""
        if r.get("regime_changed"):
            changed_text = f"\n🔄 <b>전략 전환!</b> {r.get('prev_regime')} → {r.get('regime')}"
        return f"""{em} <b>시장 국면: {r.get('regime')}장</b> (점수: {r.get('score')})
{changed_text}
📊 코스피: {r.get('kospi_current'):,}
📈 20일선: {r.get('kospi_ma20'):,}
📉 고점 대비: {r.get('kospi_drawdown')}%
🗓 연속 {r.get('consecutive_days')}일째

📋 판단 근거:
{details_text}

⚔️ 현재 전략: {p['description']}"""

if __name__ == "__main__":
    mr = MarketRegime()
    print("=" * 50)
    print("📊 시장 국면 분석 테스트")
    print("=" * 50)
    result = mr.analyze_regime()
    print(mr.get_status_text())
    print(f"\n전략 파라미터:")
    params = mr.get_strategy_params()
    for k, v in params.items():
        print(f"  {k}: {v}")
