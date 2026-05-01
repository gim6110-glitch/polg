from datetime import datetime

from modules.kis_api import KISApi


class PullbackKRScanner:
    """09:40 KR 눌림목 스캐너 (경량)"""

    def __init__(self):
        self.kis = KISApi()

    def _ok(self, ind):
        chg = float(ind.get("change_pct", 0) or 0)
        draw = abs(float(ind.get("drawdown_52w", 99) or 99))
        vol = float(ind.get("vol_ratio", 0) or 0)
        ma5 = float(ind.get("ma5", 0) or 0)
        price = float(ind.get("price", 0) or 0)
        if not (5 <= chg < 10):
            return False
        if not (3 <= draw <= 8):
            return False
        if vol > 0.5:
            return False
        if ma5 > 0 and price < ma5:
            return False
        return True

    def scan(self, rows):
        picks = []
        for r in rows[:40]:
            t = r.get("ticker")
            if not t:
                continue
            ind = self.kis.calc_indicators_kr(t, days=40)
            if ind and self._ok(ind):
                picks.append((r.get("name", t), t, ind))
            if len(picks) >= 5:
                break
        if not picks:
            return "📉 KR 눌림목 후보 없음"
        lines = [f"📉 <b>KR 눌림목 스캔</b> {datetime.now().strftime('%m/%d %H:%M')}"]
        for n, t, ind in picks:
            lines.append(f"- {n}({t}) 등락 {ind.get('change_pct',0):+.1f}% | 거래량 {ind.get('vol_ratio',0):.1f}배")
        return "\n".join(lines)
