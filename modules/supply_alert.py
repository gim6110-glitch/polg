import sys
import os
import asyncio
from datetime import datetime
from telegram import Bot
from dotenv import load_dotenv

sys.path.insert(0, '/media/dps/T7/stock_ai')
from modules.supply_demand import SupplyDemand

load_dotenv('/media/dps/T7/stock_ai/.env')

def get_dynamic_supply_watch():
    """당일 외국인/기관 순매수 TOP 종목 동적 조회"""
    from modules.kis_api import KISApi
    import requests, json

    kis    = KISApi()
    token  = kis._get_token()
    result = {}

    # KIS API 외국인 순매수 TOP20
    try:
        headers = {
            "Content-Type":  "application/json",
            "authorization": f"Bearer {token}",
            "appkey":        kis.app_key,
            "appsecret":     kis.app_secret,
            "tr_id":         "FHPST01710000",
            "custtype":      "P"
        }
        params = {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_COND_SCR_DIV_CODE":  "16448",
            "FID_INPUT_ISCD":         "0001",
            "FID_DIV_CLS_CODE":       "0",
            "FID_BLNG_CLS_CODE":      "0",
            "FID_TRGT_CLS_CODE":      "111111111",
            "FID_TRGT_EXLS_CLS_CODE": "000000",
            "FID_INPUT_PRICE_1":      "",
            "FID_INPUT_PRICE_2":      "",
            "FID_VOL_CNT":            "",
            "FID_INPUT_DATE_1":       ""
        }
        url = f"{kis.base_url}/uapi/domestic-stock/v1/quotations/foreign-institution-total"
        res = requests.get(url, headers=headers, params=params, timeout=10)
        data = res.json()
        if data.get('rt_cd') == '0':
            for item in data.get('output', [])[:20]:
                name = item.get('hts_kor_isnm', '')
                code = item.get('mksc_shrn_iscd', '')
                if name and code:
                    result[name] = code
    except Exception as e:
        print(f"  ⚠️ KIS 외국인 순매수 조회 실패: {e}")

    # KIS API 기관 순매수 TOP20
    try:
        headers['tr_id'] = "FHPST01710000"
        params['FID_BLNG_CLS_CODE'] = "1"
        url2 = f"{kis.base_url}/uapi/domestic-stock/v1/quotations/foreign-institution-total"
        res  = requests.get(url2, headers=headers, params=params, timeout=10)
        data = res.json()
        if data.get('rt_cd') == '0':
            for item in data.get('output', [])[:20]:
                name = item.get('hts_kor_isnm', '')
                code = item.get('mksc_shrn_iscd', '')
                if name and code and name not in result:
                    result[name] = code
    except Exception as e:
        print(f"  ⚠️ KIS 기관 순매수 조회 실패: {e}")

    # sector_db 대장주 + 2등주 추가
    try:
        from modules.sector_db import SECTOR_DB
        for sector_name, sector_data in SECTOR_DB.items():
            if sector_data.get('market') != 'KR':
                continue
            for tier in ['대장주', '2등주']:
                for name, ticker in sector_data.get(tier, {}).items():
                    if name not in result:
                        result[name] = ticker
    except Exception as e:
        print(f"  ⚠️ 섹터 DB 로드 실패: {e}")

    # 포트폴리오 종목도 포함
    try:
        portfolio_file = "/media/dps/T7/stock_ai/data/portfolio.json"
        if os.path.exists(portfolio_file):
            with open(portfolio_file, 'r') as f:
                portfolio = json.load(f)
            for ticker, stock in portfolio.items():
                if stock.get('market') == 'KR':
                    name = stock.get('name', ticker)
                    result[name] = ticker
    except:
        pass

    # 조회 실패시 기본 종목
    if len(result) < 5:
        result = {
            "삼성전자":           "005930",
            "SK하이닉스":         "000660",
            "한화에어로스페이스":  "012450",
            "LG에너지솔루션":     "373220",
            "LIG넥스원":          "079550",
        }

    print(f"  📊 수급 감시 종목: {len(result)}개 (섹터DB + 포트폴리오 + KIS동적)")
    return result

# 하위 호환성 유지
SUPPLY_WATCH = {
    "삼성전자":           "005930",
    "SK하이닉스":         "000660",
    "한화에어로스페이스":  "012450",
    "LG에너지솔루션":     "373220",
    "LIG넥스원":          "079550",
}

async def run_supply_scan(send_func=None):
    """수급 스캔 실행 + 텔레그램 발송 (메시지 분할)"""
    print(f"[{datetime.now().strftime('%H:%M')}] 💰 수급 스캔 시작")
    try:
        sd      = SupplyDemand()
        watch   = get_dynamic_supply_watch()
        results = sd.scan_supply(watch)

        # 메시지 리스트로 받기
        messages = sd.build_alert_messages(results)

        if messages:
            if send_func:
                # 스케줄러에서 호출 시 — 메시지 하나씩 전송
                for msg in messages:
                    if msg and msg.strip():
                        await send_func(msg)
            else:
                # 직접 실행 시 — 봇으로 직접 전송
                bot  = Bot(token=os.getenv('TELEGRAM_BOT_TOKEN'))
                chat = os.getenv('TELEGRAM_CHAT_ID')
                for msg in messages:
                    if msg and msg.strip():
                        await bot.send_message(
                            chat_id    = chat,
                            text       = msg,
                            parse_mode = 'HTML'
                        )
                        await asyncio.sleep(0.5)
            print(f"  ✅ 수급 알림 전송 완료 ({len(messages)}개 메시지)")
        else:
            print("  ℹ️ 수급 신호 없음")

        return results
    except Exception as e:
        print(f"  ❌ 수급 스캔 실패: {e}")
        return []

def get_supply_summary(results):
    """아침 브리핑용 수급 요약 (짧게)"""
    if not results:
        return "수급 데이터 없음"

    strong  = [r for r in results if r['score'] >= 4]
    warning = [r for r in results if r['score'] < 0]

    text = ""
    if strong:
        text += "💪 강한 매수세:\n"
        for r in strong[:3]:
            f_arrow = "▲" if r['foreign'] > 0 else "▼"
            o_arrow = "▲" if r['organ'] > 0 else "▼"
            text   += f"  • {r['name']}: 외국인{f_arrow} 기관{o_arrow} ★{r['score']}\n"

    if warning:
        text += "⚠️ 주의 종목:\n"
        for r in warning[:2]:
            text += f"  • {r['name']}: 외국인 대량 매도\n"

    return text if text else "특이 수급 없음"

if __name__ == "__main__":
    asyncio.run(run_supply_scan())
