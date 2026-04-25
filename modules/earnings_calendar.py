import sys
import os
import json
import time
import yfinance as yf
from datetime import datetime, timedelta
from dotenv import load_dotenv

sys.path.insert(0, '/home/dps/stock_ai')
load_dotenv('/home/dps/stock_ai/.env')

class EarningsCalendar:
    """
    실적 발표 캘린더
    보유 종목 실적 발표 전날 알림
    """
    def __init__(self):
        self.alert_file   = "/home/dps/stock_ai/data/earnings_alerts.json"
        self.alerts       = self._load_alerts()
        self.portfolio_file = "/home/dps/stock_ai/data/portfolio.json"

        # 기본 주요 종목
        self.base_watchlist = {
            "AAPL": "AAPL",
            "TSLA": "TSLA",
            "AMD":  "AMD",
            "META": "META",
            "AMZN": "AMZN",
            "PLTR": "PLTR",
            "NVDA": "NVDA",
            "MSFT": "MSFT",
            "GOOGL": "GOOGL",
        }

    @property
    def watchlist(self):
        """포트폴리오 + 기본 종목 자동 결합"""
        import json
        watchlist = dict(self.base_watchlist)
        try:
            if os.path.exists(self.portfolio_file):
                with open(self.portfolio_file, "r") as f:
                    portfolio = json.load(f)
                for ticker, stock in portfolio.items():
                    if stock.get("market") == "US":
                        watchlist[ticker] = ticker
        except:
            pass
        return watchlist

    def _load_alerts(self):
        if os.path.exists(self.alert_file):
            with open(self.alert_file, "r") as f:
                return json.load(f)
        return {}

    def _save_alerts(self):
        with open(self.alert_file, "w") as f:
            json.dump(self.alerts, f, ensure_ascii=False, indent=2)

    def _can_alert(self, key, cooldown_hours=20):
        if key in self.alerts:
            last = datetime.fromisoformat(self.alerts[key])
            diff = (datetime.now() - last).total_seconds() / 3600
            if diff < cooldown_hours:
                return False
        self.alerts[key] = datetime.now().isoformat()
        self._save_alerts()
        return True

    def get_kr_upcoming_earnings(self, days_ahead=14):
        """한국 종목 실적 발표 (DART API)"""
        import requests, os
        from dotenv import load_dotenv
        load_dotenv('/home/dps/stock_ai/.env')

        api_key  = os.getenv("DART_API_KEY")
        upcoming = []
        today    = datetime.now().date()

        # 포트폴리오에서 한국 주식 가져오기
        portfolio_file = "/home/dps/stock_ai/data/portfolio.json"
        kr_stocks = {}
        try:
            if os.path.exists(portfolio_file):
                with open(portfolio_file, "r") as f:
                    portfolio = json.load(f)
                for ticker, stock in portfolio.items():
                    if stock.get("market") == "KR":
                        kr_stocks[stock.get("name", ticker)] = ticker
        except:
            pass

        if not kr_stocks:
            return []

        for name, ticker in kr_stocks.items():
            try:
                # DART에서 실적 발표 공시 검색
                url    = "https://opendart.fss.or.kr/api/list.json"
                params = {
                    "crtfc_key": api_key,
                    "bgn_de":    today.strftime("%Y%m%d"),
                    "end_de":    (today + timedelta(days=days_ahead)).strftime("%Y%m%d"),
                    "pblntf_ty": "A",  # 정기공시
                    "page_count": 10,
                }
                res  = requests.get(url, params=params, timeout=10)
                data = res.json()
                if data.get("status") == "000":
                    for d in data.get("list", []):
                        report_nm = d.get("report_nm", "")
                        corp_name = d.get("corp_name", "")
                        if name in corp_name or ticker in d.get("stock_code", ""):
                            if any(kw in report_nm for kw in ["사업보고서", "분기보고서", "반기보고서", "잠정실적"]):
                                rcept_dt = d.get("rcept_dt", "")
                                if rcept_dt:
                                    report_date = datetime.strptime(rcept_dt, "%Y%m%d").date()
                                    days_until  = (report_date - today).days
                                    upcoming.append({
                                        "name":       name,
                                        "ticker":     ticker,
                                        "date":       report_date.strftime("%Y-%m-%d"),
                                        "days_until": days_until,
                                        "report":     report_nm,
                                        "market":     "KR"
                                    })
            except:
                pass
            time.sleep(0.2)

        upcoming.sort(key=lambda x: x["days_until"])
        return upcoming

    def get_upcoming_earnings(self, days_ahead=7):
        """향후 7일 실적 발표 종목"""
        upcoming = []
        today    = datetime.now().date()

        for name, ticker in self.watchlist.items():
            try:
                stock    = yf.Ticker(ticker)
                calendar = stock.calendar

                if calendar is None or calendar.empty:
                    continue

                # 실적 발표일
                if 'Earnings Date' in calendar.index:
                    earnings_date = calendar.loc['Earnings Date'].iloc[0]
                    if hasattr(earnings_date, 'date'):
                        earnings_date = earnings_date.date()

                    days_until = (earnings_date - today).days

                    if 0 <= days_until <= days_ahead:
                        # EPS 예측
                        eps_est = None
                        rev_est = None
                        try:
                            if 'EPS Estimate' in calendar.index:
                                eps_est = calendar.loc['EPS Estimate'].iloc[0]
                            if 'Revenue Estimate' in calendar.index:
                                rev_est = calendar.loc['Revenue Estimate'].iloc[0]
                        except:
                            pass

                        upcoming.append({
                            "name":         name,
                            "ticker":       ticker,
                            "date":         earnings_date.strftime("%Y-%m-%d"),
                            "days_until":   days_until,
                            "eps_estimate": round(float(eps_est), 2) if eps_est else None,
                            "rev_estimate": round(float(rev_est) / 1e9, 2) if rev_est else None,
                        })
                time.sleep(0.3)
            except:
                pass

        upcoming.sort(key=lambda x: x['days_until'])
        return upcoming

    def build_alert_message(self, upcoming):
        """실적 발표 알림 메시지"""
        if not upcoming:
            return None

        msg = f"📅 <b>실적 발표 예정</b> {datetime.now().strftime('%m/%d')}\n\n"

        today_list    = [u for u in upcoming if u['days_until'] == 0]
        tomorrow_list = [u for u in upcoming if u['days_until'] == 1]
        week_list     = [u for u in upcoming if u['days_until'] > 1]

        if today_list:
            msg += "🔴 <b>오늘 발표</b>\n"
            for u in today_list:
                eps = f"EPS 예상: ${u['eps_estimate']}" if u['eps_estimate'] else ""
                rev = f"매출 예상: ${u['rev_estimate']}B" if u['rev_estimate'] else ""
                msg += f"  • <b>{u['name']}</b> ({u['ticker']}) {eps} {rev}\n"
            msg += "\n"

        if tomorrow_list:
            msg += "🟡 <b>내일 발표</b>\n"
            for u in tomorrow_list:
                eps = f"EPS 예상: ${u['eps_estimate']}" if u['eps_estimate'] else ""
                rev = f"매출 예상: ${u['rev_estimate']}B" if u['rev_estimate'] else ""
                msg += f"  • <b>{u['name']}</b> ({u['ticker']}) {eps} {rev}\n"
            msg += "\n"

        if week_list:
            msg += "⚪ <b>이번 주 발표</b>\n"
            for u in week_list:
                msg += f"  • {u['name']} ({u['ticker']}) → {u['date']}\n"

        msg += f"\n💡 실적 발표 전날 변동성 주의\n"
        msg += f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        return msg

    def check_and_alert(self):
        """실적 발표 체크 + 알림 여부 판단"""
        upcoming = self.get_upcoming_earnings(days_ahead=7)
        alerts   = []

        for u in upcoming:
            # 내일 또는 오늘 발표 종목만 알림
            if u['days_until'] <= 1:
                key = f"earnings_{u['ticker']}_{u['date']}"
                if self._can_alert(key, cooldown_hours=20):
                    alerts.append(u)

        return upcoming, alerts

if __name__ == "__main__":
    print("=" * 50)
    print("📅 실적 발표 캘린더 테스트")
    print("=" * 50)
    ec      = EarningsCalendar()
    upcoming = ec.get_upcoming_earnings(days_ahead=14)
    print(f"\n향후 14일 실적 발표: {len(upcoming)}개")
    for u in upcoming:
        eps = f"EPS: ${u['eps_estimate']}" if u['eps_estimate'] else ""
        print(f"  D-{u['days_until']} {u['name']} ({u['ticker']}) {u['date']} {eps}")
    msg = ec.build_alert_message(upcoming)
    if msg:
        print(f"\n{msg}")
