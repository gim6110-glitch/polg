import json
import os
from datetime import date

BUDGET_FILE = "/media/dps/T7/stock_ai/data/ai_budget.json"
DAILY_LIMIT = 10


def can_call_ai(module_name="") -> bool:
    today = str(date.today())
    try:
        with open(BUDGET_FILE, "r") as f:
            data = json.load(f)
    except Exception:
        data = {}

    count = int(data.get(today, 0))
    if count >= DAILY_LIMIT:
        return False

    data[today] = count + 1
    os.makedirs(os.path.dirname(BUDGET_FILE), exist_ok=True)
    with open(BUDGET_FILE, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return True


def get_today_usage() -> str:
    today = str(date.today())
    try:
        with open(BUDGET_FILE, "r") as f:
            data = json.load(f)
        return f"AI 호출 {int(data.get(today, 0))}/{DAILY_LIMIT}회"
    except Exception:
        return f"AI 호출 0/{DAILY_LIMIT}회"
