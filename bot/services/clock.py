"""台北時間。整個專案唯一換算時區的地方。

VM 跑 UTC，但所有對使用者有意義的時間都是台北時間：排程幾點推送、
今天是不是交易日、報價是哪一天的收盤。以前這個換算散在四個檔案
（main.py、watch.py、alert.py 各有一份 `_TAIPEI_UTC_OFFSET = 8`，
而 main.py 的註解還寫著「見 watch.py」——連當初寫的人都知道它散了）。

散開的代價不只是難找。兩處的週末判斷曾經一個用台北時間、一個用 UTC：

    收盤速報若設在台北 08:00 之前（/settime tw 07:00 是合法輸入），
    台北星期一 07:00 是 UTC 星期日 23:00 → 被當成週末跳過；
    台北星期六 07:00 是 UTC 星期五 23:00 → 被當成平日照推。

也就是星期一不推、星期六反而推，而且預設值 14:00 剛好不會發作。
"""
from datetime import datetime, time, timedelta, timezone

# 台北沒有日光節約時間，固定 UTC+8
TAIPEI = timezone(timedelta(hours=8))


def now() -> datetime:
    """現在的台北時間。"""
    return datetime.now(TAIPEI)


def today_str(fmt: str = "%Y-%m-%d") -> str:
    return now().strftime(fmt)


def is_weekend() -> bool:
    """台北時間的今天是不是週末。

    ⚠️ 一定要用台北時間判斷。用 UTC 判斷的話，台北清晨的排程會落在
    UTC 的前一天，整個週末判斷位移一天（見模組說明）。
    """
    return now().weekday() >= 5


def utc_time_for(hour: int, minute: int = 0) -> time:
    """把台北時間的時分轉成 run_daily 要的 UTC time。"""
    return time(hour=(hour - 8) % 24, minute=minute, tzinfo=timezone.utc)
