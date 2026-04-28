# /media/dps/T7/stock_ai/anomaly_detector.py

import yfinance as yf
import aiohttp
import asyncio
from datetime import datetime

# 임계값
VIX_SURGE_PCT = 20      # VIX 20% 급등
KOSPI_DROP_PCT = -2.0   # 코스피 -2% 급락
BIGTECH_DROP_PCT = -5.0 # 빅테크 -5% 급락

BIGTECH_WATCH = ['NVDA', 'GOOGL', 'MSFT', 'AVGO', 'AAPL']

_last_vix = None
_last_kospi = None
_last_bigtech = {}

def get_vix_change() -> float | None:
    """VIX 당일 변동률"""
    try:
        vix = yf.Ticker('^VIX')
        hist = yf.download('^VIX', period='5d', progress=False).dropna()
        if len(hist) < 2:
            return None
        prev = float(hist['Close'].iloc[-2])
        curr = float(hist['Close'].iloc[-1])
        return (curr - prev) / prev * 100
    except:
        return None

async def get_kospi_change() -> float | None:
    """코스피 당일 변동률 (yfinance)"""
    try:
        hist = yf.download('^KS11', period='5d', progress=False).dropna()
        if len(hist) < 2:
            return None
        prev = float(hist['Close'].iloc[-2])
        curr = float(hist['Close'].iloc[-1])
        return (curr - prev) / prev * 100
    except:
        return None

def get_bigtech_changes() -> dict:
    """빅테크 당일 변동률"""
    results = {}
    for ticker in BIGTECH_WATCH:
        try:
            hist = yf.download(ticker, period='5d', progress=False).dropna()
            if len(hist) < 2:
                continue
            prev = float(hist['Close'].iloc[-2])
            curr = float(hist['Close'].iloc[-1])
            chg = (curr - prev) / prev * 100
            results[ticker] = round(chg, 2)
        except:
            pass
    return results

async def check_anomalies(send_func, trigger_regime_func=None):
    """
    장중 이상 신호 감지 (규칙 기반, AI 호출 없음)
    5분마다 실시간 모니터에서 호출
    """
    alerts = []
    now = datetime.now().strftime('%H:%M')
    
    # 1. VIX 급등 체크
    vix_chg = get_vix_change()
    if vix_chg is not None and vix_chg >= VIX_SURGE_PCT:
        alerts.append(
            f"[VIX 급등 경고] {now}\n"
            f"VIX +{vix_chg:.1f}% 급등\n"
            f"→ 공포 지수 급상승, 변동성 확대\n"
            f"→ 신규 진입 자제, 현금 비중 확대 고려"
        )
        # regime 재분석 트리거
        if trigger_regime_func:
            asyncio.create_task(trigger_regime_func())
    
    # 2. 코스피 급락 체크 (장중: 09:05~15:30)
    now_hour = datetime.now().hour
    now_min = datetime.now().minute
    is_market_hours = (9 <= now_hour < 15) or (now_hour == 15 and now_min <= 30)
    
    if is_market_hours:
        kospi_chg = await get_kospi_change()
        if kospi_chg is not None and kospi_chg <= KOSPI_DROP_PCT:
            alerts.append(
                f"[코스피 급락 경고] {now}\n"
                f"코스피 {kospi_chg:.1f}% 하락\n"
                f"→ 전체 시장 위험 신호\n"
                f"→ 손절선 재확인, 추가 매수 보류"
            )
    
    # 3. 빅테크 급락 체크 (미국장: 22:30~05:00)
    is_us_hours = now_hour >= 22 or now_hour < 5
    if is_us_hours:
        bt_changes = get_bigtech_changes()
        for ticker, chg in bt_changes.items():
            if chg <= BIGTECH_DROP_PCT:
                alerts.append(
                    f"[빅테크 급락 알림] {now}\n"
                    f"{ticker} {chg:.1f}% 급락\n"
                    f"→ 강세장 저점 매수 기회 검토\n"
                    f"/bigtech 로 상세 확인"
                )
    
    # 알림 전송
    for alert in alerts:
        await send_func(alert)
    
    return len(alerts) > 0
