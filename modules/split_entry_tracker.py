from modules.kis_api import KISApi


class SplitEntryTracker:
    """entry_watcher 2차 진입 추세 재확인"""

    def __init__(self):
        self.kis = KISApi()

    def check(self, watchlist):
        alerts = []
        for ticker, cfg in watchlist.items():
            if cfg.get("stage", 1) != 2:
                continue
            market = cfg.get("market", "KR")
            if market == "KR":
                ind = self.kis.calc_indicators_kr(ticker, days=40) or {}
            else:
                continue
            vol = float(ind.get("vol_ratio", 0) or 0)
            ma5 = float(ind.get("ma5", 0) or 0)
            px = float(ind.get("price", 0) or 0)
            # 허용: 거래량 감소 + 5일선 유지
            if vol <= 0.5 and (ma5 == 0 or px >= ma5):
                alerts.append(f"✅ {ticker} 2차 진입 조건 유지 (거래량 감소/5일선 유지)")
            else:
                alerts.append(f"⛔ {ticker} 2차 진입 보류 (추세 훼손 가능성, 1차 포지션 손절 검토)")
        return alerts
