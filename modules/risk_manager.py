import sys
import os
import json
import time
from datetime import datetime
from dotenv import load_dotenv

sys.path.insert(0, "/media/dps/T7/stock_ai")
load_dotenv("/media/dps/T7/stock_ai/.env")

class RiskManager:
    """
    포트폴리오 리스크 자동 계산
    섹터 편중 경고
    환율 영향 분석
    손절/익절 고도화
    """
    def __init__(self):
        self.portfolio_file = "/media/dps/T7/stock_ai/data/portfolio.json"
        self.portfolio      = self._load_portfolio()

    def _load_portfolio(self):
        if os.path.exists(self.portfolio_file):
            with open(self.portfolio_file, "r") as f:
                return json.load(f)
        return {}

    def calc_sector_concentration(self):
        """섹터 편중도 계산"""
        from modules.kis_api import KISApi
        from modules.sector_db import get_sector_by_ticker
        import yfinance as yf

        kis          = KISApi()
        sector_value = {}
        total_value  = 0

        for ticker, stock in self.portfolio.items():
            buy_price = stock.get("buy_price", 0)
            quantity  = stock.get("quantity", 0)
            market    = stock.get("market", "KR")

            # 현재가 조회
            try:
                if market == "KR":
                    data  = kis.get_kr_price(ticker)
                    price = data["price"] if data else buy_price
                else:
                    # KIS API로 미국 주식 실시간
                    us_data = None
                    for excd in ["NAS", "NYS", "AMS"]:
                        us_data = kis.get_us_price(ticker, excd)
                        if us_data and us_data.get("price", 0) > 0:
                            break
                    price = us_data["price"] if us_data and us_data.get("price", 0) > 0 else buy_price
            except:
                price = buy_price

            # 원화 환산
            try:
                if market == "US":
                    import yfinance as yf
                    usd_krw = yf.Ticker("USDKRW=X").history(period="1d").dropna()
                    rate    = float(usd_krw["Close"].iloc[-1]) if not usd_krw.empty else 1380
                    value   = price * quantity * rate
                else:
                    value = price * quantity
            except:
                value = price * quantity

            total_value += value

            # 섹터 파악
            sector_name, tier, cat = get_sector_by_ticker(ticker)
            if not sector_name:
                sector_name = stock.get("hold_type", "기타")

            if sector_name not in sector_value:
                sector_value[sector_name] = 0
            sector_value[sector_name] += value
            time.sleep(0.1)

        # 비중 계산
        sector_ratio = {}
        for sector, value in sector_value.items():
            ratio = (value / total_value * 100) if total_value > 0 else 0
            sector_ratio[sector] = {
                "value": round(value, 0),
                "ratio": round(ratio, 1)
            }

        return sector_ratio, total_value

    def calc_risk_metrics(self):
        """리스크 지표 계산"""
        from modules.kis_api import KISApi
        kis            = KISApi()
        total_invest   = 0
        total_current  = 0
        max_loss_stock = None
        max_loss_pct   = 0
        us_exposure    = 0
        kr_exposure    = 0

        # 환율 먼저
        rate_data = kis.get_exchange_rate()
        rate      = rate_data['price'] if rate_data else 1480
        print(f"  환율: {rate}")

        for ticker, stock in self.portfolio.items():
            buy_price = stock.get("buy_price", 0)
            quantity  = stock.get("quantity", 0)
            market    = stock.get("market", "KR")

            try:
                if market == "KR":
                    data  = kis.get_kr_price(ticker)
                    price = data["price"] if data else buy_price
                else:
                    us_data = None
                    for excd in ["NAS", "NYS", "AMS"]:
                        us_data = kis.get_us_price(ticker, excd)
                        if us_data and us_data.get("price", 0) > 0:
                            break
                    usd_price = us_data["price"] if us_data and us_data.get("price", 0) > 0 else buy_price
                    price     = usd_price * rate
            except:
                price = buy_price * (rate if market == "US" else 1)

            # 투자금 원화 환산
            invested_krw = buy_price * quantity * rate if market == "US" else buy_price * quantity
            current_krw  = price * quantity
            pnl_pct      = ((price - (buy_price * (rate if market == "US" else 1))) / (buy_price * (rate if market == "US" else 1)) * 100) if buy_price > 0 else 0

            total_invest  += invested_krw
            total_current += current_krw

            if pnl_pct < max_loss_pct:
                max_loss_pct   = pnl_pct
                max_loss_stock = stock.get("name", ticker)

            if market == "US":
                us_exposure += current_krw
            else:
                kr_exposure += current_krw

            import time
            time.sleep(0.1)

        total_pnl     = total_current - total_invest
        total_pnl_pct = (total_pnl / total_invest * 100) if total_invest > 0 else 0
        total_assets  = us_exposure + kr_exposure
        us_ratio      = (us_exposure / total_assets * 100) if total_assets > 0 else 0
        kr_ratio      = (kr_exposure / total_assets * 100) if total_assets > 0 else 0

        return {
            "total_invest":   round(total_invest, 0),
            "total_current":  round(total_current, 0),
            "total_pnl":      round(total_pnl, 0),
            "total_pnl_pct":  round(total_pnl_pct, 1),
            "max_loss_stock": max_loss_stock,
            "max_loss_pct":   round(max_loss_pct, 1),
            "us_ratio":       round(us_ratio, 1),
            "kr_ratio":       round(kr_ratio, 1),
        }

    def calc_exchange_rate_risk(self):
        """환율 영향 분석"""
        import yfinance as yf
        try:
            usd_krw = yf.Ticker("USDKRW=X").history(period="5d").dropna()
            if len(usd_krw) >= 2:
                current_rate = round(float(usd_krw["Close"].iloc[-1]), 2)
                prev_rate    = round(float(usd_krw["Close"].iloc[-2]), 2)
                change_pct   = round(((current_rate - prev_rate) / prev_rate) * 100, 2)

                # 달러 강세/약세 영향
                if change_pct >= 0.5:
                    fx_impact = "달러 강세 → 미국주식 원화 환산 수익 증가"
                    fx_action = "미국 주식 보유 유리"
                elif change_pct <= -0.5:
                    fx_impact = "달러 약세 → 미국주식 원화 환산 수익 감소"
                    fx_action = "한국 수출주 불리, 내수주 유리"
                else:
                    fx_impact = "환율 안정"
                    fx_action = "환율 영향 중립"

                return {
                    "rate":       current_rate,
                    "change_pct": change_pct,
                    "impact":     fx_impact,
                    "action":     fx_action,
                }
        except:
            pass
        return {"rate": 0, "change_pct": 0, "impact": "환율 조회 실패", "action": ""}

    def check_stop_loss_upgrade(self):
        """ATR 기반 동적 손절 계산"""
        import yfinance as yf
        upgrades = []

        for ticker, stock in self.portfolio.items():
            market    = stock.get("market", "KR")
            buy_price = stock.get("buy_price", 0)
            stop_loss = stock.get("stop_loss", 0)
            if not stop_loss:
                continue

            try:
                yf_ticker = f"{ticker}.KS" if market == "KR" else ticker
                hist      = yf.Ticker(yf_ticker).history(period="1mo").dropna()
                if len(hist) < 14:
                    continue

                # ATR 계산
                high  = hist["High"]
                low   = hist["Low"]
                close = hist["Close"]
                tr    = (high - low).combine(abs(high - close.shift()), max).combine(abs(low - close.shift()), max)
                atr   = tr.rolling(14).mean().iloc[-1]

                current_price = round(close.iloc[-1], 2)
                # ATR 기반 손절 = 현재가 - ATR * 2
                atr_stop = round(current_price - (atr * 2), 0 if market == "KR" else 2)

                # 기존 손절보다 ATR 손절이 더 높으면 업그레이드 권고
                if atr_stop > stop_loss and current_price > buy_price:
                    upgrades.append({
                        "name":      stock.get("name", ticker),
                        "ticker":    ticker,
                        "market":    market,
                        "current":   current_price,
                        "old_stop":  stop_loss,
                        "new_stop":  atr_stop,
                        "atr":       round(atr, 2),
                        "reason":    f"수익 중 + ATR 손절 {atr_stop:,.0f} > 기존 손절 {stop_loss:,.0f}"
                    })
            except:
                pass
            time.sleep(0.2)

        return upgrades

    async def ai_risk_analysis(self, sector_ratio, metrics, fx_data):
        """AI 리스크 종합 분석"""
        from anthropic import Anthropic
        import os
        client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

        sector_text = ""
        for sector, data in sorted(sector_ratio.items(), key=lambda x: x[1]["ratio"], reverse=True):
            sector_text += f"  {sector}: {data['ratio']:.1f}%\n"

        prompt = f"""포트폴리오 리스크를 분석해주세요.

=== 섹터 비중 ===
{sector_text}

=== 수익률 현황 ===
총 수익률: {metrics['total_pnl_pct']:+.1f}%
미국 비중: {metrics['us_ratio']:.1f}%
한국 비중: {metrics['kr_ratio']:.1f}%
최대 손실 종목: {metrics['max_loss_stock']} ({metrics['max_loss_pct']:+.1f}%)

=== 환율 ===
달러/원: {fx_data['rate']} ({fx_data['change_pct']:+.2f}%)
{fx_data['impact']}

다음을 분석해주세요:
1. 리스크 레벨 (낮음/중간/높음)
2. 가장 큰 리스크 요인
3. 개선 권고사항 (2~3가지)
4. 한줄 총평

JSON으로만:
{{
  "risk_level": "낮음/중간/높음",
  "risk_factors": ["요인1", "요인2"],
  "recommendations": ["권고1", "권고2", "권고3"],
  "summary": "한줄 총평"
}}"""

        try:
            res  = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=500,
                messages=[{"role": "user", "content": prompt}]
            )
            import re, json
            text = re.sub(r"```json|```", "", res.content[0].text.strip()).strip()
            m    = re.search(r"\{.*\}", text, re.DOTALL)
            if m:
                return json.loads(m.group())
        except Exception as e:
            print(f"  ❌ AI 분석 실패: {e}")
        return None

    def build_risk_message(self, sector_ratio, metrics, fx_data, ai_result, upgrades):
        """리스크 리포트 메시지"""
        risk_emoji = {"낮음": "🟢", "중간": "🟡", "높음": "🔴"}.get(
            ai_result.get("risk_level", "중간") if ai_result else "중간", "🟡"
        )

        msg  = f"⚠️ <b>포트폴리오 리스크 분석</b> {datetime.now().strftime('%m/%d %H:%M')}\n\n"

        if ai_result:
            msg += f"{risk_emoji} <b>리스크 레벨: {ai_result.get('risk_level', '')}</b>\n"
            msg += f"💡 {ai_result.get('summary', '')}\n\n"

        msg += f"📊 <b>수익률</b>: {metrics['total_pnl_pct']:+.1f}%\n"
        msg += f"🇺🇸 미국 비중: {metrics['us_ratio']:.1f}%\n"
        msg += f"🇰🇷 한국 비중: {metrics['kr_ratio']:.1f}%\n\n"

        msg += f"💱 <b>환율</b>: {fx_data['rate']:,}원 ({fx_data['change_pct']:+.2f}%)\n"
        msg += f"  → {fx_data['impact']}\n\n"

        # 섹터 비중 상위
        top_sectors = sorted(sector_ratio.items(), key=lambda x: x[1]["ratio"], reverse=True)[:5]
        msg += "📋 <b>섹터 비중 TOP5</b>\n"
        for sector, data in top_sectors:
            bar   = "█" * int(data["ratio"] / 5) + "░" * (20 - int(data["ratio"] / 5))
            emoji = "⚠️" if data["ratio"] > 30 else ""
            msg  += f"  {sector}: {data['ratio']:.1f}% {emoji}\n"

        if ai_result:
            factors = ai_result.get("risk_factors", [])
            if factors:
                msg += "\n🚨 <b>리스크 요인</b>\n"
                for f in factors:
                    msg += f"  • {f}\n"

            recs = ai_result.get("recommendations", [])
            if recs:
                msg += "\n💡 <b>개선 권고</b>\n"
                for r in recs:
                    msg += f"  • {r}\n"

        if upgrades:
            msg += "\n📈 <b>손절가 업그레이드 권고</b>\n"
            for u in upgrades[:3]:
                currency = "$" if u["market"] == "US" else "₩"
                msg += f"  {u['name']}: {currency}{u['old_stop']:,} → {currency}{u['new_stop']:,}\n"

        msg += f"\n⏰ {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        return msg


if __name__ == "__main__":
    import asyncio

    async def test():
        print("=" * 50)
        print("⚠️ 리스크 매니저 테스트")
        print("=" * 50)
        rm = RiskManager()

        print("\n섹터 비중 계산 중...")
        sector_ratio, total = rm.calc_sector_concentration()
        print(f"총 자산: {total:,.0f}원")
        for s, d in sorted(sector_ratio.items(), key=lambda x: x[1]["ratio"], reverse=True)[:5]:
            print(f"  {s}: {d['ratio']:.1f}%")

        print("\n리스크 지표 계산 중...")
        metrics = rm.calc_risk_metrics()
        print(f"수익률: {metrics['total_pnl_pct']:+.1f}%")
        print(f"미국비중: {metrics['us_ratio']:.1f}% / 한국비중: {metrics['kr_ratio']:.1f}%")

        print("\n환율 분석 중...")
        fx_data = rm.calc_exchange_rate_risk()
        print(f"환율: {fx_data['rate']} ({fx_data['change_pct']:+.2f}%)")

        print("\nATR 손절 업그레이드 확인 중...")
        upgrades = rm.check_stop_loss_upgrade()
        print(f"업그레이드 권고: {len(upgrades)}개")

        print("\nAI 리스크 분석 중...")
        ai_result = await rm.ai_risk_analysis(sector_ratio, metrics, fx_data)

        msg = rm.build_risk_message(sector_ratio, metrics, fx_data, ai_result, upgrades)
        print("\n" + msg)

    asyncio.run(test())
