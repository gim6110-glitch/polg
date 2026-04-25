import asyncio
from telegram import Bot
from dotenv import load_dotenv
import os

load_dotenv()

async def test():
    bot = Bot(token=os.getenv('TELEGRAM_BOT_TOKEN'))
    await bot.send_message(
        chat_id=os.getenv('TELEGRAM_CHAT_ID'),
        text="✅ 주식 AI 에이전트 연결 성공!\n\n🍓 라즈베리파이5 정상 작동 중"
    )
    print("텔레그램 전송 완료!")

asyncio.run(test())
