import os
import sys
import json
import time
from datetime import datetime, timedelta, date
from dotenv import load_dotenv

sys.path.insert(0, '/home/dps/stock_ai')
load_dotenv('/home/dps/stock_ai/.env')

CALENDAR_FILE = "/home/dps/stock_ai/data/event_calendar.json"


class EventCalendar:
    """
    이벤트 캘린더 모듈
    - FOMC/CPI: 매월 1일 AI 자동 조회
    - 한국 공휴일: workalendar 자동 계산
    - 네 마녀의 날 / 옵션만기 / 파생만기: 코드 자동 계산
    - 어닝 시즌 감지
    - 보유 종목 실적 발표일 자동 조회
    """

    def __init__(self):
        self.data = self._load()

    def _load(self):
        if os.path.exists(CALENDAR_FILE):
            with open(CALENDAR_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        default = {"fomc": [], "cpi": [], "updated_at": None}
        self._save(default)
        return default

    def _save(self, data=None):
        os.makedirs(os.path.dirname(CALENDAR_FILE), exist_ok=True)
        if data is None:
            data = self.data
        with open(CALENDAR_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    # ── 자동 계산 (코드 기반) ──────────────────────

    def _get_nth_weekday(self, year, month, weekday, n):
        """
        특정 월의 n번째 요일 반환
        weekday: 0=월, 4=금, 3=목
        """
        d     = date(year, month, 1)
        count = 0
        while True:
            if d.weekday() == weekday:
                count += 1
                if count == n:
                    return d
            d += timedelta(days=1)

    def get_quad_witching_days(self, year):
        """네 마녀의 날 (3/6/9/12월 세 번째 금요일)"""
        days = []
        for month in [3, 6, 9, 12]:
            d = self._get_nth_weekday(year, month, 4, 3)  # 세 번째 금요일
            days.append(str(d))
        return days

    def get_monthly_option_expiry(self, year, month):
        """미국 월간 옵션 만기 (매월 세 번째 금요일)"""
        return str(self._get_nth_weekday(year, month, 4, 3))

    def get_kr_derivative_expiry(self, year, month):
        """한국 파생상품 만기 (매월 두 번째 목요일)"""
        return str(self._get_nth_weekday(year, month, 3, 2))

    def get_kr_holidays(self, year):
        """한국 공휴일 (workalendar)"""
        try:
            from workalendar.asia import SouthKorea
            cal      = SouthKorea()
            holidays = cal.holidays(year)
            return [str(h[0]) for h in holidays]
        except Exception as e:
            print(f"  ⚠️ workalendar 실패: {e}")
            # 폴백: 주요 공휴일 하드코딩
            return [
                f"{year}-01-01",  # 신정
                f"{year}-03-01",  # 삼일절
                f"{year}-05-05",  # 어린이날
                f"{year}-06-06",  # 현충일
                f"{year}-08-15",  # 광복절
                f"{year}-10-03",  # 개천절
                f"{year}-10-09",  # 한글날
                f"{year}-12-25",  # 크리스마스
            ]

    def is_earning_season(self):
        """어닝 시즌 여부 (1/4/7/10월 10~31일)"""
        now   = datetime.now()
        month = now.month
        day   = now.day
        return month in [1, 4, 7, 10] and day >= 10

    # ── FOMC/CPI AI 자동 조회 ─────────────────────

    async def update_fomc_cpi(self):
        """매월 1일 AI로 FOMC/CPI 일정 조회"""
        from anthropic import Anthropic
        import re, json as _json

        print(f"[{datetime.now().strftime('%H:%M')}] 📅 FOMC/CPI 일정 자동 업데이트")

        year  = datetime.now().year
        month = datetime.now().month

        client = Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))
        prompt = f"""{year}년 {month}월부터 3개월간의 FOMC 회의 날짜와 미국 CPI 발표 날짜를 알려주세요.

JSON으로만:
{{
  "fomc": ["YYYY-MM-DD", "YYYY-MM-DD"],
  "cpi":  ["YYYY-MM-DD", "YYYY-MM-DD"]
}}"""

        try:
            res  = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=300,
                messages=[{"role": "user", "content": prompt}]
            )
            text = re.sub(r'```json|```', '', res.content[0].text.strip()).strip()
            m    = re.search(r'\{.*\}', text, re.DOTALL)
            if m:
                result = _json.loads(m.group())
                # 기존 데이터와 병합 (중복 제거)
                existing_fomc = set(self.data.get("fomc", []))
                existing_cpi  = set(self.data.get("cpi", []))
                existing_fomc.update(result.get("fomc", []))
                existing_cpi.update(result.get("cpi", []))
                self.data["fomc"]       = sorted(list(existing_fomc))
                self.data["cpi"]        = sorted(list(existing_cpi))
                self.data["updated_at"] = datetime.now().isoformat()
                self._save()
                print(f"  ✅ FOMC {len(self.data['fomc'])}개 / CPI {len(self.data['cpi'])}개 저장")
                return True
        except Exception as e:
            print(f"  ❌ FOMC/CPI 업데이트 실패: {e}")
        return False

    # ── 오늘/내일 이벤트 체크 ─────────────────────

    def get_today_events(self):
        """오늘 이벤트 목록"""
        return self._get_events_for_date(datetime.now().strftime("%Y-%m-%d"))

    def get_tomorrow_events(self):
        """내일 이벤트 목록"""
        return self._get_events_for_date(
            (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        )

    def _get_events_for_date(self, date_str):
        """특정 날짜의 이벤트 목록"""
        events = []
        year   = int(date_str[:4])
        month  = int(date_str[5:7])

        # FOMC
        if date_str in self.data.get("fomc", []):
            events.append({
                "type":     "FOMC",
                "date":     date_str,
                "emoji":    "🏦",
                "severity": "high",
                "action":   "장전 신규 진입 금지. 결과 확인 후 진입",
                "trade_block": True,
            })

        # CPI
        if date_str in self.data.get("cpi", []):
            events.append({
                "type":     "CPI",
                "date":     date_str,
                "emoji":    "📊",
                "severity": "high",
                "action":   "변동성 급등 주의. 포지션 축소 권고",
                "trade_block": False,
            })

        # 네 마녀의 날
        quad_days = self.get_quad_witching_days(year)
        if date_str in quad_days:
            events.append({
                "type":     "네마녀의날",
                "date":     date_str,
                "emoji":    "🧙",
                "severity": "high",
                "action":   "변동성 극대화. 신규 진입 자제",
                "trade_block": False,
            })

        # 미국 월간 옵션 만기
        elif self.get_monthly_option_expiry(year, month) == date_str:
            events.append({
                "type":     "미국옵션만기",
                "date":     date_str,
                "emoji":    "⚠️",
                "severity": "medium",
                "action":   "변동성 주의",
                "trade_block": False,
            })

        # 한국 파생 만기
        kr_expiry = self.get_kr_derivative_expiry(year, month)
        if date_str == kr_expiry:
            events.append({
                "type":     "한국파생만기",
                "date":     date_str,
                "emoji":    "🇰🇷",
                "severity": "medium",
                "action":   "외국인 프로그램 매매 집중. 14:00 이후 변동성 주의",
                "trade_block": False,
            })

        # 한국 파생 만기 전날
        kr_expiry_prev = (datetime.strptime(kr_expiry, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
        if date_str == kr_expiry_prev:
            events.append({
                "type":     "한국파생만기전날",
                "date":     date_str,
                "emoji":    "📢",
                "severity": "low",
                "action":   f"내일 한국 파생 만기일. 오후 변동성 대비",
                "trade_block": False,
            })

        # 한국 공휴일
        kr_holidays = self.get_kr_holidays(year)
        if date_str in kr_holidays:
            events.append({
                "type":     "한국공휴일",
                "date":     date_str,
                "emoji":    "🎌",
                "severity": "info",
                "action":   "한국 장 휴장",
                "trade_block": True,
            })

        # 어닝 시즌
        if self.is_earning_season():
            events.append({
                "type":     "어닝시즌",
                "date":     date_str,
                "emoji":    "📈",
                "severity": "low",
                "action":   "실적 발표 시즌. 개별 종목 변동성 주의",
                "trade_block": False,
            })

        return events

    def is_trade_blocked_today(self):
        """오늘 매매 금지 여부"""
        events = self.get_today_events()
        return any(e.get("trade_block") for e in events)

    # ── 보유 종목 실적 발표 조회 ──────────────────

    def get_earnings_dates(self, portfolio):
        """보유 종목 실적 발표일 조회 (yfinance)"""
        import yfinance as yf
        upcoming = []
        today    = datetime.now().date()

        for ticker, stock in portfolio.items():
            if not isinstance(stock, dict):
                continue
            market = stock.get('market', 'KR')
            if market != 'US':
                continue  # 미국 주식만 (한국은 yfinance 지원 불안정)

            try:
                info = yf.Ticker(ticker).calendar
                if info is not None and not info.empty:
                    earn_date = info.iloc[0].get('Earnings Date')
                    if earn_date:
                        earn_date = earn_date.date() if hasattr(earn_date, 'date') else earn_date
                        days_left = (earn_date - today).days
                        if 0 <= days_left <= 10:
                            upcoming.append({
                                "ticker":    ticker,
                                "name":      stock.get('name', ticker),
                                "date":      str(earn_date),
                                "days_left": days_left,
                            })
                time.sleep(0.2)
            except:
                pass

        return sorted(upcoming, key=lambda x: x['days_left'])

    # ── 메시지 생성 ────────────────────────────────

    def build_today_alert(self, events):
        """오늘 이벤트 알림 메시지"""
        if not events:
            return None

        high_events = [e for e in events if e['severity'] in ['high', 'medium']]
        if not high_events:
            return None

        msg  = f"📅 <b>오늘의 주요 이벤트</b>\n\n"
        for e in events:
            if e['severity'] == 'info':
                continue
            msg += f"{e['emoji']} <b>{e['type']}</b>\n"
            msg += f"   {e['action']}\n\n"

        msg += f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        return msg

    def build_tomorrow_preview(self, events):
        """내일 이벤트 예고 메시지"""
        if not events:
            return None

        high_events = [e for e in events if e['severity'] in ['high', 'medium']]
        if not high_events:
            return None

        msg  = f"📅 <b>내일 주요 이벤트 예고</b>\n\n"
        for e in high_events:
            msg += f"{e['emoji']} <b>{e['type']}</b>\n"
            msg += f"   {e['action']}\n\n"

        msg += f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        return msg

    def build_earnings_alert(self, upcoming):
        """실적 발표 임박 알림"""
        if not upcoming:
            return None

        msg  = f"📅 <b>실적 발표 임박</b>\n\n"
        for u in upcoming[:5]:
            days = u['days_left']
            if days == 0:
                timing = "오늘"
                emoji  = "🚨"
            elif days == 1:
                timing = "내일"
                emoji  = "⚠️"
            else:
                timing = f"{days}일 후"
                emoji  = "🔔"

            msg += f"{emoji} <b>{u['name']}</b> ({u['ticker']})\n"
            msg += f"   실적 발표: {u['date']} ({timing})\n"
            if days <= 1:
                msg += f"   💡 단기 종목은 실적 전 익절 고려\n"
            msg += "\n"

        msg += f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        return msg

    def build_calendar_summary(self):
        """이번 달 이벤트 요약"""
        year  = datetime.now().year
        month = datetime.now().month

        msg  = f"📅 <b>이번 달 주요 이벤트</b> {year}년 {month}월\n\n"

        # FOMC
        fomc_this_month = [d for d in self.data.get("fomc", []) if d.startswith(f"{year}-{month:02d}")]
        if fomc_this_month:
            msg += f"🏦 FOMC: {', '.join(fomc_this_month)}\n"

        # CPI
        cpi_this_month = [d for d in self.data.get("cpi", []) if d.startswith(f"{year}-{month:02d}")]
        if cpi_this_month:
            msg += f"📊 CPI: {', '.join(cpi_this_month)}\n"

        # 네 마녀의 날
        quad = self.get_quad_witching_days(year)
        quad_this = [d for d in quad if d.startswith(f"{year}-{month:02d}")]
        if quad_this:
            msg += f"🧙 네 마녀의 날: {', '.join(quad_this)}\n"

        # 옵션 만기
        option_expiry = self.get_monthly_option_expiry(year, month)
        msg += f"⚠️ 미국 옵션 만기: {option_expiry}\n"

        # 한국 파생 만기
        kr_expiry = self.get_kr_derivative_expiry(year, month)
        msg += f"🇰🇷 한국 파생 만기: {kr_expiry}\n"

        msg += f"\n⏰ {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        return msg
