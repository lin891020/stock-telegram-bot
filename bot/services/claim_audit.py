"""報告產出後的數字稽核：找出既不在證據包、也推導不出來的數字。

為什麼需要這一層：證據包管「餵什麼進去」，consistency 管「餵的東西
對不對」，但沒有東西管「模型寫出來的到底是不是那些數字」。

難點在分辨兩種東西：
  編造   證據包裡沒有、也算不出來             → 要標記
  推導   從證據包的數字算出來的比率、成長率     → 合法

實測一份台股報告有 17 個數字不在證據包裡，逐一手驗後**全部**是合法
推導（淨利率、年增率、資產成長率）。只比對「有沒有出現過」的稽核會
被這些誤報淹沒到沒人看——所以這裡會實際把推導算一遍。

FinGround 那篇論文的數據支持這個重點：計算類宣稱的幻覺率最高
（28.4%），而其中 43% 要靠重算才抓得到。
"""
import itertools
import logging
import re

logger = logging.getLogger(__name__)

# 相對誤差容忍度。報告會四捨五入（31.83% 寫成 31.8%），太嚴會全是誤報。
_TOLERANCE = 0.015

# 這些數字不值得追：個位數、年份、章節編號
_MIN_VALUE = 10.0
_YEAR_RANGE = (1990, 2100)

_NUM_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")


def extract_numbers(text: str) -> set[float]:
    """抓出文字裡有意義的數字。"""
    out = set()
    for m in _NUM_RE.finditer(text):
        try:
            value = float(m.group().replace(",", ""))
        except ValueError:
            continue
        if value < _MIN_VALUE or _YEAR_RANGE[0] <= value <= _YEAR_RANGE[1]:
            continue
        out.add(value)
    return out


def _close(a: float, b: float) -> bool:
    if b == 0:
        return abs(a) < _TOLERANCE
    return abs(a - b) / abs(b) <= _TOLERANCE


def _derivations(base: list[float]):
    """從證據包的數字能合法算出來的值。

    只做報告真的會用到的幾種：比率（毛利率、淨利率）、成長率、
    差額（淨現金＝現金－負債）。不做任意組合——那會讓幾乎任何
    數字都「算得出來」，稽核就失去意義。
    """
    for x, y in itertools.permutations(base, 2):
        if y == 0:
            continue
        ratio = x / y
        if 0 < ratio < 100:
            yield ratio * 100        # 佔比／利潤率（%）
            yield (ratio - 1) * 100  # 成長率（%）
        yield x - y                  # 差額


def audit_numbers(report: str, evidence_text: str) -> list[float]:
    """回傳報告裡既不在證據包、也推導不出來的數字。"""
    ev_nums = extract_numbers(evidence_text)
    if not ev_nums:
        return []

    unexplained = []
    # 推導只用證據包裡較大的那些數字當基底，避免組合爆炸
    base = sorted(ev_nums, key=abs, reverse=True)[:40]
    derived = None

    for value in sorted(extract_numbers(report)):
        if any(_close(value, e) for e in ev_nums):
            continue
        if derived is None:
            derived = list(_derivations(base))
        if any(_close(value, d) for d in derived):
            continue
        unexplained.append(value)
    return unexplained


def audit_note(report: str, evidence_text: str) -> str:
    """給報告附加的稽核結果；沒問題時回空字串。

    刻意不改寫報告——改寫要用模型驗模型，那是另一個量級的工程，
    而且會引入新的錯誤。這裡只做「說清楚哪幾個數字查不到出處」，
    跟整套設計「寧可說查不到」的原則一致。
    """
    unexplained = audit_numbers(report, evidence_text)
    if not unexplained:
        return ""
    logger.warning("報告稽核：%d 個數字查不到出處 %s", len(unexplained), unexplained[:10])
    shown = ", ".join(f"{v:,.2f}".rstrip("0").rstrip(".") for v in unexplained[:8])
    more = f"　等 {len(unexplained)} 個" if len(unexplained) > 8 else ""
    return (
        "\n\n---\n\n"
        "⚠️ **自動稽核**：以下數字既不在本次資料中，也無法從中推算出來，"
        f"引用前請自行查證：{shown}{more}"
    )
