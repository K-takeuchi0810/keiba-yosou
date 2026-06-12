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
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path

from config import DATA_DIR

logger = logging.getLogger(__name__)

STATE_FILE = DATA_DIR / "fetch_state.json"

# JV-Link は yyyymmddHHMMSS 形式の 14 桁を要求
DEFAULT_FROMTIME = "19860101000000"


def load_state() -> dict[str, str]:
    if not STATE_FILE.exists():
        return {}
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        # 黙って {} を返すと fromtime が 1986 に巻き戻り、数時間級の
        # 全量再取得が「無言で」始まる (2026-06-13 v2 監査指摘)。
        # 巻き戻り自体は安全側 (UPSERT 冪等) だが、必ず警告を残す。
        logger.warning(
            "fetch_state.json が壊れています (%s)。全 dataspec の fromtime が "
            "初期値 (1986) に戻り、次回取得は全量再取得になります。", STATE_FILE)
        return {}


def save_state(state: dict[str, str]) -> None:
    """tmp への書き出し + os.replace によるアトミック更新。

    直書きだと書込み途中のクラッシュで JSON が壊れ、load_state の
    フォールバックにより fromtime 巻き戻り事故になる。
    """
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".json.tmp")
    tmp.write_text(
        json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    os.replace(tmp, STATE_FILE)


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
