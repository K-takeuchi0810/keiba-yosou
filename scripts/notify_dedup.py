"""同じ通知を何度も送らないための重複判定 (2026-09-19)。

## なぜ要るか

`auto_predict` は Task Scheduler から **同じ日に 3 回**起動される。3 回とも
同じ結果 (生成完了 / 出走馬が未取込で中止) になるのが普通なので、同じ本文が
3 通届く。監査で 3 回連続の持ち越しになっていた。

## 設計の要点

**重複のキーは本文一致ではない。** 本文には生成時刻や URL が混ざるので、
1 文字でも変わると別物と判定されてしまう。`(通知の種類, 対象)` という
**安定した識別子**と、**意味のある中身だけを集めた payload** で判定する。

  key      = f"{notification_type}:{subject}"     例 "generation_complete:20260919"
  payload  = {"n_races": 12, "version": "v6", "push_ok": True}

生成時刻・URL 文字列・並び順は payload に入れない。中身が同じなら送らない。

**変わったときは「全文 + 変更点」を送る。** 差分だけを送ると、通知だけを見る
運用で文脈が落ちる。何が変わったかを頭に付けて全文を送る。

**判定に失敗したら送る側に倒す。** 状態ファイルが壊れていても、DB が落ちて
いても、**通知を消すより重複させる方がまし**。予想生成の中止通知を握り潰す
のが最悪の事故なので、例外は全部飲んで「送る」を返す。

**記録は送信が成功してから** (`decide` で判定、`record` で記録の 2 段)。
判定と同時に記録すると、Discord への POST が失敗したのに「送った」ことに
なり、次の起動で抑止されて通知が永久に消える。同じ理由で `record` は
`_notify` が真を返したときだけ呼ぶ。

**日付は Asia/Tokyo で決める。** 「同日」をシステムのローカル時刻任せにしない。
古い記録を捨てるときの基準も JST。

## 触らないもの

この層は **通知だけ**を見る。予測・特徴量・DB 取込・PIT・評価処理には
一切触れない (修正前後で予測結果が 1 行も変わらないことを確認する)。
"""
from __future__ import annotations

import json
import os
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

JST = timezone(timedelta(hours=9), "JST")

# 状態を残す期間 (JST の日数)。これより古い記録は捨てる。
# 「日付が変わったら前日の状態を引き継がない」ことはキーに対象日が入るので
# 自動的に満たされる。ここで消すのはファイルが際限なく育つのを防ぐため。
RETENTION_DAYS = 14


def state_path() -> Path:
    """状態ファイルの場所。

    `NOTIFY_STATE_PATH` で差し替えられる。**テストが本番の状態を汚さない**
    ために要る: テストが `main()` を通すと本番の状態ファイルに架空の payload が
    書かれ、当日の本物の中止通知が抑止されうる (導入直後に実際に起きた)。
    """
    override = os.environ.get("NOTIFY_STATE_PATH")
    if override:
        return Path(override)
    from config import PROJECT_ROOT

    return PROJECT_ROOT / "data" / "runtime" / "notification_state.json"


def jst_today() -> str:
    """JST の今日 (YYYYMMDD)。**システムのローカル時刻に依存させない**。"""
    return datetime.now(JST).strftime("%Y%m%d")


@dataclass(frozen=True)
class Decision:
    """送るかどうかと、その理由。"""

    should_send: bool
    reason: str                       # first_time / changed / duplicate / fail_open
    text: str                         # 実際に送る本文 (送らないときは空)
    changes: dict[str, tuple] | None = None
    degraded: bool = False            # 判定できず送る側に倒した


def _key(notification_type: str, subject: str) -> str:
    """重複判定のキー。**判定と記録で必ず同じものを使う**。

    以前は decide / record が別々に組み立てていた。片方だけ変えると、判定は
    毎回「初回」になり記録だけ溜まる = 抑止が黙って効かなくなる。
    """
    return f"{notification_type}:{subject}"


def _canonical(payload: dict[str, Any]) -> str:
    """payload を順序に依存しない文字列にする。

    辞書の並び順が変わっただけで「変わった」と判定されると、本質的でない差で
    再通知してしまう。キーでソートして正規化する。
    """
    return json.dumps(payload, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"), default=str)


def _load(path: Path) -> dict:
    """状態を読む。**壊れていても例外を出さない** (壊れた分だけ捨てる)。

    値が dict でない壊れ方 (`{"key": "ごみ"}`) を素通りさせると、あとで
    `_prune` の `.get` が毎回 AttributeError になり、判定は永久に fail_open、
    記録も毎回失敗して **自己修復しない**。構文が壊れている場合だけでなく、
    中身の型が壊れている場合もここで捨てる。
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except Exception:
        # 壊れたファイルで通知が止まる方が事故なので、握り潰して空から始める。
        return {}
    if not isinstance(data, dict):
        return {}
    return {k: v for k, v in data.items() if isinstance(v, dict)}


def _save(path: Path, data: dict) -> None:
    """状態を書く。途中で落ちても壊れたファイルを残さないよう原子的に置換する。

    `default=str` は `_canonical` と **必ず揃えること**。片方だけに付いていると、
    JSON 化できない値を含む payload が「判定は通るのに記録だけ毎回失敗する」= 抑止が
    無音で永久に死ぬ、という状態になる。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    _sweep_stale_tmp(path.parent)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1, default=str)
        # Windows では他プロセス (バックアップ / ウイルス対策 / エディタ) が
        # 開いているだけで replace が PermissionError になる。数十 ms で消える
        # ことが多いので少しだけ待って再試行する。
        for attempt in range(3):
            try:
                os.replace(tmp, path)
                break
            except PermissionError:
                if attempt == 2:
                    raise
                time.sleep(0.05)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _sweep_stale_tmp(directory: Path) -> None:
    """置換前に落ちて取り残された一時ファイルを掃除する。

    `mkstemp` と `os.replace` のあいだでプロセスが死ぬと `tmpXXXX.tmp` が残り、
    誰も消さない。1 日以上古いものだけ消す (書き込み中のものを消さないため)。
    """
    try:
        cutoff = time.time() - 86400
        for f in directory.glob("tmp*.tmp"):
            try:
                if f.stat().st_mtime < cutoff:
                    f.unlink()
            except OSError:
                pass
    except Exception:                              # noqa: BLE001
        pass


def _prune(data: dict, today: str) -> dict:
    try:
        cutoff = (datetime.strptime(today, "%Y%m%d")
                  - timedelta(days=RETENTION_DAYS)).strftime("%Y%m%d")
    except ValueError:
        return data
    return {k: v for k, v in data.items()
            if str(v.get("date_jst", today)) >= cutoff}


def _diff(old: dict, new: dict) -> dict[str, tuple]:
    keys = sorted(set(old) | set(new))
    return {k: (old.get(k), new.get(k)) for k in keys if old.get(k) != new.get(k)}


def decide(notification_type: str, subject: str, payload: dict[str, Any],
           text: str, path: Path | None = None) -> Decision:
    """この通知を送るべきか決める。**例外は投げない。状態も書かない。**

    記録は送信が成功してから `record()` で行う (この関数は読むだけ)。

    `notification_type` は "generation_complete" のような通知の種類。
    `subject` は対象 (レース日や race_id) で、**安定していること**が条件。
    `payload` は意味のある中身だけ。生成時刻や URL を入れてはいけない。
    """
    try:
        p = path or state_path()
        today = jst_today()
        key = _key(notification_type, subject)
        data = _prune(_load(p), today)
        prev = data.get(key)

        if prev is None:
            decision = Decision(True, "first_time", text)
        elif prev.get("canonical") == _canonical(payload):
            return Decision(False, "duplicate", "")
        else:
            changes = _diff(prev.get("payload") or {}, payload)
            lines = "\n".join(
                f"  - {k}: {o} -> {n}" for k, (o, n) in changes.items())
            decision = Decision(
                True, "changed",
                f"🔁 **前回から変更あり**\n{lines}\n\n{text}", changes)

        return decision
    except Exception as exc:                       # noqa: BLE001
        # **握り潰して送る側に倒す。** 重複を 1 通許す方が、中止通知を
        # 消してしまうよりはるかにまし。
        return Decision(True, f"fail_open:{type(exc).__name__}", text,
                        degraded=True)


def record(notification_type: str, subject: str, payload: dict[str, Any],
           path: Path | None = None, supersedes: bool = True) -> bool:
    """**送信が成功してから**呼ぶ。次回から同じ中身を抑止する。

    判定と同時に記録してはいけない。Discord への POST が失敗したのに「送った」
    と記録すると、次の起動で抑止されて **その通知は永久に届かない**。中止通知
    でこれが起きると、その日の予想を失ったことに誰も気付けない。

    `supersedes` は「これは対象の結末を伝える通知か」。True なら同じ対象の
    別の結末の記録を捨てる (下記)。最終確認の heartbeat のように結末ではない
    通知は False にする。結末の記録を消してしまうと、そのあと同じ結末を
    もう 1 通送ってしまう。

    記録に失敗しても例外は投げない (最悪もう 1 通届くだけ)。成否を返す。
    """
    try:
        p = path or state_path()
        today = jst_today()
        data = _prune(_load(p), today)
        # 同じ対象について **別の結末** を伝えたら、それ以前の結末の記録は捨てる。
        # これが無いと「08:00 生成失敗 → 09:00 生成成功 → 11:00 また生成失敗」の
        # 3 通目が「朝と同じ失敗」として抑止され、その日が成功で終わったと
        # 誤解したまま終わる (実測で再現した穴)。
        if supersedes:
            data = {k: v for k, v in data.items()
                    if v.get("subject") != subject
                    or v.get("notification_type") == notification_type}
        data[_key(notification_type, subject)] = {
            "canonical": _canonical(payload), "payload": payload,
            "date_jst": today,
            "sent_at": datetime.now(JST).isoformat(timespec="seconds"),
            "notification_type": notification_type,
            "subject": subject}
        _save(p, data)
        return True
    except Exception as exc:                       # noqa: BLE001
        # 記録できなくても通知は既に届いているので送信側は成功。ただし
        # **無音にはしない**。ここが黙ると、抑止が効かず毎回 3 通届く状態に
        # 退行しても痕跡が残らない。
        print(f"WARN: 通知の記録に失敗しました ({type(exc).__name__}: {exc})。"
              f"次の起動で同じ通知がもう 1 通届きます。")
        return False
