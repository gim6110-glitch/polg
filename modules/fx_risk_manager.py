import os
import sys
import json
import time
from datetime import datetime, timedelta
from dotenv import load_dotenv

sys.path.insert(0, '/media/dps/T7/stock_ai')
load_dotenv('/media/dps/T7/stock_ai/.env')

FX_FILE = "/media/dps/T7/stock_ai/data/fx_history.json"


class FxRiskManager:
    """
    환율 리스크 관리
    - KRW/USD 환율 추적 (yfinance, 15분 지연)
    - ±1% 주의 / ±2% 긴급 / ±3% 극단 알림
    - 환노출 비중 자동 계산
    - 5일 추세 추적
    - 환율 급변 시 손절선 재계산
    - 매수 환율 저장
    """

    def __init__(self):
        self.data = self._load()

    def _load(self):
        if os.path.exists(FX_FILE):
            with open(FX_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        default = {"history": [], "buy_rates": {}}
        self._save(default)
        return default

    def _save(self, data=None):
        os.makedirs(os.path.dirname(FX_FILE), exist_ok=True)
        if data is None:
            data = self.data
        with open(FX_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    # ── 환율 조회 ──────────────────────────────────

    def get_current_rate(self):
        """현재 달러/원 환율 조회 (15분 지연)"""
        try:
            import yfinance as yf
            hist = yf.Ticker("KRW=X").history(period="2d").dropna()
            if not hist.empty:
                return round(hist['Close'].iloc[-1], 2)
        except:
            pass
        return 1300.0  # 기본값

    def get_rate_history(self, days=5):
        """최근 N일 환율 히스토리"""
        try:
            import yfinance as yf
            hist = yf.Ticker("KRW=X").history(period=f"{days+2}d").dropna()
            if not hist.empty:
                return hist['Close'].tail(days).tolist()
        except:
            pass
        return []

    def save_daily_rate(self):
        """매일 08:00 환율 저장"""
        rate  = self.get_current_rate()
        today = datetime.now().strftime("%Y-%m-%d")

        history = self.data.get("history", [])
        # 오늘 이미 저장됐으면 업데이트
        for item in history:
            if item["date"] == today:
                item["rate"] = rate
                self._save()
                return rate

        history.append({"date": today, "rate": rate})
        # 최근 30일만 유지
        self.data["history"] = sorted(history, key=lambda x: x["date"])[-30:]
        self._save()
        return rate

    # ── 매수 환율 관리 ─────────────────────────────

    def save_buy_rate(self, ticker, rate=None):
        """매수 시 환율 저장"""
        if rate is None:
            rate = self.get_current_rate()
        self.data["buy_rates"][ticker.upper()] = {
            "rate": rate,
            "date": datetime.now().strftime("%Y-%m-%d")
        }
        self._save()
        return rate

    def get_buy_rate(self, ticker):
        """매수 환율 조회"""
        info = self.data.get("buy_rates", {}).get(ticker.upper())
        return info["rate"] if info else None

    def set_buy_rate(self, ticker, rate):
        """기존 종목 환율 수동 입력 (/buy_rate 명령어)"""
        self.save_buy_rate(ticker, rate)

    # ── 환율 변동 감지 ─────────────────────────────

    def check_fx_change(self):
        """
        환율 급변 감지
        ±1% 주의 / ±2% 긴급 / ±3% 극단
        미국 주식 보유 시만 알림
        """
        try:
            import yfinance as yf
            hist = yf.Ticker("KRW=X").history(period="3d").dropna()
            if len(hist) < 2:
                return None

            curr = hist['Close'].iloc[-1]
            prev = hist['Close'].iloc[-2]
            change_pct = ((curr - prev) / prev) * 100

            result = {
                "current_rate": round(curr, 2),
                "prev_rate":    round(prev, 2),
                "change_pct":   round(change_pct, 2),
                "severity":     None,
                "direction":    "약세" if change_pct > 0 else "강세",  # 원화 기준
            }

            # 원화 약세 = 달러/원 상승
            abs_change = abs(change_pct)
            if abs_change >= 3:
                result["severity"] = "극단"
            elif abs_change >= 2:
                result["severity"] = "긴급"
            elif abs_change >= 1:
                result["severity"] = "주의"

            return result
        except Exception as e:
            print(f"  ⚠️ 환율 변동 감지 실패: {e}")
            return None

    def get_5day_trend(self):
        """5일 환율 추세"""
        history = self.get_rate_history(days=5)
        if len(history) < 5:
            return None

        # 원화 약세 = 달러/원 상승
        rising  = sum(1 for i in range(1, len(history)) if history[i] > history[i-1])
        falling = sum(1 for i in range(1, len(history)) if history[i] < history[i-1])

        if rising >= 4:
            return {"trend": "원화 약세", "days": rising, "action": "미국 주식 환차익 실현 타이밍"}
        elif falling >= 4:
            return {"trend": "원화 강세", "days": falling, "action": "미국 주식 신규 진입 유리"}
        return {"trend": "횡보", "days": 0, "action": "환율 중립"}

    # ── 환노출 비중 계산 ───────────────────────────

    def calc_fx_exposure(self, portfolio, current_rate=None):
        """미국 주식 환노출 비중 계산"""
        if current_rate is None:
            current_rate = self.get_current_rate()

        us_value_krw = 0
        kr_value_krw = 0

        for ticker, stock in portfolio.items():
            if not isinstance(stock, dict):
                continue
            market    = stock.get('market', 'KR')
            buy_price = stock.get('buy_price', 0)
            quantity  = stock.get('quantity', 0)

            if market == 'US':
                us_value_krw += buy_price * quantity * current_rate
            else:
                kr_value_krw += buy_price * quantity

        total = us_value_krw + kr_value_krw
        if total <= 0:
            return 0, us_value_krw, total

        exposure = (us_value_krw / total) * 100
        return round(exposure, 1), round(us_value_krw, 0), round(total, 0)

    # ── 환율 반영 수익률 계산 ──────────────────────

    def calc_fx_adjusted_profit(self, ticker, stock, current_price, current_rate):
        """환율 반영 실질 수익률 계산"""
        market    = stock.get('market', 'KR')
        buy_price = stock.get('buy_price', 0)

        if market != 'US':
            # 한국 주식은 환율 무관
            return ((current_price - buy_price) / buy_price) * 100 if buy_price > 0 else 0

        buy_rate = self.get_buy_rate(ticker)
        if not buy_rate:
            # 매수 환율 없으면 달러 기준만
            return ((current_price - buy_price) / buy_price) * 100 if buy_price > 0 else 0

        # 원화 기준 수익률
        buy_krw     = buy_price * buy_rate
        current_krw = current_price * current_rate
        return ((current_krw - buy_krw) / buy_krw) * 100 if buy_krw > 0 else 0

    # ── 손절선 재계산 ──────────────────────────────

    def recalc_stop_loss(self, portfolio, current_rate):
        """환율 급변 시 미국 주식 손절선 원화 기준 재계산"""
        alerts = []

        for ticker, stock in portfolio.items():
            if not isinstance(stock, dict):
                continue
            if stock.get('market') != 'US':
                continue
            if not stock.get('stop_loss'):
                continue

            buy_rate = self.get_buy_rate(ticker)
            if not buy_rate:
                continue

            stop_loss_usd = stock['stop_loss']
            # 기존 환율 기준 원화 손절선
            original_krw = stop_loss_usd * buy_rate
            # 현재 환율 기준 원화 손절선
            current_krw  = stop_loss_usd * current_rate

            change_pct = ((current_krw - original_krw) / original_krw) * 100

            if abs(change_pct) >= 5:
                alerts.append({
                    "ticker":       ticker,
                    "name":         stock.get('name', ticker),
                    "stop_loss_usd": stop_loss_usd,
                    "original_krw": round(original_krw, 0),
                    "current_krw":  round(current_krw, 0),
                    "change_pct":   round(change_pct, 2),
                })

        return alerts

    # ── 메시지 생성 ────────────────────────────────

    def build_fx_alert(self, fx_change, portfolio, has_us_stocks):
        """환율 급변 알림 메시지"""
        if not fx_change or not fx_change.get("severity"):
            return None
        if not has_us_stocks:
            return None

        severity  = fx_change["severity"]
        change    = fx_change["change_pct"]
        curr_rate = fx_change["current_rate"]
        direction = fx_change["direction"]

        emoji = {"극단": "🚨🚨", "긴급": "🚨", "주의": "⚠️"}.get(severity, "⚠️")
        arrow = "▲" if change > 0 else "▼"

        msg  = f"{emoji} <b>환율 {severity} 알림</b>\n\n"
        msg += f"💱 달러/원: {curr_rate:,.1f}원 ({arrow}{change:+.2f}%)\n"
        msg += f"📊 원화 {direction}\n\n"

        if severity in ["긴급", "극단"]:
            current_rate  = curr_rate
            stop_alerts   = self.recalc_stop_loss(portfolio, current_rate)
            if stop_alerts:
                msg += "🔄 <b>손절선 재계산</b>\n"
                for a in stop_alerts:
                    msg += f"  {a['name']} ({a['ticker']})\n"
                    msg += f"  기존: {a['original_krw']:,.0f}원 → 현재: {a['current_krw']:,.0f}원 ({a['change_pct']:+.1f}%)\n"
                msg += "\n"

        if severity == "극단":
            msg += "⚠️ 환율 급변으로 미국 주식 포지션 전면 재검토 권고\n"
        elif severity == "긴급":
            msg += "💡 미국 주식 익절/손절 기준 재확인 권고\n"
        else:
            msg += "💡 미국 주식 보유자 환율 동향 주시 필요\n"

        msg += f"\n⏰ {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        return msg

    def build_fx_exposure_alert(self, exposure, us_value, total):
        """환노출 비중 경고"""
        if exposure < 50:
            return None

        msg  = f"⚠️ <b>환노출 비중 경고</b>\n\n"
        msg += f"💱 미국 주식 비중: {exposure:.1f}%\n"
        msg += f"💵 미국 주식 평가액: {us_value:,.0f}원\n"
        msg += f"💰 총자산: {total:,.0f}원\n\n"
        msg += f"📌 환율 리스크 집중 구간 (50% 초과)\n"
        msg += f"💡 원화 강세 시 미국 주식 일부 익절 고려\n"
        msg += f"\n⏰ {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        return msg

    def build_trend_message(self, trend_info, current_rate):
        """환율 추세 메시지"""
        if not trend_info or trend_info["trend"] == "횡보":
            return None

        trend  = trend_info["trend"]
        days   = trend_info["days"]
        action = trend_info["action"]
        emoji  = "📉" if "약세" in trend else "📈"

        msg  = f"{emoji} <b>환율 추세 알림</b>\n\n"
        msg += f"💱 현재 환율: {current_rate:,.1f}원\n"
        msg += f"📊 {days}일 연속 원화 {trend}\n"
        msg += f"💡 {action}\n"
        msg += f"\n⏰ {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        return msg

    def build_weekly_fx_summary(self, portfolio, current_rate):
        """주간 환율 요약 (주말 브리핑용)"""
        history = self.data.get("history", [])[-7:]
        trend   = self.get_5day_trend()
        exposure, us_value, total = self.calc_fx_exposure(portfolio, current_rate)

        msg  = f"💱 <b>주간 환율 요약</b>\n\n"
        msg += f"현재 달러/원: {current_rate:,.1f}원\n"

        if len(history) >= 2:
            week_change = ((history[-1]["rate"] - history[0]["rate"]) / history[0]["rate"]) * 100
            arrow = "▲" if week_change > 0 else "▼"
            msg  += f"주간 변동: {arrow}{week_change:+.2f}%\n"

        if trend:
            msg += f"추세: {trend['trend']}\n"
            msg += f"💡 {trend['action']}\n"

        msg += f"\n미국 주식 환노출: {exposure:.1f}%\n"
        if exposure >= 50:
            msg += "⚠️ 환노출 50% 초과 주의\n"

        msg += f"\n⏰ {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        return msg
