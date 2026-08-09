"""data/*.json 的共用讀寫：原子寫入 + 壞檔容錯。

以前每個狀態檔各自寫一份 _load/_save，有兩個問題：

1. write_text 是「先清空再寫」。在那中間 VM 重開或 systemd 重啟，
   檔案就停在半截。自選股壞掉等於每個指令都掛——它幾乎哪裡都要讀。
   改成寫暫存檔再 os.replace（同檔案系統上是原子操作），
   要嘛是舊的完整內容、要嘛是新的完整內容，不會有中間狀態。

2. 五份幾乎一樣的 _load/_save，其中 watchlist 那份還漏了 try/except。
   同樣的防護要靠每個檔案各自記得寫，遲早會漏。
"""
import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DATA_DIR = Path("data")


def load_json(path: Path, default: Any) -> Any:
    """讀 JSON。檔案不存在或壞掉都回 default，不讓單一壞檔弄掛整隻 bot。"""
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("狀態檔讀取失敗，改用預設值（%s）：%s", path, e)
        return default


def save_json(path: Path, data: Any) -> None:
    """原子寫入：先寫同目錄的暫存檔，fsync 後再 replace。

    暫存檔一定要跟目標同目錄——os.replace 只有在同一個檔案系統內才是原子的。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, ensure_ascii=False, indent=2)

    fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), prefix=path.name, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())  # 確保資料真的落盤，不只是進 page cache
        os.replace(tmp_path, path)
    except BaseException:
        # 失敗就把暫存檔清掉，不要在 data/ 留一堆 .tmp
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
