import json
import os
import sys
import asyncio
from datetime import datetime
from telegram import Bot
from dotenv import load_dotenv

sys.path.insert(0, '/media/dps/T7/stock_ai')
from modules.technical_analyzer import TechnicalAnalyzer

load_dotenv('/media/dps/T7/stock_ai/.env')

class WatchlistMonitor:
    def __init__(self):
        self.bot = Bot(token=os.getenv('TELEGRAM_BOT_TOKEN'))
        self.chat_id = os.getenv('TELEGRAM_CHAT_ID')
        self.analyzer = TechnicalAnalyzer()
        self.watchlist_file = "/media/dps/T7/stock_ai/data/watchlist.json"
        self.alert_history_file = "/media/dps/T7/stock_ai/data/alert_history.json"
        self.watchlist = self._load_watchlist()
        self.alert_history = self._load_alert_history()

    def _load_watchlist(self):
        os.makedirs("/media/dps/T7/stock_ai/data", exist_ok=True)
        if os.path.exists(self.watchlist_file):
            with open(self.watchlist_file, "r", encoding="utf-8") as f:
                return json.load(f)
        default = {
            "단기": {
                "삼성전자": "005930.KS",
                "SK하이닉스": "000660.KS",
                "한화에어로스페이스": "012450.KS",
                "NVIDIA": "NVDA",
                "Apple": "AAPL",
            },
            "중기": {
                "LG에너지솔루션": "373220.KS",
                "카카오": "035720.KS",
                "Tesla": "TSLA",
                "AMD": "AMD",
            },
            "장기": {
                "삼성전자": "005930.KS",
                "NVIDIA": "NVDA",
                "Microsoft": "MSFT",
            }
        }
        self._save_watchlist(default)
        return default

    def _save_watchlist(self, data=None):
        with open(self.watchlist_file, "w", encoding="utf-8") as f:
            json.dump(data or self.watchlist, f, ensure_ascii=False, indent=2)

    def _load_alert_history(self):
        if os.path.exists(self.alert_history_file):
            with open(self.alert_history_file, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}

    def _save_alert_history(self):
        with open(self.alert_history_file, "w", encoding="utf-8") as f:
            json.dump(self.alert_history, f, ensure_ascii=False, indent=2)

    def _can_alert(self, key, cooldown_hours=4):
        if key in self.alert_history:
            last = datetime.fromisoformat(self.alert_history[key])
            diff = (datetime.now() - last).total_seconds() / 3600
            if diff < cooldown_hours:
                return False
        self.alert_history[key] = datetime.now().isoformat()
        self._save_alert_history()
        return True

    def add_stock(self, name, ticker, period="중기"):
        if period not in self.watchlist:
            self.watchlist[period] = {}
        self.watchlist[period][name] = ticker
        self._save_watchlist()
        print(f"✅ {name} ({ticker}) → {period} 감시 목록 추가")

    def remove_stock(self, name):
        for period in self.watchlist:
            if name in self.watchlist[period]:
                del self.watchlist[period][name]
                self._save_watchlist()
                print(f"✅ {name} 감시 목록 제거")
                return True
        return False

    def get_watchlist_text(self):
        text = "📋 현재 감시 종목 목록\n\n"
        for period, stocks in self.watchlist.items():
            text += f"【{period}】\n"
            for name, ticker in stocks.items():
                text += f"  • {name} ({ticker})\n"
        return text

    async def send_alert(self, message):
        try:
            await self.bot.send_message(
                chat_id=self.chat_id,
                text=message,
                parse_mode='HTML'
            )
        except Exception as e:
            print(f"❌ 알림 전송 실패: {e}")

    def _build_signal_message(self, name, data, period):
        emoji = {"단기": "🟡", "중기": "🟢", "장기": "🔵"}.get(period, "🔔")
        signals_text = "\n".join([f"  • {s}" for s in data['signals']])
        return f"""{emoji} <b>[{period} 매수신호] {name}</b>

💰 현재가: {data['current_price']:,}
📊 RSI: {data['rsi']}
📈 볼린저밴드: {data['bb_position']}
📉 ATR 손절선: {data['stop_loss']:,} ({data['stop_loss_pct']}%)
📦 거래량: 평소 대비 {data['volume_ratio']}배
🏔 52주 신고가: {data['high_52w']:,} ({data['high_52w_proximity']}%)

🔔 감지된 신호:
{signals_text}

⏰ {data['timestamp']}"""

    async def check_buy_signals(self):
        print(f"\n🔍 매수 신호 감지 중... ({datetime.now().strftime('%H:%M')})")
        for period, stocks in self.watchlist.items():
            for name, ticker in stocks.items():
                print(f"  분석: {name}...")
                data = self.analyzer.get_indicators(ticker)
                if not data:
                    continue
                if period == "중기":
                    if (data['rsi'] and data['rsi'] <= 35 and
                        "볼린저밴드 하단" in str(data['signals'])):
                        key = f"{ticker}_중기_매수"
                        if self._can_alert(key):
                            await self.send_alert(self._build_signal_message(name, data, period))
                            print(f"  📱 알림 전송: {name} 중기 매수신호")
                elif period == "장기":
                    if (data['rsi'] and data['rsi'] <= 40 and
                        "MACD 골든크로스" in str(data['signals'])):
                        key = f"{ticker}_장기_매수"
                        if self._can_alert(key):
                            await self.send_alert(self._build_signal_message(name, data, period))
                            print(f"  📱 알림 전송: {name} 장기 매수신호")
                elif period == "단기":
                    if (data['volume_ratio'] >= 2.0 and
                        "이동평균 정배열" in str(data['signals'])):
                        key = f"{ticker}_단기_거래량"
                        if self._can_alert(key):
                            await self.send_alert(self._build_signal_message(name, data, period))
                            print(f"  📱 알림 전송: {name} 단기 신호")
        print("  ✅ 신호 감지 완료")

    async def run_once(self):
        await self.check_buy_signals()

if __name__ == "__main__":
    monitor = WatchlistMonitor()
    print("=" * 50)
    print("🔍 감시 루프 테스트")
    print("=" * 50)
    print(monitor.get_watchlist_text())
    print("\n신호 감지 시작... (1~2분 소요)")
    asyncio.run(monitor.run_once())
    print("\n✅ 5단계 완료!")
