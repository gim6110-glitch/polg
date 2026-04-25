import sys
import pandas as pd
import yfinance as yf
from datetime import datetime

sys.path.insert(0, '/home/dps/stock_ai')

class BullishSignals:
    """
    강세장 전용 신호 감지
    눌림목 / 신고가 돌파 / 추세 추종
    """
    def detect_pullback(self, ticker, params):
        """눌림목 매수 신호 감지"""
        try:
            stock = yf.Ticker(ticker)
            df    = stock.history(period="3mo").dropna()
            if len(df) < 20:
                return None

            close   = df['Close']
            current = close.iloc[-1]
            ma5     = close.rolling(5).mean().iloc[-1]
            ma20    = close.rolling(20).mean().iloc[-1]
            high_5d = close.iloc[-6:-1].max()

            # 눌림목 조건
            pullback_pct = ((current - high_5d) / high_5d) * 100
            near_ma20    = abs(current - ma20) / ma20 * 100

            # 거래량 감소 (눌림목 마무리 신호)
            avg_vol    = df['Volume'].rolling(20).mean().iloc[-1]
            recent_vol = df['Volume'].iloc[-3:].mean()
            vol_ratio  = recent_vol / avg_vol if avg_vol > 0 else 1

            signals = []
            score   = 0

            # 1. 조정폭 확인 (너무 적거나 많으면 아님)
            pb = params.get('pullback_pct', -5)
            if pb <= pullback_pct <= -1:
                score += 2
                signals.append(f"✅ 눌림목 구간 ({pullback_pct:.1f}%)")

            # 2. 20일선 근접
            if near_ma20 <= 2:
                score += 2
                signals.append(f"✅ 20일선 지지 근접 ({near_ma20:.1f}%)")

            # 3. 거래량 감소 (조정 마무리)
            if vol_ratio <= 0.8:
                score += 2
                signals.append(f"✅ 거래량 감소 ({vol_ratio:.2f}배) → 조정 마무리")

            # 4. 정배열 유지
            if current > ma5 > ma20:
                score += 2
                signals.append("✅ 정배열 유지 → 추세 건강")

            # 5. 최근 상승 추세 확인 (한 달 수익률)
            month_change = ((current - close.iloc[-20]) / close.iloc[-20]) * 100
            if month_change >= 5:
                score += 1
                signals.append(f"✅ 1개월 {month_change:+.1f}% 상승 추세")

            if score >= 5:
                return {
                    "type": "눌림목_매수",
                    "ticker": ticker,
                    "current_price": round(current, 2),
                    "pullback_pct": round(pullback_pct, 1),
                    "ma20": round(ma20, 2),
                    "volume_ratio": round(vol_ratio, 2),
                    "score": score,
                    "signals": signals,
                    "target_price": round(high_5d * 1.03, 2),
                    "stop_loss": round(ma20 * 0.97, 2),
                }
            return None
        except Exception as e:
            print(f"❌ {ticker} 눌림목 감지 실패: {e}")
            return None

    def detect_breakout(self, ticker, params):
        """52주 신고가 돌파 신호 감지"""
        try:
            stock = yf.Ticker(ticker)
            df    = stock.history(period="1y").dropna()
            if len(df) < 60:
                return None

            close   = df['Close']
            current = close.iloc[-1]
            prev    = close.iloc[-2]
            high_52 = close.iloc[:-1].max()

            # 거래량
            avg_vol = df['Volume'].rolling(20).mean().iloc[-1]
            vol     = df['Volume'].iloc[-1]
            vol_ratio = vol / avg_vol if avg_vol > 0 else 1

            signals = []
            score   = 0

            # 1. 신고가 돌파
            if current > high_52 and prev <= high_52:
                score += 4
                signals.append(f"🚀 52주 신고가 돌파 ({current:,.0f} > {high_52:,.0f})")

            # 2. 신고가 근접 (1% 이내)
            elif (current / high_52) >= 0.99:
                score += 2
                signals.append(f"✅ 52주 신고가 근접 ({(current/high_52*100):.1f}%)")

            # 3. 거래량 폭발 (돌파 신뢰도)
            if vol_ratio >= params.get('volume_min', 1.5):
                score += 2
                signals.append(f"✅ 거래량 폭발 ({vol_ratio:.1f}배)")

            # 4. 당일 강한 상승
            day_change = ((current - prev) / prev) * 100
            if day_change >= 2:
                score += 1
                signals.append(f"✅ 당일 {day_change:+.1f}% 강세")

            if score >= 4:
                return {
                    "type": "신고가_돌파",
                    "ticker": ticker,
                    "current_price": round(current, 2),
                    "high_52w": round(high_52, 2),
                    "volume_ratio": round(vol_ratio, 2),
                    "day_change": round(day_change, 2),
                    "score": score,
                    "signals": signals,
                    "target_price": round(current * 1.05, 2),
                    "stop_loss": round(high_52 * 0.97, 2),
                }
            return None
        except Exception as e:
            print(f"❌ {ticker} 신고가 돌파 감지 실패: {e}")
            return None

    def detect_trend_following(self, ticker, params):
        """추세 추종 신호 (강세장 핵심)"""
        try:
            stock = yf.Ticker(ticker)
            df    = stock.history(period="3mo").dropna()
            if len(df) < 20:
                return None

            close   = df['Close']
            current = close.iloc[-1]
            ma5     = close.rolling(5).mean().iloc[-1]
            ma20    = close.rolling(20).mean().iloc[-1]
            ma60    = close.rolling(60).mean().iloc[-1] if len(df) >= 60 else ma20

            # RSI
            delta    = close.diff()
            gain     = delta.clip(lower=0).rolling(14).mean()
            loss     = (-delta.clip(upper=0)).rolling(14).mean()
            rs       = gain / loss
            rsi      = (100 - (100 / (1 + rs))).iloc[-1]

            avg_vol   = df['Volume'].rolling(20).mean().iloc[-1]
            vol       = df['Volume'].iloc[-1]
            vol_ratio = vol / avg_vol if avg_vol > 0 else 1

            signals = []
            score   = 0

            rsi_min = params.get('rsi_buy_min', 50)
            rsi_max = params.get('rsi_buy_max', 72)

            # 1. RSI 강세 구간
            if rsi_min <= rsi <= rsi_max:
                score += 2
                signals.append(f"✅ RSI 강세 구간 ({rsi:.1f})")

            # 2. 정배열
            if current > ma5 > ma20:
                score += 2
                signals.append("✅ 단기 정배열")
            if ma5 > ma20 > ma60:
                score += 2
                signals.append("✅ 장기 정배열")

            # 3. 거래량 동반
            vol_min = params.get('volume_min', 1.2)
            if vol_ratio >= vol_min:
                score += 1
                signals.append(f"✅ 거래량 동반 ({vol_ratio:.1f}배)")

            # 4. 최근 상승 가속
            week_change = ((current - close.iloc[-5]) / close.iloc[-5]) * 100
            if week_change >= 3:
                score += 1
                signals.append(f"✅ 최근 5일 {week_change:+.1f}% 가속")

            if score >= 5:
                return {
                    "type": "추세_추종",
                    "ticker": ticker,
                    "current_price": round(current, 2),
                    "rsi": round(rsi, 1),
                    "ma5": round(ma5, 2),
                    "ma20": round(ma20, 2),
                    "volume_ratio": round(vol_ratio, 2),
                    "score": score,
                    "signals": signals,
                    "target_price": round(current * 1.07, 2),
                    "stop_loss": round(ma20 * 0.97, 2),
                }
            return None
        except Exception as e:
            print(f"❌ {ticker} 추세 추종 감지 실패: {e}")
            return None

    def scan_bullish(self, stock_dict, params):
        """전체 종목 강세장 신호 스캔"""
        results = []
        for name, ticker in stock_dict.items():
            print(f"  스캔: {name}...")
            use_breakout = params.get('use_breakout', True)
            use_pullback = params.get('use_pullback', True)

            if use_breakout:
                sig = self.detect_breakout(ticker, params)
                if sig:
                    sig['name'] = name
                    results.append(sig)
                    continue

            if use_pullback:
                sig = self.detect_pullback(ticker, params)
                if sig:
                    sig['name'] = name
                    results.append(sig)
                    continue

            sig = self.detect_trend_following(ticker, params)
            if sig:
                sig['name'] = name
                results.append(sig)

        results.sort(key=lambda x: x['score'], reverse=True)
        return results

if __name__ == "__main__":
    from modules.market_regime import MarketRegime
    mr     = MarketRegime()
    regime = mr.analyze_regime()
    params = mr.get_strategy_params()
    bs     = BullishSignals()
    print(f"현재 장세: {regime['regime']}")
    print(f"전략: {params['description']}\n")
    test_stocks = {
        "삼성전자": "005930.KS",
        "SK하이닉스": "000660.KS",
        "NVIDIA": "NVDA",
    }
    results = bs.scan_bullish(test_stocks, params)
    if results:
        for r in results:
            print(f"\n🚀 {r['name']} — {r['type']}")
            for s in r['signals']:
                print(f"  {s}")
            print(f"  목표가: {r['target_price']:,} | 손절가: {r['stop_loss']:,}")
    else:
        print("현재 강세 신호 없음")
