from datetime import datetime, timedelta

# 间隔天数对应每个熟悉度等级（0~5）
INTERVALS = [0, 1, 3, 7, 14, 30]


def next_review(level: int) -> str:
    days = INTERVALS[min(level, len(INTERVALS) - 1)]
    dt = datetime.now() + timedelta(days=days)
    return dt.strftime("%Y-%m-%d")


def is_due(review_date: str) -> bool:
    today = datetime.now().strftime("%Y-%m-%d")
    return review_date <= today
