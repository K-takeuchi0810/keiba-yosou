"""SQLite から開催・レース・出走馬を引いて web/dist/index.html を生成する。"""

from __future__ import annotations

import shutil
import sys
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import BUY_FILTER_DEFAULT, ICLOUD_PUBLISH_DIR, WEB_DIST, is_whitelisted_race
from db import open_db
from predictor import is_tentative, predict_race
from web.codes import (
    grade_name,
    ground_name,
    race_id_to_date,
    sex_name,
    time_hhmm,
    track_name,
    track_type,
    weather_name,
    weekday_name,
    burden_weight_kg,
)

TEMPLATES = Path(__file__).resolve().parent / "templates"

# 買い目フィルタの既定値は `config.BUY_FILTER_DEFAULT` が唯一の出典。
# 既存コード (gui / backtest 等) が `BET_MIN_*` を import している関係で、
# シンボル名はそのまま残し、実体を config からたどる薄いシムにしている。
BET_MIN_ODDS: float = float(BUY_FILTER_DEFAULT["min_odds"])
BET_MAX_ODDS: float = float(BUY_FILTER_DEFAULT["max_odds"])
# None なら「制約なし」を意味するため、それぞれ -inf へフォールバック (>= 比較で常に True)
_mv = BUY_FILTER_DEFAULT.get("min_value")
BET_MIN_VALUE: float = float(_mv) if _mv is not None else float("-inf")
_me = BUY_FILTER_DEFAULT.get("min_ev")
BET_MIN_EV: float = float(_me) if _me is not None else float("-inf")
BET_MAX_ODDS_AGE_MIN: int = int(BUY_FILTER_DEFAULT["max_odds_age_min"])


def _surface_class(t: str) -> str:
    return {"芝": "turf", "ダート": "dirt", "障害": "jump"}.get(t, "")


def build_view_model(from_date: str | None = None, to_date: str | None = None) -> dict:
    """DB → テンプレートに渡す dict 構造。

    過去走の予想根拠用データは別ロジックで参照する想定で、
    ここでは表示対象を直近 ±14 日に絞り、HTML を実用サイズに保つ。
    """
    from datetime import datetime, timedelta

    today = datetime.now().date()
    from_d = from_date or (today - timedelta(days=14)).strftime("%Y%m%d")
    to_d = to_date or (today + timedelta(days=14)).strftime("%Y%m%d")
    from_y, from_md = from_d[:4], from_d[4:]
    to_y, to_md = to_d[:4], to_d[4:]

    with open_db() as conn:
        races = conn.execute(
            """
            SELECT * FROM races
            WHERE (race_year || race_month_day) BETWEEN ? AND ?
            ORDER BY race_year, race_month_day, track_code, race_num
            """,
            (from_y + from_md, to_y + to_md),
        ).fetchall()
        horse_rows = conn.execute(
            """
            SELECT * FROM horse_races
            WHERE (race_year || race_month_day) BETWEEN ? AND ?
            ORDER BY race_year, race_month_day, track_code, race_num,
                     CAST(horse_num AS INTEGER)
            """,
            (from_y + from_md, to_y + to_md),
        ).fetchall()

    # race_id ごとに raw 行をまとめる（予想スコアリングで全フィールドが必要）
    raw_horses_by_race: dict[tuple, list[dict]] = {}
    for h in horse_rows:
        key = (
            h["race_year"], h["race_month_day"], h["track_code"],
            h["kaiji"], h["nichiji"], h["race_num"],
        )
        raw_horses_by_race.setdefault(key, []).append(dict(h))

    # 予想を計算し馬番→印 のマップを作る（過去走ベース・本格版）
    horses_by_race: dict[tuple, list] = {}
    top_picks_by_race: dict[tuple, list] = {}
    tentative_by_race: dict[tuple, bool] = {}
    # race_key → race dict のマップ（特徴量計算で必要）
    race_by_key: dict[tuple, dict] = {}
    with open_db() as conn:
        feature_cache: dict = {}
        for r in races:
            k = (r["race_year"], r["race_month_day"], r["track_code"],
                 r["kaiji"], r["nichiji"], r["race_num"])
            race_by_key[k] = dict(r)

        for key, raws in raw_horses_by_race.items():
            race_dict = race_by_key.get(key, {})
            # horse_num が "00" / "" の行は出馬表未確定のプレースホルダ。
            # 残すと HTML に「0」が並び、予想ロジックも無意味な行を含めて
            # スコアリングしてしまうため、ここで弾く。
            raws = [
                h for h in raws
                if (h.get("horse_num") or "").strip() not in ("", "00")
            ]
            if not raws:
                continue
            preds = predict_race(raws, conn=conn, race=race_dict, cache=feature_cache)
            mark_by_num = {p.horse_num: p for p in preds}
            tentative_by_race[key] = is_tentative(preds)
            # 表示は馬番順
            raws_sorted = sorted(raws, key=lambda x: int(x.get("horse_num") or "99"))
            horses_by_race[key] = [
                {
                    "num": (h["horse_num"] or "").lstrip("0") or "0",
                    "waku": h["waku_num"] or "0",
                    "name": h["horse_name"],
                    "sex": sex_name(h["sex_code"]),
                    "age": h["age"] or "",
                    "burden": burden_weight_kg(h["burden_weight"]),
                    "jockey": h["jockey_short_name"] or "",
                    "trainer": h["trainer_short_name"] or "",
                    "odds": (h["win_odds"] or 0) / 10.0,
                    "popularity": h["win_popularity"] or 0,
                    "mark": mark_by_num.get(h["horse_num"]).mark
                        if h["horse_num"] in mark_by_num else "",
                    "rationale": mark_by_num.get(h["horse_num"]).rationale
                        if h["horse_num"] in mark_by_num else "",
                    "confidence": mark_by_num.get(h["horse_num"]).confidence
                        if h["horse_num"] in mark_by_num else "",
                    "value_score": mark_by_num.get(h["horse_num"]).value_score
                        if h["horse_num"] in mark_by_num else 0,
                    "win_probability": mark_by_num.get(h["horse_num"]).win_probability
                        if h["horse_num"] in mark_by_num else 0,
                    "expected_value": mark_by_num.get(h["horse_num"]).expected_value
                        if h["horse_num"] in mark_by_num else 0,
                }
                for h in raws_sorted
            ]
            # 印つきトップ 3 を抜粋（根拠付き）
            # 重賞ホワイトリストモードでは、race が whitelist 条件を満たさない
            # 場合 bet_candidate を False に強制する。
            race_whitelisted = is_whitelisted_race(race_dict)
            # 人気帯 / 信頼度除外も config から読む (P0-4 の sweep 結果反映)
            wl_min_pop = int(BUY_FILTER_DEFAULT.get("min_popularity", 1))
            wl_max_pop = int(BUY_FILTER_DEFAULT.get("max_popularity", 18))
            wl_exclude_conf = BUY_FILTER_DEFAULT.get("exclude_confidence", ["暫定", "混戦", "接戦"])
            top_picks_by_race[key] = [
                {
                    "mark": p.mark,
                    "num": p.horse_num.lstrip("0") or "0",
                    "name": next((r["horse_name"] for r in raws
                                  if r["horse_num"] == p.horse_num), ""),
                    "odds": (next((r["win_odds"] for r in raws
                                   if r["horse_num"] == p.horse_num), 0) or 0) / 10.0,
                    "popularity": next((r["win_popularity"] for r in raws
                                        if r["horse_num"] == p.horse_num), 0) or 0,
                    "bet_candidate": (
                        race_whitelisted
                        and p.rank == 1 and not tentative_by_race.get(key, False)
                        and p.confidence not in wl_exclude_conf
                        and p.value_score >= BET_MIN_VALUE
                        and p.expected_value >= BET_MIN_EV
                        and BET_MIN_ODDS <= (
                            (next((r["win_odds"] for r in raws
                                   if r["horse_num"] == p.horse_num), 0) or 0) / 10.0
                        ) <= BET_MAX_ODDS
                        and wl_min_pop <= (
                            next((r["win_popularity"] for r in raws
                                  if r["horse_num"] == p.horse_num), 0) or 0
                        ) <= wl_max_pop
                    ),
                    "rationale": p.rationale,
                    "confidence": p.confidence,
                    "confidence_gap": p.confidence_gap,
                    "value_score": p.value_score,
                    "win_probability": p.win_probability,
                    "fair_odds": p.fair_odds,
                    "expected_value": p.expected_value,
                    "kelly_fraction": p.kelly_fraction,
                }
                for p in preds[:3] if p.mark
            ]

    days: dict[tuple, dict] = {}
    buy_candidates: list[dict] = []
    for r in races:
        date_key = (r["race_year"], r["race_month_day"], r["track_code"])
        if date_key not in days:
            days[date_key] = {
                "date": race_id_to_date(r["race_year"], r["race_month_day"]),
                "weekday": weekday_name(r["weekday_code"] or ""),
                "track": track_name(r["track_code"]),
                "races": [],
            }
        surface = track_type(r["track_type_code"] or "")
        race_key = (
            r["race_year"], r["race_month_day"], r["track_code"],
            r["kaiji"], r["nichiji"], r["race_num"],
        )
        top_picks = top_picks_by_race.get(race_key, [])
        bet_picks = [p for p in top_picks if p.get("bet_candidate")]
        anchor = f"race-{r['race_year']}{r['race_month_day']}-{r['track_code']}-{int(r['race_num'])}"
        for p in bet_picks:
            buy_candidates.append({
                "anchor": anchor,
                "date": race_id_to_date(r["race_year"], r["race_month_day"]),
                "track": track_name(r["track_code"]),
                "race_num": int(r["race_num"]),
                "race_name": r["race_name"] or r["race_short10"] or "",
                "start_time": time_hhmm(r["start_time"] or ""),
                **p,
            })
        days[date_key]["races"].append({
            "anchor": anchor,
            "race_num": r["race_num"],
            "race_name": r["race_name"] or r["race_short10"] or "",
            "grade": grade_name(r["grade_code"] or ""),
            "surface": surface,
            "surface_class": _surface_class(surface),
            "distance": r["distance"],
            "start_time": time_hhmm(r["start_time"] or ""),
            "weather": weather_name(r["weather_code"] or ""),
            "turf_ground": ground_name(r["turf_condition"] or ""),
            "dirt_ground": ground_name(r["dirt_condition"] or ""),
            "horses": horses_by_race.get(race_key, []),
            "top_picks": top_picks,
            "has_bet": bool(bet_picks),
            "bet_picks": bet_picks,
            "tentative": tentative_by_race.get(race_key, False),
        })

    return {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "race_count": len(races),
        "buy_count": len(buy_candidates),
        "buy_candidates": buy_candidates,
        "days": list(days.values()),
    }


def render(
    output_path: Path | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
) -> Path:
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES)),
        autoescape=select_autoescape(["html", "xml"]),
    )
    tmpl = env.get_template("index.html.j2")
    html = tmpl.render(**build_view_model(from_date=from_date, to_date=to_date))

    out = output_path or (WEB_DIST / "index.html")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    return out


def publish_to_icloud() -> Path:
    """生成済み web/dist/index.html を iCloud Drive 公開ディレクトリにコピー。"""
    src = WEB_DIST / "index.html"
    if not src.exists():
        raise FileNotFoundError(
            f"{src} が無い。先に render() を実行してください。"
        )
    ICLOUD_PUBLISH_DIR.mkdir(parents=True, exist_ok=True)
    dst = ICLOUD_PUBLISH_DIR / "index.html"
    shutil.copy2(src, dst)
    # CSS/画像等のアセットも、後でテンプレ外部化したらここで copy する
    for asset_dir in ("static", "assets"):
        src_dir = WEB_DIST / asset_dir
        if src_dir.exists():
            shutil.copytree(src_dir, ICLOUD_PUBLISH_DIR / asset_dir, dirs_exist_ok=True)
    return dst


if __name__ == "__main__":
    p = render()
    print(f"wrote {p}")
    pub = publish_to_icloud()
    print(f"published {pub}")
