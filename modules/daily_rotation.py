import sys
import os
import asyncio
from datetime import datetime
from telegram import Bot
from dotenv import load_dotenv

sys.path.insert(0, '/media/dps/T7/stock_ai')
from modules.news_collector import NewsCollector
from modules.sector_rotation import SectorRotation

load_dotenv('/media/dps/T7/stock_ai/.env')

async def run_daily_rotation(send_func=None):
    """매일 06:00 한국 + 미국 순환매 분석"""
    print(f"[{datetime.now().strftime('%H:%M')}] 🔄 일일 순환매 분석")
    try:
        bot  = Bot(token=os.getenv('TELEGRAM_BOT_TOKEN'))
        chat = os.getenv('TELEGRAM_CHAT_ID')
        nc   = NewsCollector()
        sr   = SectorRotation()
        news = nc.collect_news(max_per_feed=5)

        # 한국 순환매
        hot_kr, results_kr = await sr.get_today_targets(news, market="KR")
        if results_kr:
            msg_kr = sr.build_alert_message(hot_kr, results_kr, market="KR")
            if send_func:
                await send_func(msg_kr)
            else:
                await bot.send_message(chat_id=chat, text=msg_kr, parse_mode='HTML')
            print("  ✅ 한국 순환매 발송")

        await asyncio.sleep(2)

        # 미국 순환매
        hot_us, results_us = await sr.get_today_targets(news, market="US")
        if results_us:
            msg_us = sr.build_alert_message(hot_us, results_us, market="US")
            if send_func:
                await send_func(msg_us)
            else:
                await bot.send_message(chat_id=chat, text=msg_us, parse_mode='HTML')
            print("  ✅ 미국 순환매 발송")

    except Exception as e:
        print(f"  ❌ 순환매 분석 실패: {e}")

if __name__ == "__main__":
    asyncio.run(run_daily_rotation())
