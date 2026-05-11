"""JV-Data コード表 → 表示用名称のマッピング。

仕様書 docs/JV-Data4901.pdf §コード表 の主要分のみ。
未網羅のコードはコード文字列をそのまま返すフォールバック付き。
"""

from __future__ import annotations

TRACK_NAMES = {
    "01": "札幌", "02": "函館", "03": "福島", "04": "新潟", "05": "東京",
    "06": "中山", "07": "中京", "08": "京都", "09": "阪神", "10": "小倉",
    # 30 番台以降は地方競馬。海外もあるので表示時はコードのまま。
}

WEATHER_NAMES = {
    "0": "", "1": "晴", "2": "曇", "3": "小雨", "4": "雨", "5": "小雪", "6": "雪",
}

GROUND_NAMES = {
    "0": "", "1": "良", "2": "稍重", "3": "重", "4": "不良",
}

SEX_NAMES = {"0": "", "1": "牡", "2": "牝", "3": "騸"}

GRADE_NAMES = {
    "A": "G1", "B": "G2", "C": "G3",
    "D": "重賞以外", "E": "L",
    "F": "重賞", "G": "J·G1", "H": "J·G2", "I": "J·G3",
}

WEEKDAY_NAMES = {
    "1": "土", "2": "日", "3": "祝", "4": "月", "5": "火",
    "6": "水", "7": "木", "8": "金",
}


def track_name(code: str) -> str:
    return TRACK_NAMES.get(code, code)


def weather_name(code: str) -> str:
    return WEATHER_NAMES.get(code, "")


def ground_name(code: str) -> str:
    return GROUND_NAMES.get(code, "")


def sex_name(code: str) -> str:
    return SEX_NAMES.get(code, "")


def grade_name(code: str) -> str:
    return GRADE_NAMES.get(code, "")


def weekday_name(code: str) -> str:
    return WEEKDAY_NAMES.get(code, "")


def track_type(code: str) -> str:
    """トラックコード（2009）→ 大分類。"""
    if not code or code in ("00", " "):
        return ""
    try:
        n = int(code)
    except ValueError:
        return code
    if 10 <= n <= 22:
        return "芝"
    if 23 <= n <= 29:
        return "ダート"
    if 51 <= n <= 59:
        return "障害"
    return code


def race_id_to_date(year: str, month_day: str) -> str:
    """2026 + 0503 → 2026/05/03"""
    if len(year) == 4 and len(month_day) == 4:
        return f"{year}/{month_day[:2]}/{month_day[2:]}"
    return f"{year}{month_day}"


def time_hhmm(s: str) -> str:
    """0945 → 09:45"""
    if len(s) == 4 and s.isdigit():
        return f"{s[:2]}:{s[2:]}"
    return s


def burden_weight_kg(value: int) -> str:
    """0.1kg 単位 → 表示用 kg。"""
    if not value:
        return ""
    return f"{value / 10:.1f}"
