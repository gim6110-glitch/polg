import sys
import os
import json
import time
import asyncio
from datetime import datetime
from dotenv import load_dotenv

sys.path.insert(0, '/media/dps/T7/stock_ai')
from modules.kis_api import KISApi
from modules.sector_db import SECTOR_DB

load_dotenv('/media/dps/T7/stock_ai/.env')

class HighLowScanner:
    def __init__(self):
        self.kis        = KISApi()
        self.alert_file = "/media/dps/T7/stock_ai/data/highlow_alerts.json"
        self.alerts     = self._load_alerts()

    def _load_alerts(self):
        if os.path.exists(self.alert_file):
            with open(self.alert_file, "r") as f:
                return json.load(f)
        return {}

    def _save_alerts(self):
        with open(self.alert_file, "w") as f:
            json.dump(self.alerts, f, ensure_ascii=False, indent=2)

    def _can_alert(self, key, cooldown_hours=24):
        if key in self.alerts:
            last = datetime.fromisoformat(self.alerts[key])
            diff = (datetime.now() - last).total_seconds() / 3600
            if diff < cooldown_hours:
                return False
        self.alerts[key] = datetime.now().isoformat()
        self._save_alerts()
        return True

    def _analyze_stock(self, name, ticker, market="KR"):
        import yfinance as yf
        try:
            yf_ticker = f"{ticker}.KS" if market == "KR" else ticker
            hist      = yf.Ticker(yf_ticker).history(period="1y").dropna()
            if len(hist) < 20:
                return None

            close     = hist["Close"]
            volume    = hist["Volume"]
            high_52w  = close.max()
            avg_vol   = volume.mean()
            curr_vol  = volume.iloc[-1]
            vol_ratio = curr_vol / avg_vol if avg_vol > 0 else 1

            if market == "KR":
                kis_data   = self.kis.get_kr_price(ticker)
                current    = kis_data["price"] if kis_data else round(close.iloc[-1], 0)
                change_pct = kis_data["change_pct"] if kis_data else 0
            else:
                current    = round(close.iloc[-1], 2)
                change_pct = round(((close.iloc[-1] - close.iloc[-2]) / close.iloc[-2]) * 100, 2) if len(close) >= 2 else 0

            proximity   = (current / high_52w) * 100
            signal_type = None
            signal_desc = ""

            if proximity >= 97 and vol_ratio >= 2:
                signal_type = "신고가+거래량"
                signal_desc = f"신고가 근접({proximity:.1f}%) + 거래량 {vol_ratio:.1f}배 강력신호"
            elif proximity >= 99:
                signal_type = "신고가"
                signal_desc = f"52주 신고가 돌파! ({proximity:.1f}%)"
            elif vol_ratio >= 3 and abs(change_pct) < 3:
                signal_type = "거래량급증"
                signal_desc = f"거래량 {vol_ratio:.1f}배 급증 (세력 매집 의심)"

            if not signal_type:
                return None

            return {
                "name":        name,
                "ticker":      ticker,
                "sector":      "",
                "market":      market,
                "price":       current,
                "change_pct":  change_pct,
                "high_52w":    round(high_52w, 0) if market == "KR" else round(high_52w, 2),
                "proximity":   round(proximity, 1),
                "vol_ratio":   round(vol_ratio, 1),
                "signal_type": signal_type,
                "signal_desc": signal_desc,
            }
        except:
            return None

    def scan_signals(self, market="KR"):
        signals    = []
        seen_tickers = {}  # ticker → 이미 처리된 섹터 (중복 방지)

        for sector_name, sector_data in SECTOR_DB.items():
            if sector_data.get("market") != market:
                continue
            all_stocks = {}
            all_stocks.update(sector_data.get("대장주", {}))
            all_stocks.update(sector_data.get("2등주", {}))
            for cat_stocks in sector_data.get("소부장", {}).values():
                if isinstance(cat_stocks, dict):
                    all_stocks.update(cat_stocks)

            for name, ticker in all_stocks.items():
                # 이미 처리한 종목은 스킵 (중복 섹터 등록 방지)
                if ticker in seen_tickers:
                    continue
                seen_tickers[ticker] = sector_name

                result = self._analyze_stock(name, ticker, market)
                if result:
                    # 등락률 0.0% 신고가는 의미없는 신호 — 제외
                    if result["signal_type"] == "신고가" and abs(result["change_pct"]) < 0.3:
                        continue
                    result["sector"] = sector_name
                    signals.append(result)
                time.sleep(0.3 if market == "KR" else 0.1)

        priority = {"신고가+거래량": 0, "신고가": 1, "거래량급증": 2}
        signals.sort(key=lambda x: (priority.get(x["signal_type"], 9), -x["vol_ratio"]))
        return signals

    def build_alert_messages(self, kr_signals, us_signals):
        messages = []
        all_signals = kr_signals + us_signals

        # 강력 신호 즉시 알림
        for s in all_signals:
            if s["signal_type"] == "신고가+거래량":
                key = f"hl_{s['ticker']}_{datetime.now().strftime('%Y%m%d')}"
                if self._can_alert(key, cooldown_hours=24):
                    currency = "$" if s["market"] == "US" else ""
                    price    = f"${s['price']}" if s["market"] == "US" else f"{s['price']:,}원"
                    msg = f"""🚨 <b>[강력신호] {s["name"]}</b> ({s["ticker"]})

📊 {s["signal_desc"]}
섹터: {s["sector"]}

💰 현재가: {price} ({s["change_pct"]:+.2f}%)
🏔 52주 고점: {f"${s['high_52w']}" if s["market"]=="US" else f"{s['high_52w']:,}원"}
📦 거래량: {s["vol_ratio"]:.1f}배

⏰ {datetime.now().strftime("%H:%M:%S")}"""
                    messages.append(msg)

        # 신고가 묶음 알림 (하루 1회)
        kr_highs = [s for s in kr_signals if s["signal_type"] == "신고가"]
        if kr_highs:
            key = f"highs_kr_{datetime.now().strftime('%Y%m%d')}"
            if self._can_alert(key, cooldown_hours=24):
                msg = f"🏔 <b>한국 52주 신고가</b> {datetime.now().strftime('%m/%d %H:%M')}\n\n"
                for s in kr_highs[:5]:
                    msg += f"  ✅ {s['name']} ({s['ticker']}): {s['price']:,}원 ({s['change_pct']:+.1f}%) [{s['sector']}]\n"
                messages.append(msg)

        us_highs = [s for s in us_signals if s["signal_type"] == "신고가"]
        if us_highs:
            key = f"highs_us_{datetime.now().strftime('%Y%m%d')}"
            if self._can_alert(key, cooldown_hours=24):
                msg = f"🏔 <b>미국 52주 신고가</b> {datetime.now().strftime('%m/%d %H:%M')}\n\n"
                for s in us_highs[:5]:
                    msg += f"  ✅ {s['name']} ({s['ticker']}): ${s['price']} ({s['change_pct']:+.1f}%) [{s['sector']}]\n"
                messages.append(msg)

        return messages


if __name__ == "__main__":
    print("=" * 50)
    print("🔍 신고가/거래량 스캐너 테스트")
    print("=" * 50)
    hl = HighLowScanner()

    print("\n[한국 스캔 중... 시간 걸려요]")
    kr_signals = hl.scan_signals("KR")
    print(f"신호 {len(kr_signals)}개 발견")
    for s in kr_signals[:5]:
        print(f"  {s['signal_type']}: {s['name']} - {s['signal_desc']}")

    print("\n[미국 스캔 중...]")
    us_signals = hl.scan_signals("US")
    print(f"신호 {len(us_signals)}개 발견")
    for s in us_signals[:5]:
        print(f"  {s['signal_type']}: {s['name']} - {s['signal_desc']}")
