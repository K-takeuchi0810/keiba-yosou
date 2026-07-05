"""ページのコンテキスト構築 + Jinja2 レンダリング (HTTP 層から分離、単体テスト可能)。

server.py はこのモジュールの render_* を呼ぶだけ。DB 接続を引数で受けるので、
in-memory DB を渡してテストできる。
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from predictor.sire_lines import classify_sire, line_color, line_label_short
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

# build_race が horse_masters から引く血統列 (probe で欠如列は NULL 縮退)。
_MASTER_COLS = ("sire_name", "sire_breeding_num", "dam_sire_name", "dam_sire_breeding_num",
                "sire_dam_sire_name", "sire_dam_sire_breeding_num",
                "dam_dam_sire_name", "dam_dam_sire_breeding_num")
# 旧スキーマ警告はプロセス内で列セットごとに 1 回だけ (リクエスト毎のログスパム防止)
_warned_missing_cols: set[tuple] = set()


def _warn_once_missing_cols(missing: tuple) -> None:
    if missing not in _warned_missing_cols:
        _warned_missing_cols.add(missing)
        logger.warning("horse_masters に旧スキーマ列欠如 %s: 該当血統項目は縮退表示", list(missing))


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


def _horse_detail_line(h: dict, feat: dict, recent: list[dict], cur_distance: int | None,
                       corner_env: bool = False) -> dict:
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
    # 距離変更 (前走比)。符号重複 ("短縮-200m") を避け絶対値表記にする
    dist_change = "-"
    if recent and cur_distance and recent[0]["dist"]:
        delta = cur_distance - recent[0]["dist"]
        dist_change = "同距離" if delta == 0 else (f"延長+{delta}m" if delta > 0 else f"短縮{abs(delta)}m")
    # 父×馬場適性 (Share 相当)。n<10 非表示、10<=n<30 は括弧書き=標本少の参考値
    # (2026-07-05 収益性監査: 低 n 帯の過信抑止)。
    # "-" (データ無) と「n<10 につき抑制」を区別する (凡例の -=データ無 と意味衝突しない)
    apt = "-"
    rate, n = feat.get("sire_surface_top3_rate"), feat.get("sire_surface_samples") or 0
    if rate is not None and n >= 30:
        apt = f"{rate * 100:.0f}%(n={n})"
    elif rate is not None and n >= 10:
        apt = f"({rate * 100:.0f}%,n={n})"
    elif rate is not None and n > 0:
        apt = "(n<10)"
    # 先行力 (テンP 相当)。corner データは probe 緑化 + backfill 後にのみ存在するため、
    # samples>0 のときだけ表示 = hard gate クリア後に自動で有効化される安全設計。
    # corner_env=True (DB に corner データあり) で当該馬だけ履歴が無い場合は
    # 「4角-」を出し、未整備との区別をつける (凡例 -=データ無 と一貫)。
    pace = None
    c_n = feat.get("recent_4corner_samples") or 0
    c_avg = feat.get("recent_4corner_avg_position")
    c_chg = feat.get("recent_4corner_position_change")
    if c_n > 0 and c_avg is not None:
        chg = f"/上げ{c_chg:+.1f}" if c_chg is not None else ""
        pace = f"4角avg{c_avg:.1f}{chg}(n={c_n})"
    elif corner_env:
        pace = "4角-"
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

    # 血統マスタ (系統色分け用)。列は PRAGMA で probe し、無い列は NULL を選ぶ
    # (旧 DB 縮退。readonly 接続は migration を走らせないため。try/except の
    # 二重 SQL 記述を廃し単一出典化 — 2026-07-05 code-quality 監査提案)。
    brns = [h.get("blood_register_num") for h in horses if h.get("blood_register_num")]
    masters: dict[str, sqlite3.Row] = {}
    if brns:
        have = {r["name"] for r in conn.execute("PRAGMA table_info(horse_masters)").fetchall()}
        missing = [c for c in _MASTER_COLS if c not in have]
        if missing:
            _warn_once_missing_cols(tuple(missing))
        sel = ", ".join(c if c in have else f"NULL AS {c}" for c in _MASTER_COLS)
        q = ",".join("?" * len(brns))
        for m in conn.execute(
            f"SELECT blood_register_num, {sel} FROM horse_masters "
            f"WHERE blood_register_num IN ({q})", brns
        ).fetchall():
            masters[m["blood_register_num"]] = m

    # 祖先の産地 (HN 繁殖馬マスタの産地名)。BLOD 未取込 / 旧スキーマなら空 dict に縮退。
    origins: dict[str, str] = {}
    anc_bns = {bn for m in masters.values()
               for bn in (m["sire_breeding_num"], m["dam_sire_breeding_num"],
                          m["sire_dam_sire_breeding_num"], m["dam_dam_sire_breeding_num"])
               if bn}
    if anc_bns:
        try:
            qb = ",".join("?" * len(anc_bns))
            origins = {r["breeding_num"]: (r["birthplace"] or "").strip()
                       for r in conn.execute(
                           f"SELECT breeding_num, birthplace FROM breeding_horses "
                           f"WHERE breeding_num IN ({qb})", sorted(anc_bns)).fetchall()
                       if (r["birthplace"] or "").strip()}
        except sqlite3.OperationalError as e:
            # 縮退はテーブル/列欠如 (BLOD 未取込・旧スキーマ) のみ。ロック/破損を
            # 「産地なし」と誤分類しない (masters probe と同規律 — 2026-07-05 監査)。
            if "no such table" not in str(e) and "no such column" not in str(e):
                raise
            logger.warning("祖先産地を非表示に縮退: %s", e)
            origins = {}

    before_date = date  # YYYYMMDD (features の _date_key と同じ連結規約)
    # DB に corner データが存在するか (run 単位フラグ、features の _cached キーを参照)
    corner_env = bool(feature_cache.get(("_corner_data_present",), False))
    # 同日同場の前後 R (1 日巡回タスクの導線。fable gui-ux 指摘)
    sibling_nums = [r["race_num"] for r in conn.execute(
        """SELECT race_num FROM races WHERE race_year=? AND race_month_day=?
           AND track_code=? AND kaiji=? AND nichiji=?
           ORDER BY CAST(race_num AS INTEGER)""",
        (date[:4], date[4:], track, kaiji, nichiji)).fetchall()]
    idx = sibling_nums.index(num) if num in sibling_nums else -1
    nav = {
        "prev": sibling_nums[idx - 1] if idx > 0 else None,
        "next": sibling_nums[idx + 1] if 0 <= idx < len(sibling_nums) - 1 else None,
        "date": date, "track": track, "kaiji": kaiji, "nichiji": nichiji,
    }
    def _ped_extra(name: str, bn: str | None) -> str | None:
        """父母父/母母父の補助表示「名前(系統短/産地)」。名前が無ければ None。"""
        if not name:
            return None
        k = classify_sire(name, conn=conn, sire_breeding_num=bn)
        parts = line_label_short(k)
        org = origins.get(bn or "")
        if org:
            parts += f"/{org}"
        return f"{name}({parts})"

    rows = []
    for h in horses:
        m = masters.get(h.get("blood_register_num"))
        sire = m["sire_name"] if m else ""
        sire_bn = m["sire_breeding_num"] if m else None
        dam_sire = m["dam_sire_name"] if m else ""
        dam_sire_bn = m["dam_sire_breeding_num"] if m else None
        sds = m["sire_dam_sire_name"] if m else ""          # 父母父
        sds_bn = m["sire_dam_sire_breeding_num"] if m else None
        dds = m["dam_dam_sire_name"] if m else ""           # 母母父
        dds_bn = m["dam_dam_sire_breeding_num"] if m else None
        lk = classify_sire(sire, conn=conn, sire_breeding_num=sire_bn)
        # 母父系統 (SmartRC 同様の 2 段表示用)。dam_sire_breeding_num は母父自身の
        # 繁殖番号なので、そこから父系遡上すれば母父の大系統が引ける。
        dlk = classify_sire(dam_sire, conn=conn, sire_breeding_num=dam_sire_bn)
        # 父母父・母母父 (3 代血統) は補助行に「名前(系統/産地)」で出す
        sds_disp, dds_disp = _ped_extra(sds, sds_bn), _ped_extra(dds, dds_bn)
        ped_parts = [p for p in (
            f"父母父 {sds_disp}" if sds_disp else None,
            f"母母父 {dds_disp}" if dds_disp else None,
        ) if p]
        odds = h.get("win_odds")
        feat = feats.get(h.get("horse_num") or "", {})
        recent = _recent_form(conn, h.get("blood_register_num"), before_date)
        rows.append({
            "waku": h.get("waku_num"), "horse_num": h.get("horse_num"),
            "horse_name": h.get("horse_name") or "",
            "line_color": line_color(lk),
            "line_short": line_label_short(lk),
            "dam_line_color": line_color(dlk),
            "dam_line_short": line_label_short(dlk),
            "sire": sire, "dam_sire": dam_sire,
            "sire_origin": origins.get(sire_bn or ""),
            "dam_sire_origin": origins.get(dam_sire_bn or ""),
            "ped_parts": ped_parts,
            "jockey": h.get("jockey_short_name") or h.get("jockey_code") or "",
            "popularity": h.get("win_popularity"),
            "odds": (round(odds / 10, 1) if odds else None),
            "mark": marks.get(h.get("horse_num"), ""),
            "detail": _horse_detail_line(h, feat, recent, race.get("distance"), corner_env),
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
        "nav": nav,
        "horses": rows,
    }


def render_race(conn, date, track, kaiji, nichiji, num) -> str | None:
    ctx = build_race(conn, date, track, kaiji, nichiji, num)
    if ctx is None:
        return None
    # タブ識別できるよう場名+R をタイトルに (2026-07-05 fable gui-ux 指摘)
    title = f"{ctx['race']['track_name']}{ctx['race']['race_num_int']}R"
    return _env.get_template("race.html.j2").render(title=title, **ctx)


def render_error(title: str, message: str, status_note: str = "") -> str:
    """エラーページも base テンプレート経由で描画 (viewport/44pt/dark を適用)。

    生 HTML だと iPhone で 980px 仮想幅になり戻り導線が極小タップになる
    (2026-07-05 fable gui-ux 指摘)。
    """
    return _env.get_template("error.html.j2").render(
        title=title, heading=title, message=message, status_note=status_note)


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
