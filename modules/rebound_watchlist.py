import json
import os
from datetime import datetime

import yfinance as yf


class ReboundWatchlist:
    FILE = "/media/dps/T7/stock_ai/data/rebound_watchlist.json"

    def __init__(self):
        self.data = self._load()

    def _load(self):
        if os.path.exists(self.FILE):
            with open(self.FILE, "r") as f:
                return json.load(f)
        return {"KR": [], "US": []}

    def _save(self):
        os.makedirs(os.path.dirname(self.FILE), exist_ok=True)
        with open(self.FILE, "w") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)

    def update_candidates(self, kr_candidates, us_candidates):
        self.data["KR"] = kr_candidates[:5]
        self.data["US"] = us_candidates[:5]
        self._save()

    def detect_turn_signal(self):
        try:
            ks = yf.Ticker("^KS11").history(period="7d").dropna()
            sp = yf.Ticker("^GSPC").history(period="7d").dropna()
            if len(ks) >= 4:
                ks3 = ks["Close"].tail(4).tolist()
                kr_rebound = ks3[0] > ks3[1] > ks3[2] and ((ks3[3] - ks3[2]) / ks3[2]) * 100 >= 1.5
            else:
                kr_rebound = False
            if len(sp) >= 4:
                sp3 = sp["Close"].tail(4).tolist()
                us_rebound = sp3[0] > sp3[1] > sp3[2] and ((sp3[3] - sp3[2]) / sp3[2]) * 100 >= 1.0
            else:
                us_rebound = False
            return {"KR": kr_rebound, "US": us_rebound}
        except Exception:
            return {"KR": False, "US": False}

    def build_alert(self, market):
        picks = self.data.get(market, [])
        if not picks:
            return None
        lines = [f"🟢 <b>{market} 추세 전환 감지</b> {datetime.now().strftime('%m/%d %H:%M')}", "전략: 반등 선점"]
        for p in picks[:5]:
            lines.append(f"- {p}")
        return "\n".join(lines)
