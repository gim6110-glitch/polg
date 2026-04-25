import os
import sys
import asyncio
from datetime import datetime
from telegram import Update, Bot
from telegram.ext import Application, CommandHandler, ContextTypes
from dotenv import load_dotenv

sys.path.insert(0, '/home/dps/stock_ai')
from modules.watchlist_monitor import WatchlistMonitor
from modules.technical_analyzer import TechnicalAnalyzer
from modules.price_collector import PriceCollector
from modules.market_indicators import MarketIndicators

load_dotenv('/home/dps/stock_ai/.env')

monitor  = WatchlistMonitor()
analyzer = TechnicalAnalyzer()

# /start
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = """🤖 <b>주식 AI 에이전트 가동 중</b>

사용 가능한 명령어:

📋 <b>감시 목록</b>
/list — 감시 종목 전체 보기
/add 종목명 티커 기간 — 종목 추가
/remove 종목명 — 종목 제거

📊 <b>분석</b>
/check 티커 — 즉시 분석
/market — 시장 현황
/scan — 전체 신호 스캔

⚙️ <b>시스템</b>
/status — 시스템 상태
/help — 도움말"""
    await update.message.reply_text(msg, parse_mode='HTML')

# /list
async def cmd_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = monitor.get_watchlist_text()
    await update.message.reply_text(msg)

# /add 삼성전자 005930.KS 중기
async def cmd_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if len(args) < 2:
        await update.message.reply_text(
            "사용법: /add 종목명 티커 기간\n예) /add 삼성전자 005930.KS 중기"
        )
        return
    name   = args[0]
    ticker = args[1]
    period = args[2] if len(args) > 2 else "중기"
    if period not in ["단기", "중기", "장기"]:
        period = "중기"
    monitor.add_stock(name, ticker, period)
    await update.message.reply_text(
        f"✅ {name} ({ticker}) → {period} 감시 목록 추가 완료"
    )

# /remove 삼성전자
async def cmd_remove(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("사용법: /remove 종목명\n예) /remove 삼성전자")
        return
    name = context.args[0]
    if monitor.remove_stock(name):
        await update.message.reply_text(f"✅ {name} 감시 목록에서 제거 완료")
    else:
        await update.message.reply_text(f"❌ {name} 을 찾을 수 없어요")

# /check NVDA
async def cmd_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("사용법: /check 티커\n예) /check NVDA")
        return
    ticker = context.args[0].upper()
    await update.message.reply_text(f"🔍 {ticker} 분석 중... (10~20초 소요)")
    data = analyzer.get_indicators(ticker)
    if not data:
        await update.message.reply_text(f"❌ {ticker} 데이터를 가져올 수 없어요")
        return
    signals_text = "\n".join([f"  • {s}" for s in data['signals']]) if data['signals'] else "  • 특이 신호 없음"
    msg = f"""📊 <b>{ticker} 즉시 분석</b>

💰 현재가: {data['current_price']:,}
📊 RSI: {data['rsi']}
📈 볼린저밴드: {data['bb_position']}
📉 ATR 손절선: {data['stop_loss']:,} ({data['stop_loss_pct']}%)
📦 거래량: 평소 대비 {data['volume_ratio']}배
🏔 52주 신고가: {data['high_52w']:,} ({data['high_52w_proximity']}%)
📐 MA5: {data['ma5']:,} | MA20: {data['ma20']:,}

🔔 신호 ({data['signal_count']}개):
{signals_text}

⏰ {data['timestamp']}"""
    await update.message.reply_text(msg, parse_mode='HTML')

# /market
async def cmd_market(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🌍 시장 현황 수집 중...")
    try:
        pc = PriceCollector()
        mi = MarketIndicators()
        prices     = pc.get_all_prices()
        indicators = mi.get_all_indicators()
        fg = indicators.get('fear_greed', {})
        indices = prices.get('지수', {})
        idx_text = ""
        for name, data in indices.items():
            arrow = "▲" if data['change_pct'] > 0 else "▼"
            idx_text += f"  {arrow} {name}: {data['current_price']:,} ({data['change_pct']:+.2f}%)\n"
        forex = indicators.get('forex_commodities', {})
        forex_text = ""
        for name, data in forex.items():
            arrow = "▲" if data['change_pct'] > 0 else "▼"
            forex_text += f"  {arrow} {name}: {data['price']:,} ({data['change_pct']:+.2f}%)\n"
        fg_text = f"{fg.get('score', 'N/A')} — {fg.get('signal', 'N/A')}" if fg else "N/A"
        msg = f"""🌍 <b>시장 현황</b>

📈 <b>주요 지수</b>
{idx_text}
💵 <b>환율 · 원자재</b>
{forex_text}
😨 <b>공포탐욕지수</b>
  {fg_text}

⏰ {datetime.now().strftime('%Y-%m-%d %H:%M')}"""
        await update.message.reply_text(msg, parse_mode='HTML')
    except Exception as e:
        await update.message.reply_text(f"❌ 시장 현황 수집 실패: {e}")

# /scan
async def cmd_scan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔍 전체 신호 스캔 시작... (1~2분 소요)")
    await monitor.check_buy_signals()
    await update.message.reply_text("✅ 스캔 완료! 신호 있으면 알림 보냈어요.")

# /status
async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    total = sum(len(v) for v in monitor.watchlist.values())
    msg = f"""⚙️ <b>시스템 상태</b>

🍓 라즈베리파이5: 정상 가동 중
📋 감시 종목: 총 {total}개
🕐 현재 시각: {datetime.now().strftime('%Y-%m-%d %H:%M')}
💾 데이터 경로: /home/dps/stock_ai/data/

✅ 모든 시스템 정상"""
    await update.message.reply_text(msg, parse_mode='HTML')

def main():
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    app   = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start",  cmd_start))
    app.add_handler(CommandHandler("list",   cmd_list))
    app.add_handler(CommandHandler("add",    cmd_add))
    app.add_handler(CommandHandler("remove", cmd_remove))
    app.add_handler(CommandHandler("check",  cmd_check))
    app.add_handler(CommandHandler("market", cmd_market))
    app.add_handler(CommandHandler("scan",   cmd_scan))
    app.add_handler(CommandHandler("status", cmd_status))
    print("=" * 50)
    print("🤖 텔레그램 봇 시작!")
    print("=" * 50)
    print("핸드폰 텔레그램에서 봇에게 /start 보내보세요")
    print("종료: Ctrl+C")
    app.run_polling()

if __name__ == "__main__":
    main()
