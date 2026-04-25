import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime

class TechnicalAnalyzer:
    def get_indicators(self, ticker, period="6mo"):
        try:
            stock = yf.Ticker(ticker)
            df = stock.history(period=period)
            df = df.dropna()
            if len(df) < 30:
                return None
            df['rsi'] = self._calc_rsi(df['Close'])
            df['macd'], df['signal_line'], df['histogram'] = self._calc_macd(df['Close'])
            df['bb_upper'], df['bb_mid'], df['bb_lower'] = self._calc_bollinger(df['Close'])
            df['atr'] = self._calc_atr(df)
            df['ma5']  = df['Close'].rolling(5).mean()
            df['ma20'] = df['Close'].rolling(20).mean()
            df['ma60'] = df['Close'].rolling(60).mean()
            latest = df.iloc[-1]
            prev   = df.iloc[-2]
            current_price = latest['Close']
            atr_value = latest['atr']
            stop_loss = current_price - (atr_value * 1.5)
            stop_pct  = ((stop_loss - current_price) / current_price) * 100
            high_52w       = df['Close'].max()
            high_proximity = (current_price / high_52w) * 100
            avg_vol   = df['Volume'].replace(0, float('nan')).mean()
            vol_ratio = latest['Volume'] / avg_vol if (not pd.isna(avg_vol) and avg_vol > 0) else 1.0
            signals = self._detect_signals(df, latest, prev)
            return {
                "ticker": ticker,
                "current_price": round(current_price, 2),
                "rsi": round(latest['rsi'], 1) if not pd.isna(latest['rsi']) else None,
                "macd": round(latest['macd'], 3) if not pd.isna(latest['macd']) else None,
                "macd_signal": round(latest['signal_line'], 3) if not pd.isna(latest['signal_line']) else None,
                "macd_histogram": round(latest['histogram'], 3) if not pd.isna(latest['histogram']) else None,
                "bb_upper": round(latest['bb_upper'], 2) if not pd.isna(latest['bb_upper']) else None,
                "bb_lower": round(latest['bb_lower'], 2) if not pd.isna(latest['bb_lower']) else None,
                "bb_position": self._bb_position(current_price, latest['bb_upper'], latest['bb_lower']),
                "ma5":  round(latest['ma5'],  2) if not pd.isna(latest['ma5'])  else None,
                "ma20": round(latest['ma20'], 2) if not pd.isna(latest['ma20']) else None,
                "ma60": round(latest['ma60'], 2) if not pd.isna(latest['ma60']) else None,
                "atr": round(atr_value, 2) if not pd.isna(atr_value) else None,
                "stop_loss": round(stop_loss, 2),
                "stop_loss_pct": round(stop_pct, 1),
                "volume_ratio": round(vol_ratio, 2),
                "high_52w": round(high_52w, 2),
                "high_52w_proximity": round(high_proximity, 1),
                "signals": signals,
                "signal_count": len(signals),
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
            }
        except Exception as e:
            print(f"❌ {ticker} 지표 계산 실패: {e}")
            return None

    def _calc_rsi(self, prices, period=14):
        delta    = prices.diff()
        gain     = delta.clip(lower=0)
        loss     = -delta.clip(upper=0)
        avg_gain = gain.rolling(period).mean()
        avg_loss = loss.rolling(period).mean()
        rs  = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))

    def _calc_macd(self, prices, fast=12, slow=26, signal=9):
        ema_fast    = prices.ewm(span=fast).mean()
        ema_slow    = prices.ewm(span=slow).mean()
        macd        = ema_fast - ema_slow
        signal_line = macd.ewm(span=signal).mean()
        histogram   = macd - signal_line
        return macd, signal_line, histogram

    def _calc_bollinger(self, prices, period=20, std=2):
        mid   = prices.rolling(period).mean()
        upper = mid + (prices.rolling(period).std() * std)
        lower = mid - (prices.rolling(period).std() * std)
        return upper, mid, lower

    def _calc_atr(self, df, period=14):
        high  = df['High']
        low   = df['Low']
        close = df['Close']
        tr = pd.concat([
            high - low,
            (high - close.shift()).abs(),
            (low  - close.shift()).abs()
        ], axis=1).max(axis=1)
        return tr.rolling(period).mean()

    def _bb_position(self, price, upper, lower):
        if pd.isna(upper) or pd.isna(lower):
            return "N/A"
        if price >= upper:
            return "상단 돌파 (과열)"
        elif price <= lower:
            return "하단 터치 (매수 고려)"
        mid = (upper + lower) / 2
        return "상단부" if price > mid else "하단부"

    def _detect_signals(self, df, latest, prev):
        signals = []
        rsi = latest['rsi']
        if not pd.isna(rsi):
            if rsi <= 30:
                signals.append(f"RSI 과매도 ({rsi:.1f}) → 반등 가능")
            elif rsi >= 70:
                signals.append(f"RSI 과매수 ({rsi:.1f}) → 주의")
        if (not pd.isna(latest['macd']) and not pd.isna(latest['signal_line']) and
            not pd.isna(prev['macd'])   and not pd.isna(prev['signal_line'])):
            if prev['macd'] < prev['signal_line'] and latest['macd'] > latest['signal_line']:
                signals.append("MACD 골든크로스 → 매수 신호")
            elif prev['macd'] > prev['signal_line'] and latest['macd'] < latest['signal_line']:
                signals.append("MACD 데드크로스 → 매도 신호")
        if not pd.isna(latest['bb_lower']):
            if latest['Close'] <= latest['bb_lower']:
                signals.append("볼린저밴드 하단 터치 → 매수 고려")
        avg_vol = df['Volume'].replace(0, float('nan')).mean()
        if not pd.isna(avg_vol) and avg_vol > 0:
            vol_ratio = latest['Volume'] / avg_vol
            if vol_ratio >= 2.0:
                signals.append(f"거래량 급증 ({vol_ratio:.1f}배) → 세력 유입 가능")
        high_52w  = df['Close'].max()
        proximity = (latest['Close'] / high_52w) * 100
        if proximity >= 98:
            signals.append(f"52주 신고가 근접 ({proximity:.1f}%) → 돌파 시 강한 상승")
        if (not pd.isna(latest['ma5']) and
            not pd.isna(latest['ma20']) and
            not pd.isna(latest['ma60'])):
            if latest['ma5'] > latest['ma20'] > latest['ma60']:
                signals.append("이동평균 정배열 → 상승 추세")
            elif latest['ma5'] < latest['ma20'] < latest['ma60']:
                signals.append("이동평균 역배열 → 하락 추세 주의")
        return signals

    def scan_stocks(self, stock_dict):
        results = []
        for name, ticker in stock_dict.items():
            print(f"  분석 중: {name}...")
            data = self.get_indicators(ticker)
            if data:
                data['name'] = name
                results.append(data)
        results.sort(key=lambda x: x['signal_count'], reverse=True)
        return results

if __name__ == "__main__":
    analyzer = TechnicalAnalyzer()
    print("=" * 50)
    print("📊 기술적 지표 분석 테스트")
    print("=" * 50)
    test_stocks = {
        "삼성전자": "005930.KS",
        "SK하이닉스": "000660.KS",
        "NVIDIA": "NVDA",
    }
    print("\n종목 분석 중... (30초 소요)\n")
    results = analyzer.scan_stocks(test_stocks)
    for r in results:
        print(f"\n{'='*40}")
        print(f"📈 {r['name']} ({r['ticker']})")
        print(f"   현재가:      {r['current_price']}")
        print(f"   RSI:         {r['rsi']}")
        print(f"   볼린저밴드:  {r['bb_position']}")
        print(f"   ATR 손절선:  {r['stop_loss']} ({r['stop_loss_pct']}%)")
        print(f"   거래량 비율: {r['volume_ratio']}배")
        print(f"   52주 신고가: {r['high_52w']} ({r['high_52w_proximity']}%)")
        if r['signals']:
            print(f"   신호 ({r['signal_count']}개):")
            for s in r['signals']:
                print(f"     → {s}")
        else:
            print(f"   신호: 없음")
    print(f"\n✅ 4단계 완료!")
