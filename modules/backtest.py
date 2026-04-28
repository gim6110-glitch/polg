import os
import sys
import json
import time
from datetime import datetime, timedelta
from dotenv import load_dotenv

sys.path.insert(0, '/media/dps/T7/stock_ai')
load_dotenv('/media/dps/T7/stock_ai/.env')

BACKTEST_FILE = "/media/dps/T7/stock_ai/data/backtest.json"

FEE = {
    "KR": 0.004,
    "US": 0.0025,
}

EXPIRE_DAYS = {
    "단기":  14,
    "중장기": 90,
    "도박":  180,
}

TRACK_DAYS = [1, 3, 5, 10]


class BacktestSystem:
    """
    AI 추천 모의 테스트 시스템 v2
    - 1일/3일/5일/10일 수익률 자동 추적
    - 최대 상승률/최대 하락률 매일 갱신
    - 신호 등급 A/B/C/D 기록
    - 등급별/시간대별 승률 분석
    """

    def __init__(self):
        self.data = self._load()

    def _load(self):
        if os.path.exists(BACKTEST_FILE):
            with open(BACKTEST_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        default = {"records": [], "summary": {}}
        self._save(default)
        return default

    def _save(self, data=None):
        os.makedirs(os.path.dirname(BACKTEST_FILE), exist_ok=True)
        if data is None:
            data = self.data
        with open(BACKTEST_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def record(self, ticker, name, entry_price, target_price, stop_loss,
               market="KR", hold_type="단기", source="장중신호",
               regime="강세", grade="B"):
        rec = {
            "id":             f"{ticker}_{datetime.now().strftime('%Y%m%d%H%M')}",
            "ticker":         ticker,
            "name":           name,
            "market":         market,
            "hold_type":      hold_type,
            "source":         source,
            "regime":         regime,
            "grade":          grade,
            "entry_price":    entry_price,
            "target_price":   target_price,
            "stop_loss":      stop_loss,
            "entry_time":     datetime.now().isoformat(),
            "entry_date":     datetime.now().strftime("%Y-%m-%d"),
            "expire_time":    (datetime.now() + timedelta(days=EXPIRE_DAYS.get(hold_type, 14))).isoformat(),
            "status":         "진행중",
            "exit_price":     None,
            "exit_time":      None,
            "profit_pct":     None,
            "net_profit_pct": None,
            "result":         None,
            "track_1d":       None,
            "track_3d":       None,
            "track_5d":       None,
            "track_10d":      None,
            "max_profit":     0.0,
            "max_loss":       0.0,
        }
        self.data["records"].append(rec)
        self._save()
        print(f"  📝 백테스트 기록: {name}({ticker}) [{grade}등급] {entry_price:,} → 목표:{target_price:,}")
        return rec["id"]

    def daily_update(self):
        """매일 08:00 호출 — 중간 수익률 + 최대값 갱신 + 결과 확정"""
        updated = []

        for rec in self.data["records"]:
            if rec["status"] != "진행중":
                continue

            ticker      = rec["ticker"]
            market      = rec["market"]
            current     = self._get_current_price(ticker, market)
            if not current:
                continue

            entry_price = rec["entry_price"]
            fee         = FEE.get(market, 0.004)
            profit_pct  = ((current - entry_price) / entry_price) * 100

            # 최대 상승/하락 갱신
            if profit_pct > rec.get("max_profit", 0):
                rec["max_profit"] = round(profit_pct, 2)
            if profit_pct < rec.get("max_loss", 0):
                rec["max_loss"] = round(profit_pct, 2)

            # 경과일 계산
            entry_date  = rec.get("entry_date", rec["entry_time"][:10])
            days_passed = (datetime.now() - datetime.strptime(entry_date, "%Y-%m-%d")).days

            # 1/3/5/10일 수익률 기록
            for d in TRACK_DAYS:
                key = f"track_{d}d"
                if days_passed >= d and rec.get(key) is None:
                    rec[key] = round(profit_pct - (fee * 100), 2)
                    print(f"  📊 {rec['name']} {d}일 수익률: {rec[key]:+.2f}%")

            # 결과 확정
            result = None
            if current >= rec["target_price"]:
                result     = "성공"
                exit_price = rec["target_price"]
            elif current <= rec["stop_loss"]:
                result     = "실패"
                exit_price = rec["stop_loss"]
            elif datetime.now() > datetime.fromisoformat(rec["expire_time"]):
                result     = "만료"
                exit_price = current

            if result:
                profit_final          = ((exit_price - entry_price) / entry_price) * 100
                net_profit            = profit_final - (fee * 100)
                rec["status"]         = result
                rec["exit_price"]     = exit_price
                rec["exit_time"]      = datetime.now().isoformat()
                rec["profit_pct"]     = round(profit_final, 2)
                rec["net_profit_pct"] = round(net_profit, 2)
                rec["result"]         = result
                updated.append(rec)
                print(f"  ✅ 결과 확정: {rec['name']} {result} {net_profit:+.1f}%")

        self._save()
        return updated

    def update_prices(self):
        """30분마다 호출 — 목표가/손절가 도달 체크"""
        updated = []
        for rec in self.data["records"]:
            if rec["status"] != "진행중":
                continue

            ticker  = rec["ticker"]
            market  = rec["market"]
            current = self._get_current_price(ticker, market)
            if not current:
                continue

            entry_price = rec["entry_price"]
            fee         = FEE.get(market, 0.004)
            profit_pct  = ((current - entry_price) / entry_price) * 100

            if profit_pct > rec.get("max_profit", 0):
                rec["max_profit"] = round(profit_pct, 2)
            if profit_pct < rec.get("max_loss", 0):
                rec["max_loss"] = round(profit_pct, 2)

            result = None
            if current >= rec["target_price"]:
                result     = "성공"
                exit_price = rec["target_price"]
            elif current <= rec["stop_loss"]:
                result     = "실패"
                exit_price = rec["stop_loss"]
            elif datetime.now() > datetime.fromisoformat(rec["expire_time"]):
                result     = "만료"
                exit_price = current

            if result:
                profit_final          = ((exit_price - entry_price) / entry_price) * 100
                net_profit            = profit_final - (fee * 100)
                rec["status"]         = result
                rec["exit_price"]     = exit_price
                rec["exit_time"]      = datetime.now().isoformat()
                rec["profit_pct"]     = round(profit_final, 2)
                rec["net_profit_pct"] = round(net_profit, 2)
                rec["result"]         = result
                updated.append(rec)

        if updated:
            self._save()
        return updated

    def _get_current_price(self, ticker, market):
        try:
            import yfinance as yf
            yf_ticker = f"{ticker}.KS" if market == "KR" else ticker
            hist      = yf.Ticker(yf_ticker).history(period="1d").dropna()
            if not hist.empty:
                return round(hist['Close'].iloc[-1], 2)
        except:
            pass
        return None

    def get_stats(self, hold_type=None, source=None, ticker=None,
                  days=None, grade=None):
        records = self.data["records"]

        if hold_type:
            records = [r for r in records if r.get("hold_type") == hold_type]
        if source:
            records = [r for r in records if r.get("source") == source]
        if ticker:
            records = [r for r in records if r.get("ticker") == ticker.upper()]
        if days:
            cutoff  = (datetime.now() - timedelta(days=days)).isoformat()
            records = [r for r in records if r.get("entry_time", "") >= cutoff]
        if grade:
            records = [r for r in records if r.get("grade") == grade.upper()]

        total     = len(records)
        completed = [r for r in records if r.get("status") != "진행중"]
        ongoing   = [r for r in records if r.get("status") == "진행중"]
        success   = [r for r in completed if r.get("result") == "성공"]
        failed    = [r for r in completed if r.get("result") == "실패"]
        expired   = [r for r in completed if r.get("result") == "만료"]

        if not completed:
            return {
                "total": total, "completed": 0, "ongoing": len(ongoing),
                "win_rate": None, "avg_profit": None, "records": records
            }

        win_rate       = round((len(success) / len(completed)) * 100, 1)
        avg_profit     = round(sum(r.get("net_profit_pct", 0) for r in completed) / len(completed), 2)
        avg_win        = round(sum(r.get("net_profit_pct", 0) for r in success) / len(success), 2) if success else 0
        avg_loss       = round(sum(r.get("net_profit_pct", 0) for r in failed) / len(failed), 2) if failed else 0
        avg_max_profit = round(sum(r.get("max_profit", 0) for r in completed) / len(completed), 2)
        avg_max_loss   = round(sum(r.get("max_loss", 0) for r in completed) / len(completed), 2)

        track_stats = {}
        for d in TRACK_DAYS:
            key     = f"track_{d}d"
            tracked = [r.get(key) for r in completed if r.get(key) is not None]
            if tracked:
                track_stats[d] = round(sum(tracked) / len(tracked), 2)

        return {
            "total":          total,
            "completed":      len(completed),
            "ongoing":        len(ongoing),
            "success":        len(success),
            "failed":         len(failed),
            "expired":        len(expired),
            "win_rate":       win_rate,
            "avg_profit":     avg_profit,
            "avg_win":        avg_win,
            "avg_loss":       avg_loss,
            "avg_max_profit": avg_max_profit,
            "avg_max_loss":   avg_max_loss,
            "track_stats":    track_stats,
            "records":        records,
        }

    def build_report(self, hold_type=None, source=None, ticker=None,
                     days=None, grade=None, compare=False,
                     week=False, month=False):

        if week:
            days = 7
        elif month:
            days = 30

        stats = self.get_stats(hold_type, source, ticker, days, grade)

        title_parts = []
        if ticker:    title_parts.append(ticker.upper())
        if hold_type: title_parts.append(hold_type)
        if source:    title_parts.append(source)
        if grade:     title_parts.append(f"{grade}등급")
        if week:      title_parts.append("이번주")
        elif month:   title_parts.append("이번달")
        elif days:    title_parts.append(f"최근{days}일")
        title = " | ".join(title_parts) if title_parts else "전체"

        msg  = f"📊 <b>모의 백테스트</b> [{title}]\n"
        msg += f"<i>수수료 반영 실질 수익률</i>\n\n"

        if stats["completed"] == 0:
            msg += f"아직 완료된 추천 없음\n진행중: {stats['ongoing']}개\n"
            return msg

        win_emoji = "🟢" if stats["win_rate"] >= 60 else "🟡" if stats["win_rate"] >= 40 else "🔴"
        msg += f"{win_emoji} <b>승률: {stats['win_rate']}%</b> ({stats['success']}승 {stats['failed']}패 {stats['expired']}만료)\n"

        profit_emoji = "📈" if stats["avg_profit"] >= 0 else "📉"
        msg += f"{profit_emoji} 평균 수익률: {stats['avg_profit']:+.2f}%\n"
        msg += f"  ├ 평균 수익: {stats['avg_win']:+.2f}%\n"
        msg += f"  └ 평균 손실: {stats['avg_loss']:+.2f}%\n\n"

        msg += f"📈 평균 최대 상승: {stats['avg_max_profit']:+.2f}%\n"
        msg += f"📉 평균 최대 하락: {stats['avg_max_loss']:+.2f}%\n\n"

        track = stats.get("track_stats", {})
        if track:
            msg += "📅 <b>기간별 평균 수익률</b>\n"
            for d, pct in sorted(track.items()):
                emoji = "📈" if pct >= 0 else "📉"
                msg  += f"  {emoji} {d}일: {pct:+.2f}%\n"
            msg += "\n"

        msg += f"📋 총 {stats['total']}개 (완료:{stats['completed']} 진행중:{stats['ongoing']})\n\n"

        if compare:
            msg += "🎯 <b>등급별 승률 비교</b>\n"
            for g in ["A", "B", "C", "D"]:
                gs = self.get_stats(grade=g, days=days)
                if gs["completed"] > 0:
                    bar  = "🟢" if gs["win_rate"] >= 60 else "🟡" if gs["win_rate"] >= 40 else "🔴"
                    msg += f"  {bar} {g}등급: {gs['win_rate']}% ({gs['completed']}건) 평균{gs['avg_profit']:+.1f}%\n"
            msg += "\n"

        if not source and not compare:
            sources      = ["07:30단기", "14:30선점", "장중신호", "중장기", "도박"]
            source_stats = [(s, self.get_stats(source=s, days=days)) for s in sources]
            source_stats = [(s, ss) for s, ss in source_stats if ss["completed"] > 0]
            if source_stats:
                msg += "⏰ <b>시간대별 승률</b>\n"
                for s, ss in source_stats:
                    bar  = "🟢" if ss["win_rate"] >= 60 else "🟡" if ss["win_rate"] >= 40 else "🔴"
                    msg += f"  {bar} {s}: {ss['win_rate']}% ({ss['completed']}건) 평균{ss['avg_profit']:+.1f}%\n"
                msg += "\n"

        completed = [r for r in stats["records"] if r.get("status") != "진행중"]
        recent    = sorted(completed, key=lambda x: x.get("exit_time") or "", reverse=True)[:5]
        if recent:
            msg += "🕐 <b>최근 결과</b>\n"
            for r in recent:
                emoji  = "✅" if r.get("result") == "성공" else "❌" if r.get("result") == "실패" else "⏱"
                profit = r.get("net_profit_pct", 0)
                g      = r.get("grade", "?")
                msg   += f"  {emoji} {r['name']}({r['ticker']}) {profit:+.1f}% [{r.get('source','')}] {g}등급\n"

        msg += f"\n⏰ {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        return msg

    def build_result_alert(self, records):
        if not records:
            return None

        msg = f"📊 <b>모의 테스트 결과</b>\n\n"
        for r in records:
            emoji  = "✅ 성공" if r.get("result") == "성공" else "❌ 실패" if r.get("result") == "실패" else "⏱ 만료"
            profit = r.get("net_profit_pct", 0)
            grade  = r.get("grade", "?")
            msg   += f"{emoji} <b>{r['name']}</b> ({r['ticker']}) [{grade}등급]\n"
            msg   += f"  진입: {r['entry_price']:,} → 청산: {r['exit_price']:,}\n"
            msg   += f"  수익률: {profit:+.2f}% | 최대상승: {r.get('max_profit',0):+.2f}% | 최대하락: {r.get('max_loss',0):+.2f}%\n"
            msg   += f"  추천: {r.get('source','')} | {r.get('hold_type','')}\n\n"

        return msg


async def cmd_backtest(update, context):
    """
    /backtest — 전체
    /backtest 단기 — 분류별
    /backtest NVDA — 특정 종목
    /backtest 30 — 최근 30일
    /backtest grade A — 등급별
    /backtest source 07:30단기 — 시간대별
    /backtest compare — 등급 비교
    /backtest week — 이번 주
    /backtest month — 이번 달
    """
    from main import send

    bt   = BacktestSystem()
    args = context.args if context.args else []

    hold_type = None
    source    = None
    ticker    = None
    days      = None
    grade     = None
    compare   = False
    week      = False
    month     = False

    i = 0
    while i < len(args):
        arg = args[i]
        if arg in ["단기", "중장기", "도박"]:
            hold_type = arg
        elif arg == "grade" and i + 1 < len(args):
            grade = args[i + 1].upper()
            i    += 1
        elif arg == "source" and i + 1 < len(args):
            source = args[i + 1]
            i     += 1
        elif arg == "compare":
            compare = True
        elif arg == "week":
            week = True
        elif arg == "month":
            month = True
        elif arg.isdigit():
            days = int(arg)
        else:
            ticker = arg
        i += 1

    bt.update_prices()
    msg = bt.build_report(
        hold_type=hold_type, source=source, ticker=ticker,
        days=days, grade=grade, compare=compare,
        week=week, month=month
    )
    await send(msg)
