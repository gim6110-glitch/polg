import sys
import os
import json
import time
import asyncio
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv

sys.path.insert(0, '/media/dps/T7/stock_ai')
load_dotenv('/media/dps/T7/stock_ai/.env')

class DartMonitor:
    """
    DART 공시 모니터
    보유 종목 + 감시 종목 공시 즉시 알림
    대주주 매수/매도, 수주, 유상증자 등
    """
    def __init__(self):
        self.api_key    = os.getenv("DART_API_KEY")
        self.alert_file = "/media/dps/T7/stock_ai/data/dart_alerts.json"
        self.alerts     = self._load_alerts()
        self.base_url   = "https://opendart.fss.or.kr/api"

        # 중요 공시 키워드
        self.important_keywords = {
            "매우중요": [
                "주요사항보고", "유상증자", "무상증자", "자기주식취득",
                "합병", "분할", "인수", "매각", "수주", "계약체결",
                "대규모내부거래", "횡령", "배임"
            ],
            "중요": [
                "실적발표", "영업실적", "잠정실적", "배당",
                "최대주주변경", "대표이사변경", "임원변동"
            ],
            "참고": [
                "사업보고서", "반기보고서", "분기보고서"
            ]
        }

    def _load_alerts(self):
        if os.path.exists(self.alert_file):
            with open(self.alert_file, "r") as f:
                return json.load(f)
        return {}

    def _save_alerts(self):
        os.makedirs("/media/dps/T7/stock_ai/data", exist_ok=True)
        with open(self.alert_file, "w") as f:
            json.dump(self.alerts, f, ensure_ascii=False, indent=2)

    def _can_alert(self, key, cooldown_hours=12):
        if key in self.alerts:
            last = datetime.fromisoformat(self.alerts[key])
            diff = (datetime.now() - last).total_seconds() / 3600
            if diff < cooldown_hours:
                return False
        self.alerts[key] = datetime.now().isoformat()
        self._save_alerts()
        return True

    def get_corp_code(self, stock_code):
        """종목코드 → DART 고유번호 변환"""
        try:
            import zipfile, io
            url = f"{self.base_url}/corpCode.xml"
            params = {"crtfc_key": self.api_key}
            res  = requests.get(url, params=params, timeout=10)
            if res.status_code == 200:
                with zipfile.ZipFile(io.BytesIO(res.content)) as z:
                    with z.open("CORPCODE.xml") as f:
                        import xml.etree.ElementTree as ET
                        tree = ET.parse(f)
                        root = tree.getroot()
                        for corp in root.findall("list"):
                            if corp.find("stock_code") is not None:
                                if corp.find("stock_code").text == stock_code:
                                    return corp.find("corp_code").text
        except Exception as e:
            pass
        return None


    # 주요 업종코드 매핑 (한국표준산업분류 중분류)
    INDUTY_MAP = {
        '26': '전자부품/컴퓨터/통신장비',
        '261': '반도체',
        '262': '전자부품',
        '263': '통신/방송장비',
        '264': '영상/음향장비',
        '265': '측정/광학기기',
        '266': '전자부품 기타',
        '264': '디스플레이',
        '27': '의료/정밀기기',
        '28': '전기장비',
        '29': '기계장비',
        '30': '자동차/트레일러',
        '31': '기타운송장비',
        '20': '화학물질/제품',
        '21': '의약품',
        '22': '고무/플라스틱',
        '24': '금속',
        '25': '금속가공',
        '35': '전기/가스/증기',
        '36': '수도/폐기물',
        '41': '건설업',
        '46': '도매업',
        '47': '소매업',
        '58': 'SW개발/공급',
        '59': '영상/방송',
        '60': '방송업',
        '61': '통신업',
        '62': 'IT서비스',
        '63': '정보서비스',
        '64': '금융',
        '65': '보험',
        '66': '금융서비스',
        '70': '부동산',
        '72': '연구개발',
        '73': '전문서비스',
        '86': '의료/보건',
        '90': '창작/예술',
        '26429': '전자부품/통신장비',
        '26421': '반도체',
        '26110': '반도체',
        '26120': '디스플레이',
        '21202': '바이오/의약품',
        '30010': '자동차',
        '62010': 'IT서비스/SW',
    }

    def get_sector(self, stock_code):
        """종목코드 → 업종명 (DART 기업개황 API)"""
        try:
            corp_code = self.get_corp_code(stock_code)
            if not corp_code:
                return None
            url    = f'{self.base_url}/company.json'
            params = {'crtfc_key': self.api_key, 'corp_code': corp_code}
            res    = requests.get(url, params=params, timeout=10)
            data   = res.json()
            if data.get('status') == '000':
                code = data.get('induty_code', '')
                # 정확히 일치하는 코드 먼저
                if code in self.INDUTY_MAP:
                    return self.INDUTY_MAP[code]
                # 앞 2~3자리로 매핑
                for length in [3, 2]:
                    prefix = code[:length]
                    if prefix in self.INDUTY_MAP:
                        return self.INDUTY_MAP[prefix]
                return f'업종코드 {code}'
        except Exception as e:
            print(f'❌ DART 업종 조회 실패: {e}')
        return None

    def get_recent_disclosures(self, corp_code, days=3):
        """최근 공시 조회"""
        try:
            start_date = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")
            end_date   = datetime.now().strftime("%Y%m%d")
            url        = f"{self.base_url}/list.json"
            params = {
                "crtfc_key": self.api_key,
                "corp_code": corp_code,
                "bgn_de":    start_date,
                "end_de":    end_date,
                "page_count": 20,
            }
            res  = requests.get(url, params=params, timeout=10)
            data = res.json()
            if data.get("status") == "000":
                return data.get("list", [])
        except Exception as e:
            pass
        return []

    def get_today_all_disclosures(self):
        """오늘 전체 공시 조회 (중요 키워드 필터링)"""
        try:
            today = datetime.now().strftime("%Y%m%d")
            url   = f"{self.base_url}/list.json"
            params = {
                "crtfc_key": self.api_key,
                "bgn_de":    today,
                "end_de":    today,
                "page_count": 100,
            }
            res  = requests.get(url, params=params, timeout=10)
            data = res.json()
            if data.get("status") == "000":
                all_list = data.get("list", [])
                important = []
                for item in all_list:
                    report_nm = item.get("report_nm", "")
                    importance = None
                    for level, keywords in self.important_keywords.items():
                        for kw in keywords:
                            if kw in report_nm:
                                importance = level
                                break
                        if importance:
                            break
                    if importance in ["매우중요", "중요"]:
                        item["importance"] = importance
                        important.append(item)
                return important
        except Exception as e:
            print(f"  ❌ 전체 공시 조회 실패: {e}")
        return []

    def check_portfolio_disclosures(self, portfolio):
        """보유 종목 공시 체크"""
        results = []
        # 한국 주식만
        kr_stocks = {
            ticker: stock for ticker, stock in portfolio.items()
            if stock.get("market") == "KR"
        }

        for ticker, stock in kr_stocks.items():
            corp_code = self.get_corp_code(ticker)
            if not corp_code:
                continue

            disclosures = self.get_recent_disclosures(corp_code, days=1)
            for d in disclosures:
                report_nm  = d.get("report_nm", "")
                importance = None
                for level, keywords in self.important_keywords.items():
                    for kw in keywords:
                        if kw in report_nm:
                            importance = level
                            break
                    if importance:
                        break

                if importance:
                    results.append({
                        "ticker":     ticker,
                        "name":       stock.get("name", ticker),
                        "report_nm":  report_nm,
                        "rcept_dt":   d.get("rcept_dt", ""),
                        "importance": importance,
                        "url":        f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={d.get('rcept_no','')}",
                    })
            time.sleep(0.2)

        return results

    def build_alert_message(self, disclosures):
        """공시 알림 메시지"""
        if not disclosures:
            return None

        msg = f"📋 <b>DART 공시 알림</b> {datetime.now().strftime('%m/%d %H:%M')}\n\n"

        # 매우중요 먼저
        very_important = [d for d in disclosures if d["importance"] == "매우중요"]
        important      = [d for d in disclosures if d["importance"] == "중요"]

        if very_important:
            msg += "🚨 <b>매우 중요</b>\n"
            for d in very_important:
                msg += f"  • <b>{d['name']}</b> ({d['ticker']})\n"
                msg += f"    {d['report_nm']}\n"
                msg += f"    {d['url']}\n\n"

        if important:
            msg += "⚠️ <b>중요</b>\n"
            for d in important:
                msg += f"  • {d['name']} ({d['ticker']})\n"
                msg += f"    {d['report_nm']}\n\n"

        return msg

    def build_market_alert(self, disclosures):
        """시장 전체 중요 공시 알림"""
        if not disclosures:
            return None

        msg = f"📋 <b>오늘 주요 공시</b> {datetime.now().strftime('%m/%d %H:%M')}\n\n"

        very_imp = [d for d in disclosures if d.get("importance") == "매우중요"][:10]
        imp      = [d for d in disclosures if d.get("importance") == "중요"][:5]

        if very_imp:
            msg += "🚨 <b>매우 중요 공시</b>\n"
            for d in very_imp:
                msg += f"  • <b>{d.get('corp_name','')}</b>: {d.get('report_nm','')}\n"

        if imp:
            msg += "\n⚠️ <b>중요 공시</b>\n"
            for d in imp:
                msg += f"  • {d.get('corp_name','')}: {d.get('report_nm','')}\n"

        return msg


if __name__ == "__main__":
    print("=" * 50)
    print("📋 DART 공시 모니터 테스트")
    print("=" * 50)

    dm = DartMonitor()

    print("\n오늘 전체 중요 공시 조회 중...")
    all_disc = dm.get_today_all_disclosures()
    print(f"중요 공시 {len(all_disc)}개 발견")
    for d in all_disc[:10]:
        print(f"  [{d['importance']}] {d.get('corp_name','')}: {d.get('report_nm','')}")

    msg = dm.build_market_alert(all_disc)
    if msg:
        print("\n" + msg)
    else:
        print("\n오늘 중요 공시 없음")
