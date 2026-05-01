import json
import os
from datetime import datetime, timedelta

from modules.kis_api import KISApi


class EntryWatcher:
    def __init__(self):
        self.file = "/media/dps/T7/stock_ai/data/entry_watchlist.json"
        self.kis = KISApi()
        self.watchlist = self._load()

    def _load(self):
        if os.path.exists(self.file):
            with open(self.file, "r") as f:
                return json.load(f)
        return {}

    def _save(self):
        os.makedirs(os.path.dirname(self.file), exist_ok=True)
        with open(self.file, "w") as f:
            json.dump(self.watchlist, f, ensure_ascii=False, indent=2)

    def register(self, ticker, target_price, stop_loss, split="50/30/20", expire_days=3):
        now = datetime.now()
        market = "US" if ticker.isalpha() else "KR"
        self.watchlist[ticker] = {
            "target": float(target_price),
            "stop": float(stop_loss),
            "split": split,
            "stage": 1,
            "market": market,
            "registered_at": now.isoformat(),
            "expires_at": (now + timedelta(days=expire_days)).isoformat(),
        }
        self._save()

    def unregister(self, ticker):
        return self.watchlist.pop(ticker, None) is not None
        
    def get_watchlist_text(self):
        if not self.watchlist:
            return "📭 현재 watch 목록이 없습니다."
        lines = ["📌 <b>진입 Watch 목록</b>\n"]
        for t, w in self.watchlist.items():
            c = "$" if w.get("market") == "US" else "₩"
            lines.append(
                f"- {t}: 목표 {c}{w['target']:,.2f} / 손절 {c}{w['stop']:,.2f} / "
                f"분할 {w.get('split','50/30/20')} / stage {w.get('stage',1)}"
            )
        return "\n".join(lines)

    def _get_price(self, ticker, market):
        if market == "KR":
            d = self.kis.get_kr_price(ticker)
        else:
            d = self.kis.get_us_price(ticker)
        if not d:
            return None
        return float(d.get("price") or 0)

    async def check_all(self, send_func):
        now = datetime.now()
        removes = []
        for ticker, cfg in list(self.watchlist.items()):
            if now > datetime.fromisoformat(cfg["expires_at"]):
                await send_func(f"⌛ {ticker} watch 만료 (3일 경과)")
                removes.append(ticker)
                continue

            price = self._get_price(ticker, cfg.get("market", "KR"))
            if not price:
                continue

            split = cfg.get("split", "50/30/20").split("/")
            if price <= cfg["target"] and cfg.get("stage", 1) == 1:
                await send_func(
                    f"🎯 <b>진입 타이밍 도달</b>\n"
                    f"{ticker} 현재가 {price:,.2f}\n"
                    f"1차 매수 ({split[0]}%)\n"
                    f"손절가: {cfg['stop']:,.2f}"
                )
                cfg["stage"] = 2
                cfg["target"] = price * 0.97
            elif price <= cfg["target"] and cfg.get("stage", 1) == 2:
                await send_func(f"🎯 {ticker} 2차 진입 구간 도달 ({split[1]}%)")
                cfg["stage"] = 3
                cfg["target"] = price * 0.97
            elif price <= cfg["target"] and cfg.get("stage", 1) == 3:
                await send_func(f"🎯 {ticker} 3차 진입 구간 도달 ({split[2]}%)")
                removes.append(ticker)

        for t in removes:
            self.watchlist.pop(t, None)
        self._save()
