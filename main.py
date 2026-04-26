import os
import sys
import asyncio
import schedule
import time
import threading
from datetime import datetime, timedelta
from telegram import Bot, Update
from telegram.ext import Application, CommandHandler, ContextTypes
from dotenv import load_dotenv

sys.path.insert(0, '/home/dps/stock_ai')
from modules.news_collector import NewsCollector
from modules.price_collector import PriceCollector
from modules.market_indicators import MarketIndicators
from modules.technical_analyzer import TechnicalAnalyzer
from modules.watchlist_monitor import WatchlistMonitor
from modules.ai_analyzer import AIAnalyzer
from modules.market_regime import MarketRegime
from modules.bullish_signals import BullishSignals
from modules.realtime_monitor import RealtimeMonitor
from modules.supply_alert import run_supply_scan, get_supply_summary, SUPPLY_WATCH
from modules.portfolio import Portfolio
from modules.ai_learning import AILearning
from modules.dynamic_sectors import DynamicSectors
from modules.leverage_monitor import LeverageMonitor
from modules.premarket_scan import PremarketScan
from modules.dart_monitor import DartMonitor
from modules.longterm_monitor import LongtermMonitor
from modules.highlow_scanner import HighLowScanner
from modules.gamble_monitor import GambleMonitor, cmd_gamble
from modules.backtest import BacktestSystem, cmd_backtest
from modules.market_temperature import MarketTemperature
from modules.smart_recommender import SmartRecommender
from modules.shakeout_detector import ShakeoutDetector
from modules.trade_guard import TradeGuard
from modules.supply_demand import SupplyDemand
from modules.event_calendar import EventCalendar
from modules.fx_risk_manager import FxRiskManager

mt = MarketTemperature()
sr = SmartRecommender()
bt = BacktestSystem()
gm = GambleMonitor()
pm = PremarketScan()
lm = LeverageMonitor()
ds = DynamicSectors()
dm = DartMonitor()
ltm = LongtermMonitor()
hl = HighLowScanner()
al = AILearning()
sd_detector = ShakeoutDetector()
tg = TradeGuard()
pf = Portfolio()
ec = EventCalendar()
fx = FxRiskManager()

load_dotenv('/home/dps/stock_ai/.env')

monitor  = WatchlistMonitor()
analyzer = TechnicalAnalyzer()
ai       = AIAnalyzer()
regime   = MarketRegime()
bullish  = BullishSignals()

LONG_TERM_STOCKS = {
    "삼성전자":           "005930.KS",
    "SK하이닉스":         "000660.KS",
    "한화에어로스페이스":  "012450.KS",
    "현대차":             "005380.KS",
    "POSCO홀딩스":        "005490.KS",
    "LG에너지솔루션":     "373220.KS",
    "NVIDIA":             "NVDA",
    "Apple":              "AAPL",
    "Microsoft":          "MSFT",
    "TSMC":               "TSM",
    "Google":             "GOOGL",
    "META":               "META",
}

KR_SCAN_STOCKS = {
    "삼성전자":           "005930.KS",
    "SK하이닉스":         "000660.KS",
    "한화에어로스페이스":  "012450.KS",
    "현대차":             "005380.KS",
    "LG에너지솔루션":     "373220.KS",
    "카카오":             "035720.KS",
    "NAVER":              "035420.KS",
    "셀트리온":           "068270.KS",
    "기아":               "000270.KS",
    "삼성바이오로직스":   "207940.KS",
}

async def send(msg):
    try:
        bot     = Bot(token=os.getenv('TELEGRAM_BOT_TOKEN'))
        chat_id = os.getenv('TELEGRAM_CHAT_ID')
        max_len = 3500  # 여유있게 3500으로

        # ━━━ 구분선 기준으로 먼저 분할 시도
        def smart_split(text, limit):
            chunks = []
            while len(text) > limit:
                # 1순위: ━━━ 구분선에서 분할
                split_at = text.rfind('━━━', 0, limit)
                if split_at > limit * 0.5:
                    split_at = split_at + 19  # 구분선 포함
                else:
                    # 2순위: 줄바꿈에서 분할
                    split_at = text.rfind('\n', 0, limit)
                    if split_at == -1:
                        split_at = limit
                chunks.append(text[:split_at])
                text = text[split_at:].lstrip('\n')
            if text.strip():
                chunks.append(text)
            return chunks

        chunks = smart_split(msg, max_len)

        for i, chunk in enumerate(chunks):
            if not chunk.strip():
                continue
            header = f"({i+1}/{len(chunks)})\n" if len(chunks) > 1 else ""
            chunk  = header + chunk

            for attempt in range(3):
                try:
                    await bot.send_message(
                        chat_id=chat_id,
                        text=chunk,
                        parse_mode='HTML'
                    )
                    await asyncio.sleep(0.8)
                    break
                except Exception as e:
                    if "can't parse" in str(e).lower():
                        # HTML 파싱 오류시 일반 텍스트로 재시도
                        try:
                            await bot.send_message(
                                chat_id=chat_id,
                                text=chunk.replace('<b>', '').replace('</b>', '')
                                         .replace('<i>', '').replace('</i>', ''),
                            )
                            await asyncio.sleep(0.8)
                            break
                        except:
                            pass
                    if attempt < 2:
                        await asyncio.sleep(5)
                    else:
                        print(f"❌ 전송 실패: {e}")
    except Exception as e:
        print(f"❌ 전송 실패: {e}")

# ── 명령어 ──
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = """🤖 <b>주식 AI 에이전트 v4.0</b>

📊 <b>시장 분석</b>
/regime — 장세 + 전략 확인
/market — 시장 현황
/trend — 섹터 트렌드
/briefing — AI 브리핑

📈 <b>종목 분석</b>
/check 티커 — 즉시 분석
/analyze 종목명 — 시황+트렌드+AI 종합 분석
/scan — 전체 신호 스캔
/supply — 외국인/기관 수급
/leverage — 레버리지 ETF 현황
/premarket — 상한가 후보 즉시 스캔

💼 <b>포트폴리오</b>
/portfolio — 전체 현황
/buy 종목명 티커 매수가 수량
/sell 티커 매도가
/diagnosis — AI 진단
/news_impact — 뉴스 영향 분석
/accuracy — AI 정확도 리포트
/themes — 현재 임시 테마 현황
/add_sector 테마명 — 고정 섹터 승격

📋 <b>감시 목록</b>
/list — 감시 종목
/add 종목명 티커 기간
/remove 종목명
/gamble — 도박 watchlist

⚙️ <b>시스템</b>
/backtest — 모의 테스트 승률/수익률
/loss — 손실 한도 현황
/status — 시스템 상태"""
    await send(msg)

# ③ 30분마다 결과 체크 함수 추가
async def backtest_price_check():
    """30분마다 모의 테스트 결과 체크"""
    if is_weekend():
        return
    try:
        results = bt.update_prices()
        if results:
            msg = bt.build_result_alert(results)
            if msg:
                await send(msg)
    except Exception as e:
        print(f"  ❌ 백테스트 체크 실패: {e}")

async def cmd_regime(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📊 장세 분석 중...")
    regime.analyze_regime()
    await send(regime.get_status_text())

async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from modules.sector_db import SECTOR_DB, get_all_tickers
    r          = regime.current_regime
    em         = regime.get_regime_emoji()
    kr_tickers = get_all_tickers('KR')
    us_tickers = get_all_tickers('US')
    kr_sectors = len([s for s, d in SECTOR_DB.items() if d.get('market') == 'KR'])
    us_sectors = len([s for s, d in SECTOR_DB.items() if d.get('market') == 'US'])
    port_kr    = len([t for t, s in pf.portfolio.items() if s.get('market') == 'KR'])
    port_us    = len([t for t, s in pf.portfolio.items() if s.get('market') == 'US'])
    msg  = f"⚙️ <b>시스템 상태</b>\n\n"
    msg += f"🍓 라즈베리파이5: 정상\n"
    msg += f"🤖 AI: Claude Sonnet 4.6\n"
    msg += f"{em} 장세: {r.get('regime','?')}장\n\n"
    msg += f"📊 <b>섹터 DB</b>\n"
    msg += f"  🇰🇷 한국: {kr_sectors}개 섹터 / {len(kr_tickers)}개 종목\n"
    msg += f"  🇺🇸 미국: {us_sectors}개 섹터 / {len(us_tickers)}개 종목\n\n"
    msg += f"💼 <b>포트폴리오</b>\n"
    msg += f"  🇰🇷 한국: {port_kr}개\n"
    msg += f"  🇺🇸 미국: {port_us}개\n\n"
    msg += f"⚡ 실시간 모니터: 5분마다 감시 중\n"
    msg += f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    await send(msg)

async def cmd_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from modules.sector_db import SECTOR_DB
    msg  = "📋 <b>섹터 DB 감시 종목</b>\n\n"
    msg += "🇰🇷 <b>한국 섹터</b>\n"
    for sector_name, sector_data in SECTOR_DB.items():
        if sector_data.get('market') != 'KR':
            continue
        leaders = list(sector_data.get('대장주', {}).keys())
        msg += f"  [{sector_name}] {', '.join(leaders[:3])}\n"
    msg += "\n🇺🇸 <b>미국 섹터</b>\n"
    for sector_name, sector_data in SECTOR_DB.items():
        if sector_data.get('market') != 'US':
            continue
        leaders = list(sector_data.get('대장주', {}).keys())
        msg += f"  [{sector_name}] {', '.join(leaders[:3])}\n"
    msg += "\n💼 <b>포트폴리오</b>\n"
    port_kr = {t: s for t, s in pf.portfolio.items() if s.get('market') == 'KR'}
    port_us = {t: s for t, s in pf.portfolio.items() if s.get('market') == 'US'}
    if port_kr:
        msg += "🇰🇷 한국\n"
        for ticker, stock in port_kr.items():
            msg += f"  • {stock.get('name', ticker)} ({ticker})\n"
    if port_us:
        msg += "🇺🇸 미국\n"
        for ticker, stock in port_us.items():
            msg += f"  • {stock.get('name', ticker)} ({ticker})\n"
    await send(msg)


async def cmd_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("사용법: /add 종목명 티커 기간\n예) /add 에코프로 086520.KS 중기")
        return
    name   = args[0]
    ticker = args[1]
    period = args[2] if len(args) > 2 else "중기"
    if period not in ["단기", "중기", "장기"]:
        period = "중기"
    monitor.add_stock(name, ticker, period)
    await update.message.reply_text(f"✅ {name} ({ticker}) → {period} 추가")

async def cmd_remove(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("사용법: /remove 종목명")
        return
    name = context.args[0]
    if monitor.remove_stock(name):
        await update.message.reply_text(f"✅ {name} 제거")
    else:
        await update.message.reply_text(f"❌ {name} 없음")

async def cmd_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("사용법: /check 티커")
        return
    ticker = context.args[0].upper()
    r      = regime.current_regime
    em     = regime.get_regime_emoji()
    await update.message.reply_text(f"🔍 {ticker} 분석 중...")
    from modules.kis_api import KISApi
    kis = KISApi()
    # 한국/미국 자동 판단
    is_kr = ticker.isdigit() or (len(ticker) == 6 and ticker[:6].isdigit())
    if is_kr:
        kis_data = kis.get_kr_price(ticker)
        if not kis_data:
            await update.message.reply_text(f"❌ {ticker} 데이터 없음")
            return
        # 기술적 지표는 yfinance로 보완
        yf_ticker = ticker + ".KS"
        data = analyzer.get_indicators(yf_ticker)
        if data:
            data['current_price'] = kis_data['price']
            data['change_pct']    = kis_data['change_pct']
            data['timestamp']     = kis_data['timestamp'] + " (KIS실시간)"
        else:
            # yfinance 실패 시 KIS 데이터만으로 표시
            data = {
                'current_price':    kis_data['price'],
                'change_pct':       kis_data['change_pct'],
                'rsi':              'N/A',
                'bb_position':      'N/A',
                'stop_loss':        round(kis_data['price'] * 0.93, 0),
                'stop_loss_pct':    -7.0,
                'volume_ratio':     1.0,
                'high_52w_proximity': 'N/A',
                'signals':          [],
                'timestamp':        kis_data['timestamp'] + " (KIS실시간)"
            }
    else:
        # 미국 주식
        us_data = None
        for excd in ["NAS", "NYS", "AMS"]:
            us_data = kis.get_us_price(ticker, excd)
            if us_data and us_data.get('price', 0) > 0:
                break
        if not us_data or us_data.get('price', 0) == 0:
            # 미국장 마감 중 → yfinance로 전날 종가 표시
            import yfinance as yf
            yf_data = yf.Ticker(ticker).history(period="2d").dropna()
            if not yf_data.empty:
                prev_price = round(yf_data['Close'].iloc[-1], 2)
                prev_change = round(((yf_data['Close'].iloc[-1] - yf_data['Close'].iloc[-2]) / yf_data['Close'].iloc[-2]) * 100, 2)
                us_data = {
                    'price':      prev_price,
                    'change_pct': prev_change,
                    'timestamp':  '전날 종가 (미국장 마감 중)'
                }
            else:
                await update.message.reply_text(f"❌ {ticker} 데이터 없음")
                return
        data = analyzer.get_indicators(ticker)
        if data:
            data['current_price'] = us_data['price']
            data['change_pct']    = us_data['change_pct']
            data['timestamp']     = us_data['timestamp'] + " (KIS실시간)"
        else:
            data = {
                'current_price':    us_data['price'],
                'change_pct':       us_data['change_pct'],
                'rsi':              'N/A',
                'bb_position':      'N/A',
                'stop_loss':        round(us_data['price'] * 0.93, 2),
                'stop_loss_pct':    -7.0,
                'volume_ratio':     1.0,
                'high_52w_proximity': 'N/A',
                'signals':          [],
                'timestamp':        us_data['timestamp'] + " (KIS실시간)"
            }
    
    if not data:
        await update.message.reply_text(f"❌ {ticker} 데이터 없음")
        return
    ai_result    = ai.analyze_buy_signal(ticker, ticker, data)
    signals_text = "\n".join([f"  • {s}" for s in data['signals']]) if data['signals'] else "  없음"
    msg = f"""📊 <b>{ticker} 분석</b>
{em} {r.get('regime','?')}장

💰 현재가: {data['current_price']:,}
📊 RSI: {data['rsi']}
📈 볼린저밴드: {data['bb_position']}
📉 손절선: {data['stop_loss']:,} ({data['stop_loss_pct']}%)
📦 거래량: {data['volume_ratio']}배
🏔 52주 신고가: {data['high_52w_proximity']}%

🔔 신호:
{signals_text}

🤖 AI 판단:
{ai_result if ai_result else "분석 불가"}

⏰ {data['timestamp']}"""
    await send(msg)

async def cmd_analyze(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /analyze 삼성전자 — 한국 종목명
    /analyze NVDA — 미국 티커
    
    기술적 + 시황 + 트렌드 + AI 종합 예측
    """
    if not context.args:
        await update.message.reply_text(
            "사용법:\n"
            "/analyze 삼성전자 — 한국 종목\n"
            "/analyze NVDA — 미국 종목"
        )
        return
 
    query = " ".join(context.args)
    await update.message.reply_text(f"🔍 {query} 종합 분석 중... (30~40초)")
 
    try:
        from modules.kis_api import KISApi
        from modules.sector_db import SECTOR_DB
        from modules.supply_demand import SupplyDemand
        from anthropic import Anthropic
        import yfinance as yf
        import re, json as _json
 
        kis    = KISApi()
        client = Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))
 
        # ── 1. 종목 식별 ──────────────────────────────
 
        # 미국 티커 판단 (영문자만)
        is_us_ticker = query.isalpha() and query.isupper() and len(query) <= 5
 
        ticker   = None
        name     = query
        market   = None
        sector   = "알 수 없음"
 
        if is_us_ticker:
            # 미국 티커 직접 사용
            ticker = query.upper()
            market = "US"
            # sector_db에서 섹터 찾기
            for sector_name, sector_data in SECTOR_DB.items():
                if sector_data.get('market') != 'US':
                    continue
                for tier in ['대장주', '2등주']:
                    for sname, sticker in sector_data.get(tier, {}).items():
                        if sticker == ticker:
                            name   = sname
                            sector = sector_name
                            break
        else:
            # 한국 종목명 → 티커 변환
            # 1차: sector_db에서 검색
            for sector_name, sector_data in SECTOR_DB.items():
                if sector_data.get('market') != 'KR':
                    continue
                for tier in ['대장주', '2등주', '소부장']:
                    for sname, sticker in sector_data.get(tier, {}).items():
                        if query in sname or sname in query:
                            ticker = sticker
                            name   = sname
                            market = "KR"
                            sector = sector_name
                            break
                if ticker:
                    break
 
            # 2차: AI로 티커 변환
            if not ticker:
                res = client.messages.create(
                    model="claude-sonnet-4-6",
                    max_tokens=100,
                    messages=[{"role": "user", "content": f"""한국 주식 종목명을 티커로 변환해주세요.
종목명: {query}
JSON으로만: {{"ticker": "000000", "name": "정확한종목명", "sector": "섹터명"}}"""}]
                )
                text = re.sub(r'```json|```', '', res.content[0].text.strip()).strip()
                m    = re.search(r'\{.*\}', text, re.DOTALL)
                if m:
                    info   = _json.loads(m.group())
                    ticker = info.get('ticker', '')
                    name   = info.get('name', query)
                    sector = info.get('sector', '알 수 없음')
                    market = "KR"
 
        if not ticker:
            await update.message.reply_text(f"❌ {query} 종목을 찾을 수 없어요")
            return
 
        # ── 2. 기술적 데이터 수집 ─────────────────────
 
        price_data = {}
        tech_data  = {}
 
        if market == "KR":
            kis_data = kis.get_kr_price(ticker)
            if kis_data:
                price_data = kis_data
            yf_ticker = f"{ticker}.KS"
        else:
            for excd in ["NAS", "NYS", "AMS"]:
                us_data = kis.get_us_price(ticker, excd)
                if us_data and us_data.get('price', 0) > 0:
                    price_data = us_data
                    break
            if not price_data:
                yf_hist = yf.Ticker(ticker).history(period="2d").dropna()
                if not yf_hist.empty:
                    price_data = {
                        'price':      round(yf_hist['Close'].iloc[-1], 2),
                        'change_pct': round(((yf_hist['Close'].iloc[-1] - yf_hist['Close'].iloc[-2]) / yf_hist['Close'].iloc[-2]) * 100, 2),
                    }
            yf_ticker = ticker
 
        # yfinance 기술적 지표
        try:
            hist = yf.Ticker(yf_ticker).history(period="60d").dropna()
            if len(hist) >= 20:
                close     = hist['Close']
                volume    = hist['Volume']
                current   = price_data.get('price', close.iloc[-1])
                avg_vol   = volume.mean()
                curr_vol  = volume.iloc[-1]
                vol_ratio = round(curr_vol / avg_vol, 1) if avg_vol > 0 else 1
 
                # RSI
                delta = close.diff()
                gain  = delta.clip(lower=0).rolling(14).mean()
                loss  = (-delta.clip(upper=0)).rolling(14).mean()
                rs    = gain / loss
                rsi   = round((100 - (100 / (1 + rs))).iloc[-1], 1)
 
                # 이평선
                ma5  = round(close.rolling(5).mean().iloc[-1], 2)
                ma20 = round(close.rolling(20).mean().iloc[-1], 2)
 
                # OBV
                obv       = (volume * close.diff().apply(lambda x: 1 if x > 0 else -1)).cumsum()
                obv_trend = "상승" if obv.iloc[-1] > obv.iloc[-5] else "하락"
 
                # 52주
                high_52w  = close.max()
                low_52w   = close.min()
                drawdown  = round(((current - high_52w) / high_52w) * 100, 1)
 
                tech_data = {
                    "rsi":       rsi,
                    "ma5":       ma5,
                    "ma20":      ma20,
                    "vol_ratio": vol_ratio,
                    "obv_trend": obv_trend,
                    "drawdown":  drawdown,
                    "high_52w":  round(high_52w, 2),
                    "low_52w":   round(low_52w, 2),
                }
        except Exception as e:
            print(f"  ⚠️ 기술적 데이터 실패: {e}")
 
        # ── 3. 수급 데이터 (한국만) ───────────────────
 
        supply_text = "수급 데이터 없음"
        if market == "KR":
            try:
                sd          = SupplyDemand()
                supply      = sd.analyze_supply(ticker, name)
                if supply:
                    supply_text = (
                        f"외국인 {supply['foreign_consecutive']}일 연속 "
                        f"{'순매수' if supply['foreign'] > 0 else '순매도'} "
                        f"({supply['foreign']:,}주)\n"
                        f"기관 {supply['organ_consecutive']}일 연속 "
                        f"{'순매수' if supply['organ'] > 0 else '순매도'} "
                        f"({supply['organ']:,}주)"
                    )
            except:
                pass
 
        # ── 4. 시황 컨텍스트 수집 ─────────────────────
 
        # 현재 장세
        r          = regime.current_regime
        kr_regime  = r.get('kr_regime', '중립')
        us_regime  = r.get('us_regime', '중립')
        cur_regime = kr_regime if market == "KR" else us_regime
 
        # 오늘 AI 선정 섹터
        mt_context    = mt.get_current_context()
        selected_sectors = []
        overheated_sectors = []
        if mt_context:
            ai_result         = mt_context.get('ai_result', {})
            selected_sectors  = [s['kr_sector'] for s in ai_result.get('selected_sectors', [])]
            overheated_sectors = ai_result.get('overheated_sectors', [])
 
        in_selected  = any(sector.lower() in s.lower() or s.lower() in sector.lower() for s in selected_sectors)
        is_overheated = any(sector.lower() in s.lower() or s.lower() in sector.lower() for s in overheated_sectors)
 
        # 이벤트 캘린더
        today_events   = ec.get_today_events()
        event_text     = ", ".join([e['type'] for e in today_events if e['severity'] in ['high', 'medium']]) or "없음"
 
        # 환율 (미국 주식)
        fx_text = ""
        if market == "US":
            fx_rate   = fx.get_current_rate()
            fx_trend  = fx.get_5day_trend()
            fx_text   = f"환율: {fx_rate:,.0f}원 | {fx_trend.get('trend', '횡보') if fx_trend else '횡보'}"
 
        # 포트폴리오 보유 여부
        holding_text = ""
        holding_info = pf.portfolio.get(ticker)
        if holding_info and isinstance(holding_info, dict):
            buy_price   = holding_info.get('buy_price', 0)
            current     = price_data.get('price', 0)
            profit_pct  = ((current - buy_price) / buy_price) * 100 if buy_price > 0 else 0
            target1     = holding_info.get('target1')
            stop_loss   = holding_info.get('stop_loss')
            holding_text = (
                f"보유 중 | 매수가: {buy_price:,} | 수익률: {profit_pct:+.1f}%\n"
                f"목표가: {target1:,} | 손절가: {stop_loss:,}"
            ) if target1 and stop_loss else f"보유 중 | 매수가: {buy_price:,} | 수익률: {profit_pct:+.1f}%"
 
        # ── 5. AI 종합 분석 ───────────────────────────
 
        currency = "$" if market == "US" else "₩"
        current_price = price_data.get('price', 0)
        change_pct    = price_data.get('change_pct', 0)
 
        prompt = f"""주식 종합 분석을 해주세요. 뉴스보다 시황/트렌드/수급을 중심으로 판단해주세요.
 
=== 종목 정보 ===
종목: {name} ({ticker}) | 시장: {market} | 섹터: {sector}
현재가: {currency}{current_price:,} ({change_pct:+.1f}%)
{f"보유 현황: {holding_text}" if holding_text else "미보유"}
 
=== 기술적 지표 ===
RSI: {tech_data.get('rsi', 'N/A')}
5일선: {tech_data.get('ma5', 'N/A')} | 20일선: {tech_data.get('ma20', 'N/A')}
거래량: 평균 대비 {tech_data.get('vol_ratio', 1)}배
OBV: {tech_data.get('obv_trend', 'N/A')}
52주 고점 대비: {tech_data.get('drawdown', 'N/A')}%
 
=== 수급 ===
{supply_text}
 
=== 현재 시황 ===
한국 장세: {kr_regime}장 (점수: {r.get('kr_score', 0)})
미국 장세: {us_regime}장 (점수: {r.get('us_score', 0)})
현재 장세: {cur_regime}장
 
=== 오늘 AI 선정 섹터 ===
선정: {', '.join(selected_sectors) if selected_sectors else '없음'}
이 종목 섹터 포함 여부: {'✅ 포함' if in_selected else '❌ 미포함'}
과열 섹터: {', '.join(overheated_sectors) if overheated_sectors else '없음'}
이 종목 과열 여부: {'🌡️ 과열' if is_overheated else '정상'}
 
=== 이벤트 ===
오늘 이벤트: {event_text}
{f"환율: {fx_text}" if fx_text else ""}
 
분석 요청:
1. 지금 이 종목 타이밍 판단 (뉴스 아닌 시황/트렌드/수급 기반)
2. {"추가매수/익절/손절 판단" if holding_text else "단기/중장기/도박 중 전략"}
3. 목표가 / 손절가
4. 핵심 리스크 1가지
5. 같은 섹터 더 나은 대안 종목 1~2개 (있을 경우만)
 
한국어로 간결하게, JSON으로만:
{{
  "timing": "좋음 or 보통 or 나쁨",
  "timing_reason": "타이밍 판단 이유 한줄",
  "strategy": "단기 or 중장기 or 도박 or 추가매수 or 익절고려 or 손절고려",
  "strategy_reason": "전략 이유 한줄",
  "target": {current_price * 1.1:.0f},
  "stop_loss": {current_price * 0.93:.0f},
  "risk": "핵심 리스크 한줄",
  "alternatives": ["대안종목1", "대안종목2"],
  "overall": "한줄 총평"
}}"""
 
        res = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=600,
            messages=[{"role": "user", "content": prompt}]
        )
        text   = re.sub(r'```json|```', '', res.content[0].text.strip()).strip()
        m      = re.search(r'\{.*\}', text, re.DOTALL)
        ai_res = _json.loads(m.group()) if m else {}
 
        # ── 6. 메시지 생성 ────────────────────────────
 
        timing_emoji = {"좋음": "🟢", "보통": "🟡", "나쁨": "🔴"}.get(ai_res.get('timing', '보통'), "🟡")
        market_flag  = "🇺🇸" if market == "US" else "🇰🇷"
        sector_badge = "✅ 오늘 선정 섹터" if in_selected else ("🌡️ 과열 주의" if is_overheated else "")
 
        msg  = f"🔍 <b>{name}</b> ({ticker}) {market_flag}\n"
        msg += f"섹터: {sector} {sector_badge}\n\n"
 
        # 보유 현황
        if holding_text:
            msg += f"💼 <b>보유 현황</b>\n{holding_text}\n\n"
 
        # 기술적
        msg += f"📊 <b>기술적</b>\n"
        msg += f"현재가: {currency}{current_price:,} ({change_pct:+.1f}%)\n"
        msg += f"RSI: {tech_data.get('rsi', 'N/A')} | 거래량: {tech_data.get('vol_ratio', 1)}배\n"
        msg += f"OBV: {tech_data.get('obv_trend', 'N/A')} | 고점 대비: {tech_data.get('drawdown', 'N/A')}%\n\n"
 
        # 수급
        if market == "KR" and supply_text != "수급 데이터 없음":
            msg += f"💰 <b>수급</b>\n{supply_text}\n\n"
 
        # 시황
        msg += f"🌍 <b>시황</b>\n"
        msg += f"{cur_regime}장 | {', '.join(selected_sectors[:2]) if selected_sectors else '섹터 미선정'}\n"
        if event_text != "없음":
            msg += f"⚠️ 오늘 이벤트: {event_text}\n"
        if fx_text:
            msg += f"💱 {fx_text}\n"
        msg += "\n"
 
        # AI 종합 판단
        msg += f"🤖 <b>AI 종합 판단</b>\n"
        msg += f"{timing_emoji} 타이밍: {ai_res.get('timing', '?')} — {ai_res.get('timing_reason', '')}\n"
        msg += f"⚔️ 전략: {ai_res.get('strategy', '?')} — {ai_res.get('strategy_reason', '')}\n\n"
        msg += f"🎯 목표가: {currency}{float(ai_res.get('target', 0)):,.0f}\n"
        msg += f"🛑 손절가: {currency}{float(ai_res.get('stop_loss', 0)):,.0f}\n"
        msg += f"⚠️ 리스크: {ai_res.get('risk', '')}\n\n"
 
        # 대안 종목
        alternatives = ai_res.get('alternatives', [])
        if alternatives:
            msg += f"💡 <b>대안 종목</b>: {', '.join(alternatives)}\n\n"
 
        msg += f"📌 {ai_res.get('overall', '')}\n"
        msg += f"\n⚠️ 최종 판단은 본인이 하세요\n"
        msg += f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M')}"
 
        await send(msg)
 
    except Exception as e:
        await update.message.reply_text(f"❌ 분석 실패: {e}")
        print(f"  ❌ cmd_analyze 실패: {e}")

async def cmd_market(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🌍 수집 중...")
    try:
        prices     = PriceCollector().get_all_prices()
        indicators = MarketIndicators().get_all_indicators()
        fg         = indicators.get('fear_greed', {})
        indices    = prices.get('지수', {})
        r          = regime.current_regime
        em         = regime.get_regime_emoji()
        idx_text   = ""
        for name, data in indices.items():
            arrow = "▲" if data['change_pct'] > 0 else "▼"
            idx_text += f"  {arrow} {name}: {data['current_price']:,} ({data['change_pct']:+.2f}%)\n"
        forex      = indicators.get('forex_commodities', {})
        forex_text = ""
        for name, data in forex.items():
            arrow = "▲" if data['change_pct'] > 0 else "▼"
            forex_text += f"  {arrow} {name}: {data['price']:,} ({data['change_pct']:+.2f}%)\n"
        fg_text = f"{fg.get('score','N/A')} — {fg.get('signal','N/A')}" if fg else "N/A"
        msg = f"""🌍 <b>시장 현황</b>
{em} {r.get('regime','?')}장

📈 <b>지수</b>
{idx_text}
💵 <b>환율 · 원자재</b>
{forex_text}
😨 공포탐욕: {fg_text}

⏰ {datetime.now().strftime('%Y-%m-%d %H:%M')}"""
        await send(msg)
    except Exception as e:
        await update.message.reply_text(f"❌ {e}")

async def cmd_trend(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """실시간 섹터 트렌드 분석 (ETF 자금 흐름 기반)"""
    await update.message.reply_text("🔍 실시간 섹터 트렌드 분석 중... (30초)")
    try:
        # 실시간 market_temperature 실행
        r       = regime.current_regime
        context_data = await mt.select_sectors(r.get('regime', '강세'))

        if not context_data:
            await update.message.reply_text("❌ 분석 실패")
            return

        ai_result = context_data.get('ai_result', {})
        macro     = context_data.get('macro', {})
        etf_flow  = context_data.get('etf_flow', {})
        kr_temp   = context_data.get('kr_temp', {})

        # 메시지 생성
        msg  = f"📊 <b>실시간 섹터 트렌드</b> {datetime.now().strftime('%m/%d %H:%M')}\n"
        msg += f"<i>ETF 자금 흐름 + AI 분석 기반 (방금 분석)</i>\n\n"

        # 장세
        kr_regime = r.get('kr_regime', '중립')
        us_regime = r.get('us_regime', '중립')
        msg += f"🇰🇷 한국: {kr_regime}장 | 🇺🇸 미국: {us_regime}장\n\n"

        # ETF 자금 유입
        inflow = [(s, d) for s, d in etf_flow.items() if d.get('inflow')]
        outflow = [(s, d) for s, d in etf_flow.items() if not d.get('inflow') and d.get('change', 0) < -0.5]
        if inflow:
            msg += "💰 <b>자금 유입 ETF</b>\n"
            for sector, data in inflow:
                msg += f"  ▲ {sector}({data['ticker']}): {data['change']:+.2f}% 거래량{data['vol_ratio']}배\n"
            msg += "\n"
        if outflow:
            msg += "📉 <b>자금 유출 ETF</b>\n"
            for sector, data in outflow[:3]:
                msg += f"  ▼ {sector}({data['ticker']}): {data['change']:+.2f}%\n"
            msg += "\n"

        # 오늘 주력 섹터
        selected = ai_result.get('selected_sectors', [])
        if selected:
            msg += "🎯 <b>오늘 주력 섹터</b>\n"
            for s in selected:
                momentum_emoji = {"강함": "🔥", "보통": "✅", "약함": "⚠️"}.get(s.get('momentum', '보통'), "✅")
                msg += f"  {momentum_emoji} <b>{s['kr_sector']}</b>\n"
                msg += f"     {s['reason']}\n"
                if s.get('caution') and s['caution'] != '없음':
                    msg += f"     ⚠️ {s['caution']}\n"
            msg += "\n"

        # 다음 올 섹터 (순환 사이클)
        msg += f"🔄 <b>섹터 순환 예측</b>\n"
        msg += f"  {ai_result.get('market_outlook', '')}\n\n"

        # 과열 섹터
        overheated = ai_result.get('overheated_sectors', [])
        if overheated:
            msg += f"🌡️ <b>과열 주의</b> (신규 진입 금지)\n"
            for s in overheated:
                msg += f"  ❌ {s}\n"
            msg += "\n"

        # 장세 신뢰도
        msg += f"📊 장세 신뢰도: {ai_result.get('regime_confidence', '?')}\n"
        msg += f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M')}"

        await send(msg)

    except Exception as e:
        await update.message.reply_text(f"❌ 실패: {e}")
        print(f"  ❌ cmd_trend 실패: {e}")

async def cmd_briefing(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🧠 AI 브리핑 생성 중... (30~60초)")
    try:
        news       = NewsCollector().collect_news(max_per_feed=5)
        prices     = PriceCollector().get_all_prices()
        indicators = MarketIndicators().get_all_indicators()
        result     = ai.analyze_market(news, prices, indicators)
        if result:
            await send(f"🧠 <b>AI 브리핑</b>\n\n{result}")
        else:
            await update.message.reply_text("❌ 실패")
    except Exception as e:
        await update.message.reply_text(f"❌ {e}")

async def cmd_scan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    r  = regime.current_regime
    em = regime.get_regime_emoji()
    await update.message.reply_text(f"🔍 스캔 시작...\n{em} {r.get('regime')}장")
    await smart_scan(notify_all=True)
    await update.message.reply_text("✅ 완료")

async def cmd_portfolio(update, context):
    await update.message.reply_text("📊 포트폴리오 조회 중... (2~3분 소요)")
    try:
        msg = pf.build_portfolio_message()
        await send(msg)
    except Exception as e:
        await update.message.reply_text(f"❌ 실패: {e}")

async def cmd_buy(update, context):
    args = context.args

    if len(args) < 4:
        await update.message.reply_text(
            "사용법: /buy 종목명 티커 매수가 수량\n"
            "예) /buy 삼성전자 005930 219000 10\n"
            "예) /buy 엔비디아 NVDA 875 3"
        )
        return

    name      = args[0]
    ticker    = args[1].upper()
    buy_price = float(args[2].replace(",", ""))
    quantity  = int(args[3])

    market = "US" if ticker.isalpha() else "KR"

    pf.add_stock(name, ticker, buy_price, quantity,
                 market=market, hold_type="장기")

    # ✅ 미국 주식이면 환율 저장
    if market == "US":
        saved_rate = fx.save_buy_rate(ticker)

    total    = buy_price * quantity
    currency = "$" if market == "US" else "₩"

    await update.message.reply_text(
        f"✅ <b>{name}</b> 매수 등록 완료\n\n"
        f"💰 매수가: {currency}{buy_price:,}\n"
        f"📦 수량: {quantity}주\n"
        f"💵 총액: {currency}{total:,.0f}\n"
        f"📋 유형: {market} 장기",
        parse_mode="HTML"
    )

async def cmd_buy_rate(update, context):
    """
    /buy_rate TICKER 환율
    예) /buy_rate IONQ 1350
    기존 종목 매수 환율 수동 입력
    """
    args = context.args
    if len(args) < 2:
        await update.message.reply_text(
            "사용법: /buy_rate TICKER 환율\n"
            "예) /buy_rate IONQ 1350\n"
            "예) /buy_rate NVDA 1380"
        )
        return
    ticker = args[0].upper()
    try:
        rate = float(args[1].replace(",", ""))
        fx.set_buy_rate(ticker, rate)
        await update.message.reply_text(
            f"✅ {ticker} 매수 환율 저장 완료\n"
            f"💱 {rate:,.1f}원/달러",
            parse_mode="HTML"
        )
    except ValueError:
        await update.message.reply_text("❌ 환율은 숫자로 입력해주세요\n예) /buy_rate IONQ 1350")

async def cmd_sell(update, context):
    args = context.args
    if len(args) < 2:
        await update.message.reply_text(
            "사용법: /sell 티커 매도가\n"
            "예) /sell NVDA 900\n"
            "예) /sell 005930 220000"
        )
        return
    ticker    = args[0].upper()
    sell_price = float(args[1].replace(",", ""))
    name      = pf.remove_stock(ticker, sell_price)
    if name:
        stock_info = None
        for t, s in list(pf.portfolio.items()):
            if t == ticker:
                stock_info = s
                break
        await update.message.reply_text(
            f"✅ <b>{name}</b> 매도 완료\n"
            f"💰 매도가: {sell_price:,}",
            parse_mode="HTML"
        )
    else:
        await update.message.reply_text(f"❌ {ticker} 포트폴리오에 없음")

async def cmd_loss(update, context):
    """/loss — 손실 한도 현황"""
    try:
        total, exchange_rate = tg.get_total_assets(pf.portfolio)
        is_blocked, blocked, warnings = tg.full_check(mt.get_current_context(), total)
 
        violations = tg.check_loss_limits(total)
 
        msg  = f"📊 <b>손실 한도 현황</b>\n\n"
        msg += f"💰 현재 총자산: {total:,.0f}원\n\n"
 
        if violations:
            msg += "🛑 <b>손실 한도 초과</b>\n"
            for v in violations:
                msg += f"  {v['type']}: {v['actual']:+.1f}% (한도: {v['limit']}%)\n"
                msg += f"  → {v['action']}\n"
        else:
            msg += "✅ 손실 한도 정상\n"
 
        # 스냅샷 기반 수익률
        snapshots = tg.snapshots
        today_key = datetime.now().strftime("%Y-%m-%d")
        yesterday_key = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
 
        if yesterday_key in snapshots:
            prev    = snapshots[yesterday_key]["total_krw"]
            day_pct = ((total - prev) / prev) * 100
            msg    += f"\n📅 일간: {day_pct:+.2f}% (한도: -1%)\n"
 
        weekly_start = tg.data.get("weekly_start")
        if weekly_start:
            week_pct = ((total - weekly_start) / weekly_start) * 100
            msg     += f"📅 주간: {week_pct:+.2f}% (한도: -3%)\n"
 
        monthly_start = tg.data.get("monthly_start")
        if monthly_start:
            month_pct = ((total - monthly_start) / monthly_start) * 100
            msg      += f"📅 월간: {month_pct:+.2f}% (한도: -7%)\n"
 
        msg += f"\n⏰ {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        from main import send as _send
        await _send(msg)
    except Exception as e:
        await update.message.reply_text(f"❌ 실패: {e}")

async def cmd_diagnosis(update, context):
    await update.message.reply_text("🧠 AI 포트폴리오 진단 중... (30~60초)")
    try:
        news   = NewsCollector().collect_news(max_per_feed=5)
        result = pf.ai_portfolio_diagnosis(news)
        if result:
            await update.message.reply_text(
                f"🧠 <b>AI 포트폴리오 진단</b>\n\n{result}",
                parse_mode="HTML"
            )
        else:
            await update.message.reply_text("❌ 진단 실패")
    except Exception as e:
        await update.message.reply_text(f"❌ 실패: {e}")

async def cmd_news_impact(update, context):
    await update.message.reply_text("📰 보유 종목 뉴스 영향 분석 중...")
    try:
        news   = NewsCollector().collect_news(max_per_feed=5)
        result = pf.check_news_impact(news)
        if result:
            await update.message.reply_text(
                f"📰 <b>보유 종목 뉴스 영향</b>\n\n{result}",
                parse_mode="HTML"
            )
        else:
            await update.message.reply_text("보유 종목 관련 특이 뉴스 없음")
    except Exception as e:
        await update.message.reply_text(f"❌ 실패: {e}")

async def cmd_premarket(update, context):
    await update.message.reply_text("🌅 상한가 후보 스캔 중... (2~3분 소요)")
    try:
        news = NewsCollector().collect_news(max_per_feed=3)
        candidates, hot_sectors = await pm.scan_top_candidates(news)
        msg = pm.build_premarket_message(candidates, hot_sectors)
        await send(msg)
    except Exception as e:
        await update.message.reply_text(f"❌ 실패: {e}")

async def cmd_leverage(update, context):
    await update.message.reply_text("⚡ 레버리지 ETF 현황 조회 중...")
    try:
        msg = lm.build_leverage_status_message()
        await send(msg)
    except Exception as e:
        await update.message.reply_text(f"❌ 실패: {e}")

async def cmd_themes(update, context):
    """현재 임시 테마 현황"""
    msg = ds.get_status_text()
    await send(msg)

async def cmd_add_sector(update, context):
    """임시 테마를 고정 섹터로 승격"""
    if not context.args:
        await update.message.reply_text(
            "사용법: /add_sector 테마명\n"
            "예) /add_sector 양자컴퓨터"
        )
        return
    theme_name = " ".join(context.args)
    success, msg = ds.promote_to_permanent(theme_name)
    await update.message.reply_text(msg)

async def cmd_accuracy(update, context):
    await update.message.reply_text("📊 AI 정확도 리포트 생성 중...")
    try:
        report = al.get_accuracy_report(days=30)
        await send(report)
    except Exception as e:
        await update.message.reply_text(f"❌ 실패: {e}")

async def cmd_supply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("💰 수급 분석 중... (1~2분 소요)")
    try:
        sd       = SupplyDemand()
        results  = sd.scan_supply(SUPPLY_WATCH)
        messages = sd.build_alert_messages(results)
        if messages:
            for msg in messages:
                if msg and msg.strip():
                    await send(msg)
        else:
            await update.message.reply_text("ℹ️ 현재 특이 수급 신호 없음")
    except Exception as e:
        await update.message.reply_text(f"❌ 실패: {e}")

# ── 스마트 스캔 ──
async def smart_scan(notify_all=False):
    """장세 전환 감지 (30분마다)"""
    r           = regime.analyze_regime()
    regime_type = r['regime']
    em          = regime.get_regime_emoji()
    print(f"[{datetime.now().strftime('%H:%M')}] {em} {regime_type}장 체크")

    # 장세 전환 시 즉시 알림
    if r.get('regime_changed'):
        params_new = regime.get_strategy_params()
        await send(f"""🔄 <b>장세 전환!</b>

{r.get('prev_regime')}장 → <b>{r.get('regime')}장</b>
⚔️ 전략: {params_new['description']}

🇰🇷 코스피: {r.get('kospi_current'):,}
🇺🇸 나스닥: {r.get('nas_current'):,}
⏰ {datetime.now().strftime('%Y-%m-%d %H:%M')}""")

async def long_term_scan(notify_all=False):
    for name, ticker in LONG_TERM_STOCKS.items():
        data = analyzer.get_indicators(ticker)
        if not data:
            continue
        rsi_low = data['rsi'] and data['rsi'] <= 35
        bb_low  = "하단" in str(data['bb_position'])
        low_52w = data['high_52w_proximity'] <= 70
        macd_gc = "MACD 골든크로스" in str(data['signals'])
        score   = sum([rsi_low, bb_low, low_52w, macd_gc])
        if score >= 2 or notify_all:
            key = f"{ticker}_장기_저점"
            if monitor._can_alert(key, cooldown_hours=12):
                ai_result    = ai.analyze_buy_signal(name, ticker, data)
                stars        = "★" * score + "☆" * (4 - score)
                signals_text = "\n".join([f"  • {s}" for s in data['signals']]) if data['signals'] else "  없음"
                msg = f"""🔵 <b>[장기 저점] {name}</b> {stars}

💰 현재가: {data['current_price']:,}
📊 RSI: {data['rsi']}
📈 볼린저밴드: {data['bb_position']}
📉 손절선: {data['stop_loss']:,} ({data['stop_loss_pct']}%)

🔔 신호:
{signals_text}

🤖 AI:
{ai_result if ai_result else "분석 중"}

⏰ {datetime.now().strftime('%Y-%m-%d %H:%M')}"""
                await send(msg)

# ── 스케줄 작업 ──
async def premarket_morning_scan():
    """매일 새벽 5시 상한가 후보 스캔"""
    if is_weekend():
        return
    print(f"[{datetime.now().strftime('%H:%M')}] 🌅 새벽 상한가 스캔")
    try:
        nc   = NewsCollector()
        news = nc.collect_news(max_per_feed=5)
        news = nc.filter_by_importance(news)
        candidates, hot_sectors = await pm.scan_top_candidates(news)
        msg = pm.build_premarket_message(candidates, hot_sectors)
        await send(msg)
        print("  ✅ 새벽 스캔 완료")
    except Exception as e:
        print(f"  ❌ 새벽 스캔 실패: {e}")

async def run_daily_rotation():
    """매일 06:00 순환매 + 동적 테마 분석"""
    if is_weekend():
        return
    print(f"[{datetime.now().strftime('%H:%M')}] 🔄 순환매 + 테마 분석")
    try:
        from modules.daily_rotation import run_daily_rotation as _rotation
        await _rotation(send)

        # 동적 테마 감지
        news     = NewsCollector().collect_news(max_per_feed=5)
        removed  = ds.remove_expired()
        new_themes = await ds.detect_new_themes(news)

        added = []
        for t in new_themes:
            if t.get('confidence', 0) >= 0.6:
                ds.add_temp_theme(t)
                added.append(t)

        msg = ds.build_theme_message(added, removed)
        if msg:
            await send(msg)
            print(f"  ✅ 새 테마 {len(added)}개 감지")

    except Exception as e:
        print(f"  ❌ 순환매/테마 분석 실패: {e}")

async def morning_briefing():
    """07:00 아침 종합 브리핑 - 매크로 포함"""
    if is_monday():
        return  # 월요일은 monday_weekly_briefing이 대신함
    print(f"[{datetime.now().strftime('%H:%M')}] 🌅 아침 브리핑")

async def morning_briefing_old():
    print(f"[{datetime.now().strftime('%H:%M')}] 🌅 아침 브리핑")
    try:
        r          = regime.analyze_regime()
        params     = regime.get_strategy_params()
        em         = regime.get_regime_emoji()
        news       = NewsCollector().collect_news(max_per_feed=5)
        prices     = PriceCollector().get_all_prices()
        indicators = MarketIndicators().get_all_indicators()
        fg         = indicators.get('fear_greed', {})
        indices    = prices.get('지수', {})
        idx_text   = ""
        for name, data in indices.items():
            arrow = "▲" if data['change_pct'] > 0 else "▼"
            idx_text += f"  {arrow} {name}: {data['current_price']:,} ({data['change_pct']:+.2f}%)\n"
        forex      = indicators.get('forex_commodities', {})
        forex_text = ""
        for name, data in forex.items():
            arrow = "▲" if data['change_pct'] > 0 else "▼"
            forex_text += f"  {arrow} {name}: {data['price']:,} ({data['change_pct']:+.2f}%)\n"
        fg_text  = f"{fg.get('score','N/A')} — {fg.get('signal','N/A')}" if fg else "N/A"
        ai_brief = ai.analyze_market(news, prices, indicators)
        msg = f"""🌅 <b>아침 브리핑</b> {datetime.now().strftime('%m/%d')}
{em} <b>{r['regime']}장</b> ({r['consecutive_days']}일째)
⚔️ {params['description']}

📈 <b>지수</b>
{idx_text}
💵 <b>환율 · 원자재</b>
{forex_text}
😨 공포탐욕: {fg_text}

🧠 <b>AI 분석</b>
{ai_brief if ai_brief else "분석 불가"}"""
        await send(msg)
        today_events = ec.get_today_events()
        event_msg = ec.build_today_alert(today_events)
        if event_msg:
            await send(event_msg)
        earnings = ec.get_earnings_dates(pf.portfolio)
        earn_msg = ec.build_earnings_alert(earnings)
        if earn_msg:
            await send(earn_msg)
    except Exception as e:
        print(f"❌ {e}")

async def short_term_recommendation():
    """07:30 장전 단기 추천 → NXT 08:00 진입용"""
    if is_weekend():
        return
    print(f"[{datetime.now().strftime('%H:%M')}] 🟡 07:30 단기 추천 시작")
    try:
        # 레이어 1: 시장 온도 + 섹터 선정
        r = regime.current_regime
        context = await mt.select_sectors(r.get('regime', '강세'))
        if not context:
            await send("❌ 시장 분석 실패")
            return

        # 시장 온도 브리핑 발송
        briefing = mt.build_briefing_message()
        await send(briefing)

        # 매매 가드 체크
        total, _ = tg.get_total_assets(pf.portfolio)
        is_blocked, blocked, warnings = tg.full_check(context, total)
        if is_blocked:
            guard_msg = tg.build_guard_message(is_blocked, blocked, warnings)
            await send(guard_msg)
            return
        elif warnings:
            guard_msg = tg.build_guard_message(False, [], warnings)
            await send(guard_msg)

        # 레이어 2: 섹터 내 수급 기반 추천
        sector_names = mt.get_selected_sector_names()
        result = await sr.recommend_morning(
            sector_names,
            r.get('regime', '강세'),
            context
        )
        if result:
            msg = sr.build_message(result, "07:30단기")
            await send(msg)
        else:
            await send("📊 오늘 조건 맞는 추천 후보 없음 → 관망")

        print("  ✅ 07:30 단기 추천 완료")
    except Exception as e:
        print(f"  ❌ 단기 추천 실패: {e}")

async def afternoon_recommendation():
    """14:30 내일 선점 추천 → NXT/장후 진입용"""
    if is_weekend():
        return
    print(f"[{datetime.now().strftime('%H:%M')}] 🕑 14:30 선점 추천 시작")
    try:
        r = regime.current_regime
 
        # 캐시된 컨텍스트 사용 (아침에 이미 섹터 선정됨)
        context = mt.get_current_context()
        if not context:
            context = await mt.select_sectors(r.get('regime', '강세'))
 
        sector_names = mt.get_selected_sector_names()
        result = await sr.recommend_afternoon(
            sector_names,
            r.get('regime', '강세'),
            context
        )
        if result:
            msg = sr.build_message(result, "14:30선점")
            await send(msg)
        else:
            await send("📊 내일 선점 후보 없음 → 관망")
 
        print("  ✅ 14:30 선점 추천 완료")
    except Exception as e:
        print(f"  ❌ 선점 추천 실패: {e}")

async def nxt_closing_summary():
    """19:50 NXT 마감 요약"""
    if is_weekend():
        return
    print(f"[{datetime.now().strftime('%H:%M')}] \U0001f306 NXT \ub9c8\uac10 \uc694\uc57d")
    try:
        from modules.premarket_futures import PremarketFutures

        pf       = PremarketFutures()
        analysis = await pf.analyze_kr_nxt()
        hot  = [(n, d) for n, d in analysis.get('hot_sectors', []) if d['avg_change'] >= 1]
        down = [(n, d) for n, d in analysis.get('hot_sectors', []) if d['avg_change'] <= -1]
        now  = datetime.now()
        msg  = "\U0001f306 <b>NXT \ub9c8\uac10 \uc694\uc57d</b> " + now.strftime("%m/%d %H:%M") + "\n\n"
        if hot:
            msg += "\U0001f4c8 <b>NXT \uac15\uc138 \uc139\ud130</b>\n"
            for name, data in hot[:3]:
                leaders = " / ".join([f"{l['name']} {l['change']:+.1f}%" for l in data['leaders'][:2]])
                msg += f"  {name}: {data['avg_change']:+.1f}% ({leaders})\n"
        if down:
            msg += "\n\U0001f4c9 <b>NXT \uc57d\uc138 \uc139\ud130</b>\n"
            for name, data in down[:3]:
                leaders = " / ".join([f"{l['name']} {l['change']:+.1f}%" for l in data['leaders'][:2]])
                msg += f"  {name}: {data['avg_change']:+.1f}% ({leaders})\n"
        if analysis.get('recommendations'):
            msg += "\n\U0001f3af <b>\ub0b4\uc77c \uc8fc\ubaa9 \uc885\ubaa9</b>\n"
            for r in analysis['recommendations'][:3]:
                msg += f"  {r['name']} ({r['ticker']}): {r['reason']}\n"
        msg += "\n\u23f0 " + now.strftime("%Y-%m-%d %H:%M")
        await send(msg)
        print("  \u2705 NXT \ub9c8\uac10 \uc694\uc57d \uc644\ub8cc")
    except Exception as e:
        print(f"  \u274c NXT \ub9c8\uac10 \uc694\uc57d \uc2e4\ud328: {e}")

async def closing_summary():
    """15:40 마감 요약 + 내일 선점 추천"""
    if is_weekend():
        return
    print(f"[{datetime.now().strftime('%H:%M')}] 📊 마감 분석 + 내일 추천")
    try:
        nc       = NewsCollector()
        news     = nc.collect_news(max_per_feed=5)
        filtered = nc.filter_by_importance(news)

        # 오늘 섹터별 결과 수집
        sector_results = ca.get_today_movers()

        # 순환매 타겟
        targets = ca.find_rotation_targets(sector_results)

        # AI 내일 추천
        result = await ca.ai_analyze_tomorrow(sector_results, targets, filtered)
        msg    = ca.build_message(sector_results, result)
        await send(msg)
        print("  ✅ 마감 분석 + 내일 추천 완료")
    except Exception as e:
        print(f"  ❌ 마감 분석 실패: {e}")

async def closing_summary_old():
    print(f"[{datetime.now().strftime('%H:%M')}] 📋 마감")
    try:
        r      = regime.analyze_regime()
        em     = regime.get_regime_emoji()
        prices = PriceCollector().get_all_prices()
        kr     = prices.get('한국주식', {})
        us     = prices.get('미국주식', {})
        kr_text = ""
        for name, data in kr.items():
            arrow = "▲" if data['change_pct'] > 0 else "▼"
            kr_text += f"  {arrow} {name}: {data['current_price']:,} ({data['change_pct']:+.2f}%)\n"
        us_text = ""
        for name, data in us.items():
            arrow = "▲" if data['change_pct'] > 0 else "▼"
            us_text += f"  {arrow} {name}: ${data['current_price']} ({data['change_pct']:+.2f}%)\n"
        await send(f"""📋 <b>마감 요약</b> {datetime.now().strftime('%m/%d')}
{em} {r['regime']}장 {r['consecutive_days']}일째

🇰🇷 {kr_text}
🇺🇸 {us_text}
⏰ {datetime.now().strftime('%Y-%m-%d %H:%M')}""")
    except Exception as e:
        print(f"❌ {e}")

    """포트폴리오 목표가/손절가 + 환율 + 세력 흔들기 체크"""
    if is_weekend():
        return
    print(f"[{datetime.now().strftime('%H:%M')}] 💼 포트폴리오 알림 체크")

    try:
        # 기존 목표가/손절가 체크
        alerts = pf.check_price_alerts()
        messages = pf.build_alert_messages(alerts)

        for msg in messages:
            await send(msg)

        # 미국 주식 환율 체크
        us_stocks = {
            t: s for t, s in pf.portfolio.items()
            if isinstance(s, dict) and s.get("market") == "US"
        }

        if us_stocks:
            fx_change = fx.check_fx_change()
            fx_msg = fx.build_fx_alert(
                fx_change,
                pf.portfolio,
                bool(us_stocks)
            )

            if fx_msg:
                await send(fx_msg)

            rate = fx.get_current_rate()
            exposure, us_val, total = fx.calc_fx_exposure(
                pf.portfolio,
                rate
            )

            expo_msg = fx.build_fx_exposure_alert(
                exposure,
                us_val,
                total
            )

            if expo_msg:
                await send(expo_msg)

        # 세력 흔들기 감지 (장중에만)
        hour = datetime.now().hour

        if 9 <= hour < 16 and not is_weekend():
            nc = NewsCollector()
            news = nc.collect_news(max_per_feed=3)

            results = await sd_detector.scan_portfolio(
                pf.portfolio,
                news
            )

            for r in results:
                msg = sd_detector.build_alert_message(
                    r["detection"],
                    r["ai_result"]
                )

                await send(msg)
                print(f"  📱 세력 흔들기 알림: {r['detection']['name']}")

    except Exception as e:
        print(f"  ❌ 포트폴리오 알림 실패: {e}")

async def morning_portfolio_diagnosis():
    """매일 아침 AI 포트폴리오 진단 + DB 저장"""
    if is_weekend():
        return
    print(f"[{datetime.now().strftime('%H:%M')}] 🧠 아침 포트폴리오 진단")
    try:
        nc   = NewsCollector()
        news = nc.collect_news(max_per_feed=5)
        news = nc.filter_by_importance(news)

        # 전날 결과 추적
        al.track_results(pf.portfolio)

        # 시장 상황 저장
        try:
            from modules.market_regime import MarketRegime
            from modules.market_indicators import MarketIndicators
            from modules.price_collector import PriceCollector
            mr    = MarketRegime()
            r     = mr.analyze_regime()
            mi    = MarketIndicators()
            inds  = mi.get_all_indicators()
            pc    = PriceCollector()
            prices = pc.get_all_prices()
            kospi = prices.get('지수', {}).get('코스피', {}).get('current_price', 0)
            fg    = inds.get('fear_greed', {})
            fg_score = fg.get('score', 0) if fg else 0
            al.save_market_status(r['regime'], kospi, fg_score, 0)
        except Exception as e:
            print(f"  ⚠️ 시장 상황 저장 실패: {e}")

        # AI 진단
        result = pf.ai_portfolio_diagnosis(news)
        if result:
            # 현재가 수집
            portfolio_prices = {}
            for ticker, stock in pf.portfolio.items():
                from modules.kis_api import KISApi
                kis = KISApi()
                if stock.get('market') == 'KR':
                    data = kis.get_kr_price(ticker)
                else:
                    data = kis.get_us_price(ticker)
                if data:
                    portfolio_prices[ticker] = data.get('price', 0)

            # DB 저장
            al.save_diagnosis(result, portfolio_prices)

            # 뉴스 저장
            al.save_news(news)

            # 텔레그램 발송
            await send(f"🧠 <b>오늘의 포트폴리오 진단</b>\n\n{result}")

        # 뉴스 영향 분석
        impact = pf.check_news_impact(news)
        if impact and "특이 뉴스 없음" not in impact:
            await send(f"📰 <b>보유 종목 뉴스 영향</b>\n\n{impact}")

        print("  ✅ 포트폴리오 진단 + DB 저장 완료")
    except Exception as e:
        print(f"  ❌ 포트폴리오 진단 실패: {e}")

async def save_asset_snapshot():
    print(f"[{datetime.now().strftime('%H:%M')}] 💾 총자산 스냅샷 저장")
    if is_weekend():
        return

    try:
        total, exchange_rate = tg.get_total_assets(pf.portfolio)

        if total > 0:
            tg.save_snapshot(total, exchange_rate)

            # 환율 일일 저장
            fx.save_daily_rate()

            msg = tg.build_snapshot_message(total, exchange_rate)
            await send(msg)

        results = bt.daily_update()

        if results:
            alert = bt.build_result_alert(results)

            if alert:
                await send(alert)

        print("  ✅ 스냅샷 + 환율 + backtest 업데이트 완료")

    except Exception as e:
        print(f"  ❌ 스냅샷 저장 실패: {e}")

# ② 23:30 미국 대형주 저점 스캔 함수 추가
async def us_lowpoint_scan():
    """23:30 미국 대형주 저점 스캔"""
    if is_weekend():
        return
    print(f"[{datetime.now().strftime('%H:%M')}] 🌙 미국 대형주 저점 스캔")
    try:
        from modules.realtime_monitor import RealtimeMonitor
        rt      = RealtimeMonitor(alert_callback=send, monitor=monitor, regime=regime)
        context = mt.get_current_context()
        await rt.scan_us_evening(context)
    except Exception as e:
        print(f"  ❌ 미국 저점 스캔 실패: {e}")

async def update_event_calendar():
    if datetime.now().day != 1:
        return
    print(f"[{datetime.now().strftime('%H:%M')}] 📅 이벤트 캘린더 업데이트")
    try:
        await ec.update_fomc_cpi()
        msg = ec.build_calendar_summary()
        await send(msg)
        print("  ✅ 캘린더 업데이트 완료")
    except Exception as e:
        print(f"  ❌ 캘린더 업데이트 실패: {e}")

    r     = regime.current_regime
    em    = regime.get_regime_emoji()
    total = sum(len(v) for v in monitor.watchlist.values())
    await send(f"""✅ <b>정상 가동</b>
{em} {r.get('regime','?')}장 | ⚡실시간 감시 중
📋 {total}개 | 🔵 {len(LONG_TERM_STOCKS)}개
⏰ {datetime.now().strftime('%Y-%m-%d %H:%M')}""")

async def nxt_realtime_scan():
    """NXT 시간 (15:30~20:00) 실시간 감시"""
    try:
        r           = regime.analyze_regime()
        regime_type = r.get('regime', '중립')
        params      = regime.get_strategy_params()

        # NXT 감시 종목 (오늘 순환매 타겟 + 장기 대장주)
        from modules.sector_rotation import SectorRotation
        sr        = SectorRotation()
        watchlist = sr.get_watchlist_for_realtime("KR")

        # 장기 대장주 추가
        from main import LONG_TERM_STOCKS
        kr_long = {k: v for k, v in LONG_TERM_STOCKS.items()
                   if not v.startswith('NV') and not v.startswith('AA')
                   and not v.startswith('MS') and len(v) == 6}
        watchlist.update(kr_long)

        for name, ticker in list(watchlist.items())[:15]:
            data = kis_rt.get_kr_price(ticker) if hasattr(kis_rt, 'get_kr_price') else None
            if not data:
                continue

            change = data.get('change_pct', 0)
            price  = data.get('price', 0)

            # NXT에서 의미있는 움직임만 알림
            if abs(change) >= 2:
                key = f"nxt_{ticker}_{datetime.now().strftime('%H')}"
                if monitor._can_alert(key, cooldown_hours=2):
                    arrow = "▲" if change > 0 else "▼"
                    emoji = "📈" if change > 0 else "📉"
                    msg = f"""{emoji} <b>[NXT] {name}</b> ({ticker})

💰 현재가: {price:,}원
{arrow} NXT 등락: {change:+.2f}%

💡 {'내일 갭상승 가능성' if change > 0 else '내일 갭하락 주의'}
⏰ {datetime.now().strftime('%H:%M')} (NXT)"""
                    await send(msg)
                    print(f"  📱 NXT 알림: {name} {change:+.1f}%")

    except Exception as e:
        print(f"  ❌ NXT 스캔 오류: {e}")


async def us_market_closing_analysis():
    """08:00 미국장 마감 분석 + 오늘 한국장 예측"""
    print(f"[{datetime.now().strftime('%H:%M')}] 🌙 미국장 마감 분석")
    try:
        import yfinance as yf

        # 미국 주요 지수 마감 결과
        indices = {"나스닥": "^IXIC", "S&P500": "^GSPC", "다우": "^DJI", "VIX": "^VIX"}
        idx_text = ""
        nas_change = 0
        for name, ticker in indices.items():
            try:
                hist = yf.Ticker(ticker).history(period="2d").dropna()
                if len(hist) >= 2:
                    current    = hist['Close'].iloc[-1]
                    prev       = hist['Close'].iloc[-2]
                    change_pct = ((current - prev) / prev) * 100
                    arrow      = "▲" if change_pct > 0 else "▼"
                    idx_text  += f"  {arrow} {name}: {current:,.2f} ({change_pct:+.2f}%)\n"
                    if '나스닥' in name:
                        nas_change = change_pct
            except:
                pass

        # 보유 미국 주식 마감 결과 (KIS API)
        from modules.kis_api import KISApi
        kis = KISApi()
        portfolio_text = ""
        us_stocks = {t: s for t, s in pf.portfolio.items() if s.get('market') == 'US'}
        for ticker, stock in list(us_stocks.items())[:8]:
            for excd in ["NAS", "NYS"]:
                data = kis.get_us_price(ticker, excd)
                if data and data.get('price', 0) > 0:
                    arrow = "▲" if data['change_pct'] > 0 else "▼"
                    portfolio_text += f"  {arrow} {stock.get('name', ticker)}: ${data['price']} ({data['change_pct']:+.2f}%)\n"
                    break

        # 뉴스 + AI 분석
        nc       = NewsCollector()
        news     = nc.collect_news(max_per_feed=3)
        filtered = nc.filter_by_importance(news)
        news_text = "\n".join([f"  {'🔴' if n.get('importance')=='high' else '🟡'} {n['title'][:50]}" for n in filtered[:6]])

        from anthropic import Anthropic
        import os
        client = Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))
        prompt = f"""미국장 마감 결과를 분석해서 오늘 한국장을 예측해주세요.

미국 지수:
{idx_text}

오늘 주요 뉴스:
{news_text}

다음을 한국어로 간단히 답해주세요:
1. 미국장 총평 한줄
2. 오늘 한국장 갭상승/갭하락 예상
3. 오늘 주목할 한국 섹터 2개
4. 주의사항"""

        res = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=400,
            messages=[{"role": "user", "content": prompt}]
        )
        ai_result = res.content[0].text

        direction = "🚀 갭상승 예상" if nas_change >= 0.5 else "📉 갭하락 주의" if nas_change <= -0.5 else "➡️ 보합 예상"

        msg  = f"🌙 <b>미국장 마감 + 한국장 예측</b> {datetime.now().strftime('%m/%d %H:%M')}\n\n"
        msg += f"{direction}\n\n"
        msg += f"📊 <b>미국 지수 마감</b>\n{idx_text}\n"
        if portfolio_text:
            msg += f"💼 <b>보유 주식</b>\n{portfolio_text}\n"
        msg += f"🧠 <b>AI 분석</b>\n{ai_result}\n"
        msg += f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        await send(msg)
        print("  ✅ 미국장 마감 분석 완료")
    except Exception as e:
        print(f"  ❌ 미국장 마감 분석 실패: {e}")

async def us_pre_trading_briefing():
    """20:30 미국장 전 브리핑"""
    print(f"[{datetime.now().strftime('%H:%M')}] 🌙 미국장 전 브리핑")
    try:
        nc       = NewsCollector()
        news     = nc.collect_news(max_per_feed=5)
        filtered = nc.filter_by_importance(news)
        macro    = await ma.analyze_macro_context(filtered)
        result   = await sr.analyze_and_recommend(filtered, regime.current_regime.get('regime', '강세'), "20:30", macro)
        msg      = sr.build_message(result, "20:30")
        full_msg = f"🌙 <b>미국장 오늘 밤 전략</b> {datetime.now().strftime('%m/%d %H:%M')}\n\n"
        full_msg += f"📊 {macro.get('summary', '')}\n"
        full_msg += f"🇺🇸 {macro.get('us_strategy', '')}\n\n"
        full_msg += msg
        await send(full_msg)
        tomorrow_events = ec.get_tomorrow_events()
        preview_msg = ec.build_tomorrow_preview(tomorrow_events)
        if preview_msg:
            await send(preview_msg)
    except Exception as e:
        print(f"  ❌ 미국장 브리핑 실패: {e}")

async def nxt_analysis():
    """08:00 NXT 분석"""
    print(f"[{datetime.now().strftime('%H:%M')}] 🌅 NXT 분석")
    try:
        from modules.premarket_futures import PremarketFutures
        pf       = PremarketFutures()
        analysis = await pf.analyze_kr_nxt()
        msg      = pf.build_kr_message(analysis)
        await send(msg)
        print("  ✅ NXT 분석 완료")
    except Exception as e:
        print(f"  ❌ NXT 분석 실패: {e}")

async def earnings_check():
    """07:00 실적 발표 체크"""
    print(f"[{datetime.now().strftime('%H:%M')}] 📅 실적 발표 체크")
    try:
        upcoming, alerts = ec.check_and_alert()
        if alerts:
            msg = ec.build_alert_message(upcoming)
            if msg:
                await send(msg)
                print(f"  📱 실적 발표 알림: {len(alerts)}개")
        else:
            print("  ✅ 오늘/내일 실적 발표 없음")
    except Exception as e:
        print(f"  ❌ 실적 체크 실패: {e}")

async def dart_scan():
    """09:05, 13:00 DART 공시 체크"""
    if is_weekend():
        return
    print(f"[{datetime.now().strftime('%H:%M')}] 📋 DART 공시 체크")
    try:
        port_disc = dm.check_portfolio_disclosures(pf.portfolio)
        if port_disc:
            msg = dm.build_alert_message(port_disc)
            if msg:
                await send(msg)
        all_disc = dm.get_today_all_disclosures()
        if all_disc:
            key = f"dart_market_{datetime.now().strftime('%Y%m%d%H')}"
            if dm._can_alert(key, cooldown_hours=3):
                msg = dm.build_market_alert(all_disc)
                if msg:
                    await send(msg)
    except Exception as e:
        print(f"  ❌ DART 스캔 실패: {e}")

async def longterm_scan():
    """30분마다 중장기 + 도박 매수 타이밍"""
    hour = datetime.now().hour
    if not (9 <= hour < 16 or hour >= 21 or hour < 4):
        return
    try:
        # 기존 중장기 스캔
        nc      = NewsCollector()
        news    = nc.collect_news(max_per_feed=3)
        signals = await ltm.scan_all_themes(news)
        if signals:
            msg = ltm.build_alert_message(signals)
            if msg:
                for s in signals:
                    key = f"longterm_{s['ticker']}"
                    if ltm._can_alert(key, cooldown_hours=24):
                        await send(msg)
                        break
 
        # 도박 매수 타이밍 추가
        gamble_signals = await gm.scan_buy_timing()
        if gamble_signals:
            msg = gm.build_buy_timing_message(gamble_signals)
            if msg:
                for s in gamble_signals:
                    key = f"gamble_{s['ticker']}"
                    if ltm._can_alert(key, cooldown_hours=24):
                        await send(msg)
                        break
 
    except Exception as e:
        print(f"  ❌ 중장기/도박 스캔 실패: {e}")

async def highlow_scan():
    """30분마다 신고가 + 거래량 이상 감지"""
    if is_weekend():
        return
    hour = datetime.now().hour
    if not (9 <= hour < 16):
        return
    try:
        kr_signals = hl.scan_signals("KR")
        messages   = hl.build_alert_messages(kr_signals, [])
        for msg in messages:
            await send(msg)
    except Exception as e:
        print(f"  ❌ 신고가 스캔 실패: {e}")

async def risk_analysis():
    """08:10 포트폴리오 리스크 분석"""
    print(f"[{datetime.now().strftime('%H:%M')}] ⚠️ 리스크 분석")
    try:
        rm.portfolio     = rm._load_portfolio()
        sector_ratio, _  = rm.calc_sector_concentration()
        metrics          = rm.calc_risk_metrics()
        fx_data          = rm.calc_exchange_rate_risk()
        upgrades         = rm.check_stop_loss_upgrade()
        ai_result        = await rm.ai_risk_analysis(sector_ratio, metrics, fx_data)
        msg              = rm.build_risk_message(sector_ratio, metrics, fx_data, ai_result, upgrades)
        await send(msg)
        print("  ✅ 리스크 분석 완료")
    except Exception as e:
        print(f"  ❌ 리스크 분석 실패: {e}")

async def us_premarket_analysis():
    """21:00 미국 프리마켓 분석"""
    print(f"[{datetime.now().strftime('%H:%M')}] 🌙 미국 프리마켓")
    try:
        from modules.premarket_futures import PremarketFutures
        pf_us    = PremarketFutures()
        analysis = await pf_us.analyze_us_premarket()
        msg      = pf_us.build_us_message(analysis)
        await send(msg)
    except Exception as e:
        print(f"  ❌ 미국 프리마켓 실패: {e}")


async def us_pre_trading_briefing():
    """20:30 미국장 전 브리핑"""
    print(f"[{datetime.now().strftime('%H:%M')}] 🌙 미국장 전 브리핑")
    try:
        nc       = NewsCollector()
        news     = nc.collect_news(max_per_feed=5)
        filtered = nc.filter_by_importance(news)
        macro    = await ma.analyze_macro_context(filtered)
        result   = await sr.analyze_and_recommend(filtered, regime.current_regime.get('regime', '강세'), "20:30", macro)
        msg      = sr.build_message(result, "20:30")
        full_msg = f"🌙 <b>미국장 오늘 밤 전략</b> {datetime.now().strftime('%m/%d %H:%M')}\n\n"
        full_msg += f"📊 {macro.get('summary', '')}\n"
        full_msg += f"🇺🇸 {macro.get('us_strategy', '')}\n\n"
        full_msg += msg
        await send(full_msg)
    except Exception as e:
        print(f"  ❌ 미국장 브리핑 실패: {e}")

async def nxt_analysis():
    """08:30 NXT 분석 → 정규장 선점 추천"""
    print(f"[{datetime.now().strftime('%H:%M')}] 🌅 NXT 분석 시작")
    try:
        from modules.kis_api import KISApi
        from modules.sector_db import SECTOR_DB
        from anthropic import Anthropic
        import os, time as _time

        kis    = KISApi()
        client = Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))

        # ① NXT 강세 종목 파악
        print("  📊 NXT 강세 종목 수집 중...")
        nxt_strong = []
        nxt_weak   = []

        for sector_name, sector_data in SECTOR_DB.items():
            if sector_data.get('market') != 'KR':
                continue
            for tier in ['대장주', '2등주']:
                for name, ticker in sector_data.get(tier, {}).items():
                    data = kis.get_kr_price(ticker)
                    if not data:
                        continue
                    change = data['change_pct']
                    price  = data['price']
                    volume = data['volume']

                    if change >= 1.0:
                        nxt_strong.append({
                            "name": name, "ticker": ticker,
                            "sector": sector_name, "tier": tier,
                            "change": change, "price": price, "volume": volume
                        })
                    elif change <= -1.0:
                        nxt_weak.append({
                            "name": name, "ticker": ticker,
                            "sector": sector_name, "tier": tier,
                            "change": change, "price": price, "volume": volume
                        })
                    _time.sleep(0.15)

        nxt_strong.sort(key=lambda x: x['change'], reverse=True)

        # ② 뉴스 수집
        nc       = NewsCollector()
        news     = nc.collect_news(max_per_feed=3)
        filtered = nc.filter_by_importance(news)
        news_text = "\n".join([f"{'🔴' if n.get('importance')=='high' else '🟡'} {n['title'][:50]}" for n in filtered[:8]])

        # ③ AI 판단 - 진짜 상승 vs 흔들기 + 정규장 선점 추천
        strong_text = ""
        for s in nxt_strong[:8]:
            strong_text += f"{s['name']}({s['ticker']}) {s['sector']}/{s['tier']}: 현재가:{s['price']:,}원 등락:{s['change']:+.1f}% 거래량:{s['volume']:,}\n"

        weak_text = ""
        for s in nxt_weak[:5]:
            weak_text += f"{s['name']}({s['ticker']}): {s['change']:+.1f}%\n"

        prompt = f"""NXT(장전 거래) 데이터를 분석해서 정규장 전략을 알려주세요.

=== NXT 강세 종목 ===
{strong_text if strong_text else "강세 종목 없음"}

=== NXT 약세 종목 ===
{weak_text if weak_text else "약세 종목 없음"}

=== 오늘 뉴스 ===
{news_text}

분석 요청:
1. NXT 강세 종목 중 진짜 상승 vs 흔들기 판단
   (거래량, 뉴스, 선물 방향 고려)
2. 정규장에서 오를 가능성 높은 종목 TOP5
   - NXT 강세 섹터의 아직 안 오른 2등주/소부장 우선
   - 이미 많이 오른 종목보다 파급 효과 종목
3. 주의할 종목 (흔들기 가능성)

JSON으로만:
{{
  "market_outlook": "오늘 정규장 한줄 예측",
  "real_movers": ["진짜 상승 종목1", "종목2"],
  "fake_movers": ["흔들기 의심 종목"],
  "recommendations": [
    {{
      "name": "종목명",
      "ticker": "티커",
      "sector": "섹터",
      "reason": "추천 이유 한줄",
      "current_price": 실제현재가숫자,
      "buy_price": 실제매수가숫자,
      "target1": 목표가1숫자,
      "target2": 목표가2숫자,
      "stop_loss": 손절가숫자,
      "buy_timing": "NXT 매수 또는 정규장 초반"
    }}
  ],
  "caution": "주의사항"
}}"""

        res  = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1500,
            messages=[{"role": "user", "content": prompt}]
        )
        import re, json as _json
        text = re.sub(r'```json|```', '', res.content[0].text.strip()).strip()
        m    = re.search(r'\{.*\}', text, re.DOTALL)
        result = _json.loads(m.group()) if m else None

        # ④ 메시지 생성
        msg  = f"🌅 <b>NXT 분석 → 정규장 선점</b> {datetime.now().strftime('%m/%d %H:%M')}\n\n"

        if nxt_strong:
            msg += "📈 <b>NXT 강세 종목</b>\n"
            for s in nxt_strong[:5]:
                msg += f"  ▲ {s['name']} ({s['ticker']}): {s['change']:+.1f}% [{s['sector']}]\n"
        else:
            msg += "📊 NXT 특이 움직임 없음\n"

        if result:
            msg += f"\n💡 <b>오늘 전망</b>: {result.get('market_outlook', '')}\n"

            real = result.get('real_movers', [])
            fake = result.get('fake_movers', [])
            if real:
                msg += f"✅ 진짜 상승: {', '.join(real)}\n"
            if fake:
                msg += f"⚠️ 흔들기 주의: {', '.join(fake)}\n"

            recs = result.get('recommendations', [])
            if recs:
                msg += "\n━━━━━━━━━━━━━━━━━━━\n"
                msg += "🎯 <b>정규장 선점 추천</b>\n"
                msg += "<i>(NXT 파급 효과 종목)</i>\n\n"
                for r in recs[:5]:
                    msg += f"⭐ <b>{r['name']}</b> ({r['ticker']})\n"
                    msg += f"   {r['reason']}\n\n"
                    def fmt(val):
                        try: return f"{int(val):,}"
                        except: return "0"
                    msg += f"   💰 현재가: {fmt(r.get('current_price', 0))}원\n"
                    msg += f"   🟢 매수가: {fmt(r.get('buy_price', 0))}원\n"
                    msg += f"   ⏱ 진입:   {r.get('buy_timing', '')}\n"
                    msg += f"   🎯 목표1:  {fmt(r.get('target1', 0))}원\n"
                    msg += f"   🎯 목표2:  {fmt(r.get('target2', 0))}원\n"
                    msg += f"   🛑 손절:   {fmt(r.get('stop_loss', 0))}원\n"
                    msg += "━━━━━━━━━━━━━━━━━━━\n"

            caution = result.get('caution', '')
            if caution:
                msg += f"\n⚠️ {caution}\n"

        msg += f"\n⏰ {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        await send(msg)
        print(f"  ✅ NXT 분석 완료 (강세:{len(nxt_strong)}개)")
    except Exception as e:
        print(f"  ❌ NXT 분석 실패: {e}")

async def earnings_check():
    """07:00 실적 발표 체크"""
    print(f"[{datetime.now().strftime('%H:%M')}] 📅 실적 발표 체크")
    try:
        upcoming, alerts = ec.check_and_alert()
        if alerts:
            msg = ec.build_alert_message(upcoming)
            if msg:
                await send(msg)
    except Exception as e:
        print(f"  ❌ 실적 체크 실패: {e}")

async def dart_scan():
    """09:05, 13:00 DART 공시 체크"""
    print(f"[{datetime.now().strftime('%H:%M')}] 📋 DART 공시 체크")
    try:
        port_disc = dm.check_portfolio_disclosures(pf.portfolio)
        if port_disc:
            msg = dm.build_alert_message(port_disc)
            if msg:
                await send(msg)
        all_disc = dm.get_today_all_disclosures()
        if all_disc:
            key = f"dart_market_{datetime.now().strftime('%Y%m%d%H')}"
            if dm._can_alert(key, cooldown_hours=3):
                msg = dm.build_market_alert(all_disc)
                if msg:
                    await send(msg)
    except Exception as e:
        print(f"  ❌ DART 스캔 실패: {e}")

async def longterm_scan():
    """30분마다 중장기 매수 타이밍"""
    hour = datetime.now().hour
    if not (9 <= hour < 16 or hour >= 21 or hour < 4):
        return
    try:
        nc      = NewsCollector()
        news    = nc.collect_news(max_per_feed=3)
        signals = await ltm.scan_all_themes(news)
        if signals:
            msg = ltm.build_alert_message(signals)
            if msg:
                for s in signals:
                    key = f"longterm_{s['ticker']}"
                    if ltm._can_alert(key, cooldown_hours=24):
                        await send(msg)
                        break
    except Exception as e:
        print(f"  ❌ 중장기 스캔 실패: {e}")

async def highlow_scan():
    """30분마다 신고가 + 거래량 이상 감지"""
    hour = datetime.now().hour
    if not (9 <= hour < 16):
        return
    try:
        kr_signals = hl.scan_signals("KR")
        messages   = hl.build_alert_messages(kr_signals, [])
        for msg in messages:
            await send(msg)
    except Exception as e:
        print(f"  ❌ 신고가 스캔 실패: {e}")

async def risk_analysis():
    """08:10 포트폴리오 리스크 분석"""
    print(f"[{datetime.now().strftime('%H:%M')}] ⚠️ 리스크 분석")
    try:
        rm.portfolio     = rm._load_portfolio()
        sector_ratio, _  = rm.calc_sector_concentration()
        metrics          = rm.calc_risk_metrics()
        fx_data          = rm.calc_exchange_rate_risk()
        upgrades         = rm.check_stop_loss_upgrade()
        ai_result        = await rm.ai_risk_analysis(sector_ratio, metrics, fx_data)
        msg              = rm.build_risk_message(sector_ratio, metrics, fx_data, ai_result, upgrades)
        await send(msg)
    except Exception as e:
        print(f"  ❌ 리스크 분석 실패: {e}")

async def us_premarket_analysis():
    """21:00 미국 프리마켓 분석"""
    print(f"[{datetime.now().strftime('%H:%M')}] 🌙 미국 프리마켓")
    try:
        from modules.premarket_futures import PremarketFutures
        pf_us    = PremarketFutures()
        analysis = await pf_us.analyze_us_premarket()
        msg      = pf_us.build_us_message(analysis)
        await send(msg)
    except Exception as e:
        print(f"  ❌ 미국 프리마켓 실패: {e}")

async def intraday_scan():
    if is_weekend():
        return
    hour = datetime.now().hour
    if (9 <= hour < 16) or (hour >= 21 or hour < 4):
        await smart_scan()

# ── 스케줄 스레드 ──
def run_schedule_job(coro_func):
    """스케줄 작업 안전 실행 - 에러나도 계속 동작"""
    try:
        asyncio.run(coro_func())
    except Exception as e:
        print(f"⚠️ 스케줄 작업 에러 ({coro_func.__name__}): {e}")

# ③ 주말 전용 스케줄 함수들
 
async def weekend_us_closing():
    """토 06:00 미국장 주간 결산 + 보유 미국주식 점검"""

    if not is_saturday():
        return

    print(f"[{datetime.now().strftime('%H:%M')}] 🌙 주말 미국장 주간 결산")

    try:
        import yfinance as yf
        from modules.kis_api import KISApi

        kis = KISApi()

        # 미국 주요 지수 주간 성과
        indices = {
            "나스닥": "^IXIC",
            "S&P500": "^GSPC",
            "다우": "^DJI",
            "VIX": "^VIX"
        }

        idx_text = ""

        for name, ticker in indices.items():
            try:
                hist = yf.Ticker(ticker).history(period="5d").dropna()

                if len(hist) >= 2:
                    week_change = (
                        (hist['Close'].iloc[-1] - hist['Close'].iloc[0])
                        / hist['Close'].iloc[0]
                    ) * 100

                    day_change = (
                        (hist['Close'].iloc[-1] - hist['Close'].iloc[-2])
                        / hist['Close'].iloc[-2]
                    ) * 100

                    arrow = "▲" if week_change > 0 else "▼"

                    idx_text += (
                        f"  {arrow} {name}: "
                        f"주간{week_change:+.2f}% / 금일{day_change:+.2f}%\n"
                    )
            except:
                pass

        # 보유 미국주식 점검
        us_stocks = {
            t: s for t, s in pf.portfolio.items()
            if s.get('market') == 'US'
        }

        portfolio_text = ""

        for ticker, stock in list(us_stocks.items())[:8]:
            for excd in ["NAS", "NYS"]:
                data = kis.get_us_price(ticker, excd)

                if data and data.get('price', 0) > 0:
                    buy_price = stock.get('buy_price', 0)
                    curr_price = data['price']

                    profit_pct = (
                        ((curr_price - buy_price) / buy_price) * 100
                        if buy_price > 0 else 0
                    )

                    arrow = "▲" if profit_pct > 0 else "▼"

                    portfolio_text += (
                        f"  {arrow} {stock.get('name', ticker)}: "
                        f"${curr_price} ({profit_pct:+.1f}%)\n"
                    )
                    break

        # 메시지 구성
        msg  = f"🌙 <b>주간 미국장 결산</b> {datetime.now().strftime('%m/%d')}\n\n"
        msg += f"📊 <b>주간 지수 성과</b>\n{idx_text}\n"

        if portfolio_text:
            msg += f"💼 <b>보유 미국주식</b>\n{portfolio_text}\n"

        msg += f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M')}"

        # 전송
        await send(msg)

        # ✅ 환율 주간 요약 추가 (여기가 핵심 위치)
        current_rate = fx.get_current_rate()
        fx_summary = fx.build_weekly_fx_summary(pf.portfolio, current_rate)

        if fx_summary:
            await send(fx_summary)

        print("  ✅ 미국장 주간 결산 + 환율 요약 완료")

    except Exception as e:
        print(f"  ❌ 미국장 주간 결산 실패: {e}")
 
async def weekend_backtest_summary():
    """토 08:00 이번 주 모의 수익률 결산"""
    if not is_saturday():
        return
    print(f"[{datetime.now().strftime('%H:%M')}] 📊 주간 백테스트 결산")
    try:
        bt  = BacktestSystem()
        bt.update_prices()
        msg = bt.build_report(days=7)
        header = f"📊 <b>이번 주 모의 테스트 결산</b>\n\n"
        await send(header + msg)
        print("  ✅ 주간 백테스트 결산 완료")
    except Exception as e:
        print(f"  ❌ 주간 백테스트 결산 실패: {e}")
  
async def weekend_sector_flow():
    """토 10:00 섹터 자금 흐름 총정리"""
    if not is_saturday():
        return
    print(f"[{datetime.now().strftime('%H:%M')}] 📈 주간 섹터 흐름 분석")
    try:
        context = await mt.select_sectors(regime.current_regime.get('regime', '강세'))
        if context:
            msg = mt.build_briefing_message()
            header = f"📈 <b>주간 섹터 자금 흐름 총정리</b>\n\n"
            await send(header + msg)
        print("  ✅ 섹터 흐름 분석 완료")
    except Exception as e:
        print(f"  ❌ 섹터 흐름 분석 실패: {e}")
 
 
async def weekend_macro_check():
    """일 08:00 글로벌 매크로 점검"""
    if not is_sunday():
        return
    print(f"[{datetime.now().strftime('%H:%M')}] 🌍 주말 매크로 점검")
    try:
        from anthropic import Anthropic
        import yfinance as yf
 
        # 주말 뉴스 수집
        nc       = NewsCollector()
        news     = nc.collect_news(max_per_feed=5)
        filtered = nc.filter_by_importance(news)
        news_text = "\n".join([f"{'🔴' if n.get('importance')=='high' else '🟡'} {n['title'][:60]}" for n in filtered[:10]])
 
        # 매크로 데이터
        macro_data = {}
        for name, ticker in {"달러인덱스": "DX-Y.NYB", "금": "GC=F", "WTI": "CL=F", "미국10년채권": "^TNX"}.items():
            try:
                hist = yf.Ticker(ticker).history(period="5d").dropna()
                if len(hist) >= 2:
                    change = ((hist['Close'].iloc[-1] - hist['Close'].iloc[0]) / hist['Close'].iloc[0]) * 100
                    macro_data[name] = round(change, 2)
            except:
                pass
 
        macro_text = "\n".join([f"  {'▲' if v > 0 else '▼'} {k}: {v:+.2f}%" for k, v in macro_data.items()])
 
        client = Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))
        prompt = f"""주말 글로벌 매크로를 점검해주세요.
 
=== 주간 매크로 변화 ===
{macro_text}
 
=== 주말 주요 뉴스 ===
{news_text}
 
다음을 한국어로 간단히:
1. 이번 주 매크로 핵심 변화 2가지
2. 다음 주 한국 시장 영향
3. 주목할 이벤트 (FOMC/CPI/실적 등)
4. 다음 주 유망 섹터 힌트"""
 
        res = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}]
        )
 
        msg  = f"🌍 <b>주말 글로벌 매크로 점검</b> {datetime.now().strftime('%m/%d')}\n\n"
        msg += f"📊 <b>주간 매크로</b>\n{macro_text}\n\n"
        msg += f"🧠 <b>AI 분석</b>\n{res.content[0].text}\n"
        msg += f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        await send(msg)
        print("  ✅ 매크로 점검 완료")
    except Exception as e:
        print(f"  ❌ 매크로 점검 실패: {e}")
 
 
async def weekend_social_collect():
    """일 20:00 주말 뉴스 + 소셜 반응 수집"""
    if not is_sunday():
        return
    print(f"[{datetime.now().strftime('%H:%M')}] 📱 주말 소셜 수집")
    try:
        import aiohttp
 
        nc       = NewsCollector()
        news     = nc.collect_news(max_per_feed=5)
        filtered = nc.filter_by_importance(news)
 
        # StockTwits 주요 종목 소셜 반응
        us_tickers = [t for t, s in pf.portfolio.items() if s.get('market') == 'US']
        social_text = ""
        async with aiohttp.ClientSession() as session:
            for ticker in us_tickers[:5]:
                try:
                    url = f"https://api.stocktwits.com/api/2/streams/symbol/{ticker}.json"
                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                        if resp.status == 200:
                            data      = await resp.json()
                            messages  = data.get("messages", [])[:5]
                            sentiment = [m.get("entities", {}).get("sentiment", {}).get("basic", "") for m in messages]
                            bull      = sentiment.count("Bullish")
                            bear      = sentiment.count("Bearish")
                            social_text += f"  {ticker}: 강세 {bull} / 약세 {bear}\n"
                except:
                    pass
 
        news_text = "\n".join([f"  {'🔴' if n.get('importance')=='high' else '🟡'} {n['title'][:50]}" for n in filtered[:8]])
 
        msg  = f"📱 <b>주말 뉴스 + 소셜 반응</b> {datetime.now().strftime('%m/%d %H:%M')}\n\n"
        msg += f"📰 <b>주말 주요 뉴스</b>\n{news_text}\n\n"
        if social_text:
            msg += f"💬 <b>StockTwits 반응</b>\n{social_text}\n"
        msg += f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        await send(msg)
        print("  ✅ 소셜 수집 완료")
    except Exception as e:
        print(f"  ❌ 소셜 수집 실패: {e}")
 
 
async def monday_weekly_briefing():
    """월 07:00 이번 주 전략 브리핑 (평일 매크로 브리핑 대체)"""
    if not is_monday():
        return
    print(f"[{datetime.now().strftime('%H:%M')}] 📅 월요일 주간 전략 브리핑")
    try:
        from anthropic import Anthropic
 
        # 뉴스 수집
        nc       = NewsCollector()
        news     = nc.collect_news(max_per_feed=5)
        filtered = nc.filter_by_importance(news)
        news_text = "\n".join([f"{'🔴' if n.get('importance')=='high' else '🟡'} {n['title'][:60]}" for n in filtered[:10]])
 
        # 레이어 1 섹터 선정
        r       = regime.current_regime
        context = await mt.select_sectors(r.get('regime', '강세'))
 
        sector_text = ""
        if context:
            ai_result = context.get("ai_result", {})
            for s in ai_result.get("selected_sectors", []):
                sector_text += f"  🎯 {s['kr_sector']} — {s['reason']}\n"
 
        # AI 주간 전략
        client = Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))
        prompt = f"""이번 주 한국/미국 주식 투자 전략을 알려주세요.
직장인 투자자 맞춤 (정규장 09:00 진입 불가, NXT 활용)
 
=== 장세 ===
{r.get('regime', '?')}장
 
=== 이번 주 유망 섹터 ===
{sector_text}
 
=== 주말 주요 뉴스 ===
{news_text}
 
다음을 간단히:
1. 이번 주 시장 키워드 3개
2. 이번 주 전략 (공격/중립/방어)
3. 주목할 한국 섹터 2개 + 이유
4. 주목할 미국 섹터/종목 1개 + 이유
5. 이번 주 주의사항
6. 이번 주 주요 이벤트 일정"""
 
        res = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=600,
            messages=[{"role": "user", "content": prompt}]
        )
 
        em  = regime.get_regime_emoji()
        msg  = f"📅 <b>이번 주 전략 브리핑</b> {datetime.now().strftime('%m/%d')}\n"
        msg += f"{em} {r.get('regime', '?')}장\n\n"
        if sector_text:
            msg += f"🎯 <b>이번 주 주력 섹터</b>\n{sector_text}\n"
        msg += f"🧠 <b>AI 주간 전략</b>\n{res.content[0].text}\n"
        msg += f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        await send(msg)
        print("  ✅ 월요일 주간 브리핑 완료")
    except Exception as e:
        print(f"  ❌ 월요일 브리핑 실패: {e}")

# 스케줄 함수 추가 (schedule_thread 위에)
async def gamble_weekly_review():
    """토요일 12:00 도박 watchlist AI 검토"""
    print(f"[{datetime.now().strftime('%H:%M')}] 🎰 도박 watchlist 주간 검토")
    try:
        msg = await gm.weekly_review()
        await send(msg)
        print("  ✅ 도박 watchlist 검토 완료")
    except Exception as e:
        print(f"  ❌ 도박 watchlist 검토 실패: {e}")

# ① 평일/주말 판단 헬퍼 함수 추가 (schedule_thread 위에)
 
def is_weekday():
    """평일 여부 (월~금)"""
    return datetime.now().weekday() < 5
 
def is_weekend():
    """주말 여부 (토~일)"""
    return datetime.now().weekday() >= 5
 
def is_saturday():
    return datetime.now().weekday() == 5
 
def is_sunday():
    return datetime.now().weekday() == 6
 
def is_monday():
    return datetime.now().weekday() == 0

def schedule_thread():

    schedule.every().day.at("00:00").do(run_schedule_job, update_event_calendar)
    # 새벽
    schedule.every().day.at("05:00").do(run_schedule_job, premarket_morning_scan)
    # 아침
    schedule.every().day.at("06:00").do(run_schedule_job, run_daily_rotation)
    schedule.every().day.at("07:00").do(run_schedule_job, morning_briefing)
    schedule.every().day.at("07:00").do(run_schedule_job, earnings_check)
    schedule.every().day.at("07:30").do(run_schedule_job, short_term_recommendation)
    # 장전
    schedule.every().day.at("08:00").do(run_schedule_job, save_asset_snapshot)
    schedule.every().day.at("08:00").do(run_schedule_job, us_market_closing_analysis)
    schedule.every().day.at("08:10").do(run_schedule_job, morning_portfolio_diagnosis)
    schedule.every().day.at("08:10").do(run_schedule_job, risk_analysis)
    schedule.every().day.at("08:30").do(run_schedule_job, nxt_analysis)
    # 장중
    schedule.every().day.at("09:05").do(run_schedule_job, run_supply_scan)
    schedule.every().day.at("09:05").do(run_schedule_job, dart_scan)
    schedule.every().day.at("13:00").do(run_schedule_job, run_supply_scan)
    schedule.every().day.at("13:00").do(run_schedule_job, dart_scan)
    # 장마감
    schedule.every().day.at("14:30").do(run_schedule_job, afternoon_recommendation)
    schedule.every().day.at("15:40").do(run_schedule_job, closing_summary)
    # 저녁
    schedule.every().day.at("19:50").do(run_schedule_job, nxt_closing_summary)
    # 미국장
    schedule.every().day.at("20:30").do(run_schedule_job, us_pre_trading_briefing)
    schedule.every().day.at("21:00").do(run_schedule_job, us_premarket_analysis)
    schedule.every().day.at("23:30").do(run_schedule_job, us_lowpoint_scan)
    # 실시간
    schedule.every(30).minutes.do(run_schedule_job, intraday_scan)
    schedule.every(30).minutes.do(run_schedule_job, longterm_scan)
    schedule.every(30).minutes.do(run_schedule_job, highlow_scan)
    schedule.every(30).minutes.do(run_schedule_job, backtest_price_check)
    
    # 주말 스케줄
    schedule.every().saturday.at("06:00").do(run_schedule_job, weekend_us_closing)
    schedule.every().saturday.at("08:00").do(run_schedule_job, weekend_backtest_summary)
    schedule.every().saturday.at("10:00").do(run_schedule_job, weekend_sector_flow)
    schedule.every().sunday.at("08:00").do(run_schedule_job, weekend_macro_check)
    schedule.every().sunday.at("20:00").do(run_schedule_job, weekend_social_collect)
    schedule.every().monday.at("07:00").do(run_schedule_job, monday_weekly_briefing)

    # 주말 도박 watchlist 검토 (토요일 12:00)
    schedule.every().saturday.at("12:00").do(run_schedule_job, gamble_weekly_review)
    print("✅ 스케줄 등록 완료")
    print("  05:00 상한가 후보")
    print("  06:00 순환매 분석")
    print("  07:00 매크로 브리핑 + 실적 체크")
    print("  07:30 한국 단기 추천")
    print("  08:00 미국장 마감 분석 + 헬스체크")
    print("  08:10 포트폴리오 진단 + 리스크 분석")
    print("  08:30 NXT 분석 (NXT 데이터 쌓인 후)")
    print("  09:05 수급 + DART 공시")
    print("  13:00 수급 + DART 공시")
    print("  14:30 내일 선점 추천")
    print("  15:40 마감 분석 + 내일 추천")
    print("  19:50 NXT 마감 요약")
    print("  20:30 미국장 전 브리핑")
    print("  21:00 미국 프리마켓")
    print("  30분마다 장중스캔+포트폴리오+중장기+신고가")
    print("✅ 스케줄 등록")
    while True:
        schedule.run_pending()
        time.sleep(60)

# ── 실시간 모니터 스레드 ──
def realtime_thread():
    async def run():
        rt = RealtimeMonitor(
            alert_callback=send,
            monitor=monitor,
            regime=regime
        )
        await rt.run_forever(interval_sec=300)
    asyncio.run(run())

# ── 메인 ──
def main():
    print("=" * 50)
    print("🚀 주식 AI 에이전트 v4.0")
    print("=" * 50)
    r      = regime.analyze_regime()
    params = regime.get_strategy_params()
    em     = regime.get_regime_emoji()
    print(f"{em} 장세: {r['regime']}장")
    print(f"⚔️ 전략: {params['description']}")

    # 스케줄러 스레드
    t1 = threading.Thread(target=schedule_thread, daemon=True)
    t1.start()

    # 실시간 모니터 스레드
    t2 = threading.Thread(target=realtime_thread, daemon=True)
    t2.start()

    from modules.sector_db import get_all_tickers as _gat
    _kr = len(_gat('KR'))
    _us = len(_gat('US'))
    asyncio.run(send(f"""🚀 <b>주식 AI 에이전트 v4.0 가동!</b>

{em} 장세: <b>{r['regime']}장</b>
⚔️ {params['description']}
⚡ 실시간 모니터: 5분마다 감시
🤖 Claude Sonnet 4.6
📊 한국 {_kr}개 + 미국 {_us}개 종목 감시
📱 /start 명령어 확인"""))

    token = os.getenv('TELEGRAM_BOT_TOKEN')
    app   = Application.builder().token(token).updater(None).build()
    app.add_handler(CommandHandler("start",    cmd_start))
    app.add_handler(CommandHandler("status",   cmd_status))
    app.add_handler(CommandHandler("regime",   cmd_regime))
    app.add_handler(CommandHandler("list",     cmd_list))
    app.add_handler(CommandHandler("add",      cmd_add))
    app.add_handler(CommandHandler("remove",   cmd_remove))
    app.add_handler(CommandHandler("check",    cmd_check))
    app.add_handler(CommandHandler("market",   cmd_market))
    app.add_handler(CommandHandler("scan",     cmd_scan))
    app.add_handler(CommandHandler("trend",    cmd_trend))
    app.add_handler(CommandHandler("briefing", cmd_briefing))
    app.add_handler(CommandHandler("supply",     cmd_supply))
    app.add_handler(CommandHandler("portfolio",  cmd_portfolio))
    app.add_handler(CommandHandler("buy",        cmd_buy))
    app.add_handler(CommandHandler("sell",       cmd_sell))
    app.add_handler(CommandHandler("diagnosis",  cmd_diagnosis))
    app.add_handler(CommandHandler("news_impact", cmd_news_impact))
    app.add_handler(CommandHandler("accuracy",    cmd_accuracy))
    app.add_handler(CommandHandler("premarket",   cmd_premarket))
    app.add_handler(CommandHandler("leverage",    cmd_leverage))
    app.add_handler(CommandHandler("themes",      cmd_themes))
    app.add_handler(CommandHandler("add_sector",  cmd_add_sector))
    app.add_handler(CommandHandler("gamble", cmd_gamble))
    app.add_handler(CommandHandler("backtest", cmd_backtest))
    app.add_handler(CommandHandler("buy_rate", cmd_buy_rate))
    app.add_handler(CommandHandler("loss", cmd_loss))
    app.add_handler(CommandHandler("analyze", cmd_analyze))

    print("🤖 봇 대기 중...")

    async def error_handler(update, context):
        print(f"⚠️ 텔레그램 에러: {context.error}")
        # 네트워크 에러면 5초 후 재시도
        await asyncio.sleep(5)

    app.add_error_handler(error_handler)

    # 봇 연결 끊겨도 자동 재연결
    async def run_bot():
        await app.bot.delete_webhook(drop_pending_updates=True)
        print("✅ 텔레그램 봇 시작")
        async with app:
            await app.start()
            await asyncio.Event().wait()

    asyncio.run(run_bot())

if __name__ == "__main__":
    main()
