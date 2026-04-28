import sys
import os
import json
import time
from datetime import datetime
from dotenv import load_dotenv

sys.path.insert(0, '/media/dps/T7/stock_ai')
from modules.kis_api import KISApi
from modules.ai_analyzer import AIAnalyzer

load_dotenv('/media/dps/T7/stock_ai/.env')

class Portfolio:
    def __init__(self):
        self.kis            = KISApi()
        self.ai             = AIAnalyzer()
        self.portfolio_file = "/media/dps/T7/stock_ai/data/portfolio.json"
        self.alert_file     = "/media/dps/T7/stock_ai/data/portfolio_alerts.json"
        self.portfolio      = self._load_portfolio()
        self.alert_history  = self._load_alerts()

    # ───────────────────────────────────────────────
    # 파일 입출력
    # ───────────────────────────────────────────────
    def _load_portfolio(self):
        if os.path.exists(self.portfolio_file):
            with open(self.portfolio_file, "r", encoding="utf-8") as f:
                return json.load(f)
        return {"_cash": 0, "_cash_usd": 0.0}

    def _save_portfolio(self):
        os.makedirs("/media/dps/T7/stock_ai/data", exist_ok=True)
        with open(self.portfolio_file, "w", encoding="utf-8") as f:
            json.dump(self.portfolio, f, ensure_ascii=False, indent=2)

    def _load_alerts(self):
        if os.path.exists(self.alert_file):
            with open(self.alert_file, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}

    def _save_alerts(self):
        with open(self.alert_file, "w", encoding="utf-8") as f:
            json.dump(self.alert_history, f, ensure_ascii=False, indent=2)

    def _can_alert(self, key, cooldown_hours=6):
        if key in self.alert_history:
            last = datetime.fromisoformat(self.alert_history[key])
            diff = (datetime.now() - last).total_seconds() / 3600
            if diff < cooldown_hours:
                return False
        self.alert_history[key] = datetime.now().isoformat()
        self._save_alerts()
        return True

    # ───────────────────────────────────────────────
    # 예수금 관리
    # ───────────────────────────────────────────────
    def get_cash(self):
        """예수금 조회"""
        return {
            "KRW": self.portfolio.get("_cash", 0),
            "USD": self.portfolio.get("_cash_usd", 0.0)
        }

    def set_cash(self, krw=None, usd=None):
        """예수금 수동 설정"""
        if krw is not None:
            self.portfolio["_cash"] = float(krw)
        if usd is not None:
            self.portfolio["_cash_usd"] = float(usd)
        self._save_portfolio()

    def _add_cash(self, market, amount):
        """예수금 증가 (매도 시)"""
        if market == "KR":
            self.portfolio["_cash"] = self.portfolio.get("_cash", 0) + amount
        else:
            self.portfolio["_cash_usd"] = self.portfolio.get("_cash_usd", 0.0) + amount
        self._save_portfolio()

    def _deduct_cash(self, market, amount):
        """예수금 차감 (매수 시) — 잔액 부족 시 False 반환"""
        if market == "KR":
            current = self.portfolio.get("_cash", 0)
            if current < amount:
                return False
            self.portfolio["_cash"] = current - amount
        else:
            current = self.portfolio.get("_cash_usd", 0.0)
            if current < amount:
                return False
            self.portfolio["_cash_usd"] = current - amount
        self._save_portfolio()
        return True

    # ───────────────────────────────────────────────
    # 환율 조회
    # ───────────────────────────────────────────────
    def _get_exchange_rate(self):
        try:
            import yfinance as yf
            fx = yf.Ticker("USDKRW=X").history(period="1d").dropna()
            if not fx.empty:
                return float(fx['Close'].iloc[-1])
        except:
            pass
        return 1400.0

    # ───────────────────────────────────────────────
    # 총 자산 계산
    # ───────────────────────────────────────────────
    def get_total_asset(self):
        """
        총 자산 = 예수금(KRW) + 예수금(USD×환율) + 보유종목 평가금액(KRW 환산)
        """
        exchange_rate = self._get_exchange_rate()
        cash_krw      = self.portfolio.get("_cash", 0)
        cash_usd      = self.portfolio.get("_cash_usd", 0.0)
        cash_usd_krw  = cash_usd * exchange_rate

        total_invested = 0
        total_current  = 0

        for ticker, stock in self.portfolio.items():
            if ticker.startswith("_"):
                continue
            buy_price = stock['buy_price']
            quantity  = stock['quantity']
            market    = stock['market']
            invested  = buy_price * quantity

            current_price, _ = self.get_current_price(ticker, market)
            current_val      = (current_price * quantity) if current_price else invested

            if market == "US":
                invested    *= exchange_rate
                current_val *= exchange_rate

            total_invested += invested
            total_current  += current_val
            time.sleep(0.1)

        stock_profit     = total_current - total_invested
        stock_profit_pct = (stock_profit / total_invested * 100) if total_invested > 0 else 0
        total_krw        = cash_krw + cash_usd_krw + total_current

        return {
            "total_krw":        total_krw,
            "cash_krw":         cash_krw,
            "cash_usd":         cash_usd,
            "cash_usd_krw":     cash_usd_krw,
            "stock_value_krw":  total_current,
            "total_invested":   total_invested,
            "stock_profit":     stock_profit,
            "stock_profit_pct": stock_profit_pct,
            "exchange_rate":    exchange_rate,
        }

    def get_portfolio_ratio(self, asset=None):
        """현재 포트폴리오 비중 계산"""
        if asset is None:
            asset = self.get_total_asset()
        total = asset['total_krw']
        if total <= 0:
            return None

        short_val    = 0
        longterm_val = 0

        for ticker, stock in self.portfolio.items():
            if ticker.startswith("_"):
                continue
            current_price, _ = self.get_current_price(ticker, stock['market'])
            if not current_price:
                current_price = stock['buy_price']
            val = current_price * stock['quantity']
            if stock['market'] == "US":
                val *= asset['exchange_rate']

            if stock.get('hold_type') == '단기':
                short_val += val
            else:
                longterm_val += val

        return {
            "total_krw":       total,
            "cash_ratio":      (asset['cash_krw'] + asset['cash_usd_krw']) / total * 100,
            "short_ratio":     short_val / total * 100,
            "longterm_ratio":  longterm_val / total * 100,
            "exchange_rate":   asset['exchange_rate'],
        }

    # ───────────────────────────────────────────────
    # 종목 추가 (매수)
    # ───────────────────────────────────────────────
    def add_stock(self, name, ticker, buy_price, quantity, market="KR",
                  hold_type="장기", target1=None, target2=None,
                  stop_loss=None, exit_target=None, deduct_cash=False):
        """종목 추가. deduct_cash=True 면 예수금 자동 차감"""
        buy_price = float(str(buy_price).replace(',', ''))
        quantity  = int(quantity)
        total     = buy_price * quantity

        if deduct_cash:
            ok = self._deduct_cash(market, total)
            if not ok:
                cash = self.get_cash()
                avail = cash['KRW'] if market == "KR" else cash['USD']
                currency = "₩" if market == "KR" else "$"
                return False, f"예수금 부족 (보유: {currency}{avail:,.0f} / 필요: {currency}{total:,.0f})"

        # 기존 종목이면 평균단가 계산
        if ticker in self.portfolio and not ticker.startswith("_"):
            existing  = self.portfolio[ticker]
            old_qty   = existing['quantity']
            old_price = existing['buy_price']
            new_qty   = old_qty + quantity
            avg_price = (old_price * old_qty + buy_price * quantity) / new_qty
            self.portfolio[ticker]['buy_price'] = round(avg_price, 4)
            self.portfolio[ticker]['quantity']  = new_qty
        else:
            self.portfolio[ticker] = {
                "name":        name,
                "ticker":      ticker,
                "buy_price":   buy_price,
                "quantity":    quantity,
                "market":      market,
                "hold_type":   hold_type,
                "target1":     target1,
                "target2":     target2,
                "stop_loss":   stop_loss,
                "exit_target": exit_target,
                "buy_date":    datetime.now().strftime("%Y-%m-%d"),
                "memo":        ""
            }

        self._save_portfolio()
        currency = "$" if market == "US" else "₩"
        print(f"✅ {name} 매수: {currency}{buy_price:,} × {quantity}주 = {currency}{total:,.0f}")
        return True, f"✅ 매수 완료"

    # ───────────────────────────────────────────────
    # 종목 제거 (매도)
    # ───────────────────────────────────────────────
    def remove_stock(self, ticker, sell_price, quantity=None):
        """
        종목 매도. quantity=None 이면 전량 매도.
        예수금 자동 증가.
        반환: (성공여부, 메시지, 수익률)
        """
        if ticker not in self.portfolio:
            return False, f"{ticker} 포트폴리오에 없음", 0

        stock     = self.portfolio[ticker]
        name      = stock['name']
        buy_price = stock['buy_price']
        held_qty  = stock['quantity']
        market    = stock['market']
        sell_price = float(str(sell_price).replace(',', ''))

        # 수량 결정
        if quantity is None or quantity >= held_qty:
            sell_qty = held_qty
            full_sell = True
        else:
            sell_qty  = int(quantity)
            full_sell = False

        total_sell  = sell_price * sell_qty
        profit_pct  = ((sell_price - buy_price) / buy_price) * 100
        profit_amt  = (sell_price - buy_price) * sell_qty
        currency    = "$" if market == "US" else "₩"

        # 예수금 증가
        self._add_cash(market, total_sell)

        if full_sell:
            del self.portfolio[ticker]
        else:
            self.portfolio[ticker]['quantity'] -= sell_qty

        self._save_portfolio()

        msg = (
            f"✅ {name} {'전량' if full_sell else f'{sell_qty}주'} 매도\n"
            f"매도가: {currency}{sell_price:,}\n"
            f"수익률: {profit_pct:+.2f}%\n"
            f"손익: {currency}{profit_amt:+,.0f}"
        )
        return True, msg, profit_pct

    # ───────────────────────────────────────────────
    # 현재가 조회
    # ───────────────────────────────────────────────
    def get_current_price(self, ticker, market):
        try:
            if market == "KR":
                data = self.kis.get_kr_price(ticker)
                if data:
                    return data['price'], data['change_pct']
            else:
                for excd in ["NAS", "NYS", "AMS"]:
                    data = self.kis.get_us_price(ticker, excd)
                    if data and data['price'] > 0:
                        return data['price'], data['change_pct']
        except:
            pass
        return None, None

    # ───────────────────────────────────────────────
    # 포트폴리오 현황
    # ───────────────────────────────────────────────
    def get_portfolio_status(self):
        results        = []
        total_invested = 0
        total_current  = 0

        for ticker, stock in self.portfolio.items():
            if ticker.startswith("_"):
                continue
            current_price, change_pct = self.get_current_price(ticker, stock['market'])
            buy_price = stock['buy_price']
            quantity  = stock['quantity']
            invested  = buy_price * quantity

            if current_price:
                current_val = current_price * quantity
                profit      = current_val - invested
                profit_pct  = ((current_price - buy_price) / buy_price) * 100
            else:
                current_val = invested
                profit      = 0
                profit_pct  = 0

            total_invested += invested
            total_current  += current_val

            results.append({
                "name":          stock['name'],
                "ticker":        ticker,
                "market":        stock['market'],
                "hold_type":     stock.get('hold_type', '장기'),
                "buy_price":     buy_price,
                "current_price": current_price,
                "quantity":      quantity,
                "invested":      invested,
                "current_val":   current_val,
                "profit":        profit,
                "profit_pct":    profit_pct,
                "change_pct":    change_pct or 0,
                "target1":       stock.get('target1'),
                "target2":       stock.get('target2'),
                "stop_loss":     stock.get('stop_loss'),
                "exit_target":   stock.get('exit_target'),
            })
            time.sleep(0.2)

        results.sort(key=lambda x: x['profit_pct'], reverse=True)
        total_profit     = total_current - total_invested
        total_profit_pct = ((total_profit / total_invested) * 100) if total_invested > 0 else 0

        return results, total_invested, total_current, total_profit, total_profit_pct

    # ───────────────────────────────────────────────
    # 가격 알림 (목표가/손절가 근접 + 도달)
    # ───────────────────────────────────────────────
    def check_price_alerts(self):
        alerts = []
        for ticker, stock in self.portfolio.items():
            if ticker.startswith("_"):
                continue
            current_price, _ = self.get_current_price(ticker, stock['market'])
            if not current_price:
                continue

            buy_price  = stock['buy_price']
            profit_pct = ((current_price - buy_price) / buy_price) * 100
            name       = stock['name']
            currency   = "$" if stock['market'] == "US" else "₩"

            # 1차 목표가 도달
            if stock.get('target1') and current_price >= stock['target1']:
                key = f"{ticker}_target1"
                if self._can_alert(key, cooldown_hours=24):
                    alerts.append({
                        "type": "🎯 1차 목표가 도달", "name": name, "ticker": ticker,
                        "profit": profit_pct, "price": current_price, "currency": currency,
                        "action": "30% 익절 고려", "urgency": "high"
                    })
            # 1차 목표가 90% 근접
            elif stock.get('target1') and current_price / stock['target1'] >= 0.90:
                key = f"{ticker}_target1_near"
                if self._can_alert(key, cooldown_hours=12):
                    alerts.append({
                        "type": "🔔 1차 목표가 근접", "name": name, "ticker": ticker,
                        "profit": profit_pct, "price": current_price, "currency": currency,
                        "action": f"목표가 {currency}{stock['target1']:,} 90% 도달 — 익절 준비",
                        "urgency": "medium"
                    })

            # 2차 목표가 도달
            if stock.get('target2') and current_price >= stock['target2']:
                key = f"{ticker}_target2"
                if self._can_alert(key, cooldown_hours=24):
                    alerts.append({
                        "type": "🎯🎯 2차 목표가 도달", "name": name, "ticker": ticker,
                        "profit": profit_pct, "price": current_price, "currency": currency,
                        "action": "나머지 전량 익절 고려", "urgency": "high"
                    })

            # 탈출가 도달
            if stock.get('exit_target') and current_price >= stock['exit_target']:
                key = f"{ticker}_exit"
                if self._can_alert(key, cooldown_hours=6):
                    alerts.append({
                        "type": "📤 반등 손절 타이밍", "name": name, "ticker": ticker,
                        "profit": profit_pct, "price": current_price, "currency": currency,
                        "action": "지금 손절 탈출하세요!", "urgency": "urgent"
                    })
            # 탈출가 90% 근접
            elif stock.get('exit_target') and current_price / stock['exit_target'] >= 0.90:
                key = f"{ticker}_exit_near"
                if self._can_alert(key, cooldown_hours=6):
                    alerts.append({
                        "type": "⚠️ 탈출 가격 근접", "name": name, "ticker": ticker,
                        "profit": profit_pct, "price": current_price, "currency": currency,
                        "action": f"탈출가 {currency}{stock['exit_target']:,} 근접 — 손절 준비",
                        "urgency": "high"
                    })

            # 손절선 도달
            if stock.get('stop_loss') and current_price <= stock['stop_loss']:
                key = f"{ticker}_stoploss"
                if self._can_alert(key, cooldown_hours=4):
                    alerts.append({
                        "type": "🛑 손절선 도달", "name": name, "ticker": ticker,
                        "profit": profit_pct, "price": current_price, "currency": currency,
                        "action": "즉시 손절하세요!", "urgency": "urgent"
                    })
            # 손절선 10% 근접
            elif stock.get('stop_loss') and current_price / stock['stop_loss'] <= 1.10:
                key = f"{ticker}_stoploss_near"
                if self._can_alert(key, cooldown_hours=4):
                    alerts.append({
                        "type": "⚠️ 손절선 근접 경고", "name": name, "ticker": ticker,
                        "profit": profit_pct, "price": current_price, "currency": currency,
                        "action": f"손절선 {currency}{stock['stop_loss']:,} 10% 이내 — 대응 준비",
                        "urgency": "high"
                    })

            time.sleep(0.2)
        return alerts

    # ───────────────────────────────────────────────
    # AI 진단
    # ───────────────────────────────────────────────
    def ai_portfolio_diagnosis(self, news_list):
        holdings = []
        for ticker, stock in self.portfolio.items():
            if ticker.startswith("_"):
                continue
            current_price, _ = self.get_current_price(ticker, stock['market'])
            profit_pct = 0
            if current_price:
                profit_pct = ((current_price - stock['buy_price']) / stock['buy_price']) * 100
            holdings.append({
                "name":       stock['name'],
                "ticker":     ticker,
                "hold_type":  stock.get('hold_type', '장기'),
                "profit_pct": round(profit_pct, 2),
            })
            time.sleep(0.2)

        news_text     = "\n".join([f"{i+1}. [{n['source']}] {n['title']}" for i, n in enumerate(news_list[:10])])
        holdings_text = "\n".join([f"- {h['name']} ({h['ticker']}): {h['profit_pct']:+.1f}% [{h['hold_type']}]" for h in holdings])

        from anthropic import Anthropic
        client = Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))

        prompt = f"""포트폴리오 매니저로서 보유 종목을 진단해주세요.
마크다운(##, **, ---) 금지. 이모지와 줄바꿈만 사용. 각 종목 3줄 이내.

=== 오늘 주요 뉴스 ===
{news_text}

=== 보유 종목 ===
{holdings_text}

형식:
[종목명] 상태: ✅순항/⚠️주의/🚨위험
이유: (한 줄)
판단: 계속보유/익절고려/손절고려

마지막에 총평 한 줄."""

        try:
            response = client.messages.create(
                model="claude-sonnet-4-6", max_tokens=600,
                messages=[{"role": "user", "content": prompt}]
            )
            return response.content[0].text
        except Exception as e:
            print(f"❌ AI 진단 실패: {e}")
            return None

    def check_news_impact(self, news_list):
        holding_names = [s['name'] for s in self.portfolio.values() if not isinstance(s, (int, float))]
        news_text     = "\n".join([f"{i+1}. [{n['source']}] {n['title']}" for i, n in enumerate(news_list[:15])])

        from anthropic import Anthropic
        client = Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))

        prompt = f"""뉴스가 보유 종목에 미치는 영향을 분석해주세요.
마크다운 금지. 이모지와 줄바꿈만 사용.

=== 오늘 뉴스 ===
{news_text}

=== 보유 종목 ===
{', '.join(holding_names)}

영향 있는 종목만:
✅ 긍정: 종목명 - 이유 한 줄
❌ 부정: 종목명 - 이유 한 줄

영향 없으면 "보유 종목 관련 특이 뉴스 없음"."""

        try:
            response = client.messages.create(
                model="claude-sonnet-4-6", max_tokens=300,
                messages=[{"role": "user", "content": prompt}]
            )
            return response.content[0].text
        except:
            return None

    # ───────────────────────────────────────────────
    # 메시지 빌드
    # ───────────────────────────────────────────────
    def build_portfolio_message(self):
        results, invested, current, profit, profit_pct = self.get_portfolio_status()
        if not results:
            return "📋 보유 종목 없음"

        # 총 자산 계산
        cash     = self.get_cash()
        exrate   = self._get_exchange_rate()
        cash_krw = cash['KRW'] + cash['USD'] * exrate
        total_asset = current + cash_krw

        profit_emoji = "📈" if profit >= 0 else "📉"
        msg  = f"📊 <b>포트폴리오 현황</b> {datetime.now().strftime('%m/%d %H:%M')}\n\n"
        msg += f"💰 총 자산: ₩{total_asset:,.0f}\n"
        msg += f"🏦 예수금: ₩{cash['KRW']:,.0f}"
        if cash['USD'] > 0:
            msg += f" + ${cash['USD']:,.2f}"
        msg += f"\n{profit_emoji} 주식 수익률: {profit_pct:+.2f}%\n"
        msg += "━━━━━━━━━━━━━━━━━━━\n"
        msg += "🇺🇸 <b>미국 주식</b>\n"

        for r in [r for r in results if r['market'] == "US"]:
            emoji = "📈" if r['profit_pct'] >= 0 else "📉"
            price = f"${r['current_price']:.2f}" if r['current_price'] else "조회중"
            t1    = f" | 목표: ${r['target1']}" if r.get('target1') else ""
            sl    = f" | 손절: ${r['stop_loss']}" if r.get('stop_loss') else ""
            msg  += f"{emoji} {r['name']}: {price} ({r['profit_pct']:+.1f}%){t1}{sl}\n"

        msg += "\n🇰🇷 <b>한국 주식</b>\n"
        for r in [r for r in results if r['market'] == "KR"]:
            emoji = "📈" if r['profit_pct'] >= 0 else "📉"
            price = f"{r['current_price']:,}원" if r['current_price'] else "조회중"
            if r.get('exit_target'):
                extra = f" | 탈출: {r['exit_target']:,}"
            elif r.get('target1'):
                extra = f" | 목표: {r['target1']:,}"
            else:
                extra = ""
            if r.get('stop_loss'):
                extra += f" | 손절: {r['stop_loss']:,}"
            msg += f"{emoji} {r['name']}: {price} ({r['profit_pct']:+.1f}%){extra}\n"

        msg += f"\n⏰ {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        return msg

    def build_alert_messages(self, alerts):
        messages = []
        for a in alerts:
            urgency_emoji = {"urgent": "🚨", "high": "⚡", "medium": "🔔"}.get(a['urgency'], "🔔")
            msg = f"""{urgency_emoji} <b>{a['type']}</b>
{a['name']} ({a['ticker']})

💰 현재가: {a['currency']}{a['price']:,}
📊 수익률: {a['profit']:+.2f}%
💡 {a['action']}

⏰ {datetime.now().strftime('%H:%M:%S')}"""
            messages.append(msg)
        return messages


if __name__ == "__main__":
    pf = Portfolio()
    print("총 자산 계산 중...")
    asset = pf.get_total_asset()
    print(f"총 자산: ₩{asset['total_krw']:,.0f}")
    print(f"예수금(KRW): ₩{asset['cash_krw']:,.0f}")
    print(f"예수금(USD): ${asset['cash_usd']:,.2f}")
    print(f"주식 평가액: ₩{asset['stock_value_krw']:,.0f}")
    print(f"환율: {asset['exchange_rate']:,.0f}")
