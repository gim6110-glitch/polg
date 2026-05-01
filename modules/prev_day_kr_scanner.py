from datetime import datetime

from modules.kis_api import KISApi
from modules.theme_hunter import ThemeHunter


class PrevDayKRScanner:
    """15:40 한국 전날 선점 후보 스캐너 (경량 버전)"""

    def __init__(self):
        self.kis = KISApi()
        self.th = ThemeHunter()

    def scan(self):
        movers = self.kis.get_top_fluctuation("KR") or []
        if not movers:
            return None

        fired = self.th._group_by_theme(movers)
        lines = [f"📌 <b>KR 전날 선점 후보</b> {datetime.now().strftime('%m/%d %H:%M')}", ""]
        count = 0
        for theme, d in fired.items():
            leaders = d.get("leaders", [])
            if len(leaders) < 2:
                continue
            top = leaders[0]
            if top.get("change_pct", 0) < 20:
                continue
            for r in leaders[1:4]:
                chg = r.get("change_pct", 0)
                if chg >= 10:
                    continue
                lines.append(
                    f"- [{theme}] {r['name']} {chg:+.2f}% | 대장 {top['name']} {top['change_pct']:+.2f}%"
                )
                count += 1
                if count >= 5:
                    break
            if count >= 5:
                break

        if count == 0:
            return "📌 KR 전날 선점 후보 없음"
        return "\n".join(lines)
