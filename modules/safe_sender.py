import asyncio
import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv('/media/dps/T7/stock_ai/.env')

async def safe_send(bot, chat_id, text, parse_mode='HTML', max_length=4000):
    """
    안전한 텔레그램 전송
    1. 메시지 자동 분할 (4096자 제한)
    2. 네트워크 오류 시 재시도 3회
    3. 에러 로깅
    """
    # 메시지 분할
    chunks = []
    while len(text) > max_length:
        # 줄바꿈 기준으로 분할
        split_at = text.rfind('\n', 0, max_length)
        if split_at == -1:
            split_at = max_length
        chunks.append(text[:split_at])
        text = text[split_at:]
    chunks.append(text)

    for i, chunk in enumerate(chunks):
        if not chunk.strip():
            continue
        # 분할된 경우 표시
        if len(chunks) > 1:
            chunk = f"({i+1}/{len(chunks)})\n{chunk}"

        # 재시도 3회
        for attempt in range(3):
            try:
                await bot.send_message(
                    chat_id=chat_id,
                    text=chunk,
                    parse_mode=parse_mode
                )
                await asyncio.sleep(0.5)
                break
            except Exception as e:
                print(f"  ⚠️ 전송 실패 {attempt+1}/3: {e}")
                if attempt < 2:
                    await asyncio.sleep(5)
                else:
                    print(f"  ❌ 최종 전송 실패: {chunk[:50]}...")
