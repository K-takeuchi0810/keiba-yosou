"""dataspec ごとの最終取得タイムスタンプを JSON で永続化する。

差分取得の起点は「JV-Link が前回 JVOpen で返した last_timestamp」。
これを覚えておかないと毎回頭から再取得する羽目になる。

形式:
{
    "RACE": "20260502112825",
    "DIFN": "20260502112825",
    ...
}

注意: JV-Link の option=1/2 は fromtime が最新タイムスタンプと完全一致だと
rc=-1 (パラメータエラー) を返す仕様（実装バグに近い挙動）。回避のため
get_fromtime() は保存値から 1 秒戻したものを返す。境界の最後の 1 ファイルが
重複取得されることがあるが DB は UPSERT なので副作用なし。
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

from config import DATA_DIR

STATE_FILE = DATA_DIR / "fetch_state.json"

# JV-Link は yyyymmddHHMMSS 形式の 14 桁を要求
DEFAULT_FROMTIME = "19860101000000"


def load_state() -> dict[str, str]:
    if not STATE_FILE.exists():
        return {}
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def save_state(state: dict[str, str]) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(
        json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def _shift_back_1s(ts: str) -> str:
    """yyyymmddHHMMSS から 1 秒引く。"""
    try:
        dt = datetime.strptime(ts, "%Y%m%d%H%M%S")
    except ValueError:
        return ts
    return (dt - timedelta(seconds=1)).strftime("%Y%m%d%H%M%S")


def get_fromtime(dataspec: str, default: str = DEFAULT_FROMTIME) -> str:
    saved = load_state().get(dataspec)
    if saved is None or saved == default:
        return default
    return _shift_back_1s(saved)


def update_timestamp(dataspec: str, last_timestamp: str) -> None:
    state = load_state()
    if last_timestamp:
        state[dataspec] = last_timestamp
        save_state(state)
