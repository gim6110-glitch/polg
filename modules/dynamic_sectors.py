import sys
import os
import json
import asyncio
from datetime import datetime, timedelta
from dotenv import load_dotenv

sys.path.insert(0, '/home/dps/stock_ai')
from modules.sector_db import SECTOR_DB

load_dotenv('/home/dps/stock_ai/.env')

class DynamicSectors:
    """
    AI가 매일 뉴스 분석해서 새 테마 자동 감지
    임시 테마 3일 후 자동 제거
    완전 정착하면 고정 섹터 DB에 추가
    """
    def __init__(self):
        self.dynamic_file = "/home/dps/stock_ai/data/dynamic_sectors.json"
        self.dynamic      = self._load()

    def _load(self):
        if os.path.exists(self.dynamic_file):
            with open(self.dynamic_file, "r", encoding="utf-8") as f:
                return json.load(f)
        return {"themes": {}}

    def _save(self):
        os.makedirs("/home/dps/stock_ai/data", exist_ok=True)
        with open(self.dynamic_file, "w", encoding="utf-8") as f:
            json.dump(self.dynamic, f, ensure_ascii=False, indent=2)

    async def detect_new_themes(self, news_list):
        """AI로 새 테마 감지"""
        news_text = ""
        for i, n in enumerate(news_list[:20]):
            news_text += f"{i+1}. [{n['source']}] {n['title']}\n"

        existing = list(SECTOR_DB.keys()) + list(self.dynamic['themes'].keys())
        existing_text = ", ".join(existing)

        from anthropic import Anthropic
        client = Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))

        prompt = f"""오늘 뉴스에서 새로운 주식 테마/섹터를 감지해주세요.

=== 오늘 뉴스 ===
{news_text}

=== 이미 추적 중인 섹터 ===
{existing_text}

기존 섹터에 없는 새로운 테마가 있으면 찾아주세요.
없으면 빈 배열로 답해주세요.

JSON으로만 답변:
{{
  "new_themes": [
    {{
      "name": "테마명",
      "description": "테마 설명 한줄",
      "market": "KR 또는 US 또는 BOTH",
      "reason": "이 테마가 급부상한 이유",
      "stocks": {{
        "종목명1": "티커1",
        "종목명2": "티커2",
        "종목명3": "티커3"
      }},
      "confidence": 0.0~1.0
    }}
  ]
}}"""

        try:
            res  = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=800,
                messages=[{"role": "user", "content": prompt}]
            )
            text = res.content[0].text.strip()
            import re
            m = re.search(r'\{.*\}', text, re.DOTALL)
            if m:
                data = json.loads(m.group())
                return data.get("new_themes", [])
        except Exception as e:
            print(f"❌ 새 테마 감지 실패: {e}")
        return []

    def add_temp_theme(self, theme_data):
        """임시 테마 추가 (3일 유효)"""
        name = theme_data.get("name")
        if not name:
            return False

        # 이미 고정 섹터에 있으면 스킵
        if name in SECTOR_DB:
            return False

        today    = datetime.now().strftime("%Y-%m-%d")
        expire   = (datetime.now() + timedelta(days=3)).strftime("%Y-%m-%d")

        # 기존 임시 테마면 mentions 증가
        if name in self.dynamic['themes']:
            self.dynamic['themes'][name]['mentions'] += 1
            self.dynamic['themes'][name]['last_seen'] = today
            # 3일 연속 언급되면 만료일 연장
            mentions = self.dynamic['themes'][name]['mentions']
            if mentions >= 3:
                self.dynamic['themes'][name]['status'] = '정착중'
                expire = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
            self.dynamic['themes'][name]['expires'] = expire
        else:
            self.dynamic['themes'][name] = {
                "name":        name,
                "description": theme_data.get("description", ""),
                "market":      theme_data.get("market", "KR"),
                "reason":      theme_data.get("reason", ""),
                "stocks":      theme_data.get("stocks", {}),
                "confidence":  theme_data.get("confidence", 0.5),
                "status":      "임시",
                "mentions":    1,
                "added":       today,
                "last_seen":   today,
                "expires":     expire,
            }

        self._save()
        return True

    def remove_expired(self):
        """만료된 임시 테마 제거"""
        today   = datetime.now().strftime("%Y-%m-%d")
        removed = []

        for name, theme in list(self.dynamic['themes'].items()):
            if theme.get('expires', '9999-12-31') < today:
                removed.append(name)
                del self.dynamic['themes'][name]

        if removed:
            self._save()
            print(f"🗑️ 만료 테마 제거: {', '.join(removed)}")

        return removed

    def promote_to_permanent(self, theme_name):
        """임시 테마를 고정 섹터 DB에 영구 추가"""
        if theme_name not in self.dynamic['themes']:
            return False, "임시 테마에 없음"

        theme = self.dynamic['themes'][theme_name]

        # sector_db.py에 추가
        new_sector = f'''
    "{theme_name}": {{
        "description": "{theme.get('description', '')}",
        "market": "{theme.get('market', 'KR')}",
        "대장주": {json.dumps(theme.get('stocks', {}), ensure_ascii=False)},
        "2등주": {{}},
        "소부장": {{}}
    }},'''

        try:
            with open('/home/dps/stock_ai/modules/sector_db.py', 'r') as f:
                content = f.read()

            # SECTOR_DB 마지막 항목 앞에 추가
            insert_point = content.rfind('}  # end')
            if insert_point == -1:
                insert_point = content.rfind('\n}')

            new_content = content[:insert_point] + new_sector + content[insert_point:]

            with open('/home/dps/stock_ai/modules/sector_db.py', 'w') as f:
                f.write(new_content)

            # 임시 목록에서 제거
            del self.dynamic['themes'][theme_name]
            self._save()

            return True, f"✅ {theme_name} 고정 섹터로 승격 완료"
        except Exception as e:
            return False, f"❌ 승격 실패: {e}"

    def get_all_watchlist(self):
        """고정 + 임시 전체 감시 종목"""
        watchlist = {}

        # 고정 섹터 (오늘 순환매 파일에서)
        rotation_file = "/home/dps/stock_ai/data/sector_rotation.json"
        if os.path.exists(rotation_file):
            with open(rotation_file, "r") as f:
                rot = json.load(f)
            today = datetime.now().strftime("%Y-%m-%d")
            for key in ['rotation_KR', 'rotation_US']:
                data = rot.get(key, {})
                if data.get('date') == today:
                    for sector_name, rotation in data.get('results', {}).items():
                        if sector_name in SECTOR_DB:
                            target = rotation.get('target', '대장주')
                            stocks = SECTOR_DB[sector_name].get(target, {})
                            watchlist.update(stocks)

        # 임시 테마 종목
        for name, theme in self.dynamic['themes'].items():
            watchlist.update(theme.get('stocks', {}))

        return watchlist

    def build_theme_message(self, new_themes, removed_themes):
        """새 테마 알림 메시지"""
        if not new_themes and not removed_themes:
            return None

        msg = f"🆕 <b>테마 업데이트</b> {datetime.now().strftime('%m/%d')}\n\n"

        if new_themes:
            msg += "🔥 <b>새로 감지된 테마</b>\n"
            for t in new_themes:
                conf_emoji = "🔴" if t['confidence'] >= 0.8 else "🟡" if t['confidence'] >= 0.6 else "⚪"
                market_flag = {"KR": "🇰🇷", "US": "🇺🇸", "BOTH": "🌐"}.get(t['market'], "🌐")
                stocks_text = " / ".join(
                    [f"{n}({tk})" for n, tk in list(t.get('stocks', {}).items())[:3]]
                )
                existing = self.dynamic['themes'].get(t['name'], {})
                mentions = existing.get('mentions', 1)
                status   = existing.get('status', '임시')

                msg += f"""━━━━━━━━━━━━━━━━━━━
{conf_emoji} {market_flag} <b>{t['name']}</b> [{status} {mentions}일째]
📋 {t.get('reason', '')}
🎯 {stocks_text}
⏰ 만료: {existing.get('expires', '3일 후')}

"""

        if removed_themes:
            msg += f"🗑️ <b>만료 제거:</b> {', '.join(removed_themes)}\n"

        msg += f"\n💡 /add_sector {'{테마명}'} → 고정 섹터로 승격"
        return msg

    def get_status_text(self):
        """현재 임시 테마 현황"""
        if not self.dynamic['themes']:
            return "현재 임시 테마 없음"

        msg = "🆕 <b>현재 임시 테마</b>\n\n"
        for name, theme in self.dynamic['themes'].items():
            conf_emoji = "🔴" if theme['confidence'] >= 0.8 else "🟡"
            market_flag = {"KR": "🇰🇷", "US": "🇺🇸", "BOTH": "🌐"}.get(theme['market'], "🌐")
            msg += f"{conf_emoji} {market_flag} <b>{name}</b>\n"
            msg += f"  언급: {theme['mentions']}일 | 상태: {theme['status']}\n"
            msg += f"  만료: {theme['expires']}\n"
            stocks = list(theme.get('stocks', {}).items())[:3]
            if stocks:
                msg += f"  종목: {' / '.join([f'{n}({t})' for n, t in stocks])}\n"
            msg += "\n"
        return msg

if __name__ == "__main__":
    import asyncio
    from modules.news_collector import NewsCollector

    async def test():
        print("=" * 50)
        print("🆕 동적 테마 감지 테스트")
        print("=" * 50)

        ds   = DynamicSectors()
        nc   = NewsCollector()
        news = nc.collect_news(max_per_feed=5)

        print("만료 테마 정리 중...")
        removed = ds.remove_expired()

        print("새 테마 감지 중...")
        new_themes = await ds.detect_new_themes(news)

        if new_themes:
            print(f"\n✅ {len(new_themes)}개 새 테마 감지!")
            for t in new_themes:
                ds.add_temp_theme(t)
                print(f"  → {t['name']} (신뢰도: {t['confidence']})")
        else:
            print("새 테마 없음")

        msg = ds.build_theme_message(new_themes, removed)
        if msg:
            print("\n" + msg)

        print("\n현재 임시 테마:")
        print(ds.get_status_text())

    asyncio.run(test())
