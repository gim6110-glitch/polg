import os
import sys
import json
import time
import asyncio
from datetime import datetime, timedelta
from dotenv import load_dotenv

sys.path.insert(0, '/media/dps/T7/stock_ai')
load_dotenv('/media/dps/T7/stock_ai/.env')

GAMBLE_FILE = "/media/dps/T7/stock_ai/data/gamble_watchlist.json"


class GambleMonitor:
    """
    도박 watchlist 동적 관리
    - gamble_watchlist.json 파일 기반
    - 매주 토요일 AI 자동 검토 (탈락/유지/신규 발굴)
    - /gamble 명령어로 수동 관리
    - 총자산 5% 이하 고정
    """

    def __init__(self):
        self.watchlist = self._load()

    # ── 파일 관리 ──────────────────────────────────────

    def _load(self):
        if os.path.exists(GAMBLE_FILE):
            with open(GAMBLE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        # 최초 생성
        default = {"version": "1.0", "updated_at": datetime.now().strftime("%Y-%m-%d"), "stocks": {}}
        self._save(default)
        return default

    def _save(self, data=None):
        os.makedirs(os.path.dirname(GAMBLE_FILE), exist_ok=True)
        if data is None:
            data = self.watchlist
        data["updated_at"] = datetime.now().strftime("%Y-%m-%d")
        with open(GAMBLE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def get_stocks(self):
        return self.watchlist.get("stocks", {})

    # ── 수동 관리 ──────────────────────────────────────

    def add(self, ticker, name, theme, memo=""):
        ticker = ticker.upper()
        stocks = self.get_stocks()
        if ticker in stocks:
            return False, f"{ticker} 이미 존재"
        stocks[ticker] = {
            "name":          name,
            "theme":         theme,
            "memo":          memo,
            "added_at":      datetime.now().strftime("%Y-%m-%d"),
            "status":        "유지",
            "last_reviewed": datetime.now().strftime("%Y-%m-%d")
        }
        self._save()
        return True, f"✅ {name} ({ticker}) 추가 완료\n테마: {theme}\n메모: {memo}"

    def remove(self, ticker):
        ticker = ticker.upper()
        stocks = self.get_stocks()
        if ticker not in stocks:
            return False, f"{ticker} 목록에 없음"
        name = stocks[ticker]["name"]
        del stocks[ticker]
        self._save()
        return True, f"✅ {name} ({ticker}) 제거 완료"

    def build_list_message(self):
        stocks = self.get_stocks()
        if not stocks:
            return "📋 도박 watchlist 비어있음\n/gamble add TICKER 이름 테마 메모"

        msg  = f"🎰 <b>도박 Watchlist</b> ({len(stocks)}개)\n"
        msg += f"<i>총자산 5% 이하 고정 | 손절 없음 | 1~5년 홀딩</i>\n\n"

        # 테마별 그룹핑
        by_theme = {}
        for ticker, info in stocks.items():
            theme = info.get("theme", "기타")
            if theme not in by_theme:
                by_theme[theme] = []
            by_theme[theme].append((ticker, info))

        for theme, items in by_theme.items():
            msg += f"📌 <b>{theme}</b>\n"
            for ticker, info in items:
                status_emoji = {"유지": "✅", "관심 약화": "⚠️", "탈락": "❌"}.get(info.get("status", "유지"), "✅")
                memo = f" — {info['memo']}" if info.get("memo") else ""
                msg += f"  {status_emoji} {info['name']} ({ticker}){memo}\n"
            msg += "\n"

        msg += f"🔄 최근 검토: {self.watchlist.get('updated_at', '-')}\n"
        msg += f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        return msg

    # ── AI 자동 검토 (매주 토요일) ──────────────────────

    async def weekly_review(self):
        """매주 토 12:00 AI 전체 검토"""
        print(f"[{datetime.now().strftime('%H:%M')}] 🎰 도박 watchlist AI 검토 시작")
        stocks = self.get_stocks()
        if not stocks:
            return "도박 watchlist 비어있음"

        # 1. 각 종목 기술적 데이터 수집
        stock_data = {}
        for ticker, info in stocks.items():
            data = self._get_stock_data(ticker)
            if data:
                stock_data[ticker] = {**info, **data}
            time.sleep(0.3)

        # 2. 소셜/뉴스 데이터 수집
        social_text = await self._get_social_context(list(stocks.keys()))

        # 3. AI 종합 판단
        result = await self._ai_review(stock_data, social_text)

        # 4. 결과 반영
        msg = self._apply_review_result(result, stock_data)

        # 5. 신규 발굴
        new_candidates = await self._discover_new_candidates()
        if new_candidates:
            msg += f"\n\n🔍 <b>신규 후보 발굴</b>\n{new_candidates}"

        return msg

    def _get_stock_data(self, ticker):
        """yfinance로 기술적 데이터 수집"""
        try:
            import yfinance as yf
            hist = yf.Ticker(ticker).history(period="6mo").dropna()
            if len(hist) < 20:
                return None

            close  = hist['Close']
            volume = hist['Volume']

            current   = close.iloc[-1]
            high_52w  = close.max()
            low_52w   = close.min()
            avg_vol   = volume.mean()
            curr_vol  = volume.iloc[-1]

            # RSI
            delta = close.diff()
            gain  = delta.clip(lower=0).rolling(14).mean()
            loss  = (-delta.clip(upper=0)).rolling(14).mean()
            rs    = gain / loss
            rsi   = round((100 - (100 / (1 + rs))).iloc[-1], 1)

            # OBV 방향
            obv       = (volume * close.diff().apply(lambda x: 1 if x > 0 else -1)).cumsum()
            obv_trend = "상승" if obv.iloc[-1] > obv.iloc[-5] else "하락"

            # 6개월 수익률
            ret_6m = round(((current - close.iloc[0]) / close.iloc[0]) * 100, 1)

            # 52주 저점 근접도
            low_proximity = round(((current - low_52w) / low_52w) * 100, 1)

            return {
                "price":         round(current, 2),
                "rsi":           rsi,
                "obv_trend":     obv_trend,
                "ret_6m":        ret_6m,
                "low_proximity": low_proximity,
                "vol_ratio":     round(curr_vol / avg_vol, 1) if avg_vol > 0 else 1
            }
        except Exception as e:
            print(f"  ⚠️ {ticker} 데이터 수집 실패: {e}")
            return None

    async def _get_social_context(self, tickers):
        """Reddit/StockTwits 소셜 반응 수집"""
        social_text = ""
        try:
            import aiohttp
            for ticker in tickers[:5]:  # 상위 5개만
                try:
                    url = f"https://api.stocktwits.com/api/2/streams/symbol/{ticker}.json"
                    async with aiohttp.ClientSession() as session:
                        async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                            if resp.status == 200:
                                data      = await resp.json()
                                messages  = data.get("messages", [])[:5]
                                sentiment = [m.get("entities", {}).get("sentiment", {}).get("basic", "") for m in messages]
                                bull      = sentiment.count("Bullish")
                                bear      = sentiment.count("Bearish")
                                social_text += f"{ticker}: 강세 {bull}개 / 약세 {bear}개\n"
                except:
                    pass
        except:
            pass
        return social_text if social_text else "소셜 데이터 수집 실패"

    async def _ai_review(self, stock_data, social_text):
        """AI 종합 판단"""
        from anthropic import Anthropic
        import re

        client    = Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))
        data_text = ""
        for ticker, d in stock_data.items():
            data_text += (
                f"{ticker}({d.get('name','')}) 테마:{d.get('theme','')} "
                f"RSI:{d.get('rsi','?')} OBV:{d.get('obv_trend','?')} "
                f"6개월수익:{d.get('ret_6m','?')}% "
                f"저점근접:{d.get('low_proximity','?')}% "
                f"거래량:{d.get('vol_ratio','?')}배\n"
            )

        prompt = f"""도박 watchlist 주간 검토를 해주세요.
이 종목들은 1~5년 장기 보유 혁신기술 초기 투자입니다.
손절 없이 끝까지 홀딩하는 전략이므로 탈락 기준은 엄격하게 봐주세요.

=== 종목 데이터 ===
{data_text}

=== 소셜 반응 ===
{social_text}

각 종목 판단:
- 유지: 기술/모멘텀 살아있음
- 관심 약화: 모멘텀 줄어드는 중 (경고)
- 탈락: 기술 개발 멈춤, 경쟁사에 밀림, 테마 소멸

JSON으로만 답하세요:
{{
  "reviews": [
    {{
      "ticker": "티커",
      "status": "유지 또는 관심 약화 또는 탈락",
      "reason": "판단 이유 한줄",
      "momentum": "강함 또는 보통 또는 약함"
    }}
  ],
  "summary": "전체 한줄 요약"
}}"""

        try:
            res  = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=1000,
                messages=[{"role": "user", "content": prompt}]
            )
            text = re.sub(r'```json|```', '', res.content[0].text.strip()).strip()
            m    = re.search(r'\{.*\}', text, re.DOTALL)
            if m:
                return json.loads(m.group())
        except Exception as e:
            print(f"  ❌ AI 검토 실패: {e}")
        return None

    def _apply_review_result(self, result, stock_data):
        """AI 결과 반영 + 메시지 생성"""
        stocks  = self.get_stocks()
        removed = []
        weakened = []

        if result:
            for review in result.get("reviews", []):
                ticker = review.get("ticker", "").upper()
                status = review.get("status", "유지")
                reason = review.get("reason", "")

                if ticker in stocks:
                    stocks[ticker]["status"]        = status
                    stocks[ticker]["last_reviewed"]  = datetime.now().strftime("%Y-%m-%d")
                    stocks[ticker]["review_reason"]  = reason

                    if status == "탈락":
                        removed.append((ticker, stocks[ticker]["name"], reason))
                        del stocks[ticker]
                    elif status == "관심 약화":
                        weakened.append((ticker, stocks[ticker]["name"], reason))

        self._save()

        # 메시지 생성
        msg  = f"🎰 <b>도박 Watchlist 주간 검토</b> {datetime.now().strftime('%m/%d')}\n\n"

        if result:
            msg += f"📊 {result.get('summary', '')}\n\n"

        # 유지 종목
        maintained = [(t, i) for t, i in stocks.items() if i.get("status") == "유지"]
        if maintained:
            msg += f"✅ <b>유지</b> ({len(maintained)}개)\n"
            for ticker, info in maintained:
                data   = stock_data.get(ticker, {})
                msg   += f"  • {info['name']} ({ticker}) — RSI:{data.get('rsi','?')} 6개월:{data.get('ret_6m','?')}%\n"

        # 관심 약화
        if weakened:
            msg += f"\n⚠️ <b>관심 약화</b> ({len(weakened)}개)\n"
            for ticker, name, reason in weakened:
                msg += f"  • {name} ({ticker}) — {reason}\n"

        # 탈락
        if removed:
            msg += f"\n❌ <b>탈락 제거</b> ({len(removed)}개)\n"
            for ticker, name, reason in removed:
                msg += f"  • {name} ({ticker}) — {reason}\n"

        msg += f"\n⏰ {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        return msg

    async def _discover_new_candidates(self):
        """AI가 새 도박 후보 발굴"""
        from anthropic import Anthropic
        import re

        client = Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))
        existing = list(self.get_stocks().keys())

        prompt = f"""혁신기술 초기 투자 후보를 발굴해주세요.
조건: 1~5년 장기 보유, 시총 소형, 혁신기술 초기, 기관/대형사 관심 시작

현재 보유: {', '.join(existing)}
위 종목과 중복 제외

JSON으로만:
{{
  "candidates": [
    {{
      "ticker": "티커",
      "name": "회사명",
      "theme": "테마",
      "reason": "추천 이유 한줄"
    }}
  ]
}}"""

        try:
            res  = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=500,
                messages=[{"role": "user", "content": prompt}]
            )
            text = re.sub(r'```json|```', '', res.content[0].text.strip()).strip()
            m    = re.search(r'\{.*\}', text, re.DOTALL)
            if m:
                data       = json.loads(m.group())
                candidates = data.get("candidates", [])
                if candidates:
                    msg = ""
                    for c in candidates[:3]:
                        msg += f"  🆕 {c['name']} ({c['ticker']}) — {c['theme']}\n     {c['reason']}\n"
                    msg += "\n추가하려면: /gamble add TICKER 이름 테마"
                    return msg
        except Exception as e:
            print(f"  ❌ 신규 발굴 실패: {e}")
        return ""

    # ── 30분마다 스캔 ──────────────────────────────────

    async def scan_buy_timing(self):
        """30분마다 도박 종목 매수 타이밍 체크"""
        stocks  = self.get_stocks()
        signals = []

        for ticker, info in stocks.items():
            data = self._get_stock_data(ticker)
            if not data:
                continue

            score    = 0
            sig_list = []

            # 52주 저점 20% 이내
            if data.get("low_proximity", 100) <= 20:
                score   += 3
                sig_list.append(f"52주 저점 근접 ({data['low_proximity']}%)")

            # RSI 35 이하
            if data.get("rsi", 50) <= 35:
                score   += 3
                sig_list.append(f"RSI {data['rsi']} 과매도")

            # 거래량 2배
            if data.get("vol_ratio", 1) >= 2:
                score   += 3
                sig_list.append(f"거래량 {data['vol_ratio']}배 급증")

            # OBV 상승 전환
            if data.get("obv_trend") == "상승":
                score   += 2
                sig_list.append("OBV 상승 전환")

            if score >= 5:
                signals.append({
                    "ticker":  ticker,
                    "name":    info["name"],
                    "theme":   info["theme"],
                    "price":   data["price"],
                    "score":   score,
                    "signals": sig_list,
                    "rsi":     data.get("rsi"),
                })

        return signals

    def build_buy_timing_message(self, signals):
        """도박 매수 타이밍 알림"""
        if not signals:
            return None

        msg = f"🎰 <b>도박 매수 타이밍</b> {datetime.now().strftime('%m/%d %H:%M')}\n"
        msg += f"<i>소액만 (총자산 2% 이내) | 손절 없음 | 끝까지 홀딩</i>\n\n"

        for s in signals:
            stars     = "★" * min(s["score"] // 2, 5)
            sig_text  = "\n".join([f"  • {sg}" for sg in s["signals"]])
            msg += f"⭐ <b>{s['name']}</b> ({s['ticker']}) {stars}\n"
            msg += f"테마: {s['theme']}\n"
            msg += f"{sig_text}\n"
            msg += f"💰 현재가: ${s['price']:,.2f}\n"
            msg += f"━━━━━━━━━━━━━━━━━━━\n"

        msg += f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        return msg


# ── 텔레그램 명령어 핸들러 ──────────────────────────────

async def cmd_gamble(update, context):
    """
    /gamble — 목록 보기
    /gamble list — 목록 보기
    /gamble add TICKER 이름 테마 메모 — 추가
    /gamble remove TICKER — 제거
    """
    gm   = GambleMonitor()
    args = context.args if context.args else []

    if not args or args[0] == "list":
        msg = gm.build_list_message()
        from main import send
        await send(msg)
        return

    if args[0] == "add":
        if len(args) < 3:
            await update.message.reply_text(
                "사용법: /gamble add TICKER 이름 테마 메모\n"
                "예) /gamble add PLTR 팔란티어 AI분석 피터틸창업"
            )
            return
        ticker = args[1]
        name   = args[2]
        theme  = args[3] if len(args) > 3 else "혁신기술"
        memo   = " ".join(args[4:]) if len(args) > 4 else ""
        ok, msg = gm.add(ticker, name, theme, memo)
        await update.message.reply_text(msg)
        return

    if args[0] == "remove":
        if len(args) < 2:
            await update.message.reply_text("사용법: /gamble remove TICKER")
            return
        ok, msg = gm.remove(args[1])
        await update.message.reply_text(msg)
        return

    await update.message.reply_text(
        "사용법:\n"
        "/gamble — 목록\n"
        "/gamble add TICKER 이름 테마 메모\n"
        "/gamble remove TICKER"
    )
