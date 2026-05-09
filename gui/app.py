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
from config import ICLOUD_PUBLISH_DIR, WEB_DIST, ensure_dirs
from db import open_db
from jvlink_client import ALL_DATASPECS, JVLinkClient
from jvlink_client.ingest import ingest_all
from predictor import is_tentative, predict_race
from scripts.backtest import get_payout, horses_for_race, list_races
from scripts.fetch_odds import race_key
from web.codes import race_id_to_date, track_name
from web.generator import BET_MAX_ODDS, BET_MIN_EV, BET_MIN_ODDS, BET_MIN_VALUE, publish_to_icloud, render

ensure_dirs()


def _safe(fn):
    """API 呼び出しをまるごと try で包んで例外を JSON 化する。"""

    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            if args and hasattr(args[0], "_set_status"):
                args[0]._set_status(f"エラー: {type(e).__name__}: {e}", "error", running=False)
            return {
                "ok": False,
                "error": f"{type(e).__name__}: {e}",
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
        self._weather_cache: dict[tuple[str, str], tuple[float, dict]] = {}

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
        ds = info.get("dataspec", "")
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
        self._set_status(msg, stage, info, running=True)

    @_safe
    def get_status(self, options: dict | None = None) -> dict:
        with self._status_lock:
            return dict(self._status)

    def _date_range(self, options: dict | None = None) -> tuple[str, str]:
        options = options or {}
        from_date = (options.get("from_date") or "").replace("-", "")
        to_date = (options.get("to_date") or "").replace("-", "")
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

    def _is_buy_candidate(self, pred, horse: dict, tentative: bool) -> bool:
        odds = (horse.get("win_odds") or 0) / 10.0
        return (
            pred.rank == 1
            and pred.mark
            and not tentative
            and pred.confidence not in ("暫定", "混戦", "接戦")
            and pred.value_score >= BET_MIN_VALUE
            and pred.expected_value >= BET_MIN_EV
            and pred.kelly_fraction > 0
            and BET_MIN_ODDS <= odds <= BET_MAX_ODDS
        )

    def _recent_backtest(self, conn, to_date: str) -> dict:
        rows = conn.execute(
            """
            SELECT DISTINCT race_year || race_month_day AS d
            FROM horse_races
            WHERE confirmed_order > 0 AND (race_year || race_month_day) <= ?
            ORDER BY d DESC
            LIMIT 3
            """,
            (to_date,),
        ).fetchall()
        dates = sorted([r["d"] for r in rows])
        if not dates:
            return {"label": "直近3日", "races": 0, "wins": 0, "top3": 0, "return_rate": 0}
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
            "label": f"{dates[0]}-{dates[-1]}",
            "races": total,
            "wins": wins,
            "top3": top3,
            "win_rate": round(wins / total * 100, 1) if total else 0,
            "top3_rate": round(top3 / total * 100, 1) if total else 0,
            "return_rate": round(payout / (total * 100) * 100, 1) if total else 0,
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

    @_safe
    def get_dashboard(self, options: dict | None = None) -> dict:
        from_date, to_date = self._date_range(options)
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
            buy_candidates: list[dict] = []
            top_preview: list[dict] = []
            prediction_items: list[dict] = []
            feature_cache: dict = {}
            for race in races:
                horses = horses_for_race(conn, race)
                if not horses:
                    continue
                preds = predict_race(horses, conn=conn, race=race, cache=feature_cache)
                tentative = is_tentative(preds)
                horse_by_num = {h["horse_num"]: h for h in horses}
                for pred in preds[:3]:
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
                        "kelly": round(pred.kelly_fraction * 100, 2),
                        "buy": self._is_buy_candidate(pred, horse, tentative),
                    }
                    if pred.rank == 1:
                        prediction_items.append(item)
                    if item["buy"]:
                        buy_candidates.append(item)
                if preds:
                    pred = preds[0]
                    horse = horse_by_num.get(pred.horse_num, {})
                    top_preview.append({
                        "track": track_name(race["track_code"]),
                        "race_num": int(race["race_num"]),
                        "horse_name": horse.get("horse_name") or "",
                        "odds": round((horse.get("win_odds") or 0) / 10.0, 1),
                        "confidence": pred.confidence,
                        "ev": pred.expected_value,
                    })
            backtest = self._recent_backtest(conn, to_date)
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
        if not buy_candidates:
            warnings.append("買い候補なし: EV/信頼度条件を満たすレースは見送り")
        warnings.append("OP/重賞と長距離は継続改善中")
        warnings.append("接戦・混戦は買い対象外")
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
            },
            "buy_candidates": buy_candidates,
            "top_preview": top_preview[:4],
            "backtest": backtest,
            "track_trends": trends,
            "venues": venues,
            "warnings": warnings,
        }

    @_safe
    def fetch_data(self, options: dict | None = None) -> dict:
        """JV-Link 差分取得 → raw 保存 → SQLite 取り込み。"""
        self._set_status("出馬表/結果データを取得中...", "fetch_data", running=True)
        with JVLinkClient() as cli:
            summaries = cli.fetch_all(option=1, dataspecs=["RACE", "HOSE"], on_progress=self._progress)
        self._set_status("DBへ取り込み中...", "ingest", running=True)
        ingest_summary = ingest_all()
        self._set_status("データ取得が完了しました。", "done", running=False)
        return {
            "ok": True,
            "fetch": summaries,
            "ingest": ingest_summary,
        }

    @_safe
    def fetch_odds(self, options: dict | None = None) -> dict:
        options = options or {}
        from_date = (options.get("from_date") or options.get("date") or "").replace("-", "")
        to_date = (options.get("to_date") or options.get("date") or "").replace("-", "")
        with open_db() as conn:
            if not from_date or not to_date:
                row = conn.execute("SELECT MAX(race_year || race_month_day) FROM races").fetchone()
                from_date = to_date = row[0]
            races = list_races(conn, from_date, to_date, jra_only=True)
        self._set_status(f"オッズ取得開始: {len(races)}レース", "fetch_odds", running=True)
        with JVLinkClient() as cli:
            summaries = []
            for i, r in enumerate(races, start=1):
                self._set_status(
                    f"オッズ取得中: {i}/{len(races)} {r['track_code']} {int(r['race_num'])}R",
                    "fetch_odds",
                    {"current": i, "total": len(races)},
                    running=True,
                )
                summaries.append(cli.fetch_realtime("0B31", race_key(dict(r)), on_progress=self._progress))
        self._set_status("オッズをDBへ取り込み中...", "ingest_odds", running=True)
        ingest_summary = ingest_all(force=True, dataspecs=["0B31"])
        self._set_status("オッズ取得が完了しました。", "done", running=False)
        return {"ok": True, "races": len(races), "fetch": summaries, "ingest": ingest_summary}

    @_safe
    def fetch_bloodline(self, options: dict | None = None) -> dict:
        """血統マスタを取得して、父系・母父系特徴量を有効化する。"""
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
        self._set_status("血統データをDBへ取り込み中...", "ingest_bloodline", running=True)
        ingest_summary = ingest_all(dataspecs=["DIFN", "BLOD"])
        with open_db() as conn:
            count = conn.execute("SELECT COUNT(*) FROM horse_masters").fetchone()[0]
        self._set_status(f"血統データ取得が完了しました。horse_masters={count}", "done", running=False)
        return {"ok": True, "horse_masters": count, "fetch": summaries, "ingest": ingest_summary}

    @_safe
    def run_prediction(self, options: dict | None = None) -> dict:
        """DB を読んで予想込み HTML を生成。"""
        options = options or {}
        from_date = (options.get("from_date") or "").replace("-", "") or None
        to_date = (options.get("to_date") or "").replace("-", "") or from_date
        self._set_status("予想HTMLを生成中...", "prediction", running=True)
        path = render(from_date=from_date, to_date=to_date)
        self._set_status("予想生成が完了しました。", "done", running=False)
        return {"ok": True, "message": f"生成: {path}"}

    @_safe
    def publish(self, options: dict | None = None) -> dict:
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
    def open_preview(self, options: dict | None = None) -> dict:
        index = WEB_DIST / "index.html"
        if not index.exists():
            index.write_text(
                "<!doctype html><meta charset='utf-8'>"
                "<h1>プレビュー未生成</h1>"
                "<p>「予想生成」を実行すると HTML がここに作られます。</p>",
                encoding="utf-8",
            )
        preview_url = index.as_uri().replace("&", "&amp;").replace('"', "&quot;")
        webview.windows[0].load_html(
            PREVIEW_HTML.replace("__PREVIEW_URL__", preview_url)
        )
        return {"ok": True}

    @_safe
    def show_control(self, options: dict | None = None) -> dict:
        webview.windows[0].load_html(CONTROL_HTML)
        return {"ok": True}

    @_safe
    def run_all(self, options: dict | None = None) -> dict:
        """① 取得 → ② 予想 → ③ 公開 を一括実行。"""
        self._set_status("一括実行: データ取得中...", "run_all", running=True)
        with JVLinkClient() as cli:
            summaries = cli.fetch_all(option=1, dataspecs=["RACE", "HOSE"], on_progress=self._progress)
        self._set_status("一括実行: DB取り込み中...", "ingest", running=True)
        ingest_summary = ingest_all()
        odds_summary = self.fetch_odds(options)
        options = options or {}
        from_date = (options.get("from_date") or "").replace("-", "") or None
        to_date = (options.get("to_date") or "").replace("-", "") or from_date
        self._set_status("一括実行: 予想生成中...", "prediction", running=True)
        rendered = render(from_date=from_date, to_date=to_date)
        self._set_status("一括実行: 公開中...", "publish", running=True)
        published = publish_to_icloud()
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
    --bg:          #eef0f3;
    --surface:     #f8f9fb;
    --surface-2:   #eceff3;
    --border:      #c7cdd5;
    --border-soft: #d7dce3;
    --text:        #252a31;
    --text-dim:    #59616c;
    --text-mute:   #7d8591;
    --accent:      #6b7280;
    --accent-hi:   #374151;
    --accent-soft: rgba(107,114,128,.12);
    --accent-line: rgba(107,114,128,.35);
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
  /* 左カラム = 既存コントロールパネル。幅固定。広げても膨らまない。 */
  .sidebar {
    flex: 0 0 460px;
    width: 460px;
    padding: .85rem 1rem .9rem;
    border-right: 1px solid var(--border-soft);
    height: 100vh;
    overflow: hidden;
    display: flex;
    flex-direction: column;
  }
  /* 右カラム = 将来のコンテンツ用エリア (予想結果プレビュー等)。 */
  .main {
    flex: 1 1 auto;
    min-width: 0;
    padding: .65rem .85rem;
    height: 100vh;
    overflow: hidden;
  }
  .card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 3px;
    padding: .52rem .62rem;
    margin: 0;
  }
  .card-title {
    font-size: .65rem;
    letter-spacing: .28em;
    text-transform: uppercase;
    color: var(--accent);
    margin-bottom: .26rem;
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
    height: 100%;
    grid-template-rows: auto auto auto minmax(0, 1fr);
  }
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
    font-size: .66rem;
    color: var(--text-mute);
    letter-spacing: .08em;
    text-transform: uppercase;
  }
  .buy-item, .preview-item, .warn-item {
    border-top: 1px solid var(--border-soft);
    padding: .32rem 0;
    min-width: 0;
  }
  .buy-item:first-child, .preview-item:first-child, .warn-item:first-child { border-top: 0; padding-top: 0; }
  .buy-main { font-size: .95rem; font-weight: 700; color: #9f1239; }
  .preview-item strong,
  .buy-main {
    display: block;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .buy-sub, .preview-sub, .warn-item {
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
  .pill.buy { background: #fff1f2; border-color: #fecdd3; color: #9f1239; }
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
  .preview-compact {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: .3rem;
  }
  #previewList .mini-card {
    min-height: 0;
  }
  .dashboard-grid > section:not(.wide):not(.span-2) .preview-compact {
    grid-template-columns: 1fr;
  }
  .preview-compact .mini-card { padding: .32rem .38rem; }
  .main > section.card { display: none; }
  #warnings .warn-item:nth-child(n+4) { display: none; }
  #venues, #trackTrends, #previewList {
    overflow: hidden;
  }
  @media (max-width: 980px) {
    .dashboard-grid { grid-template-columns: 1fr; }
    .span-2 { grid-column: 1 / -1; }
    .metric-row { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  }

  /* ---------- header ---------- */
  header { margin-bottom: .65rem; }
  .brand {
    font-size: 1.05rem;
    font-weight: 500;
    letter-spacing: .32em;
    color: var(--text);
  }
  .brand .ornament {
    color: var(--accent);
    margin-right: .55em;
    font-size: .95em;
  }
  .subtitle {
    font-size: .65rem;
    letter-spacing: .22em;
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
  label {
    display: block;
    font-size: .68rem;
    letter-spacing: .12em;
    color: var(--text-dim);
    margin-bottom: .25rem;
    text-transform: uppercase;
  }
  input[type="date"], input[type="text"] {
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

  /* ---------- status ---------- */
  #status {
    background: var(--surface);
    border: 1px solid var(--border);
    border-left: 2px solid var(--text-mute);
    border-radius: 2px;
    padding: .46rem .65rem;
    margin: .62rem 0 .35rem;
    font-size: .8rem;
    color: var(--text-dim);
    font-variant-numeric: tabular-nums;
    word-break: break-all;
    transition: all .25s ease;
  }
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
  @keyframes pulse {
    0%, 100% { opacity: .25; }
    50%      { opacity: 1; }
  }

  /* ---------- section labels ---------- */
  .section-label {
    font-size: .62rem;
    letter-spacing: .3em;
    color: var(--text-mute);
    text-transform: uppercase;
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
  button .step {
    display: inline-block;
    color: var(--accent);
    margin-right: .65rem;
    font-weight: 500;
    min-width: 1em;
  }
  button.primary {
    background: linear-gradient(180deg, #f3f4f6 0%, #e1e5eb 100%);
    border-color: var(--accent);
    color: var(--accent-hi);
    padding: .68rem .78rem;
    font-size: .88rem;
    letter-spacing: .14em;
    margin: .35rem 0 .5rem;
    text-align: center;
    font-weight: 500;
    text-transform: uppercase;
  }
  button.primary:hover {
    background: linear-gradient(180deg, #e5e7eb 0%, #d1d5db 100%);
    color: #1f2937;
    border-color: var(--accent-hi);
    box-shadow: 0 0 0 1px var(--accent-soft), 0 4px 14px -8px rgba(55,65,81,.35);
  }

  /* ---------- log ---------- */
  #log {
    white-space: pre-wrap;
    word-break: break-all;
    background: var(--log-bg);
    color: var(--log-fg);
    padding: .58rem .7rem;
    border-radius: 3px;
    border: 1px solid var(--border-soft);
    height: 6.4rem;
    min-height: 6.4rem;
    max-height: 6.4rem;
    overflow: hidden;
    font-family: "JetBrains Mono", "Cascadia Code", "Consolas",
                 ui-monospace, monospace;
    font-size: .7rem;
    line-height: 1.42;
    margin: .62rem 0 0;
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
  <div class="subtitle">JV-Link Control · 鈍金 Edition</div>
  <div class="rule"></div>
</header>

<div class="field">
  <label>開催日 (From)</label>
  <input id="from_date" type="date">
</div>
<div class="field">
  <label>開催日 (To)</label>
  <input id="to_date" type="date">
</div>
<div class="field">
  <label>血統取得 開始時刻 (任意)</label>
  <input id="bloodline_fromtime" type="text" placeholder="空欄なら前回以降の差分">
  <div class="hint">例 — 20260501000000</div>
</div>

<div id="status">準備完了。</div>

<button class="primary" data-action="run_all" onclick="run(this.dataset.action)">取得 → 予想 → 公開</button>

<div class="section-label">個別実行</div>
<button data-action="fetch_data" onclick="run(this.dataset.action)"><span class="step">Ⅰ</span>JVLink でデータ取得</button>
<button data-action="fetch_odds" onclick="run(this.dataset.action)"><span class="step">Ⅱ</span>最新オッズ取得</button>
<button data-action="fetch_bloodline" onclick="run(this.dataset.action)"><span class="step">＊</span>血統データ取得</button>
<button data-action="run_prediction" onclick="run(this.dataset.action)"><span class="step">Ⅲ</span>予想生成</button>
<button data-action="publish" onclick="run(this.dataset.action)"><span class="step">Ⅳ</span>iCloud Drive へ公開</button>

<div class="section-label">確認</div>
<button data-action="open_preview" onclick="run(this.dataset.action)"><span class="step">›</span>プレビューを開く</button>
<button data-action="open_icloud_folder" onclick="run(this.dataset.action)"><span class="step">›</span>iCloud 公開先を Explorer で開く</button>

<pre id="log">準備完了。</pre>
</aside>

<main class="main">
  <div class="dashboard-grid">
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
    <section class="card wide">
      <div class="card-title">上位予想プレビュー</div>
      <div id="previewList" class="card-empty">読み込み中...</div>
    </section>
  </div>
  <section class="card">
    <div class="card-title">直近の予想</div>
    <div class="card-empty">予想を実行するとここに概要が表示されます</div>
  </section>
  <section class="card">
    <div class="card-title">取得サマリ</div>
    <div class="card-empty">JVLink 取得結果のグラフ・件数推移などを今後ここに</div>
  </section>
  <section class="card">
    <div class="card-title">バックテスト</div>
    <div class="card-empty">的中率 / 回収率の履歴比較を今後ここに</div>
  </section>
</main>

<script>
  function esc(v) {
    return String(v ?? '').replace(/[&<>"']/g, ch => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    }[ch]));
  }
  function metric(label, value) {
    return '<div class="metric"><div class="num">' + esc(value) + '</div><div class="label">' + esc(label) + '</div></div>';
  }
  function renderDashboard(data) {
    if (!data || !data.ok) return;
    const s = data.summary || {};
    document.getElementById('summary').innerHTML =
      metric('レース', s.races ?? 0) +
      metric('出走頭数', s.horses ?? 0) +
      metric('オッズ', (s.odds ?? 0) + '/' + (s.horses ?? 0)) +
      metric('買い候補', s.buy_count ?? 0);

    const buys = data.buy_candidates || [];
    document.getElementById('buyList').innerHTML = buys.length
      ? buys.map(b =>
          '<div class="buy-item">' +
          '<div class="buy-main">' + esc(b.track) + ' ' + esc(b.race_num) + 'R ' + esc(b.horse_num) + ' ' + esc(b.horse_name) + '</div>' +
          '<div class="buy-sub">' + esc(b.start_time) + ' / ' + esc(b.race_name || '') +
          '<span class="pill buy">' + esc(b.odds) + '倍</span>' +
          '<span class="pill">' + esc(b.popularity) + '人気</span>' +
          '<span class="pill">P ' + esc(b.probability) + '%</span>' +
          '<span class="pill">EV ' + esc(b.ev) + '</span>' +
          '<span class="pill">K ' + esc(b.kelly) + '%</span></div>' +
          '</div>'
        ).join('')
      : '<div class="card-empty">買い候補なし。EV/信頼度条件では見送りです。</div>';

    const bt = data.backtest || {};
    document.getElementById('backtest').innerHTML =
      '<div class="metric-row">' +
      metric('対象', bt.label || '-') +
      metric('単勝', (bt.wins ?? 0) + '/' + (bt.races ?? 0)) +
      metric('3着内', (bt.top3 ?? 0) + '/' + (bt.races ?? 0)) +
      metric('回収率', (bt.return_rate ?? 0) + '%') +
      '</div>';

    const warnings = data.warnings || [];
    document.getElementById('warnings').innerHTML = warnings.length
      ? warnings.map(w => '<div class="warn-item">' + esc(w) + '</div>').join('')
      : '<div class="card-empty">注意点はありません。</div>';

    const venues = data.venues || [];
    document.getElementById('venues').innerHTML = venues.length
      ? '<div class="compact-grid">' + venues.map(v =>
          '<div class="mini-card venue-card" data-track="' + esc(v.track) + '" data-lat="' + esc(v.lat) + '" data-lon="' + esc(v.lon) + '">' +
          '<div class="mini-title">' + esc(v.track) + ' <span class="pill">' + esc(v.races) + 'R</span></div>' +
          '<div class="mini-line">' + esc(v.surfaces) + '</div>' +
          '<div class="mini-line weather-line">天候 ' + esc(v.weather) + ' / 芝 ' + esc(v.turf) + ' / ダ ' + esc(v.dirt) + '</div>' +
          '</div>'
        ).join('') + '</div>'
      : '<div class="card-empty">開催情報がありません。</div>';
    updateVenueWeather();

    const trends = data.track_trends || [];
    document.getElementById('trackTrends').innerHTML = trends.length
      ? '<div class="compact-grid">' + trends.map(t =>
          '<div class="mini-card">' +
          '<div class="mini-title">' + esc(t.track) + ' <span class="pill">3着内 ' + esc(t.top3_samples) + '</span></div>' +
          '<div class="mini-line">' + esc(t.surface) + ' / ' + esc(t.leg) + ' / ' + esc(t.gate) + '</div>' +
          '<div class="mini-line">' + esc(t.note) + '</div>' +
          '</div>'
        ).join('') + '</div>'
      : '<div class="card-empty">確定済みの当日結果がまだ少なく、傾向は表示できません。</div>';

    const preview = data.top_preview || [];
    document.getElementById('previewList').innerHTML = preview.length
      ? '<div class="preview-compact">' + preview.map(p =>
          '<div class="mini-card">' +
          '<div class="mini-title">' + esc(p.track) + ' ' + esc(p.race_num) + 'R</div>' +
          '<div class="mini-line">' + esc(p.horse_name) + '</div>' +
          '<div class="mini-line">' + esc(p.odds) + '倍 / ' + esc(p.confidence) + ' / EV ' + esc(p.ev) + '</div>' +
          '</div>'
        ).join('') + '</div>'
      : '<div class="card-empty">予想データがありません。</div>';
  }
  async function refreshDashboard() {
    if (!window.pywebview || !window.pywebview.api || !window.pywebview.api.get_dashboard) return;
    try {
      const data = await window.pywebview.api.get_dashboard(options());
      renderDashboard(data);
    } catch (e) {
      document.getElementById('summary').innerHTML = '<div class="card-empty">ダッシュボード取得エラー: ' + esc(e) + '</div>';
    }
  }
  function weatherText(code) {
    const m = {0:'晴', 1:'晴', 2:'曇', 3:'曇', 45:'霧', 48:'霧', 51:'霧雨', 53:'霧雨', 55:'霧雨', 61:'雨', 63:'雨', 65:'強雨', 71:'雪', 73:'雪', 75:'大雪', 80:'にわか雨', 81:'にわか雨', 82:'強雨', 95:'雷雨'};
    return m[code] || '天候取得';
  }
  async function updateVenueWeather() {
    const cards = Array.from(document.querySelectorAll('.venue-card'));
    for (const card of cards) {
      const lat = card.dataset.lat;
      const lon = card.dataset.lon;
      const line = card.querySelector('.weather-line');
      if (!lat || !lon || lat === 'None' || lon === 'None' || !line) continue;
      try {
        let cur = null;
        if (window.pywebview && window.pywebview.api && window.pywebview.api.get_weather) {
          const py = await window.pywebview.api.get_weather({lat, lon});
          if (py && py.ok) cur = {weather_code: py.weather_code, temperature_2m: py.temperature, precipitation: py.precipitation};
        }
        if (!cur) {
          const url = 'https://api.open-meteo.com/v1/forecast?latitude=' + encodeURIComponent(lat) +
            '&longitude=' + encodeURIComponent(lon) + '&current=weather_code,temperature_2m,precipitation';
          const res = await fetch(url);
          if (!res.ok) continue;
          const data = await res.json();
          cur = data.current || {};
        }
        const w = weatherText(cur.weather_code);
        const temp = cur.temperature_2m == null ? '-' : Math.round(cur.temperature_2m) + '℃';
        const rain = cur.precipitation == null ? '-' : cur.precipitation + 'mm';
        line.textContent = '現在 ' + w + ' / ' + temp + ' / 降水 ' + rain;
      } catch (_e) {
        // Network/weather fallback: keep JV-Data weather line.
      }
    }
  }
  function options() {
    return {
      from_date: document.getElementById('from_date').value,
      to_date: document.getElementById('to_date').value,
      bloodline_fromtime: document.getElementById('bloodline_fromtime').value
    };
  }
  function setActionButtonsDisabled(disabled) {
    document.querySelectorAll('.sidebar button[data-action]').forEach(button => {
      button.disabled = disabled;
    });
  }
  function applyStatus(st) {
    const box = document.getElementById('status');
    box.textContent = '[' + st.updated_at + '] ' + st.message;
    box.className = st.running ? 'running' : '';
    setActionButtonsDisabled(Boolean(st.running));
    return Boolean(st.running);
  }
  async function refreshStatus() {
    const box = document.getElementById('status');
    // pywebview の JS ブリッジ注入前に呼ばれることがあるのでガード
    if (!window.pywebview || !window.pywebview.api || !window.pywebview.api.get_status) {
      return false;
    }
    try {
      const st = await window.pywebview.api.get_status({});
      return applyStatus(st);
    } catch (e) {
      box.textContent = '進捗取得エラー: ' + e;
      return false;
    }
  }
  async function run(method) {
    const log = document.getElementById('log');
    if (await refreshStatus()) {
      log.textContent = '別の処理が実行中です。完了後に再実行してください。';
      return;
    }
    setActionButtonsDisabled(true);
    log.textContent = method + ' 実行中…';
    let timer = setInterval(refreshStatus, 1000);
    refreshStatus();
    try {
      const res = await window.pywebview.api[method](options());
      clearInterval(timer);
      await refreshStatus();
      refreshDashboard();
      log.textContent = JSON.stringify(res, null, 2);
    } catch (e) {
      clearInterval(timer);
      await refreshStatus();
      log.textContent = 'エラー: ' + e;
    } finally {
      if (!(await refreshStatus())) {
        setActionButtonsDisabled(false);
      }
    }
  }
  // pywebview の JS ブリッジが準備できてから初回の進捗取得を行う
  window.addEventListener('pywebviewready', () => { refreshStatus(); refreshDashboard(); });
  // 既に準備済みなら即時実行 (リロード時など)
  if (window.pywebview && window.pywebview.api) { refreshStatus(); refreshDashboard(); }
  document.getElementById('from_date').addEventListener('change', refreshDashboard);
  document.getElementById('to_date').addEventListener('change', refreshDashboard);
</script>
</body>
</html>
"""


PREVIEW_HTML = """<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>予想プレビュー</title>
<style>
  :root {
    --bg: #eef0f3;
    --surface: #f8f9fb;
    --border: #c7cdd5;
    --text: #252a31;
    --text-dim: #59616c;
    --accent: #374151;
  }
  * { box-sizing: border-box; }
  html, body {
    margin: 0;
    width: 100%;
    height: 100%;
    overflow: hidden;
    background: var(--bg);
    color: var(--text);
    font-family: "Yu Gothic UI", "Meiryo", system-ui, sans-serif;
  }
  .bar {
    height: 42px;
    display: flex;
    align-items: center;
    gap: .75rem;
    padding: 0 .75rem;
    background: var(--surface);
    border-bottom: 1px solid var(--border);
  }
  button {
    height: 28px;
    border: 1px solid var(--border);
    border-radius: 3px;
    background: #eceff3;
    color: var(--text);
    padding: 0 .75rem;
    font: inherit;
    cursor: pointer;
  }
  button:hover {
    background: #e1e5eb;
    color: var(--accent);
  }
  .title {
    font-size: .82rem;
    color: var(--text-dim);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  iframe {
    width: 100%;
    height: calc(100% - 42px);
    border: 0;
    display: block;
    background: white;
  }
</style>
</head>
<body>
  <div class="bar">
    <button type="button" onclick="window.pywebview.api.show_control()">操作画面に戻る</button>
    <div class="title">予想プレビュー</div>
  </div>
  <iframe src="__PREVIEW_URL__"></iframe>
</body>
</html>
"""


def main() -> None:
    print("[gui.app] creating window...", flush=True)
    api = Api()
    webview.create_window(
        title="競馬予想",
        html=CONTROL_HTML,
        js_api=api,
        width=1100,
        height=780,
        x=80,
        y=60,
        on_top=False,
        background_color="#eef0f3",
    )
    print("[gui.app] starting event loop...", flush=True)
    webview.start()
    print("[gui.app] event loop ended", flush=True)


if __name__ == "__main__":
    main()
