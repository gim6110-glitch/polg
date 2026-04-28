# /media/dps/T7/stock_ai/bigtech_monitor.py

import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
import json
import os

BASE_DIR = "/media/dps/T7/stock_ai"
STRATEGY_FILE = os.path.join(BASE_DIR, "dynamic_strategy.json")

BIGTECH_TICKERS = {
    'NVDA': '엔비디아',
    'GOOGL': '구글',
    'MSFT': '마이크로소프트',
    'AVGO': '브로드컴',
    'AAPL': '애플',
    'META': '메타',
    'AMZN': '아마존',
}

def load_strategy():
    try:
        with open(STRATEGY_FILE) as f:
            return json.load(f)
    except:
        return {'cycle': '강세장', 'recommended_position': 80}

def get_bigtech_data(ticker: str) -> dict:
    """yfinance로 빅테크 데이터 수집"""
    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period='60d').dropna()
        if hist.empty or len(hist) < 20:
            return {}
        
        current = hist['Close'].iloc[-1]
        ma5   = hist['Close'].rolling(5).mean().iloc[-1]
        ma20  = hist['Close'].rolling(20).mean().iloc[-1]
        ma60  = hist['Close'].rolling(60).mean().iloc[-1] if len(hist) >= 60 else ma20
        
        high_52w = hist['Close'].rolling(min(252, len(hist))).max().iloc[-1]
        low_52w  = hist['Close'].rolling(min(252, len(hist))).min().iloc[-1]
        
        # RSI
        delta = hist['Close'].diff()
        gain = delta.clip(lower=0).rolling(14).mean()
        loss = (-delta.clip(upper=0)).rolling(14).mean()
        rs = gain / loss.replace(0, 0.0001)
        rsi = float((100 - 100 / (1 + rs)).iloc[-1])
        
        # 변동성 (20일 표준편차)
        vol_20d = float(hist['Close'].pct_change().rolling(20).std().iloc[-1] * 100)
        
        # 52주 고점 대비 하락률
        drawdown_from_high = (current - high_52w) / high_52w * 100
        
        # 52주 저점 대비 상승률
        rise_from_low = (current - low_52w) / low_52w * 100
        
        return {
            'ticker': ticker,
            'name': BIGTECH_TICKERS.get(ticker, ticker),
            'current': round(current, 2),
            'ma5': round(ma5, 2),
            'ma20': round(ma20, 2),
            'ma60': round(ma60, 2),
            'rsi': round(rsi, 1),
            'vol_20d': round(vol_20d, 2),
            'drawdown_from_high': round(drawdown_from_high, 1),
            'rise_from_low': round(rise_from_low, 1),
            'high_52w': round(high_52w, 2),
            'low_52w': round(low_52w, 2),
        }
    except Exception as e:
        return {'ticker': ticker, 'error': str(e)}

def judge_bigtech(data: dict, cycle: str) -> dict:
    """규칙 기반 빅테크 판단 (AI 호출 없음)"""
    if 'error' in data or not data:
        return {'signal': '오류', 'reason': data.get('error', '데이터 없음')}
    
    current = data['current']
    ma5, ma20, ma60 = data['ma5'], data['ma20'], data['ma60']
    rsi = data['rsi']
    drawdown = data['drawdown_from_high']
    rise_from_low = data['rise_from_low']
    
    signals = []
    bubble_score = 0
    dip_score = 0
    
    # ── 버블 감지 ──────────────────────────────
    if rsi >= 85:
        bubble_score += 3
        signals.append(f"RSI {rsi:.0f} 과열")
    elif rsi >= 75:
        bubble_score += 1
        signals.append(f"RSI {rsi:.0f} 주의")
    
    if drawdown > -5:  # 52주 고점 5% 이내
        bubble_score += 2
        signals.append("52주 고점 근접")
    
    # 가속 상승: 5일선이 20일선보다 10% 이상 위
    if ma5 > ma20 * 1.10:
        bubble_score += 2
        signals.append("단기 과열 상승")
    
    # ── 저점 판단 (강세장 저점 매수 기회) ──────────
    if drawdown <= -20:
        dip_score += 3
        signals.append(f"고점 대비 {drawdown:.0f}% 급락")
    elif drawdown <= -10:
        dip_score += 2
        signals.append(f"고점 대비 {drawdown:.0f}% 조정")
    
    if rsi <= 35:
        dip_score += 3
        signals.append(f"RSI {rsi:.0f} 과매도")
    elif rsi <= 45:
        dip_score += 1
        signals.append(f"RSI {rsi:.0f} 저점 근접")
    
    # 5일선이 20일선 아래 → 단기 눌림
    if ma5 < ma20 and ma20 > ma60:  # 중장기는 정배열
        dip_score += 1
        signals.append("중장기 정배열 + 단기 눌림")
    
    # 장세 보정
    if cycle in ('강세장', '상승가속'):
        dip_score += 1  # 강세장에서 저점 가중
    elif cycle in ('조정중', '조정초입'):
        bubble_score -= 1
        dip_score -= 1  # 조정장에서는 신중
    
    # 최종 판단
    if bubble_score >= 5:
        signal = '버블경고'
        action = '비중축소 검토'
    elif bubble_score >= 3:
        signal = '과열주의'
        action = '신규매수 자제'
    elif dip_score >= 5 and cycle in ('강세장', '상승가속', '과열경계'):
        signal = '저점매수기회'
        action = '분할매수 검토'
    elif dip_score >= 3:
        signal = '눌림목'
        action = '관찰 유지'
    else:
        signal = '중립'
        action = '보유 유지'
    
    return {
        'signal': signal,
        'action': action,
        'bubble_score': bubble_score,
        'dip_score': dip_score,
        'signals': signals,
    }

async def analyze_bigtech(send_func) -> str:
    """빅테크 모니터 전체 실행 → 텔레그램 전송"""
    strategy = load_strategy()
    cycle = strategy.get('cycle', '강세장')
    
    results = []
    alert_tickers = []  # 즉시 알림 대상
    
    for ticker in BIGTECH_TICKERS:
        data = get_bigtech_data(ticker)
        judgment = judge_bigtech(data, cycle)
        results.append((data, judgment))
        
        if judgment['signal'] in ('저점매수기회', '버블경고'):
            alert_tickers.append((data, judgment))
    
    # 즉시 알림 (저점 or 버블)
    if alert_tickers:
        alert_lines = [f"[빅테크 알림] 장세: {cycle}"]
        for d, j in alert_tickers:
            name = d.get('name', d.get('ticker'))
            ticker = d.get('ticker')
            current = d.get('current', '?')
            signal = j['signal']
            action = j['action']
            sigs = ', '.join(j.get('signals', []))
            alert_lines.append(
                f"{name}({ticker}) ${current}\n"
                f"  신호: {signal}\n"
                f"  조치: {action}\n"
                f"  근거: {sigs}"
            )
        await send_func('\n\n'.join(alert_lines))
    
    # 전체 요약
    summary_lines = [f"[빅테크 모니터] 장세: {cycle}"]
    for d, j in results:
        if 'error' in d:
            continue
        name = d.get('name', d.get('ticker'))
        ticker = d.get('ticker')
        current = d.get('current', '?')
        rsi = d.get('rsi', '?')
        drawdown = d.get('drawdown_from_high', '?')
        signal = j['signal']
        summary_lines.append(
            f"{name}({ticker}) ${current}\n"
            f"  RSI {rsi} | 고점대비 {drawdown}%\n"
            f"  → {signal}"
        )
    
    return '\n\n'.join(summary_lines)
