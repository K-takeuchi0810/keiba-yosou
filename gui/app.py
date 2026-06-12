"""管理画面（pywebview）。

ボタンから JVLink 取得・予想生成・公開（iCloud Drive へ書き出し）を実行し、
生成済みの index.html をその場でプレビューする。
"""

from __future__ import annotations

import os
import json
import subprocess
import sys
import threading
import traceback
import time
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

import webview

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import (
    BUY_FILTER_DEFAULT,
    ICLOUD_PUBLISH_DIR,
    WEB_DIST,
    ensure_dirs,
    is_whitelisted_race,
)
from db import open_db
from jvlink_client import ALL_DATASPECS, JVLinkClient
from jvlink_client.ingest import ingest_all
from predictor import is_tentative, predict_race
from predictor.portfolio import compute_day_portfolio
from predictor.risk import recommended_fraction
from scripts.backtest import get_payout, horses_for_race, list_races
from scripts.fetch_odds import race_key
from web.codes import race_id_to_date, track_name
from web.generator import publish_to_icloud, render

ensure_dirs()

# .venv64 (Python 3.14 64-bit) Python のパス。LightGBM v5 ensemble 予測のため
# GUI (.venv32) から subprocess 経由で render を呼ぶ。詳細は
# scripts/predict.py や docs/OPERATION.md の "2 venvs" アーキテクチャ参照。
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_VENV64_PYTHON = _PROJECT_ROOT / ".venv64" / "Scripts" / "python.exe"


def _run_render_in_venv64(from_date: str | None, to_date: str | None,
                         publish: bool = True,
                         cancel_check=None,
                         on_elapsed=None) -> dict:
    """render() を .venv64 subprocess で実行し、結果 dict を返す。

    なぜ subprocess: GUI は pywebview 制約で .venv32 (Python 3.13 32-bit) で
    動くが、LightGBM は .venv64 にしか install されていない。同一プロセスで
    render() を呼ぶと predictor.ml_model.load_lgbm() が失敗し、rule-only
    予測になってしまう (backtest と乖離)。subprocess で .venv64 を kick
    すれば LightGBM v5 ensemble が正しく適用される。

    cancel_check: 定期的に呼ばれる callable。例外 (CancelledError) を
    投げたら子プロセスを kill して再送出する。予想生成は最長ステージ
    なのに従来 (subprocess.run ブロック) は中止が届かなかった。
    """
    if not _VENV64_PYTHON.exists():
        # フォールバック: .venv64 が無い環境では in-process render (rule-only)
        path = render(from_date=from_date, to_date=to_date)
        pub = publish_to_icloud() if publish else None
        return {"rendered": str(path), "published": str(pub) if pub else None,
                "warning": "venv64 not found, fell back to rule-only render"}
    cmd = [str(_VENV64_PYTHON), "-m", "web.generator", "--json"]
    if from_date:
        cmd += ["--from", from_date]
    if to_date:
        cmd += ["--to", to_date]
    if not publish:
        cmd += ["--no-publish"]
    # PYTHONIOENCODING=utf-8 を child に渡し、Windows console の cp932 default
    # で stdout が encode されないようにする (日本語パス文字化け防止)。
    child_env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding="utf-8", errors="replace",
        cwd=str(_PROJECT_ROOT), env=child_env,
    )
    # communicate(timeout) ループ: pipe デッドロックを避けつつ
    # 0.5 秒ごとに cancel_check と経過通知 (on_elapsed) を差し込む。
    # 予想生成は最長ステージ (分単位) なのに従来は静止表示のままで
    # 「固まったように見える」UX だった (2026-06-13 v2 監査指摘)。
    start = time.time()
    while True:
        try:
            stdout, stderr = proc.communicate(timeout=0.5)
            break
        except subprocess.TimeoutExpired:
            # cancel_check を先に評価する (逆順だと中止押下後の 0.5 秒間
            # 「中止しています...」が経過表示で上書きされてチラつく)
            if cancel_check is not None:
                try:
                    cancel_check()
                except BaseException:
                    proc.kill()
                    proc.communicate()
                    raise
            if on_elapsed is not None:
                on_elapsed(time.time() - start)
    if proc.returncode != 0:
        raise RuntimeError(
            f"venv64 render failed (exit {proc.returncode}):\n"
            f"stderr: {stderr[-2000:]}"
        )
    # 最終行から JSON を取り出す (途中の INFO log 等を skip)
    last_json_line = ""
    for line in stdout.strip().split("\n"):
        line = line.strip()
        if line.startswith("{") and line.endswith("}"):
            last_json_line = line
    if not last_json_line:
        raise RuntimeError(
            f"venv64 render did not emit JSON. stdout: {stdout[-2000:]}"
        )
    return json.loads(last_json_line)


class CancelledError(Exception):
    pass


class BusyError(Exception):
    """別アクション実行中の二重起動。_safe が status を触らずに返すための専用型。"""


# GUI ミニ backtest の統計ガード閾値。表示文字列も Python 側で組み立てて
# JS に渡す (閾値 30 が Python 判定と JS 表示文字列に二重直書きになる事故防止)。
BT_LOW_N_THRESHOLD = 30
BT_LOW_N_NOTE = f"n<{BT_LOW_N_THRESHOLD} 参考値"
# anchor (確定データの最新日) が表示対象日からこれ以上古いと警告表示
BT_ANCHOR_STALE_DAYS = 7


def _normalize_date(value: object) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def _fetched_filenames(summaries: list[dict]) -> set[str] | None:
    """fetch_all の戻りから書き出されたファイル名 set を作る。

    ingest_all(only_files=...) に渡して「同名ファイルの内容更新」(週次 RACE) を
    確実に再取込する。1 件も無ければ None (= 通常の全体スキャン)。
    """
    names = {n for s in summaries for n in (s.get("filenames") or [])}
    return names or None


def _error_hint(e: Exception) -> str:
    text = f"{type(e).__name__}: {e}"
    if "venv64" in text or "did not emit JSON" in text:
        return ("予想 HTML 生成 (.venv64) で失敗しています。.venv64/Scripts/python.exe の存在と、"
                "コンソールで `python -m web.generator --no-publish` が単体で通るか確認してください。")
    if "JVInit" in text or "JV-Link" in text:
        return "JV-Link が起動できません。JV-Link の設定と 32bit Python で起動しているか確認してください。"
    if "32" in text and "bit" in text:
        return "32bit Python で起動しているか確認してください。"
    if "database is locked" in text:
        return "SQLite DB がロックされています。別の実行中プロセスや開いている確認ツールを閉じてください。"
    if "iCloud" in text or "ICLOUD" in text:
        return "iCloud Drive が同期/マウントされているか確認してください。"
    if "Permission denied" in text:
        return "ファイル権限で失敗しています。対象フォルダを開いているアプリを閉じるか、権限を確認してください。"
    return ""


def _safe(fn):
    """API 呼び出しをまるごと try で包んで例外を JSON 化する。"""

    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except BusyError as e:
            # 実行中アクションの status には触らない (上書きすると走っている
            # 本体の running 表示・キャッシュが壊れる)。busy はそのまま返す。
            return {"ok": False, "busy": True, "message": str(e)}
        except CancelledError:
            if args and hasattr(args[0], "_set_status"):
                # 中止 = ingest 途中の可能性。部分取込み DB で再充填された
                # キャッシュが生存しないよう、失敗経路でも必ず invalidate
                # (正常系の「完了側の防御」と対になる)。
                args[0]._invalidate_caches()
                args[0]._set_status("中止しました", "cancelled", running=False)
            return {"ok": False, "cancelled": True, "message": "中止しました"}
        except Exception as e:
            if args and hasattr(args[0], "_set_status"):
                args[0]._invalidate_caches()
                args[0]._set_status(f"エラー: {type(e).__name__}: {e}", "error", running=False)
            return {
                "ok": False,
                "error": f"{type(e).__name__}: {e}",
                "hint": _error_hint(e),
                "trace": traceback.format_exc(),
            }

    wrapper.__name__ = fn.__name__
    return wrapper


class Api:
    """JS から呼び出される Python 側のエンドポイント。"""

    def __init__(self) -> None:
        self._status_lock = threading.Lock()
        self._status = {
            "running": False,
            "stage": "idle",
            "message": "準備完了。",
            "updated_at": datetime.now().strftime("%H:%M:%S"),
            "detail": {},
        }
        self._cancel_event = threading.Event()
        self._progress_samples: list[tuple[float, float]] = []
        self._weather_cache: dict[tuple[str, str], tuple[float, dict]] = {}
        # ダッシュボード計算キャッシュ。predict_race (全レース) と
        # _recent_backtest (最大100日分の再予測) は数秒かかるため、
        # フィルタ変更や期間ボタン切替のたびに再計算しない。
        # データが変わりうるアクション開始時 (_begin_run) に無効化する。
        self._cache_lock = threading.Lock()
        self._pred_cache: dict[tuple[str, str], list] = {}
        self._backtest_cache: dict[tuple[str, str], dict] = {}
        # 世代カウンタ: invalidate をまたいで走っていた計算が完了後に
        # 古い結果をキャッシュへ書き戻すのを防ぐ (計算開始時の世代と
        # 書き込み時の世代が一致するときのみ store する)。
        self._cache_gen = 0

    def _begin_run(self) -> None:
        # Python 側の二重実行ガード。JS の「refreshStatus → disable」の間の
        # TOCTOU 窓 (数十 ms) で 2 操作が滑り込むと JV-Link COM が二重 Open
        # しうるため、running フラグの check-and-set を lock 内で原子的に行う
        # (2026-06-13 v2 監査 gui-ux 指摘の閉鎖)。
        with self._status_lock:
            if self._status.get("running"):
                raise BusyError("別の処理が実行中です。完了後に再実行してください。")
            self._status["running"] = True
        self._cancel_event.clear()
        self._progress_samples = []
        self._invalidate_caches()

    def _invalidate_caches(self) -> None:
        with self._cache_lock:
            self._cache_gen += 1
            self._pred_cache.clear()
            self._backtest_cache.clear()

    def _check_cancel(self) -> None:
        if self._cancel_event.is_set():
            raise CancelledError()

    def _set_status(
        self,
        message: str,
        stage: str = "",
        detail: dict | None = None,
        running: bool | None = None,
    ) -> None:
        with self._status_lock:
            if running is not None:
                self._status["running"] = running
            if stage:
                self._status["stage"] = stage
            self._status["message"] = message
            self._status["updated_at"] = datetime.now().strftime("%H:%M:%S")
            self._status["detail"] = detail or {}

    def _progress(self, stage: str, info: dict) -> None:
        self._check_cancel()
        ds = info.get("dataspec", "")
        progress = self._stage_progress(ds, stage)
        detail = dict(info)
        if progress is not None:
            detail.update(self._progress_detail(progress, 100))
        if stage == "open":
            msg = f"{ds} 開始: 読込{info.get('readcount', 0)}件 / DL{info.get('downloadcount', 0)}件"
        elif stage == "download":
            msg = f"{ds} ダウンロード中: 残り{info.get('remaining', 0)}"
        elif stage == "read":
            msg = f"{ds} 読込中: {info.get('records', 0)}件 / {info.get('files_done', 0)}ファイル"
        elif stage == "retry":
            msg = f"{ds} 通信リトライ {info.get('attempt')}/{info.get('max_attempts')} ({info.get('wait_sec')}秒待機)"
        elif stage in ("error", "warn"):
            msg = f"{ds} {stage}: {info.get('message') or info}"
        else:
            msg = f"{ds} {stage}: {info}"
        self._set_status(msg, stage, detail, running=True)

    def _stage_progress(self, dataspec: str, stage: str) -> float | None:
        weights = {"RACE": (0, 40), "HOSE": (40, 80), "DIFN": (0, 45), "BLOD": (45, 90), "0B31": (0, 90)}
        if dataspec not in weights:
            return None
        start, end = weights[dataspec]
        frac = {"open": 0.05, "download": 0.35, "read": 0.85}.get(stage, 0.2)
        return start + (end - start) * frac

    def _progress_detail(self, current: float, total: float) -> dict:
        now = time.time()
        progress = max(0.0, min(100.0, current / total * 100 if total else 0.0))
        self._progress_samples.append((now, progress))
        self._progress_samples = self._progress_samples[-5:]
        eta_sec = None
        if len(self._progress_samples) >= 2:
            t0, p0 = self._progress_samples[0]
            t1, p1 = self._progress_samples[-1]
            if t1 > t0 and p1 > p0:
                per_sec = (p1 - p0) / (t1 - t0)
                eta_sec = int((100.0 - progress) / per_sec) if per_sec > 0 else None
        return {"progress": round(progress, 1), "eta_sec": eta_sec}

    @_safe
    def get_status(self, options: dict | None = None) -> dict:
        with self._status_lock:
            return dict(self._status)

    @_safe
    def get_buy_filter_default(self, options: dict | None = None) -> dict:
        """JS dashboard が input の初期値を取りに来る API。

        config.BUY_FILTER_DEFAULT を直接配信。これで HTML 内ハードコードの
        初期値 (例: value="1.05") と Python 側 BET_MIN_* がズレる事故を防ぐ。
        """
        return {"ok": True, "filter": dict(BUY_FILTER_DEFAULT)}

    @_safe
    def cancel(self, options: dict | None = None) -> dict:
        # check-and-set を 1 つの lock 区間で行う。旧実装は「lock 内で読み →
        # lock 外で running=True を書く」非原子で、その間にワーカーが正常完了
        # すると誰も下ろさない running=True が恒久化し全ボタン disable +
        # BusyError 永続 (再起動でしか回復しない) というロックアップ経路が
        # あった (2026-06-13 v2 監査 gui-ux 反証で発見)。
        # _set_status は lock 非再入のため使わず、フィールドを直接更新する。
        self._cancel_event.set()
        with self._status_lock:
            if not self._status.get("running"):
                self._cancel_event.clear()
                return {"ok": True, "message": "実行中の処理はありません"}
            self._status["message"] = "中止しています..."
            self._status["stage"] = "cancelling"
            self._status["updated_at"] = datetime.now().strftime("%H:%M:%S")
        return {"ok": True, "message": "中止要求を送信しました"}

    def _date_range(self, options: dict | None = None) -> tuple[str, str]:
        options = options or {}
        from_date = _normalize_date(options.get("from_date"))
        to_date = _normalize_date(options.get("to_date"))
        if from_date and not to_date:
            to_date = from_date
        if to_date and not from_date:
            from_date = to_date
        if from_date and to_date:
            return from_date, to_date
        today = datetime.now().strftime("%Y%m%d")
        with open_db() as conn:
            exists = conn.execute(
                "SELECT 1 FROM races WHERE race_year || race_month_day=? LIMIT 1",
                (today,),
            ).fetchone()
            if exists:
                return today, today
            row = conn.execute("SELECT MAX(race_year || race_month_day) FROM races").fetchone()
            latest = row[0] if row and row[0] else today
            return latest, latest

    def _is_buy_candidate(
        self,
        pred,
        horse: dict,
        tentative: bool,
        filters: dict | None = None,
        race: dict | None = None,
    ) -> bool:
        """買い候補判定。predictor.filter.is_buy_candidate に全面委譲。

        オッズ鮮度 (max_odds_age_min) も 2026-06-13 に集約関数へ統合済み
        (now を渡すとライブ評価)。GUI 独自実装は持たない。
        """
        from predictor.filter import is_buy_candidate
        spec = filters if filters else None
        return is_buy_candidate(
            pred, horse, tentative, race=race, filter_spec=spec, now=datetime.now())

    def _odds_age_minutes(self, fetched_at: str | None) -> int | None:
        from predictor.filter import odds_age_minutes
        return odds_age_minutes(fetched_at, datetime.now())

    def _recent_backtest(self, conn, to_date: str, range_key: str = "3") -> dict:
        # 確定済みレースは to_date (= 予想対象日 = 当日/未来) の近辺には無く、
        # 過去にしか存在しない。to_date から素朴に遡ると窓に確定データが
        # 1 件も入らず全 0 になる (例: 当日 06-07 の「直近3日」は 06-05..06-07 で
        # 確定レースゼロ)。そこで **to_date 以前で最新の確定開催日 (anchor)** を
        # 起点に窓を取り、いつ開いても直近の確定結果が出るようにする。
        anchor = conn.execute(
            """
            SELECT MAX(race_year || race_month_day)
            FROM horse_races
            WHERE confirmed_order > 0 AND (race_year || race_month_day) <= ?
            """,
            (to_date,),
        ).fetchone()[0]
        label = f"{(anchor or to_date)[:6]}月" if range_key == "month" else f"直近{range_key}日"
        # anchor 鮮度: 「直近3日」と表示しながら実は数週間前の確定データを
        # 見せている事故の検知 (validation-process-auditor 5 回持ち越し分)。
        anchor_age_days = None
        if anchor:
            try:
                anchor_age_days = (
                    datetime.strptime(to_date, "%Y%m%d") - datetime.strptime(anchor, "%Y%m%d")
                ).days
            except ValueError:
                anchor_age_days = None
        anchor_stale = anchor_age_days is not None and anchor_age_days > BT_ANCHOR_STALE_DAYS
        common = {
            "label": label,
            "low_n_note": BT_LOW_N_NOTE,
            "anchor_age_days": anchor_age_days,
            "anchor_stale": anchor_stale,
        }
        if not anchor:
            return {**common, "races": 0, "wins": 0, "top3": 0, "return_rate": 0, "low_n": True}
        if range_key == "month":
            start_date = anchor[:6] + "01"
        else:
            days = int(range_key) if str(range_key).isdigit() else 3
            try:
                start_date = (datetime.strptime(anchor, "%Y%m%d") - timedelta(days=days - 1)).strftime("%Y%m%d")
            except ValueError:
                start_date = anchor
        limit = 100
        rows = conn.execute(
            """
            SELECT DISTINCT race_year || race_month_day AS d
            FROM horse_races
            WHERE confirmed_order > 0 AND (race_year || race_month_day) BETWEEN ? AND ?
            ORDER BY d DESC
            LIMIT ?
            """,
            (start_date, anchor, limit),
        ).fetchall()
        dates = sorted([r["d"] for r in rows])
        if not dates:
            return {**common, "races": 0, "wins": 0, "top3": 0, "return_rate": 0, "low_n": True}
        races = list_races(conn, dates[0], dates[-1], jra_only=True)
        date_set = set(dates)
        feature_cache: dict = {}
        total = wins = top3 = payout = 0
        for race in races:
            if race["race_year"] + race["race_month_day"] not in date_set:
                continue
            horses = horses_for_race(conn, race)
            if not horses or not any(h.get("confirmed_order") == 1 for h in horses):
                continue
            preds = predict_race(horses, conn=conn, race=race, cache=feature_cache)
            top = preds[0]
            total += 1
            actual_top3 = {h["horse_num"] for h in horses if h.get("confirmed_order") in (1, 2, 3)}
            if any(h.get("horse_num") == top.horse_num and h.get("confirmed_order") == 1 for h in horses):
                wins += 1
            if top.horse_num in actual_top3:
                top3 += 1
            payout += get_payout(conn, race, top.horse_num, "tan")
        return {
            **common,
            "period": f"{dates[0]}-{dates[-1]}",
            # この backtest は **全確定レースで本命 (preds[0]) を単勝 100 円**。
            # 上段「買い候補」の EV/Kelly/オッズ フィルタは一切通していないため、
            # ここの回収率は買い候補戦略の期待成績ではない (誤読防止の注記)。
            # さらに GUI は venv32 (LGBM 無し) で動くため rule-only 予測。
            "note": "本命単勝・全レース / 買いフィルタ非適用の参考値",
            "races": total,
            "wins": wins,
            "top3": top3,
            "win_rate": round(wins / total * 100, 1) if total else 0,
            "top3_rate": round(top3 / total * 100, 1) if total else 0,
            "return_rate": round(payout / (total * 100) * 100, 1) if total else 0,
            # 件数が少ない回収率は分散が巨大で参考にならない。
            # JS 側で low_n_note (Python 組み立て) をマーキングする。
            "low_n": total < BT_LOW_N_THRESHOLD,
        }

    def _surface_label(self, code: str | None) -> str:
        try:
            n = int((code or "").strip())
        except ValueError:
            return "その他"
        if 10 <= n <= 22:
            return "芝"
        if 23 <= n <= 29:
            return "ダート"
        return "その他"

    def _gate_zone(self, horse_num: str | int | None, starter_count: int | None) -> str:
        try:
            num = int(str(horse_num or "").strip())
            starters = int(starter_count or 0)
        except ValueError:
            return ""
        if num <= 0 or starters <= 0:
            return ""
        pos = num / starters
        if pos <= 1 / 3:
            return "内"
        if pos <= 2 / 3:
            return "中"
        return "外"

    def _track_trends(self, conn, from_date: str, to_date: str) -> list[dict]:
        rows = conn.execute(
            """
            SELECT
              r.race_year, r.race_month_day, r.track_code, r.race_num,
              r.track_type_code, r.starter_count, r.start_time,
              hr.horse_num, hr.leg_quality_code, hr.confirmed_order
            FROM races r
            JOIN horse_races hr
              ON hr.race_year = r.race_year
             AND hr.race_month_day = r.race_month_day
             AND hr.track_code = r.track_code
             AND hr.kaiji = r.kaiji
             AND hr.nichiji = r.nichiji
             AND hr.race_num = r.race_num
            WHERE (r.race_year || r.race_month_day) BETWEEN ? AND ?
              AND CAST(r.track_code AS INTEGER) BETWEEN 1 AND 10
              AND hr.confirmed_order BETWEEN 1 AND 3
            ORDER BY r.race_year, r.race_month_day, r.track_code, r.race_num
            """,
            (from_date, to_date),
        ).fetchall()
        data: dict[str, dict] = {}
        for row in rows:
            track = track_name(row["track_code"])
            surface = self._surface_label(row["track_type_code"])
            d = data.setdefault(track, {
                "track": track,
                "top3": 0,
                "surfaces": {},
                "legs": {},
                "gates": {},
            })
            d["top3"] += 1
            d["surfaces"][surface] = d["surfaces"].get(surface, 0) + 1
            leg = (row["leg_quality_code"] or "").strip() or "不明"
            d["legs"][leg] = d["legs"].get(leg, 0) + 1
            zone = self._gate_zone(row["horse_num"], row["starter_count"]) or "不明"
            d["gates"][zone] = d["gates"].get(zone, 0) + 1

        leg_names = {"1": "逃げ", "2": "先行", "3": "差し", "4": "追込", "不明": "不明"}
        trends = []
        for track, d in sorted(data.items()):
            total = d["top3"] or 1
            surface_top = max(d["surfaces"].items(), key=lambda x: x[1]) if d["surfaces"] else ("-", 0)
            leg_top = max(d["legs"].items(), key=lambda x: x[1]) if d["legs"] else ("-", 0)
            gate_top = max(d["gates"].items(), key=lambda x: x[1]) if d["gates"] else ("-", 0)
            note = []
            if surface_top[1] / total >= 0.6:
                note.append(f"{surface_top[0]}寄り")
            if leg_top[1] / total >= 0.35:
                note.append(f"{leg_names.get(leg_top[0], leg_top[0])}優勢")
            if gate_top[1] / total >= 0.40:
                note.append(f"{gate_top[0]}枠寄り")
            trends.append({
                "track": track,
                "top3_samples": d["top3"],
                "surface": f"{surface_top[0]} {round(surface_top[1] / total * 100)}%",
                "leg": f"{leg_names.get(leg_top[0], leg_top[0])} {round(leg_top[1] / total * 100)}%",
                "gate": f"{gate_top[0]} {round(gate_top[1] / total * 100)}%",
                "note": " / ".join(note) if note else "明確な偏りは弱め",
                "source": "確定結果",
            })
        return trends

    def _venue_info(self, races: list[dict]) -> list[dict]:
        coords = {
            "札幌": (43.071, 141.326),
            "函館": (41.782, 140.753),
            "福島": (37.767, 140.471),
            "新潟": (37.947, 139.186),
            "東京": (35.666, 139.485),
            "中山": (35.725, 139.959),
            "中京": (35.066, 136.960),
            "京都": (34.905, 135.719),
            "阪神": (34.780, 135.361),
            "小倉": (33.842, 130.875),
        }
        data: dict[str, dict] = {}
        for r in races:
            track = track_name(r["track_code"])
            d = data.setdefault(track, {
                "track": track,
                "races": 0,
                "surfaces": {},
                "weather": {},
                "turf": {},
                "dirt": {},
            })
            d["races"] += 1
            surface = self._surface_label(r.get("track_type_code"))
            d["surfaces"][surface] = d["surfaces"].get(surface, 0) + 1
            weather = (r.get("weather_code") or "").strip()
            if not weather or weather == "0":
                weather = "不明"
            d["weather"][weather] = d["weather"].get(weather, 0) + 1
            turf = (r.get("turf_condition") or "").strip()
            dirt = (r.get("dirt_condition") or "").strip()
            if turf and turf != "0":
                d["turf"][turf] = d["turf"].get(turf, 0) + 1
            if dirt and dirt != "0":
                d["dirt"][dirt] = d["dirt"].get(dirt, 0) + 1

        weather_names = {
            "1": "晴", "2": "曇", "3": "雨", "4": "小雨", "5": "雪", "6": "小雪", "不明": "-"
        }
        ground_names = {"1": "良", "2": "稍重", "3": "重", "4": "不良"}
        out = []
        for track, d in sorted(data.items()):
            surface_text = " / ".join(f"{k}{v}" for k, v in sorted(d["surfaces"].items()))
            weather = max(d["weather"].items(), key=lambda x: x[1])[0] if d["weather"] else "不明"
            turf = max(d["turf"].items(), key=lambda x: x[1])[0] if d["turf"] else ""
            dirt = max(d["dirt"].items(), key=lambda x: x[1])[0] if d["dirt"] else ""
            out.append({
                "track": track,
                "races": d["races"],
                "surfaces": surface_text,
                "weather": weather_names.get(weather, weather),
                "turf": ground_names.get(turf, turf) if turf else "-",
                "dirt": ground_names.get(dirt, dirt) if dirt else "-",
                "lat": coords.get(track, (None, None))[0],
                "lon": coords.get(track, (None, None))[1],
            })
        return out

    @_safe
    def get_weather(self, options: dict | None = None) -> dict:
        options = options or {}
        lat = str(options.get("lat") or "").strip()
        lon = str(options.get("lon") or "").strip()
        if not lat or not lon or lat == "None" or lon == "None":
            return {"ok": False, "error": "missing coordinates"}
        key = (lat, lon)
        now = time.time()
        cached = self._weather_cache.get(key)
        if cached and now - cached[0] < 600:
            return {"ok": True, **cached[1], "cached": True}
        url = (
            "https://api.open-meteo.com/v1/forecast"
            f"?latitude={lat}&longitude={lon}"
            "&current=weather_code,temperature_2m,precipitation"
        )
        with urllib.request.urlopen(url, timeout=3) as res:
            data = json.loads(res.read().decode("utf-8"))
        current = data.get("current") or {}
        payload = {
            "weather_code": current.get("weather_code"),
            "temperature": current.get("temperature_2m"),
            "precipitation": current.get("precipitation"),
        }
        self._weather_cache[key] = (now, payload)
        return {"ok": True, **payload, "cached": False}

    def _prediction_trends(self, races: list[dict], predictions: list[dict]) -> list[dict]:
        if not predictions:
            return []
        by_track: dict[str, dict] = {}
        race_by_key = {
            (r["race_year"], r["race_month_day"], r["track_code"], r["race_num"]): r
            for r in races
        }
        for p in predictions:
            track = p["track"]
            d = by_track.setdefault(track, {
                "track": track,
                "count": 0,
                "conf": {},
                "ev_good": 0,
                "buy": 0,
            })
            d["count"] += 1
            d["conf"][p["confidence"]] = d["conf"].get(p["confidence"], 0) + 1
            if p["ev"] >= 1.0:
                d["ev_good"] += 1
            if p.get("buy"):
                d["buy"] += 1
        out = []
        for track, d in sorted(by_track.items()):
            total = d["count"] or 1
            conf_top = max(d["conf"].items(), key=lambda x: x[1]) if d["conf"] else ("-", 0)
            out.append({
                "track": track,
                "top3_samples": d["count"],
                "surface": f"本命 {d['count']}頭",
                "leg": f"{conf_top[0]} {round(conf_top[1] / total * 100)}%",
                "gate": f"EV>=1 {d['ev_good']}頭",
                "note": f"買い候補 {d['buy']}件 / 予想ベース",
                "source": "予想",
            })
        return out

    def _predictions_cached(self, conn, from_date: str, to_date: str, races: list) -> list:
        """期間内全レースの予測を計算してキャッシュする。

        返り値は (race, horses, preds, tentative) のリスト。
        フィルタ変更ごとの再計算 (数秒) を避けるためのキャッシュで、
        買い候補判定 (フィルタ依存) は呼び出し側で entries から都度作る。
        単一キーのみ保持 (期間を変えたら前の期間分は捨てる)。
        """
        key = (from_date, to_date)
        with self._cache_lock:
            cached = self._pred_cache.get(key)
            gen = self._cache_gen
        if cached is not None:
            return cached
        feature_cache: dict = {}
        entries = []
        for race in races:
            horses = horses_for_race(conn, race)
            if not horses:
                continue
            preds = predict_race(horses, conn=conn, race=race, cache=feature_cache)
            entries.append((race, horses, preds, is_tentative(preds)))
        with self._cache_lock:
            # 計算中に invalidate された (= データ取得が走った) 場合は
            # stale な結果を書き戻さない。返り値は今回表示用に使ってよい
            # (直後の refreshAll が fresh で上書きする)。
            if gen == self._cache_gen:
                self._pred_cache = {key: entries}
        return entries

    def _recent_backtest_cached(self, conn, to_date: str, range_key: str) -> dict:
        key = (to_date, range_key)
        with self._cache_lock:
            hit = self._backtest_cache.get(key)
            gen = self._cache_gen
        if hit is not None:
            return hit
        result = self._recent_backtest(conn, to_date, range_key)
        with self._cache_lock:
            if gen == self._cache_gen:
                self._backtest_cache[key] = result
        return result

    @_safe
    def get_backtest(self, options: dict | None = None) -> dict:
        """バックテストカードのみ更新する軽量 API (期間ボタン切替用)。

        get_dashboard 全体 (予測再計算込み) を呼び直さずに済む。
        """
        options = options or {}
        _, to_date = self._date_range(options)
        with open_db() as conn:
            backtest = self._recent_backtest_cached(
                conn, to_date, str(options.get("backtest_range") or "3"))
        return {"ok": True, "backtest": backtest}

    @_safe
    def get_dashboard(self, options: dict | None = None) -> dict:
        options = options or {}
        if options.get("force_refresh"):
            self._invalidate_caches()
        from_date, to_date = self._date_range(options)
        # 買い目フィルタは config.BUY_FILTER_DEFAULT (採用戦略の単一出典) を
        # ベースに、GUI input で明示された 4 値だけを上書きする。
        # 旧実装は 4 キーのみの dict を filter_spec として渡しており、
        # min_kelly / max_predicted_p (P15 主絞り + S5-3 防御) が脱落して
        # 「GUI の買い候補 ≠ backtest で検証した集合」になっていた
        # (2026-06-12 profitability-judge 指摘で是正)。
        bet_filter = dict(BUY_FILTER_DEFAULT)
        for key in ("min_value", "min_ev", "min_odds", "max_odds"):
            if options.get(key) is not None:
                bet_filter[key] = options[key]
        with open_db() as conn:
            races = list_races(conn, from_date, to_date, jra_only=True)
            race_count = len(races)
            horse_count = conn.execute(
                """
                SELECT COUNT(*) FROM horse_races
                WHERE (race_year || race_month_day) BETWEEN ? AND ?
                """,
                (from_date, to_date),
            ).fetchone()[0]
            odds_count = conn.execute(
                """
                SELECT COUNT(*) FROM horse_races
                WHERE (race_year || race_month_day) BETWEEN ? AND ?
                  AND win_odds > 0
                """,
                (from_date, to_date),
            ).fetchone()[0]
            odds_meta = conn.execute(
                """
                SELECT MAX(odds_fetched_at) AS fetched_at, MAX(odds_dataspec) AS dataspec
                FROM horse_races
                WHERE (race_year || race_month_day) BETWEEN ? AND ?
                  AND win_odds > 0
                """,
                (from_date, to_date),
            ).fetchone()
            buy_candidates: list[dict] = []
            prediction_items: list[dict] = []
            feature_warning_counts: dict[str, int] = {}
            feature_warning_total = 0
            entries = self._predictions_cached(conn, from_date, to_date, races)
            for race, horses, preds, tentative in entries:
                horse_by_num = {h["horse_num"]: h for h in horses}
                for pred in preds[:3]:
                    if pred.rank == 1:
                        feature_warning_total += 1
                        for w in pred.feature_warnings:
                            feature_warning_counts[w] = feature_warning_counts.get(w, 0) + 1
                    horse = horse_by_num.get(pred.horse_num, {})
                    item = {
                        "date": race_id_to_date(race["race_year"], race["race_month_day"]),
                        "track": track_name(race["track_code"]),
                        "race_num": int(race["race_num"]),
                        "race_name": race.get("race_name") or race.get("race_short10") or "",
                        "start_time": race.get("start_time") or "",
                        "mark": pred.mark,
                        "horse_num": int(pred.horse_num or 0),
                        "horse_name": horse.get("horse_name") or "",
                        "odds": round((horse.get("win_odds") or 0) / 10.0, 1),
                        "popularity": horse.get("win_popularity") or 0,
                        "confidence": pred.confidence,
                        "probability": round(pred.win_probability * 100, 1),
                        "ev": pred.expected_value,
                        # full Kelly (kelly_fraction) は実推奨賭金の ~3-4 倍に相当する
                        # 過大値。表示・集計には recommended (1/4 Kelly + per-bet cap)
                        # を使う (web/generator.py P20 の是正と同一方針)。
                        # recommended_kelly は **fraction (0-1)** で持つ
                        # (web/generator.py:277 と同一スケール。表示直前にのみ ×100)。
                        "kelly": round(pred.kelly_fraction * 100, 2),
                        "recommended_kelly": round(
                            recommended_fraction(pred.kelly_fraction), 4
                        ),
                        "buy": self._is_buy_candidate(pred, horse, tentative, bet_filter, race=race),
                    }
                    if pred.rank == 1:
                        prediction_items.append(item)
                    if item["buy"]:
                        buy_candidates.append(item)
            # skip_backtest: JS ダッシュボードは backtest を get_backtest で
            # 分離取得するため常に skip を指定してくる (本体描画を 100 日分の
            # 再予測で待たせない)。同梱取得はスクリプト等の直叩き用に残す。
            backtest = None
            if not options.get("skip_backtest"):
                backtest = self._recent_backtest_cached(
                    conn, to_date, str(options.get("backtest_range") or "3"))
            trends = self._track_trends(conn, from_date, to_date)
            if not trends:
                trends = self._prediction_trends(races, prediction_items)
            venues = self._venue_info(races)
        index = WEB_DIST / "index.html"
        generated_at = (
            datetime.fromtimestamp(index.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
            if index.exists()
            else "未生成"
        )
        warnings = []
        if horse_count and odds_count < horse_count:
            warnings.append(f"オッズ未取得: {horse_count - odds_count}頭")
        odds_fetched_at = odds_meta["fetched_at"] if odds_meta else None
        odds_age = self._odds_age_minutes(odds_fetched_at)
        max_age = int(BUY_FILTER_DEFAULT["max_odds_age_min"])
        if odds_age is not None and odds_age > max_age:
            warnings.append(f"オッズ鮮度警告: {odds_age}分前 (>{max_age}分) / 買い候補から除外")
        if feature_warning_total:
            leg_missing = feature_warning_counts.get("leg_quality_unavailable", 0)
            same_day_missing = feature_warning_counts.get("same_day_bias_unavailable", 0)
            if leg_missing:
                rate = round((feature_warning_total - leg_missing) / feature_warning_total * 100)
                warnings.append(f"leg_quality 取得率 {rate}% / 不足分は過去走から推定")
            if same_day_missing:
                rate = round((feature_warning_total - same_day_missing) / feature_warning_total * 100)
                warnings.append(f"当日傾向 利用率 {rate}% / 朝はデータなし")
        if not buy_candidates:
            warnings.append("買い候補なし: EV/信頼度条件を満たすレースは見送り")
        # 買い候補ポートフォリオ集計。bankroll は 1 開催日ごとに区切られるため
        # **日単位** で推奨投資率を合算する (多日窓を全合算すると過大化する)。
        # 集計ロジックは web/generator.py と共通の単一出典
        # predictor.portfolio.compute_day_portfolio に集約 (P20-3 / 2026-06-07)。
        # 想定回収率 (exp_return_pct) は推奨賭金で加重平均した EV。
        buy_portfolio = compute_day_portfolio(buy_candidates)
        return {
            "ok": True,
            "from_date": from_date,
            "to_date": to_date,
            "summary": {
                "races": race_count,
                "horses": horse_count,
                "odds": odds_count,
                "buy_count": len(buy_candidates),
                "generated_at": generated_at,
                "feature_warnings": feature_warning_counts,
                "last_fetched_odds": odds_fetched_at,
                "odds_dataspec": odds_meta["dataspec"] if odds_meta else None,
                "odds_age_minutes": odds_age,
                "bet_filter": bet_filter,
            },
            "buy_candidates": buy_candidates,
            "buy_portfolio": buy_portfolio,
            "backtest": backtest,
            "track_trends": trends,
            "venues": venues,
            "warnings": warnings,
        }

    @_safe
    def fetch_data(self, options: dict | None = None) -> dict:
        """JV-Link 差分取得 → raw 保存 → SQLite 取り込み。"""
        self._begin_run()
        self._set_status("出馬表/結果データを取得中...", "fetch_data", running=True)
        with JVLinkClient() as cli:
            summaries = cli.fetch_all(option=1, dataspecs=["RACE", "HOSE"], on_progress=self._progress)
        self._check_cancel()
        self._set_status("DBへ取り込み中...", "ingest", running=True)
        # 今回 fetch したファイルは ingest 済みでも強制再取込 (同名更新対応)。
        # 空なら通常の全体スキャン (未取り込み分の回復)。
        ingest_summary = ingest_all(only_files=_fetched_filenames(summaries))
        # 実行中にユーザがフィルタ/期間を触ると部分取込み DB でキャッシュが
        # 再充填されうるため、取り込み完了時にも invalidate して捨てる
        # (開始時 _begin_run と対になる完了側の防御)。
        self._invalidate_caches()
        self._set_status("データ取得が完了しました。", "done", running=False)
        return {
            "ok": True,
            "fetch": summaries,
            "ingest": ingest_summary,
        }

    @_safe
    def fetch_odds(self, options: dict | None = None) -> dict:
        self._begin_run()
        return self._fetch_odds_inner(options, finish=True)

    def _fetch_odds_inner(self, options: dict | None = None, *, finish: bool) -> dict:
        options = options or {}
        from_date = _normalize_date(options.get("from_date") or options.get("date"))
        to_date = _normalize_date(options.get("to_date") or options.get("date"))
        with open_db() as conn:
            if not from_date or not to_date:
                row = conn.execute("SELECT MAX(race_year || race_month_day) FROM races").fetchone()
                from_date = to_date = row[0]
            races = list_races(conn, from_date, to_date, jra_only=True)
        self._set_status(f"\u30aa\u30c3\u30ba\u53d6\u5f97\u958b\u59cb: {len(races)}\u30ec\u30fc\u30b9", "fetch_odds", running=True)
        with JVLinkClient() as cli:
            summaries = []
            for i, r in enumerate(races, start=1):
                self._check_cancel()
                self._set_status(
                    f"\u30aa\u30c3\u30ba\u53d6\u5f97\u4e2d: {i}/{len(races)} {r['track_code']} {int(r['race_num'])}R",
                    "fetch_odds",
                    {"current": i, "total": len(races), **self._progress_detail(i, len(races) or 1)},
                    running=True,
                )
                summaries.append(cli.fetch_realtime("0B31", race_key(dict(r)), on_progress=self._progress))
        self._set_status("\u30aa\u30c3\u30ba\u3092DB\u3078\u53d6\u308a\u8fbc\u307f\u4e2d...", "ingest_odds", running=True)
        self._check_cancel()
        ingest_summary = ingest_all(force=True, dataspecs=["0B31"])
        self._invalidate_caches()  # 完了側の防御 (fetch_data と同旨)
        if finish:
            self._set_status("\u30aa\u30c3\u30ba\u53d6\u5f97\u304c\u5b8c\u4e86\u3057\u307e\u3057\u305f\u3002", "done", running=False)
        return {"ok": True, "races": len(races), "fetch": summaries, "ingest": ingest_summary}

    @_safe
    def fetch_bloodline(self, options: dict | None = None) -> dict:
        """血統マスタを取得して、父系・母父系特徴量を有効化する。"""
        self._begin_run()
        options = options or {}
        raw_fromtime = (options.get("bloodline_fromtime") or "").replace("-", "")
        fromtime = raw_fromtime or None
        mode = f"{fromtime}から取得" if fromtime else "前回取得以降の差分取得"
        self._set_status(f"血統データ取得開始: {mode}", "fetch_bloodline", running=True)
        with JVLinkClient() as cli:
            summaries = cli.fetch_all(
                fromtime=fromtime,
                option=1,
                dataspecs=["DIFN", "BLOD"],
                on_progress=self._progress,
            )
        self._check_cancel()
        self._set_status("血統データをDBへ取り込み中...", "ingest_bloodline", running=True)
        ingest_summary = ingest_all(dataspecs=["DIFN", "BLOD"],
                                    only_files=_fetched_filenames(summaries))
        self._invalidate_caches()  # 完了側の防御 (fetch_data と同旨)
        with open_db() as conn:
            count = conn.execute("SELECT COUNT(*) FROM horse_masters").fetchone()[0]
        self._set_status(f"血統データ取得が完了しました。horse_masters={count}", "done", running=False)
        return {"ok": True, "horse_masters": count, "fetch": summaries, "ingest": ingest_summary}

    @_safe
    def run_prediction(self, options: dict | None = None) -> dict:
        """DB を読んで予想込み HTML を生成 (LightGBM v5 ensemble、subprocess 経由)。"""
        self._begin_run()
        options = options or {}
        from_date = _normalize_date(options.get("from_date")) or None
        to_date = _normalize_date(options.get("to_date")) or from_date
        self._set_status("予想HTMLを生成中... (.venv64 で LightGBM 実行)", "prediction", running=True)
        result = _run_render_in_venv64(
            from_date, to_date, publish=False,
            cancel_check=self._check_cancel,
            on_elapsed=lambda s: self._set_status(
                f"予想HTMLを生成中... 経過 {int(s)}秒 (.venv64 で LightGBM 実行)",
                "prediction", running=True))
        msg = f"生成: {result.get('rendered')}"
        if result.get("warning"):
            msg = f"{msg} (警告: {result['warning']})"
        self._set_status("予想生成が完了しました。", "done", running=False)
        return {"ok": True, "message": msg, **result}

    @_safe
    def publish(self, options: dict | None = None) -> dict:
        self._begin_run()
        self._set_status("iCloud Driveへ公開中...", "publish", running=True)
        path = publish_to_icloud()
        now = datetime.now().strftime("%H:%M:%S")
        self._set_status("公開が完了しました。", "done", running=False)
        return {
            "ok": True,
            "published_at": now,
            "path": str(path),
            "note": "iPhone Files への反映には数十秒〜数分かかります。"
                    "PC のエクスプローラで ☁→✓ に変わったら同期完了。",
        }

    @_safe
    def open_icloud_folder(self, options: dict | None = None) -> dict:
        """iCloud Drive 公開先フォルダを Explorer で開く（同期状況の目視用）。"""
        os.startfile(str(ICLOUD_PUBLISH_DIR))
        return {"ok": True, "opened": str(ICLOUD_PUBLISH_DIR)}

    @_safe
    def run_all(self, options: dict | None = None) -> dict:
        """① 取得 → ② 予想 → ③ 公開 を一括実行。"""
        self._begin_run()
        self._set_status("一括実行: データ取得中...", "run_all", running=True)
        with JVLinkClient() as cli:
            summaries = cli.fetch_all(option=1, dataspecs=["RACE", "HOSE"], on_progress=self._progress)
        self._check_cancel()
        self._set_status("一括実行: DB取り込み中...", "ingest", running=True)
        ingest_summary = ingest_all(only_files=_fetched_filenames(summaries))
        self._invalidate_caches()  # 完了側の防御 (fetch_data と同旨)
        odds_summary = self._fetch_odds_inner(options, finish=False)
        self._check_cancel()
        options = options or {}
        from_date = _normalize_date(options.get("from_date")) or None
        to_date = _normalize_date(options.get("to_date")) or from_date
        self._set_status("一括実行: 予想生成 + 公開中... (.venv64 で LightGBM)", "prediction", running=True)
        # subprocess で .venv64 を呼び LightGBM v5 ensemble 予測 + iCloud 公開を一括実行
        result = _run_render_in_venv64(
            from_date, to_date, publish=True,
            cancel_check=self._check_cancel,
            on_elapsed=lambda s: self._set_status(
                f"一括実行: 予想生成 + 公開中... 経過 {int(s)}秒 (.venv64 で LightGBM)",
                "prediction", running=True))
        rendered = result.get("rendered")
        published = result.get("published") or "(skipped)"
        now = datetime.now().strftime("%H:%M:%S")
        self._set_status("一括実行が完了しました。", "done", running=False)
        return {
            "ok": True,
            "published_at": now,
            "fetch": summaries,
            "ingest": ingest_summary,
            "odds": odds_summary,
            "rendered": str(rendered),
            "published": str(published),
            "lgbm_warning": result.get("warning"),
            "note": "公開時刻は HTML 先頭にも表示されます。"
                    "iPhone Files で開いた時に時刻が一致すれば同期済み。"
                    "反映には数十秒〜数分。Explorer で ☁→✓ 変化も目視可。",
        }


CONTROL_HTML = """<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>競馬予想</title>
<style>
  :root {
    --bg:          #eaedf1;
    --surface:     #ffffff;
    --surface-2:   #eceff3;
    --border:      #c2c9d2;
    --border-soft: #d4dae1;
    --text:        #1f242b;
    --text-dim:    #545c67;
    /* 旧 #7d8591 は surface 上 3.73:1 / bg 上 3.17:1 で WCAG AA (4.5:1) fail。
       metric ラベル・ETA・hint 等の機能テキストに使われるため #5d6570
       (surface 5.90 / surface-2 5.11 / bg 5.02) に変更 (2026-06-13 実測)。 */
    --text-mute:   #5d6570;
    --accent:      #5b626d;
    --accent-hi:   #374151;
    --accent-soft: rgba(55,65,81,.10);
    --accent-line: rgba(55,65,81,.30);
    /* 主要 CTA = 濃色塗りつぶし (白文字)。最重要操作の視認性を担保。
       base / hover の全状態を :root 単一出典にする (hover の直書き漏れ防止) */
    --primary:      #2f3a49;
    --primary-hi:   #1f2937;
    --primary-soft: #3a4656;
    --primary-deep: #111827;
    --on-primary:   #ffffff;
    /* 買い目 = 金額の色。トークン化して散在を防ぐ (旧: #9f1239 直書き) */
    --buy:         #9f1239;
    --buy-bg:      #fff1f2;
    --buy-border:  #fecdd3;
    --log-fg:      #27313b;
    --log-bg:      #f3f5f7;
  }
  * { box-sizing: border-box; }
  html, body {
    margin: 0; padding: 0;
    background: var(--bg);
    color: var(--text);
    font-family: "Yu Gothic UI", "Hiragino Sans", "Noto Sans JP",
                 -apple-system, system-ui, sans-serif;
    font-size: 14px;
    line-height: 1.5;
    -webkit-font-smoothing: antialiased;
    text-rendering: geometricPrecision;
  }
  body {
    padding: 0;
    margin: 0;
    display: flex;
    flex-direction: row;
    align-items: stretch;
    height: 100vh;
    overflow: hidden;
  }
  /* 左カラム = コントロールパネル。幅固定。
     460px は 1100px 窓の 42% を占めて広すぎたため 380px に縮小
     (ノート PC の実効幅 1280px 前後でダッシュボードに 900px 残す)。 */
  .sidebar {
    flex: 0 0 380px;
    width: 380px;
    padding: .85rem 1rem .9rem;
    border-right: 1px solid var(--border-soft);
    height: 100vh;
    overflow-y: auto;
    overflow-x: hidden;
    display: flex;
    flex-direction: column;
  }
  /* 右カラム = タブ切替 (ダッシュボード / 予想 HTML プレビュー)。 */
  .main {
    flex: 1 1 auto;
    min-width: 0;
    height: 100vh;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }
  .main-toolbar {
    flex: 0 0 auto;
    display: flex;
    align-items: center;
    gap: .6rem;
    padding: .42rem .85rem .38rem;
    background: var(--surface);
    border-bottom: 1px solid var(--border-soft);
  }
  .tabs { display: flex; gap: .2rem; }
  .tabs .tab {
    display: inline-block;
    width: auto;
    margin: 0;
    padding: .3rem .7rem;
    font-size: .78rem;
    background: transparent;
    border: 1px solid transparent;
    border-radius: 3px;
    color: var(--text-dim);
    text-align: center;
  }
  .tabs .tab.active {
    background: var(--accent-soft);
    border-color: var(--accent-line);
    color: var(--accent-hi);
    font-weight: 600;
  }
  .tabs .close-tab { color: var(--buy); }
  .tabs .close-tab:hover {
    background: var(--buy-bg);
    border-color: var(--buy-border);
    color: var(--buy);
  }
  .toolbar-meta {
    flex: 1 1 auto;
    min-width: 0;
    text-align: right;
    font-size: .7rem;
    color: var(--text-mute);
    font-variant-numeric: tabular-nums;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .tool-btn {
    display: inline-block;
    width: auto;
    flex: 0 0 auto;
    margin: 0;
    padding: .3rem .6rem;
    font-size: .74rem;
  }
  #dashboardPane {
    flex: 1 1 auto;
    overflow-y: auto;
    overflow-x: hidden;
    padding: .65rem .85rem;
  }
  #previewPane {
    flex: 1 1 auto;
    overflow: hidden;
    background: #ffffff;
  }
  #previewPane iframe {
    width: 100%;
    height: 100%;
    border: 0;
    display: block;
    background: #ffffff;
  }
  .card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 5px;
    padding: .52rem .62rem;
    margin: 0;
    box-shadow: 0 1px 2px rgba(16,24,40,.05);
  }
  .card-title {
    font-size: .69rem;
    letter-spacing: .14em;
    text-transform: uppercase;
    color: var(--accent);
    font-weight: 600;
    margin-bottom: .3rem;
  }
  .card-empty {
    color: var(--text-mute);
    font-size: .82rem;
    padding: .8rem 0;
    text-align: center;
    border-top: 1px dashed var(--border-soft);
    border-bottom: 1px dashed var(--border-soft);
    letter-spacing: .04em;
  }
  .dashboard-grid {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: .3rem;
    grid-auto-rows: min-content;
    align-content: start;
    transition: opacity .15s ease;
  }
  /* 更新中はグリッドを淡くして「固まっていない」ことを可視化 */
  .dashboard-grid.loading { opacity: .55; pointer-events: none; }
  .wide { grid-column: 1 / -1; }
  .span-2 { grid-column: span 2; }
  .metric-row {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: .38rem;
  }
  .dashboard-grid > section:not(.wide) .metric-row {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .metric {
    border: 1px solid var(--border-soft);
    background: var(--surface-2);
    border-radius: 3px;
    padding: .45rem .5rem;
  }
  .metric .num {
    font-size: 1.05rem;
    font-weight: 700;
    color: var(--accent-hi);
    font-variant-numeric: tabular-nums;
  }
  .metric .label {
    font-size: .68rem;
    color: var(--text-mute);
    letter-spacing: .04em;
    text-transform: uppercase;
    margin-top: .12rem;
  }
  .buy-item, .warn-item {
    border-top: 1px solid var(--border-soft);
    padding: .32rem 0;
    min-width: 0;
  }
  .buy-item:first-child, .warn-item:first-child { border-top: 0; padding-top: 0; }
  .buy-main {
    font-size: .95rem;
    font-weight: 700;
    color: var(--buy);
    display: block;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .buy-sub, .warn-item {
    color: var(--text-dim);
    font-size: .74rem;
    margin-top: .12rem;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .pill {
    display: inline-block;
    border-radius: 3px;
    background: var(--surface-2);
    border: 1px solid var(--border);
    padding: .06rem .35rem;
    margin-left: .25rem;
    font-size: .72rem;
    color: var(--text-dim);
    font-variant-numeric: tabular-nums;
  }
  .pill.buy { background: var(--buy-bg); border-color: var(--buy-border); color: var(--buy); }
  .compact-grid {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: .32rem;
  }
  .dashboard-grid > section:not(.wide):not(.span-2) .compact-grid {
    grid-template-columns: 1fr;
  }
  .mini-card {
    min-width: 0;
    border: 1px solid var(--border-soft);
    background: var(--surface-2);
    border-radius: 3px;
    padding: .38rem .45rem;
    overflow: hidden;
  }
  .mini-title {
    font-weight: 700;
    color: var(--accent-hi);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .mini-line {
    margin-top: .12rem;
    color: var(--text-dim);
    font-size: .72rem;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  /* ライブ天候 (open-meteo)。JV-Data の確定天候とは別行で併記し、
     上書きによるチラつき・情報消失を避ける。空のあいだは非表示。 */
  .live-weather { color: var(--accent-hi); }
  .live-weather:empty { display: none; }
  /* 買い候補ポートフォリオ集計バー (点数 / 推奨投資率 / 想定回収) */
  .buy-portfolio {
    display: flex;
    flex-wrap: wrap;
    align-items: baseline;
    gap: .25rem .8rem;
    padding: .3rem .5rem;
    margin-bottom: .35rem;
    background: var(--surface-2);
    border: 1px solid var(--border-soft);
    border-left: 2px solid var(--accent);
    border-radius: 3px;
    font-size: .74rem;
    color: var(--text-dim);
  }
  .buy-portfolio strong {
    color: var(--accent-hi);
    font-variant-numeric: tabular-nums;
  }
  .buy-portfolio .bp-count {
    font-weight: 700;
    color: var(--buy);
  }
  .buy-portfolio.over {
    border-left-color: var(--buy);
    background: var(--buy-bg);
  }
  .buy-portfolio .bp-warn {
    color: var(--buy);
    font-weight: 700;
  }
  .filter-panel {
    grid-column: 1 / -1;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 3px;
    padding: .35rem .55rem;
  }
  .filter-panel summary { cursor: pointer; color: var(--accent-hi); font-size: .76rem; }
  .filter-panel .filter-note { color: var(--text-mute); font-size: .7rem; margin-left: .4rem; }
  .filter-panel .hint { margin-top: .3rem; }
  .filter-controls {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr)) auto;
    gap: .45rem;
    margin-top: .35rem;
    align-items: end;
  }
  .filter-controls input { width: 100%; }
  .filter-reset {
    width: auto;
    margin: 0;
    padding: .32rem .55rem;
    font-size: .72rem;
    text-align: center;
    white-space: nowrap;
  }
  .seg {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: .25rem;
    margin-bottom: .35rem;
  }
  .seg button {
    margin: 0;
    padding: .26rem .35rem;
    text-align: center;
    font-size: .72rem;
  }
  .seg button.active { background: var(--accent-soft); border-color: var(--accent-hi); }
  .bt-period {
    font-size: .68rem;
    color: var(--text-mute);
    font-variant-numeric: tabular-nums;
    margin-bottom: .3rem;
  }
  /* n<30: 回収率が統計的に参考にならないサンプル数の警告 */
  .low-n {
    color: var(--buy);
    font-weight: 600;
  }
  .bt-note {
    margin-top: .3rem;
    font-size: .66rem;
    color: var(--text-mute);
    line-height: 1.35;
  }
  #warnings {
    max-height: 9rem;
    overflow-y: auto;
  }
  /* ブレークポイントは「サイドバー 380px を引いた main の実効幅」基準。
     3 列が成立する main >= 760px → viewport >= 1150px。
     2 列が成立する main >= 500px → viewport >= 890px。 */
  @media (max-width: 1150px) {
    .dashboard-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    .span-2 { grid-column: 1 / -1; }
  }
  @media (max-width: 1000px) {
    .sidebar { flex-basis: 330px; width: 330px; }
  }
  @media (max-width: 890px) {
    .dashboard-grid { grid-template-columns: 1fr; }
    .metric-row { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    .filter-controls { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    .filter-controls .filter-reset { grid-column: 1 / -1; }
  }

  /* ---------- header ---------- */
  header { margin-bottom: .65rem; }
  .brand {
    font-size: 1.08rem;
    font-weight: 600;
    letter-spacing: .22em;
    color: var(--text);
  }
  .brand .ornament {
    color: var(--accent);
    margin-right: .55em;
    font-size: .95em;
  }
  .subtitle {
    font-size: .67rem;
    letter-spacing: .16em;
    color: var(--text-mute);
    margin-top: .25rem;
    text-transform: uppercase;
  }
  .rule {
    height: 1px;
    background: linear-gradient(to right,
      var(--accent-line) 0%, var(--accent-line) 30%, transparent 100%);
    margin-top: .45rem;
  }

  /* ---------- form ---------- */
  .field { margin: .38rem 0; }
  .field-row {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: .5rem;
  }
  label {
    display: block;
    font-size: .68rem;
    letter-spacing: .12em;
    color: var(--text-dim);
    margin-bottom: .25rem;
    text-transform: uppercase;
  }
  input[type="date"], input[type="text"], input[type="number"] {
    width: 100%;
    background: var(--surface);
    border: 1px solid var(--border);
    color: var(--text);
    padding: .36rem .52rem;
    font-size: .84rem;
    border-radius: 3px;
    font-family: inherit;
    font-variant-numeric: tabular-nums;
    transition: border-color .15s ease, background .15s ease;
  }
  input:focus {
    outline: none;
    border-color: var(--accent);
    background: var(--surface-2);
  }
  input[type="date"]::-webkit-calendar-picker-indicator {
    filter: invert(.65) sepia(.3) hue-rotate(-15deg);
    cursor: pointer;
  }
  ::placeholder { color: var(--text-mute); opacity: .7; }
  .hint {
    color: var(--text-mute);
    font-size: .7rem;
    margin: .2rem 0 0;
  }
  .chip-row {
    display: flex;
    gap: .3rem;
    margin: .1rem 0 .15rem;
  }
  .chip-row button {
    display: inline-block;
    width: auto;
    flex: 1 1 0;
    margin: 0;
    padding: .26rem .4rem;
    font-size: .72rem;
    text-align: center;
    color: var(--text-dim);
  }

  /* ---------- status ---------- */
  .status-row {
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto;
    gap: .35rem;
    align-items: stretch;
    margin: .62rem 0 .35rem;
  }
  #status {
    background: var(--surface);
    border: 1px solid var(--border);
    border-left: 2px solid var(--text-mute);
    border-radius: 2px;
    padding: .46rem .65rem;
    margin: 0;
    font-size: .8rem;
    color: var(--text-dim);
    font-variant-numeric: tabular-nums;
    overflow-wrap: anywhere;
    transition: all .25s ease;
  }
  #cancelBtn {
    width: auto;
    min-width: 4.8rem;
    margin: 0;
    text-align: center;
    display: none;
  }
  #cancelBtn.visible { display: block; }
  #status.running {
    border-left-color: var(--accent);
    color: var(--text);
    background: var(--accent-soft);
  }
  #status.running::before {
    content: "●";
    color: var(--accent);
    margin-right: .5rem;
    animation: pulse 1.4s ease-in-out infinite;
  }
  .progress-wrap {
    grid-column: 1 / -1;
    height: 6px;
    background: var(--surface-2);
    border: 1px solid var(--border-soft);
    border-radius: 999px;
    overflow: hidden;
    display: none;
  }
  .progress-wrap.visible { display: block; }
  #progressBar {
    height: 100%;
    width: 0%;
    background: var(--accent-hi);
    transition: width .25s ease;
  }
  #progressText {
    grid-column: 1 / -1;
    color: var(--text-mute);
    font-size: .68rem;
    display: none;
  }
  #progressText.visible { display: block; }
  @keyframes pulse {
    0%, 100% { opacity: .25; }
    50%      { opacity: 1; }
  }

  /* ---------- section labels ---------- */
  .section-label {
    font-size: .67rem;
    letter-spacing: .18em;
    color: var(--text-mute);
    text-transform: uppercase;
    font-weight: 600;
    margin: .72rem 0 .32rem;
    display: flex;
    align-items: center;
    gap: .55rem;
  }
  .section-label::after {
    content: "";
    flex: 1;
    height: 1px;
    background: var(--border-soft);
  }

  /* ---------- buttons ---------- */
  button {
    display: block;
    width: 100%;
    padding: .48rem .72rem;
    margin: .22rem 0;
    font-size: .83rem;
    font-family: inherit;
    color: var(--text);
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 3px;
    cursor: pointer;
    text-align: left;
    transition: all .14s ease;
    font-variant-numeric: tabular-nums;
    letter-spacing: .02em;
  }
  button:hover {
    background: var(--surface-2);
    border-color: var(--accent);
    color: var(--accent-hi);
  }
  button:disabled {
    cursor: not-allowed;
    opacity: .52;
  }
  button:disabled:hover {
    background: var(--surface);
    border-color: var(--border);
    color: var(--text);
    box-shadow: none;
  }
  button:active { transform: translateY(1px); }
  button:focus-visible,
  summary:focus-visible {
    outline: 2px solid var(--accent-hi);
    outline-offset: 1px;
  }
  button .step {
    display: inline-block;
    color: var(--accent);
    margin-right: .65rem;
    font-weight: 500;
    min-width: 1em;
  }
  button.primary {
    background: linear-gradient(180deg, var(--primary) 0%, var(--primary-hi) 100%);
    border-color: var(--primary-hi);
    color: var(--on-primary);
    padding: .7rem .78rem;
    font-size: .9rem;
    letter-spacing: .1em;
    margin: .35rem 0 .5rem;
    text-align: center;
    font-weight: 600;
    box-shadow: 0 2px 6px -2px rgba(31,41,55,.35);
  }
  button.primary:hover {
    background: linear-gradient(180deg, var(--primary-soft) 0%, var(--primary-deep) 100%);
    color: var(--on-primary);
    border-color: var(--primary-deep);
    box-shadow: 0 4px 14px -4px rgba(17,24,39,.5);
  }
  button.primary:disabled,
  button.primary:disabled:hover {
    background: var(--primary);
    color: var(--on-primary);
    border-color: var(--primary-hi);
    box-shadow: none;
  }

  /* ---------- details ---------- */
  .adv {
    background: var(--surface);
    border: 1px solid var(--border-soft);
    border-radius: 3px;
    margin: .45rem 0 0;
    font-size: .76rem;
  }
  .adv summary {
    cursor: pointer;
    padding: .35rem .55rem;
    color: var(--text-dim);
  }
  .adv .field {
    padding: 0 .55rem .45rem;
    margin: 0;
  }
  #detailsBox {
    background: var(--log-bg);
    color: var(--log-fg);
    border-radius: 3px;
    border: 1px solid var(--border-soft);
    margin: .62rem 0 0;
    font-size: .72rem;
  }
  #detailsBox summary {
    cursor: pointer;
    padding: .45rem .62rem;
    color: var(--text-dim);
  }
  #detailsText {
    white-space: pre-wrap;
    word-break: break-all;
    padding: 0 .7rem .7rem;
    font-family: "JetBrains Mono", "Cascadia Code", "Consolas",
                 ui-monospace, monospace;
    font-size: .7rem;
    line-height: 1.42;
  }

  /* ---------- scrollbar ---------- */
  ::-webkit-scrollbar { width: 6px; height: 6px; }
  ::-webkit-scrollbar-track { background: var(--bg); }
  ::-webkit-scrollbar-thumb {
    background: var(--border);
    border-radius: 3px;
  }
  ::-webkit-scrollbar-thumb:hover { background: var(--accent); }
</style>
</head>
<body>
<aside class="sidebar">
<header>
  <div class="brand"><span class="ornament">◆</span>競 馬 予 想</div>
  <div class="subtitle">JV-Link Control</div>
  <div class="rule"></div>
</header>

<div class="field-row">
  <div class="field">
    <label>開催日 From</label>
    <input id="from_date" type="date">
  </div>
  <div class="field">
    <label>To</label>
    <input id="to_date" type="date">
  </div>
</div>
<div class="chip-row">
  <button type="button" onclick="presetToday()">今日</button>
  <button type="button" onclick="presetWeekend()">今週末</button>
  <button type="button" onclick="presetLatest()" title="データが存在する最新の開催日を表示 (平日など当日にレースが無いときに)">最新開催</button>
</div>

<div class="status-row">
  <div id="status" role="status" aria-live="polite">準備完了。</div>
  <button id="cancelBtn" type="button" onclick="cancelRun()">中止</button>
  <div id="progressWrap" class="progress-wrap"><div id="progressBar"></div></div>
  <div id="progressText"></div>
</div>

<button class="primary" data-action="run_all" onclick="runAction(this)">取得 → 予想 → 公開</button>

<div class="section-label">個別実行</div>
<button data-action="fetch_data" onclick="runAction(this)"><span class="step">Ⅰ</span>JVLink でデータ取得</button>
<button data-action="fetch_odds" onclick="runAction(this)"><span class="step">Ⅱ</span>最新オッズ取得</button>
<button data-action="run_prediction" onclick="runAction(this)"><span class="step">Ⅲ</span>予想生成</button>
<button data-action="publish" onclick="runAction(this)"><span class="step">Ⅳ</span>iCloud Drive へ公開</button>
<button data-action="fetch_bloodline" onclick="runAction(this)"><span class="step">＊</span>血統データ取得</button>

<div class="section-label">確認</div>
<button data-action="open_icloud_folder" onclick="runAction(this)"><span class="step">›</span>iCloud 公開先を Explorer で開く</button>

<details class="adv">
  <summary>詳細設定</summary>
  <div class="field">
    <label>血統取得 開始時刻 (任意)</label>
    <input id="bloodline_fromtime" type="text" placeholder="空欄なら前回以降の差分">
    <div class="hint">例 — 20260501000000</div>
  </div>
</details>

<details id="detailsBox">
  <summary>詳細を表示</summary>
  <pre id="detailsText">準備完了。</pre>
</details>
</aside>

<main class="main">
  <div class="main-toolbar">
    <div class="tabs">
      <button id="tabDash" type="button" class="tab active" onclick="showTab('dash')">ダッシュボード</button>
      <button id="tabPreview" type="button" class="tab" onclick="showTab('preview')">予想 HTML</button>
      <button id="closePreviewBtn" type="button" class="tab close-tab" onclick="showTab('dash')" style="display:none" title="プレビューを閉じてダッシュボードに戻る (Esc)">✕ 閉じる</button>
    </div>
    <span id="dashMeta" class="toolbar-meta"></span>
    <button id="refreshBtn" type="button" class="tool-btn" onclick="forceRefresh()" title="キャッシュを破棄して再計算">⟳ 更新</button>
  </div>
  <div id="dashboardPane">
    <div class="dashboard-grid" id="dashGrid">
      <details class="filter-panel">
        <summary>買い目フィルタ <span class="filter-note">__FILTER_BASE_NOTE__</span></summary>
        <div class="filter-controls">
          <label>EV<input id="filter_ev" type="number" min="0" max="3" step="0.01" placeholder="なし"></label>
          <label>Value<input id="filter_value" type="number" min="-50" max="200" step="1" placeholder="なし"></label>
          <label>Odds min<input id="filter_min_odds" type="number" min="1" max="100" step="0.1" placeholder="なし"></label>
          <label>Odds max<input id="filter_max_odds" type="number" min="1" max="100" step="0.1" placeholder="なし"></label>
          <button type="button" class="filter-reset" onclick="resetFilters()">既定値に戻す</button>
        </div>
        <div class="hint">空欄 = 制限なし。上記 4 項目以外の採用戦略条件 (左記) は常に適用される。</div>
      </details>
      <section class="card wide">
        <div class="card-title">本日の状況</div>
        <div id="summary" class="metric-row"><div class="card-empty">読み込み中...</div></div>
      </section>
      <section class="card span-2">
        <div class="card-title">買い候補</div>
        <div id="buyList" class="card-empty">読み込み中...</div>
      </section>
      <section class="card">
        <div class="card-title">直近バックテスト</div>
        <div id="backtest" class="card-empty">読み込み中...</div>
      </section>
      <section class="card">
        <div class="card-title">注意点</div>
        <div id="warnings" class="card-empty">読み込み中...</div>
      </section>
      <section class="card">
        <div class="card-title">開催競馬場</div>
        <div id="venues" class="card-empty">読み込み中...</div>
      </section>
      <section class="card">
        <div class="card-title">本日の場別傾向</div>
        <div id="trackTrends" class="card-empty">読み込み中...</div>
      </section>
    </div>
  </div>
  <div id="previewPane" style="display:none"><iframe id="previewFrame" src="about:blank"></iframe></div>
</main>

<script>
  var backtestRange = '3';
  var dashSeq = 0;
  var btSeq = 0;
  var filterTimer = null;

  function valueOr(value, fallback) {
    return value == null ? fallback : value;
  }
  function byId(id) {
    return document.getElementById(id);
  }
  function esc(v) {
    return String(valueOr(v, '')).replace(/[&<>"']/g, function (ch) {
      return {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[ch];
    });
  }
  function metric(label, value) {
    return '<div class="metric"><div class="num">' + esc(value) + '</div><div class="label">' + esc(label) + '</div></div>';
  }
  function pct2(frac) {
    var n = Number(frac);
    if (!isFinite(n)) return '0.00';
    return (n * 100).toFixed(2);
  }
  function shortTime(v) {
    if (!v) return '-';
    var d = new Date(v);
    if (isNaN(d.getTime())) return String(v).slice(11, 16) || String(v);
    return String(d.getHours()).padStart ? String(d.getHours()).padStart(2, '0') + ':' + String(d.getMinutes()).padStart(2, '0') : d.getHours() + ':' + d.getMinutes();
  }
  function fmtYmd(v) {
    v = String(valueOr(v, ''));
    return v.length === 8 ? v.slice(4, 6) + '/' + v.slice(6, 8) : v;
  }
  function fmtDateInput(d) {
    return d.getFullYear() + '-' + ('0' + (d.getMonth() + 1)).slice(-2) + '-' + ('0' + d.getDate()).slice(-2);
  }
  function ymdToInput(v) {
    v = String(valueOr(v, ''));
    return v.length === 8 ? v.slice(0, 4) + '-' + v.slice(4, 6) + '-' + v.slice(6, 8) : '';
  }
  // フィルタ key ↔ input id の対応 (options / applyBuyFilter で共用)
  var FILTER_INPUTS = {
    min_ev: 'filter_ev',
    min_value: 'filter_value',
    min_odds: 'filter_min_odds',
    max_odds: 'filter_max_odds'
  };
  function options() {
    var o = {
      from_date: byId('from_date').value,
      to_date: byId('to_date').value,
      bloodline_fromtime: byId('bloodline_fromtime').value,
      backtest_range: backtestRange
    };
    // 空欄の input は送らない → Python 側が config.BUY_FILTER_DEFAULT を使う。
    // JS にフォールバック定数 (旧: 1.05/0/10/20) を持たない。config と
    // 乖離した「幻の制約」が常時送信されていた事故 (P21 review 指摘) の再発防止。
    for (var key in FILTER_INPUTS) {
      var el = byId(FILTER_INPUTS[key]);
      if (!el || el.value === '') continue;
      var n = Number(el.value);
      if (isFinite(n)) o[key] = n;
    }
    return o;
  }
  function setActionButtonsDisabled(disabled) {
    var buttons = document.querySelectorAll('.sidebar button[data-action]');
    for (var i = 0; i < buttons.length; i += 1) buttons[i].disabled = disabled;
  }
  function setDetails(value, open) {
    var box = byId('detailsBox');
    var text = byId('detailsText');
    text.textContent = typeof value === 'string' ? value : JSON.stringify(value, null, 2);
    box.open = Boolean(open);
  }

  /* ---------- タブ (ダッシュボード / 予想 HTML プレビュー) ---------- */
  function showTab(name) {
    var isPreview = name === 'preview';
    byId('dashboardPane').style.display = isPreview ? 'none' : '';
    byId('previewPane').style.display = isPreview ? '' : 'none';
    byId('tabDash').className = isPreview ? 'tab' : 'tab active';
    byId('tabPreview').className = isPreview ? 'tab active' : 'tab';
    // プレビュー表示中だけ「✕ 閉じる」を出す (戻る導線の明示)
    byId('closePreviewBtn').style.display = isPreview ? '' : 'none';
    if (isPreview && !byId('previewFrame').getAttribute('data-loaded')) {
      reloadPreview();
    }
  }
  function reloadPreview() {
    var frame = byId('previewFrame');
    if (!frame) return;
    frame.setAttribute('data-loaded', '1');
    // control.html は web/dist/_gui/ に置かれるので ../index.html = web/dist/index.html。
    // ?ts= はキャッシュバスター (予想生成後に必ず新しい HTML を読む)。
    frame.src = '../index.html?ts=' + Date.now();
  }

  /* ---------- 日付プリセット ---------- */
  function setDates(from, to) {
    byId('from_date').value = from;
    byId('to_date').value = to;
    refreshAll();
  }
  function presetToday() {
    var t = fmtDateInput(new Date());
    setDates(t, t);
  }
  function presetWeekend() {
    var now = new Date();
    var dow = now.getDay();
    var sat = new Date(now.getTime());
    if (dow === 0) {
      sat.setDate(now.getDate() - 1);
    } else {
      sat.setDate(now.getDate() + (6 - dow));
    }
    var sun = new Date(sat.getTime());
    sun.setDate(sat.getDate() + 1);
    setDates(fmtDateInput(sat), fmtDateInput(sun));
  }
  function presetLatest() {
    // 空欄 = Python 側 _date_range が「データのある最新開催日」に解決する。
    // 解決結果は renderDashboard が input に書き戻すので、ユーザには
    // 「最新開催の日付が入った」ように見える (空欄のままだと意図が
    // 伝わらない、という 2026-06-12 ユーザフィードバックへの対応)。
    setDates('', '');
  }

  /* ---------- 買い目フィルタ ---------- */
  function applyBuyFilter(f) {
    if (!f) return;
    // null は「config 上 制限なし」= input を空欄に戻す。
    // 旧実装は null を skip していたため「既定値に戻す」がユーザ入力を
    // クリアできなかった (現 config は 4 値とも None)。
    for (var key in FILTER_INPUTS) {
      var el = byId(FILTER_INPUTS[key]);
      if (!el || !(key in f)) continue;
      el.value = f[key] == null ? '' : f[key];
    }
  }
  function resetFilters() {
    if (!window.pywebview || !window.pywebview.api || !window.pywebview.api.get_buy_filter_default) return;
    window.pywebview.api.get_buy_filter_default({}).then(function (res) {
      if (res && res.filter) {
        applyBuyFilter(res.filter);
        refreshDashboard();
      }
    }).catch(function () {});
  }
  function onFilterChange() {
    // 連続入力をデバウンス。フィルタはバックテストに影響しないので
    // 本体のみ更新 (予測はキャッシュ済みで 1 秒未満)。
    if (filterTimer) clearTimeout(filterTimer);
    filterTimer = setTimeout(function () {
      refreshDashboard();
    }, 350);
  }

  /* ---------- バックテストカード ---------- */
  function bindBacktestRangeButtons() {
    var buttons = document.querySelectorAll('#backtest button[data-range]');
    for (var i = 0; i < buttons.length; i += 1) {
      buttons[i].onclick = function () {
        backtestRange = this.getAttribute('data-range');
        var all = document.querySelectorAll('#backtest button[data-range]');
        for (var j = 0; j < all.length; j += 1) {
          all[j].className = all[j].getAttribute('data-range') === backtestRange ? 'active' : '';
        }
        // 未キャッシュの期間は計算に数十秒かかりうるので即時フィードバック
        var period = document.querySelector('#backtest .bt-period');
        if (period) period.textContent = '計算中...';
        refreshBacktest();
      };
    }
  }
  function renderBacktest(bt) {
    if (!bt) return;
    var btPeriod = bt.period ? esc(bt.label) + ' ' + esc(bt.period) : esc(bt.label || '-');
    if (bt.low_n) btPeriod += ' <span class="low-n">' + esc(bt.low_n_note || 'n少 参考値') + '</span>';
    if (bt.anchor_stale) btPeriod += ' <span class="low-n">確定データ' + esc(bt.anchor_age_days) + '日前</span>';
    byId('backtest').innerHTML = '<div class="seg">' +
      ['3', '7', '30', 'month'].map(function (v) {
        return '<button type="button" data-range="' + esc(v) + '" class="' + (backtestRange === v ? 'active' : '') + '">' + (v === 'month' ? '当月' : v + '日') + '</button>';
      }).join('') + '</div>' +
      '<div class="bt-period">' + btPeriod + '</div>' +
      '<div class="metric-row">' +
      metric('対象R', valueOr(bt.races, 0)) +
      metric('単勝', valueOr(bt.wins, 0) + '/' + valueOr(bt.races, 0)) +
      metric('3着内', valueOr(bt.top3, 0) + '/' + valueOr(bt.races, 0)) +
      metric('回収率', valueOr(bt.return_rate, 0) + '%') + '</div>' +
      (bt.note ? '<div class="bt-note">' + esc(bt.note) + '</div>' : '');
    bindBacktestRangeButtons();
  }
  function refreshBacktest() {
    if (!window.pywebview || !window.pywebview.api || !window.pywebview.api.get_backtest) return;
    // 未キャッシュ期間は数十秒かかるため、連打時に古い応答が後着して
    // 「active ボタン ≠ 表示データ」にならないよう seq ガード
    var seq = ++btSeq;
    window.pywebview.api.get_backtest(options()).then(function (res) {
      if (seq !== btSeq) return;
      if (res && res.ok) renderBacktest(res.backtest);
    }).catch(function () {});
  }

  /* ---------- ダッシュボード ---------- */
  function weatherText(code) {
    var m = {0: '晴', 1: '晴', 2: '曇', 3: '曇', 45: '霧', 48: '霧', 51: '小雨', 53: '小雨', 55: '雨', 61: '雨', 63: '雨', 65: '強雨', 71: '雪', 73: '雪', 75: '大雪', 80: 'にわか雨', 81: 'にわか雨', 82: '強雨', 95: '雷雨'};
    return m[code] || '天候取得';
  }
  function setDashLoading(on) {
    var grid = byId('dashGrid');
    if (grid) grid.className = on ? 'dashboard-grid loading' : 'dashboard-grid';
    var btn = byId('refreshBtn');
    if (btn) btn.disabled = on;
    if (on) byId('dashMeta').textContent = '更新中...';
  }
  function renderDashboard(data) {
    if (!data || !data.ok) return;
    var s = data.summary || {};

    var metaParts = [];
    if (data.from_date) {
      var range = fmtYmd(data.from_date);
      if (data.to_date && data.to_date !== data.from_date) range += '〜' + fmtYmd(data.to_date);
      metaParts.push('対象 ' + range);
    }
    metaParts.push('HTML生成 ' + valueOr(s.generated_at, '-'));
    byId('dashMeta').textContent = metaParts.join('  /  ');

    // 日付が両方空欄 (= 自動解決、「最新開催」プリセット含む) のときは
    // 解決された開催日を input に書き戻して「何が表示されているか」を明示。
    // ユーザ入力中 (片方だけ空欄) は触らない。
    var fromEl = byId('from_date');
    var toEl = byId('to_date');
    if (fromEl && toEl && !fromEl.value && !toEl.value && data.from_date) {
      fromEl.value = ymdToInput(data.from_date);
      toEl.value = ymdToInput(data.to_date || data.from_date);
    }

    byId('summary').innerHTML =
      metric('レース', valueOr(s.races, 0)) +
      metric('出走頭数', valueOr(s.horses, 0)) +
      metric('買い候補', valueOr(s.buy_count, 0)) +
      metric('Odds最新', shortTime(s.last_fetched_odds) + (s.odds_age_minutes == null ? '' : ' / ' + s.odds_age_minutes + '分前'));

    var buys = data.buy_candidates || [];
    var bp = data.buy_portfolio || {};
    var portfolioHtml = '';
    if (bp.count) {
      var investLabel = bp.multi_day ? '推奨投資(最大日)' : '推奨投資';
      var ret = bp.exp_return_pct == null ? '-' : esc(bp.exp_return_pct) + '%';
      portfolioHtml = '<div class="buy-portfolio' + (bp.any_over_cap ? ' over' : '') + '">' +
        '<span class="bp-count">' + esc(bp.count) + '点</span>' +
        '<span>' + investLabel + ' <strong>' + esc(bp.max_day_pct) + '%</strong> / 上限 ' + esc(bp.cap_pct) + '%</span>' +
        '<span>想定回収 <strong>' + ret + '</strong></span>' +
        (bp.any_over_cap ? '<span class="bp-warn">⚠ 上限超過</span>' : '') +
        '</div>';
    }
    byId('buyList').innerHTML = buys.length ? portfolioHtml + buys.map(function (b) {
      return '<div class="buy-item">' +
        '<div class="buy-main">' + esc(b.track) + ' ' + esc(b.race_num) + 'R ' + esc(b.horse_num) + ' ' + esc(b.horse_name) + '</div>' +
        '<div class="buy-sub">' + esc(b.start_time) + ' / ' + esc(b.race_name || '') +
        '<span class="pill buy">' + esc(b.odds) + '倍</span>' +
        '<span class="pill">' + esc(b.popularity) + '人気</span>' +
        '<span class="pill">P ' + esc(b.probability) + '%</span>' +
        '<span class="pill">EV ' + esc(b.ev) + '</span>' +
        '<span class="pill" title="1/4 Kelly + 1点上限cap済みの推奨投資率">推奨 ' + pct2(b.recommended_kelly) + '%</span></div></div>';
    }).join('') : '<div class="card-empty">買い候補なし。EV/信頼度条件では見送りです。</div>';

    var warnings = data.warnings || [];
    byId('warnings').innerHTML = warnings.length ? warnings.map(function (w) { return '<div class="warn-item">' + esc(w) + '</div>'; }).join('') : '<div class="card-empty">注意点はありません。</div>';

    var venues = data.venues || [];
    byId('venues').innerHTML = venues.length ? '<div class="compact-grid">' + venues.map(function (v) {
      return '<div class="mini-card venue-card" data-track="' + esc(v.track) + '" data-lat="' + esc(v.lat) + '" data-lon="' + esc(v.lon) + '">' +
        '<div class="mini-title">' + esc(v.track) + ' <span class="pill">' + esc(v.races) + 'R</span></div>' +
        '<div class="mini-line">' + esc(v.surfaces) + '</div>' +
        '<div class="mini-line">天候 ' + esc(v.weather) + ' / 芝 ' + esc(v.turf) + ' / ダ ' + esc(v.dirt) + '</div>' +
        '<div class="mini-line live-weather"></div></div>';
    }).join('') + '</div>' : '<div class="card-empty">開催情報がありません。</div>';
    updateVenueWeather();

    var trends = data.track_trends || [];
    byId('trackTrends').innerHTML = trends.length ? '<div class="compact-grid">' + trends.map(function (t) {
      return '<div class="mini-card"><div class="mini-title">' + esc(t.track) + ' <span class="pill">3着内 ' + esc(t.top3_samples) + '</span></div>' +
        '<div class="mini-line">' + esc(t.surface) + ' / ' + esc(t.leg) + ' / ' + esc(t.gate) + '</div><div class="mini-line">' + esc(t.note) + '</div></div>';
    }).join('') + '</div>' : '<div class="card-empty">確定済みの当日結果がまだ少なく、傾向は表示できません。</div>';
  }
  function refreshDashboard(opts) {
    if (!window.pywebview || !window.pywebview.api || !window.pywebview.api.get_dashboard) return Promise.resolve();
    opts = opts || {};
    var payload = options();
    // backtest は常に分離取得 (refreshAll 参照)。初回 100 日分の再予測は
    // 数十秒〜かかるため、ダッシュボード本体の描画を待たせない。
    payload.skip_backtest = true;
    if (opts.force) payload.force_refresh = true;
    var seq = ++dashSeq;
    setDashLoading(true);
    return window.pywebview.api.get_dashboard(payload).then(function (data) {
      if (seq !== dashSeq) return;
      setDashLoading(false);
      renderDashboard(data);
    }).catch(function (e) {
      if (seq !== dashSeq) return;
      setDashLoading(false);
      byId('dashMeta').textContent = '';
      byId('summary').innerHTML = '<div class="card-empty">ダッシュボード取得エラー: ' + esc(e) + '</div>';
    });
  }
  // 本体を先に描画 → 完了後にバックテストを後追いロード。
  // 並列にしない (同一プロセスの GIL で取り合うだけ + force 時のキャッシュ
  // 破棄レースを避ける)。
  function refreshAll(opts) {
    refreshDashboard(opts).then(function () { refreshBacktest(); });
  }
  function forceRefresh() {
    refreshAll({force: true});
  }
  function updateVenueWeather() {
    if (!window.pywebview || !window.pywebview.api || !window.pywebview.api.get_weather) return;
    var cards = document.querySelectorAll('.venue-card');
    for (var i = 0; i < cards.length; i += 1) {
      (function (card) {
        var lat = card.getAttribute('data-lat');
        var lon = card.getAttribute('data-lon');
        var line = card.querySelector('.live-weather');
        if (!lat || !lon || lat === 'None' || lon === 'None' || !line) return;
        window.pywebview.api.get_weather({lat: lat, lon: lon}).then(function (py) {
          if (!py || !py.ok) return;
          var temp = py.temperature == null ? '-' : Math.round(py.temperature) + '度';
          var rain = py.precipitation == null ? '-' : py.precipitation + 'mm';
          line.textContent = '現在 ' + weatherText(py.weather_code) + ' / ' + temp + ' / 降水 ' + rain;
        }).catch(function () {});
      })(cards[i]);
    }
  }

  /* ---------- ステータス / 実行 ---------- */
  function applyStatus(st) {
    var box = byId('status');
    var cancelBtn = byId('cancelBtn');
    var progressWrap = byId('progressWrap');
    var progressBar = byId('progressBar');
    var progressText = byId('progressText');
    box.textContent = '[' + st.updated_at + '] ' + st.message;
    box.className = st.running ? 'running' : '';
    cancelBtn.className = st.running ? 'visible' : '';
    var detail = st.detail || {};
    var progress = detail.progress;
    if (st.running && progress != null) {
      progressWrap.className = 'progress-wrap visible';
      progressBar.style.width = Math.max(0, Math.min(100, progress)) + '%';
      var eta = detail.eta_sec == null ? '-' : Math.ceil(detail.eta_sec / 60) + '分';
      progressText.textContent = progress.toFixed ? progress.toFixed(1) + '% / 残り 約' + eta : progress + '%';
      progressText.className = 'visible';
    } else {
      progressWrap.className = 'progress-wrap';
      progressBar.style.width = '0%';
      progressText.className = '';
      progressText.textContent = '';
    }
    setActionButtonsDisabled(Boolean(st.running));
    return Boolean(st.running);
  }
  function refreshStatus() {
    if (!window.pywebview || !window.pywebview.api || !window.pywebview.api.get_status) return Promise.resolve(false);
    return window.pywebview.api.get_status({}).then(function (st) { return applyStatus(st); }).catch(function (e) {
      byId('status').textContent = '進捗取得エラー: ' + e;
      return false;
    });
  }
  function cancelRun() {
    if (!window.pywebview || !window.pywebview.api || !window.pywebview.api.cancel) return;
    byId('cancelBtn').disabled = true;
    window.pywebview.api.cancel({}).then(function () { return refreshStatus(); }).then(function () {
      byId('cancelBtn').disabled = false;
    }).catch(function () { byId('cancelBtn').disabled = false; });
  }
  function runAction(button) {
    run(button.getAttribute('data-action'));
  }
  function run(method) {
    if (!method || !window.pywebview || !window.pywebview.api || typeof window.pywebview.api[method] !== 'function') {
      setDetails('実行できない操作です: ' + method, true);
      return;
    }
    refreshStatus().then(function (running) {
      if (running) {
        setDetails('別の処理が実行中です。完了後に再実行してください。', true);
        return;
      }
      setActionButtonsDisabled(true);
      setDetails(method + ' 実行中...', false);
      var timer = setInterval(refreshStatus, 1000);
      window.pywebview.api[method](options()).then(function (res) {
        refreshAll();
        if (res && res.ok === false) {
          var summary = [res.error || res.message || 'エラーが発生しました', res.hint || ''].filter(function (x) { return Boolean(x); }).join('\\n');
          setDetails(summary + '\\n\\n' + JSON.stringify(res, null, 2), true);
        } else {
          setDetails(res, false);
          // 予想 HTML が更新されるアクション後はプレビューを再読込。
          // 生成系はそのまま結果を見せる (タブ切替)。
          if (method === 'run_prediction' || method === 'run_all') {
            reloadPreview();
            showTab('preview');
          } else if (method === 'publish') {
            reloadPreview();
          }
        }
      }).catch(function (e) {
        setDetails('エラー: ' + e, true);
      }).then(function () {
        clearInterval(timer);
        return refreshStatus();
      }).then(function (stillRunning) {
        if (!stillRunning) setActionButtonsDisabled(false);
      });
    });
  }

  /* ---------- 起動 ---------- */
  function restoreOptions() {
    // Python 側 config.BUY_FILTER_DEFAULT を input 初期値に反映。
    // HTML に value をハードコードしない (Python 側既定値とズレる事故防止)。
    if (!window.pywebview || !window.pywebview.api || !window.pywebview.api.get_buy_filter_default) return Promise.resolve();
    return window.pywebview.api.get_buy_filter_default({}).then(function (res) {
      if (res && res.filter) applyBuyFilter(res.filter);
    }).catch(function () {});
  }
  function boot() {
    restoreOptions().then(function () {
      refreshStatus();
      refreshAll();
    });
    var from = byId('from_date');
    var to = byId('to_date');
    if (from) from.onchange = function () { refreshAll(); };
    if (to) to.onchange = function () { refreshAll(); };
    var ids = ['filter_ev', 'filter_value', 'filter_min_odds', 'filter_max_odds'];
    for (var i = 0; i < ids.length; i += 1) {
      var el = byId(ids[i]);
      if (el) el.onchange = onFilterChange;
    }
  }
  // Esc でプレビューを閉じる (iframe 内にフォーカスがあるときは届かないが、
  // タブ/閉じるボタンへの補助導線として)
  window.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && byId('previewPane').style.display !== 'none') {
      showTab('dash');
    }
  });
  window.addEventListener('pywebviewready', boot);
  if (window.pywebview && window.pywebview.api) boot();
</script>
</body>
</html>
"""


def _write_control_page() -> Path:
    """CONTROL_HTML を WEB_DIST/_gui/control.html に書き出して Path を返す。

    なぜ file 配信: 右ペインの「予想 HTML」タブは web/dist/index.html を
    iframe で表示する。load_html (data URI 相当の origin) からは file://
    iframe の読み込みが Chromium にブロックされるため、コントロールパネル
    自体を file:// で配信してスキームを揃える (旧 preview.html ラッパーと
    同じ手法をコントロール側にも適用)。
    """
    index = WEB_DIST / "index.html"
    if not index.exists():
        # viewport を入れておく: 未生成のまま「公開」されて iPhone で
        # 開かれるエッジケースでも素の極小表示にならないように。
        index.write_text(
            "<!doctype html><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width,initial-scale=1'>"
            "<h1>プレビュー未生成</h1>"
            "<p>「予想生成」を実行すると HTML がここに作られます。</p>",
            encoding="utf-8",
        )
    page_dir = WEB_DIST / "_gui"
    page_dir.mkdir(parents=True, exist_ok=True)
    page = page_dir / "control.html"
    page.write_text(CONTROL_HTML.replace(
        "__FILTER_BASE_NOTE__", _filter_base_note()), encoding="utf-8")
    return page


def _filter_base_note() -> str:
    """買い目フィルタパネルに出す「常時適用される採用戦略条件」の注記。

    config.BUY_FILTER_DEFAULT から動的に組み立てる (HTML に静的記述すると
    戦略変更時に乖離するため)。GUI input で上書きできる 4 値は含めない。
    """
    parts = []
    if BUY_FILTER_DEFAULT.get("min_kelly") is not None:
        parts.append(f"Kelly≥{BUY_FILTER_DEFAULT['min_kelly']}")
    if BUY_FILTER_DEFAULT.get("max_predicted_p") is not None:
        parts.append(f"p≤{BUY_FILTER_DEFAULT['max_predicted_p']}")
    if BUY_FILTER_DEFAULT.get("max_odds_age_min") is not None:
        parts.append(f"オッズ鮮度≤{BUY_FILTER_DEFAULT['max_odds_age_min']}分")
    return "既定: " + " / ".join(parts) if parts else ""


def main() -> None:
    print("[gui.app] creating window...", flush=True)
    api = Api()
    page = _write_control_page()
    # 1240x690: ノート PC 基準。1366x768 (タスクバー込み実効 ~720px) と
    # 1920x1080 の 150% スケーリング (実効 1280x720 相当) のどちらでも
    # はみ出さない。旧 1100x780 は縦 780 が両ケースで画面外に出ていた。
    webview.create_window(
        title="競馬予想",
        url=page.as_uri(),
        js_api=api,
        width=1240,
        height=690,
        min_size=(960, 600),
        x=60,
        y=40,
        on_top=False,
        background_color="#eaedf1",
    )
    print("[gui.app] starting event loop...", flush=True)
    webview.start()
    print("[gui.app] event loop ended", flush=True)


if __name__ == "__main__":
    main()
