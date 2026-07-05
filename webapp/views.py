"""ページのコンテキスト構築 + Jinja2 レンダリング (HTTP 層から分離、単体テスト可能)。

server.py はこのモジュールの render_* を呼ぶだけ。DB 接続を引数で受けるので、
in-memory DB を渡してテストできる。
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from predictor.sire_lines import classify_sire, line_color, line_label
from web.codes import burden_weight_kg, ground_name, track_name, track_type, weather_name
from webapp import aggregate as agg
from webapp.aggregate import jra_track_clause

logger = logging.getLogger(__name__)

_TEMPLATES = Path(__file__).resolve().parent / "templates"
_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATES)),
    autoescape=select_autoescape(["html", "j2"]),
)

_SURFACE_LABEL = {"turf": "芝", "dirt": "ダート", "jump": "障害", "other": "他"}


def _surface_label(s: str) -> str:
    return _SURFACE_LABEL.get(s, s)


# ---------------------------------------------------------------------------
# / (開催日一覧)
# ---------------------------------------------------------------------------
def build_index(conn, limit_days: int = 40) -> dict:
    rows = conn.execute(
        f"""
        SELECT race_year, race_month_day, track_code, kaiji, nichiji, race_num
        FROM races
        WHERE {jra_track_clause()}
        ORDER BY race_year DESC, race_month_day DESC, track_code, CAST(race_num AS INTEGER)
        """
    ).fetchall()
    days: dict[str, dict] = {}
    for r in rows:
        date = f"{r['race_year']}{r['race_month_day']}"
        d = days.setdefault(date, {"date": date, "races": [], "track_set": set()})
        d["track_set"].add(r["track_code"])
        d["races"].append({
            "track_code": r["track_code"], "track_name": track_name(r["track_code"]),
            "kaiji": r["kaiji"], "nichiji": r["nichiji"], "race_num": r["race_num"],
            "race_num_int": int(r["race_num"]) if str(r["race_num"]).isdigit() else r["race_num"],
        })
    out = []
    for date in list(days)[:limit_days]:
        d = days[date]
        out.append({
            "date": date,
            "label": f"{date[:4]}/{date[4:6]}/{date[6:8]}",
            "n_races": len(d["races"]),
            "tracks": "・".join(track_name(t) for t in sorted(d["track_set"])),
            "races": d["races"],
        })
    return {"dates": out}


def render_index(conn) -> str:
    ctx = build_index(conn)
    return _env.get_template("index.html.j2").render(title="開催", **ctx)


# ---------------------------------------------------------------------------
# /race (出馬表 + 系統色分け + 予想)
# ---------------------------------------------------------------------------
_LEG_NAMES = {"1": "逃", "2": "先", "3": "差", "4": "追"}


def _recent_form(conn, blood_register_num: str | None, before_date: str) -> list[dict]:
    """直近 3 走の (着順, 距離)。before_date 未満のみ (リーク防止、features と同規律)。"""
    if not blood_register_num:
        return []
    rows = conn.execute(
        """
        SELECT hr.confirmed_order AS ord, r.distance AS dist
        FROM horse_races hr
        JOIN races r
          ON r.race_year=hr.race_year AND r.race_month_day=hr.race_month_day
         AND r.track_code=hr.track_code AND r.kaiji=hr.kaiji
         AND r.nichiji=hr.nichiji AND r.race_num=hr.race_num
        WHERE hr.blood_register_num = ?
          AND (hr.race_year || hr.race_month_day) < ?
          AND hr.confirmed_order IS NOT NULL AND hr.confirmed_order > 0
        ORDER BY (hr.race_year || hr.race_month_day) DESC
        LIMIT 3
        """,
        (blood_register_num, before_date),
    ).fetchall()
    return [{"ord": r["ord"], "dist": r["dist"]} for r in rows]


def _horse_detail_line(h: dict, feat: dict, recent: list[dict], cur_distance: int | None) -> dict:
    """出馬表サブ行 (SmartRC 的な補助指標)。features 計算済みの値を表示に流用する。"""
    # 脚質 (公式が空なら推定値に ※)
    leg = _LEG_NAMES.get((h.get("leg_quality_code") or "").strip(), "")
    if not leg:
        est = _LEG_NAMES.get((feat.get("estimated_leg_code") or "").strip(), "")
        leg = f"{est}※" if est else "-"
    # 馬体重 (999=計量不能, 000=取消)。非数字混入でもページを 500 にしない。
    hw = (h.get("horse_weight") or "").strip()
    if hw.isdigit() and hw not in ("999", "000"):
        sign = (h.get("weight_change_sign") or "").strip()
        diff = (h.get("weight_change_diff") or "").strip().lstrip("0") or "0"
        weight = f"{int(hw)}" + (f"({sign}{diff})" if sign in ("+", "-") and diff != "0" else "")
    else:
        weight = "-"
    # 近3走着順 (新しい順)
    recent3 = "-".join(str(r["ord"]) for r in recent) if recent else "-"
    # 上がりT (直近の補正なし最速上がり3F, 0.1 秒単位)
    b3f = feat.get("best_final_3f")
    agari = f"{b3f / 10:.1f}" if b3f else "-"
    # 出走間隔
    days = feat.get("days_since_last")
    rest = (f"休み明け({days}日)" if days and days >= 90 else f"間隔{days}日" if days else "-")
    # 距離変更 (前走比)
    dist_change = "-"
    if recent and cur_distance and recent[0]["dist"]:
        delta = cur_distance - recent[0]["dist"]
        dist_change = "同距離" if delta == 0 else (f"延長+{delta}m" if delta > 0 else f"短縮{delta}m")
    # 父×馬場適性 (Share 相当)。n<10 非表示、10<=n<30 は括弧書き=標本少の参考値
    # (2026-07-05 収益性監査: 低 n 帯の過信抑止)。
    apt = "-"
    rate, n = feat.get("sire_surface_top3_rate"), feat.get("sire_surface_samples") or 0
    if rate is not None and n >= 30:
        apt = f"{rate * 100:.0f}%(n={n})"
    elif rate is not None and n >= 10:
        apt = f"({rate * 100:.0f}%,n={n})"
    # 先行力 (テンP 相当)。corner データは probe 緑化 + backfill 後にのみ存在するため、
    # samples>0 のときだけ表示 = hard gate クリア後に自動で有効化される安全設計。
    pace = None
    c_n = feat.get("recent_4corner_samples") or 0
    c_avg = feat.get("recent_4corner_avg_position")
    c_chg = feat.get("recent_4corner_position_change")
    if c_n > 0 and c_avg is not None:
        chg = f"/上げ{c_chg:+.1f}" if c_chg is not None else ""
        pace = f"4角avg{c_avg:.1f}{chg}(n={c_n})"
    detail = {
        "burden": burden_weight_kg(h.get("burden_weight") or 0) or "-",
        "weight": weight, "leg": leg, "recent3": recent3, "agari_t": agari,
        "rest": rest, "dist_change": dist_change, "sire_apt": apt, "pace": pace,
    }
    # 全項目データ無しなら 1 語に畳む ("-" の羅列は壊れて見える — gui-ux 監査指摘)
    detail["empty"] = all(
        v in ("-", None) for k, v in detail.items() if k != "pace"
    ) and pace is None
    return detail


def build_race(conn, date: str, track: str, kaiji: str, nichiji: str, num: str) -> dict | None:
    race = conn.execute(
        """SELECT * FROM races WHERE race_year=? AND race_month_day=? AND track_code=?
           AND kaiji=? AND nichiji=? AND race_num=?""",
        (date[:4], date[4:], track, kaiji, nichiji, num),
    ).fetchone()
    if race is None:
        return None
    race = dict(race)
    from scripts.backtest import horses_for_race
    horses = horses_for_race(conn, race)

    # 特徴量 (表示用: 上がりT/脚質/間隔/父適性)。cache は予想と共有し再計算を防ぐ。
    # 落ちても出馬表は出す (最小スキーマの DB や欠損データへの耐性)。
    feature_cache: dict = {}
    feats: dict[str, dict] = {}
    for h in horses:
        try:
            from predictor.features import compute_features
            feats[h.get("horse_num") or ""] = compute_features(conn, h, race, cache=feature_cache)
        except Exception as e:  # noqa: BLE001
            logger.warning("compute_features failed for %s%s R%s 馬%s: %s",
                           date, track, num, h.get("horse_num"), e)
            feats[h.get("horse_num") or ""] = {}

    # 予想 (診断用)。落ちても出馬表は出す。
    marks: dict[str, str] = {}
    try:
        from predictor.rules import predict_race
        preds = predict_race(horses, conn=conn, race=race, cache=feature_cache)
        for p in preds:
            marks[p.horse_num] = getattr(p, "mark", "") or ""
    except Exception as e:  # noqa: BLE001 — 予想失敗時も出馬表は表示する
        logger.warning("predict_race failed for %s%s R%s: %s", date, track, num, e)
        marks = {}

    # 血統マスタ (系統色分け用)
    brns = [h.get("blood_register_num") for h in horses if h.get("blood_register_num")]
    masters: dict[str, sqlite3.Row] = {}
    if brns:
        q = ",".join("?" * len(brns))
        for m in conn.execute(
            f"SELECT blood_register_num, sire_name, sire_breeding_num, dam_sire_name "
            f"FROM horse_masters WHERE blood_register_num IN ({q})", brns
        ).fetchall():
            masters[m["blood_register_num"]] = m

    before_date = date  # YYYYMMDD (features の _date_key と同じ連結規約)
    rows = []
    for h in horses:
        m = masters.get(h.get("blood_register_num"))
        sire = m["sire_name"] if m else ""
        sire_bn = m["sire_breeding_num"] if m else None
        dam_sire = m["dam_sire_name"] if m else ""
        lk = classify_sire(sire, conn=conn, sire_breeding_num=sire_bn)
        odds = h.get("win_odds")
        feat = feats.get(h.get("horse_num") or "", {})
        recent = _recent_form(conn, h.get("blood_register_num"), before_date)
        rows.append({
            "waku": h.get("waku_num"), "horse_num": h.get("horse_num"),
            "horse_name": h.get("horse_name") or "",
            "line_label": line_label(lk), "line_color": line_color(lk),
            "sire": sire, "dam_sire": dam_sire,
            "jockey": h.get("jockey_short_name") or h.get("jockey_code") or "",
            "popularity": h.get("win_popularity"),
            "odds": (round(odds / 10, 1) if odds else None),
            "mark": marks.get(h.get("horse_num"), ""),
            "detail": _horse_detail_line(h, feat, recent, race.get("distance")),
        })

    surf = agg.surface_of(race.get("track_type_code"))
    return {
        "race": {
            "track_name": track_name(track),
            "race_num_int": int(num) if str(num).isdigit() else num,
            "date_label": f"{date[:4]}/{date[4:6]}/{date[6:8]}",
            "name": race.get("race_name") or "",
            "surface_label": _surface_label(surf),
            "distance": race.get("distance") or "",
            "weather": weather_name(race.get("weather_code") or ""),
            "going": ground_name(race.get("turf_condition") if surf == "turf"
                                 else race.get("dirt_condition") or ""),
            "starter_count": race.get("starter_count") or len(horses),
        },
        "horses": rows,
    }


def render_race(conn, date, track, kaiji, nichiji, num) -> str | None:
    ctx = build_race(conn, date, track, kaiji, nichiji, num)
    if ctx is None:
        return None
    return _env.get_template("race.html.j2").render(title="出馬表", **ctx)


# ---------------------------------------------------------------------------
# /trends (傾向集計)
# ---------------------------------------------------------------------------
def build_trends(conn, from_date: str, to_date: str, course: str | None,
                 factor: str, min_n: int = 30) -> dict:
    courses_raw = agg.list_courses(conn, from_date, to_date)
    # course = "track|surface|distance"
    sel = course or (f"{courses_raw[0]['track_code']}|{courses_raw[0]['surface']}|{courses_raw[0]['distance']}"
                     if courses_raw else None)
    courses = [{
        "track_code": c["track_code"], "track_name": c["track_name"],
        "surface": c["surface"], "surface_label": _surface_label(c["surface"]),
        "distance": c["distance"], "n_races": c["n_races"],
        "selected": (f"{c['track_code']}|{c['surface']}|{c['distance']}" == sel),
    } for c in courses_raw]
    factors = [{"key": k, "label": v, "selected": (k == factor)} for k, v in agg.FACTORS.items()]

    result = None
    if sel:
        tc, surf, dist = sel.split("|")
        r = agg.aggregate_course(conn, tc, surf, int(dist), factor, from_date, to_date, min_n=min_n)
        r["surface_label"] = _surface_label(r["surface"])
        result = r
    return {"courses": courses, "factors": factors, "result": result}


def render_trends(conn, from_date, to_date, course, factor, min_n=30) -> str:
    ctx = build_trends(conn, from_date, to_date, course, factor, min_n)
    return _env.get_template("trends.html.j2").render(title="傾向集計", **ctx)


# ---------------------------------------------------------------------------
# /today (当日傾向速報)
# ---------------------------------------------------------------------------
def build_today(conn, date: str, factor: str = "waku") -> dict:
    result = agg.today_trends(conn, date, factor)
    factors = [{"key": k, "label": v, "selected": (k == factor)}
               for k, v in (("waku", "枠番"), ("sire_line", "父系統"), ("leg", "脚質"))]
    return {
        "date": date, "date_label": f"{date[:4]}/{date[4:6]}/{date[6:8]}",
        "factors": factors, "result": result,
    }


def render_today(conn, date, factor="waku") -> str:
    ctx = build_today(conn, date, factor)
    return _env.get_template("today.html.j2").render(title="当日速報", **ctx)
