"""SQLite から開催・レース・出走馬を引いて web/dist/index.html を生成する。"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

logger = logging.getLogger(__name__)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import (
    BET_KELLY_MAX_PCT,
    BET_KELLY_MODE,
    BUY_FILTER_DEFAULT,
    ICLOUD_PUBLISH_DIR,
    WEB_DIST,
    is_whitelisted_race,
)
from db import open_db
from predictor import is_tentative, predict_race
from predictor.candidates import (
    BUY_CANDIDATE_MAX,
    mark_single_race_buy_pick,
    select_buy_candidate_picks,
    select_race_buy_pick,
)
from predictor.filter import is_buy_candidate
from predictor.portfolio import apply_daily_budget, compute_day_portfolio, sync_actual_stakes
from predictor.risk import recommended_fraction
from predictor.tickets import build_recommended_tickets, ticket_stake_yen
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
# None なら「制約なし」を意味するため、odds は (-inf, +inf) へフォールバック、
# value / ev も -inf。2026-05-16 P15 採用以降は min_odds / max_odds 共に None。
# 旧 BET_MIN_ODDS / BET_MAX_ODDS / BET_MIN_VALUE / BET_MIN_EV /
# BET_MAX_ODDS_AGE_MIN は 2026-06-13 に削除 (全箇所 dead constant 化していた)。
# 買い目フィルタの単一出典は config.BUY_FILTER_DEFAULT +
# predictor.filter.is_buy_candidate であり、ここに定数を複製しない。
SYNC_DIAGNOSTIC_RETENTION = 20


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _prune_old_files(
    directory: Path,
    pattern: str,
    keep: int = SYNC_DIAGNOSTIC_RETENTION,
) -> None:
    def sort_key(path: Path) -> tuple[float, str]:
        try:
            return (path.stat().st_mtime, path.name)
        except OSError:
            return (0.0, path.name)

    files = sorted(
        (p for p in directory.glob(pattern) if p.is_file()),
        key=sort_key,
        reverse=True,
    )
    for path in files[keep:]:
        try:
            path.unlink()
        except OSError:
            pass


def _surface_class(t: str) -> str:
    return {"芝": "turf", "ダート": "dirt", "障害": "jump"}.get(t, "")


# S7-γ (2026-05-18): pick-reason トリミング
# predict_race の rationale は 10-15 シグナル並列で、ほぼ全馬に含まれる無情報
# シグナル ("当日傾向: データなし"、"同脚質過多"、"父系/母父...低調 %") が
# ユーザーの認知負荷を増やすだけになっている。除外リストでこれらを落とし、
# 残ったシグナルから先頭 4 つだけを表示する。
# Phase B1 後の feature 構造変化を待ってメタ情報追加 (重要度タグ) を検討する
# 余地はあるが、S7 では表面的トリミングで足りる。
_RATIONALE_EXCLUDE_PREFIXES = (
    "当日傾向: データなし",
    "同脚質過多",
    "父系同馬場低調",
    "父系距離帯低調",
    "母父同馬場低調",
    "母父距離帯低調",
    "父系道悪低調",
    "母父道悪低調",
    "脚質推定",  # "脚質推定3(15走)" 等、レース予想の中核ではない補足情報
)


def _trim_rationale(rationale: str, max_signals: int = 4) -> str:
    """rationale を除外リスト + 先頭 N シグナル の方式でトリミング。

    元の rationale は "; " 区切りで複数シグナルが並ぶ。"; 信頼度=..." の
    付加情報は最後尾に保持。
    """
    if not rationale:
        return rationale
    parts = [s.strip() for s in rationale.split(";") if s.strip()]
    # 信頼度行 (rank=1 の馬で末尾に付く "信頼度=...(2位差...)") は別途保持
    confidence_part: str | None = None
    others: list[str] = []
    for p in parts:
        if p.startswith("信頼度="):
            confidence_part = p
        else:
            others.append(p)
    # 除外リスト
    kept = [p for p in others if not p.startswith(_RATIONALE_EXCLUDE_PREFIXES)]
    # 先頭 N シグナル
    kept = kept[:max_signals]
    if confidence_part:
        kept.append(confidence_part)
    return "; ".join(kept)


def build_view_model(
    from_date: str | None = None,
    to_date: str | None = None,
    daily_budget_yen: int | None = None,
    ignore_odds_freshness: bool = False,
) -> dict:
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
        payout_rows = conn.execute(
            """
            SELECT * FROM payouts
            WHERE (race_year || race_month_day) BETWEEN ? AND ?
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
    payouts_by_race: dict[tuple, dict] = {}
    for row in payout_rows:
        key = (
            row["race_year"], row["race_month_day"], row["track_code"],
            row["kaiji"], row["nichiji"], row["race_num"],
        )
        payouts_by_race[key] = dict(row)

    # 予想を計算し馬番→印 のマップを作る（過去走ベース・本格版）
    horses_by_race: dict[tuple, list] = {}
    top_picks_by_race: dict[tuple, list] = {}
    tentative_by_race: dict[tuple, bool] = {}
    # オッズ鮮度 (max_odds_age_min) だけで買い候補から落ちた件数
    stale_suppressed = 0
    buy_filter = dict(BUY_FILTER_DEFAULT)
    if ignore_odds_freshness:
        buy_filter["max_odds_age_min"] = None
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
                    "rationale": _trim_rationale(
                        mark_by_num.get(h["horse_num"]).rationale
                    ) if h["horse_num"] in mark_by_num else "",
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
            # S7-α-2 (2026-05-18): bet_candidate 判定は predictor.filter.is_buy_candidate
            # に集約。以前は web/generator.py が独立した判定ロジック (172-185 行) を
            # 持ち、S5-3 で追加した min_kelly / max_predicted_p が反映されず、HTML に
            # 全 ◎ 馬が買い候補として表示される重大バグの原因だった。
            top_picks_for_race = []
            for p in preds[:BUY_CANDIDATE_MAX]:
                horse_for_pred = next(
                    (r for r in raws if r["horse_num"] == p.horse_num), None
                )
                if horse_for_pred is None:
                    continue
                tent = tentative_by_race.get(key, False)
                bet_ok = is_buy_candidate(
                    p, horse_for_pred, tent, race=race_dict,
                    filter_spec=buy_filter, now=datetime.now())
                # 鮮度だけで落ちた候補を数える (now なし評価なら通る場合)。
                # 「候補ゼロ」と「オッズが古いだけ」をユーザが区別できるように
                # テンプレートで件数を出す。
                if (
                    not ignore_odds_freshness
                    and not bet_ok
                    and is_buy_candidate(p, horse_for_pred, tent, race=race_dict)
                ):
                    stale_suppressed += 1
                ticket = f"単勝 {p.horse_num.lstrip('0') or '0'}番"
                top_picks_for_race.append({
                    "mark": p.mark,
                    "num": p.horse_num.lstrip("0") or "0",
                    "name": horse_for_pred.get("horse_name", ""),
                    "bet_type": "単勝",
                    "ticket": ticket,
                    "odds": (horse_for_pred.get("win_odds", 0) or 0) / 10.0,
                    "popularity": horse_for_pred.get("win_popularity", 0) or 0,
                    # now つき評価 = オッズ鮮度 (max_odds_age_min) 込み。
                    # 旧実装は鮮度未評価で、古いオッズの候補が公開 HTML に
                    # 出うる経路乖離があった (2026-06-13 v2 監査指摘)。
                    "bet_candidate": bet_ok,
                    "rationale": _trim_rationale(p.rationale),
                    "confidence": p.confidence,
                    "confidence_gap": p.confidence_gap,
                    "value_score": p.value_score,
                    "win_probability": p.win_probability,
                    "fair_odds": p.fair_odds,
                    "expected_value": p.expected_value,
                    "kelly_fraction": p.kelly_fraction,
                    # P20 (2026-06-07): full Kelly は過大表示なので、実際の
                    # 推奨賭金率 (= 1/4 Kelly + per-bet cap) を併せて持たせる。
                    # 表示・バッジ判定はこちらを使い、full Kelly は副次表示に降格。
                    "recommended_kelly": recommended_fraction(
                        p.kelly_fraction, mode=BET_KELLY_MODE, max_pct=BET_KELLY_MAX_PCT
                    ),
                })
            top_picks_by_race[key] = top_picks_for_race

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
        # S7-α-3 (2026-05-18): 二重防御ガード。
        # bet_candidate が True でも kelly_fraction が 0 近傍の馬は HTML
        # 買い候補ボードから除外する。is_buy_candidate 側で kelly_fraction > 0
        # は既にチェック済みだが、過去 1 ヶ月で「フィルタ漏れで Kelly 0% 馬が
        # 候補表示」事故が 2 回発生 (S5-3 GUI 欠落、S7-α web/generator.py 欠落)
        # しているため、表示層での明示ガードを追加。is_buy_candidate の責務と
        # 二重になるが、防御の冗長性として正当化。
        bet_picks = [
            p for p in top_picks
            if p.get("bet_candidate") and (p.get("kelly_fraction") or 0) >= 0.0001
        ]
        race_candidate_picks = select_buy_candidate_picks(top_picks) if bet_picks else []
        race_buy_pick = select_race_buy_pick(bet_picks)
        race_candidate_picks = mark_single_race_buy_pick(race_candidate_picks, race_buy_pick)
        candidate_summary = "・".join(p.get("ticket", "") for p in race_candidate_picks)
        anchor = f"race-{r['race_year']}{r['race_month_day']}-{r['track_code']}-{int(r['race_num'])}"
        if race_buy_pick:
            buy_candidates.append({
                "anchor": anchor,
                "date": race_id_to_date(r["race_year"], r["race_month_day"]),
                "track": track_name(r["track_code"]),
                "race_num": int(r["race_num"]),
                "race_name": r["race_name"] or r["race_short10"] or "",
                "start_time": time_hhmm(r["start_time"] or ""),
                "candidate_picks": race_candidate_picks,
                "candidate_summary": candidate_summary,
                "recommended_tickets": [],
                "_payout_row": payouts_by_race.get(race_key),
                **race_buy_pick,
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
            "candidate_picks": race_candidate_picks,
            "candidate_summary": candidate_summary,
            "recommended_tickets": [],
            "_payout_row": payouts_by_race.get(race_key),
            "tentative": tentative_by_race.get(race_key, False),
        })

    # P22-2 (2026-06-12): 開催日ごとの買い候補数。テンプレート 2 箇所
    # (day-nav チップ / day-section h2) が使う値の単一出典。
    # テンプレート側 selectattr の重複式 (code-quality 指摘) を解消。
    for d in days.values():
        d["buy_count"] = sum(1 for race in d["races"] if race["has_bet"])

    # S7-β-2 (2026-05-18): buy_candidates を kelly_fraction 降順でソート。
    # 強いシグナル (Kelly 高) を最上位に表示することでユーザーが最初に目にする
    # 情報の価値を高める。同 Kelly 内は発走時刻昇順。
    buy_candidates.sort(
        key=lambda b: (-(b.get("kelly_fraction") or 0), b.get("start_time") or "")
    )

    # P20 (2026-06-07): ポートフォリオ推奨投資率の上限チェック。
    # full Kelly 合計だと bankroll の 100% 超 (= 物理的に賭けられない) になる
    # 事故があったため、recommended_kelly (= quarter + per-bet cap 済) を **日単位**
    # で集計する (実際の bankroll は 1 開催日ごとに区切られるため、多日窓の買い候補を
    # 全部合算すると誤って巨大化する)。集計ロジックは gui/app.py と共通の単一出典
    # predictor.portfolio.compute_day_portfolio に集約 (P20-3 / 2026-06-07)。
    budget_info = apply_daily_budget(buy_candidates, daily_budget_yen)
    portfolio_info = compute_day_portfolio(buy_candidates)
    portfolio_info.update(budget_info)
    unit_yen = portfolio_info.get("unit_yen") or 100
    tickets_by_anchor: dict[str, list[dict]] = {}
    stake_by_anchor: dict[str, dict] = {}
    for b in buy_candidates:
        allocated_stake_yen = b.get("stake_yen")
        b["allocated_stake_yen"] = allocated_stake_yen
        tickets = build_recommended_tickets(
            b.get("candidate_picks", []),
            b.pop("_payout_row", None),
            max_stake_yen=allocated_stake_yen,
            unit_yen=unit_yen,
        ) if b.get("candidate_picks") else []
        b["recommended_tickets"] = tickets
        if allocated_stake_yen is not None:
            b["stake_yen"] = ticket_stake_yen(tickets)
        anchor = str(b.get("anchor") or "")
        tickets_by_anchor[anchor] = tickets
        stake_by_anchor[anchor] = b
    sync_actual_stakes(buy_candidates, portfolio_info)
    for d in days.values():
        for race in d["races"]:
            matched = stake_by_anchor.get(str(race.get("anchor") or ""))
            for p in race.get("bet_picks", []) + race.get("candidate_picks", []):
                if matched and str(p.get("num")) == str(matched.get("num")):
                    p["stake_yen"] = matched.get("stake_yen")
                    p["raw_stake_yen"] = matched.get("raw_stake_yen")
                    p["budget_scale"] = matched.get("budget_scale")
            race["recommended_tickets"] = tickets_by_anchor.get(
                str(race.get("anchor") or ""),
                [],
            )
            race.pop("_payout_row", None)

    # S7-β-4 (2026-05-18): フィルタ条件の header 明示用 context。
    # config.BUY_FILTER_DEFAULT を読み、None でない項目を表示文字列にまとめる。
    # ユーザーが「フィルタが効いていない状態」を検知できるセンサーとして機能。
    filter_summary = _build_filter_summary()
    # S7-β-5 (2026-05-18): footer version snapshot 用 context。
    version_info = _build_version_snapshot()
    return {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "race_count": len(races),
        "buy_count": len(buy_candidates),
        "buy_candidates": buy_candidates,
        "days": list(days.values()),
        "filter_summary": filter_summary,
        "stale_suppressed": stale_suppressed,
        "version_info": version_info,
        "portfolio_info": portfolio_info,
        "ignore_odds_freshness": ignore_odds_freshness,
    }


def _build_filter_summary() -> str:
    """BUY_FILTER_DEFAULT の現状を 1 行文字列に。HTML header に表示する。"""
    parts: list[str] = []
    spec = BUY_FILTER_DEFAULT
    if spec.get("min_kelly") is not None:
        parts.append(f"min_kelly≥{spec['min_kelly']}")
    if spec.get("max_predicted_p") is not None:
        parts.append(f"max_predicted_p≤{spec['max_predicted_p']}")
    if spec.get("min_ev") is not None:
        parts.append(f"min_ev≥{spec['min_ev']}")
    if spec.get("max_ev") is not None:
        parts.append(f"max_ev≤{spec['max_ev']}")
    if spec.get("min_odds") is not None:
        parts.append(f"min_odds≥{spec['min_odds']}")
    if spec.get("max_odds") is not None:
        parts.append(f"max_odds≤{spec['max_odds']}")
    min_pop = spec.get("min_popularity")
    max_pop = spec.get("max_popularity")
    if min_pop is not None or max_pop is not None:
        lo = min_pop if min_pop is not None else 1
        hi = max_pop if max_pop is not None else "-"
        parts.append(f"{lo}-{hi}番人気")
    wl_mode = spec.get("whitelist_mode")
    wl_tracks = spec.get("whitelist_tracks") or []
    if wl_mode and wl_tracks:
        parts.append(f"WL={'/'.join(wl_tracks)}")
    elif wl_mode is False or not wl_tracks:
        parts.append("全場開放")
    excl = spec.get("exclude_confidence") or []
    if excl:
        parts.append(f"除外={'/'.join(excl)}")
    return " / ".join(parts) if parts else "フィルタなし"


def _build_version_snapshot() -> dict:
    """calibrator / LGBM / git の version snapshot。footer 表示用。"""
    import json
    import subprocess
    root = Path(__file__).resolve().parent.parent
    info: dict = {}
    try:
        cal = json.loads((root / "predictor" / "calibrator.json").read_text(encoding="utf-8"))
        info["calibrator_type"] = cal.get("type", "?")
        info["calibrator_generated_at"] = (cal.get("generated_at") or "?")[:10]
        info["calibrator_rule_version"] = cal.get("rule_version", "?")
    except (OSError, ValueError):
        info["calibrator_type"] = "?"
    try:
        lgbm = json.loads((root / "predictor" / "lgbm_meta.json").read_text(encoding="utf-8"))
        info["lgbm_rule_version"] = lgbm.get("rule_version", "?")
        info["lgbm_generated_at"] = (lgbm.get("generated_at") or "?")[:10]
    except (OSError, ValueError):
        info["lgbm_rule_version"] = "?"
    try:
        sha = subprocess.check_output(
            ["git", "-C", str(root), "rev-parse", "--short", "HEAD"],
            stderr=subprocess.DEVNULL,
        ).strip().decode("ascii")
        info["git_sha"] = sha
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        info["git_sha"] = "?"
    return info


def render(
    output_path: Path | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    daily_budget_yen: int | None = None,
    ignore_odds_freshness: bool = False,
) -> Path:
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES)),
        autoescape=select_autoescape(["html", "xml"]),
    )
    tmpl = env.get_template("index.html.j2")
    html = tmpl.render(**build_view_model(
        from_date=from_date,
        to_date=to_date,
        daily_budget_yen=daily_budget_yen,
        ignore_odds_freshness=ignore_odds_freshness,
    ))

    out = output_path or (WEB_DIST / "index.html")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    # サイズ予算の監視 (mobile-html-reviewer 3 回指摘): file:// 配信は
    # キャッシュも遅延読込も無いため、1.5MB 超で iPhone Files の初回パースが
    # 体感に乗り始める。超過したら warning (生成は止めない)。
    size = out.stat().st_size
    if size > 1_500_000:
        logger.warning(
            "index.html が %0.2fMB とサイズ予算 (1.5MB) を超過。対象期間の"
            "短縮や古い開催の間引きを検討してください。", size / 1e6)
    return out


class StalePublishRefused(RuntimeError):
    """検証モード HTML を iCloud に出そうとしたときに raise する。

    Python から render(ignore_odds_freshness=True) + publish_to_icloud() を直接呼ぶ
    第三経路の保護。CLI/GUI ではこのチェックに来る前に publish_safety で塞いでいる。
    """


def publish_to_icloud(allow_stale: bool = False) -> Path:
    """生成済み web/dist/index.html を iCloud Drive 公開ディレクトリにコピー。

    allow_stale=False (デフォルト) で index.html に verification-banner が含まれて
    いる (= ignore_odds_freshness=True で render された) と StalePublishRefused を
    raise する。直 import 経路 (CLI/GUI 以外) の保護層。
    """
    src = WEB_DIST / "index.html"
    if not src.exists():
        raise FileNotFoundError(
            f"{src} が無い。先に render() を実行してください。"
        )
    if not allow_stale:
        try:
            preview_head = src.read_text(encoding="utf-8", errors="replace")[:5000]
        except OSError:
            preview_head = ""
        if 'class="verification-banner"' in preview_head:
            raise StalePublishRefused(
                "index.html は検証モード (オッズ鮮度無視) で生成されています。"
                "iCloud 公開を中止しました。意図的に公開する場合は "
                "publish_to_icloud(allow_stale=True) を渡してください。"
            )
    src_stat = src.stat()
    src_digest = _file_sha256(src)
    ICLOUD_PUBLISH_DIR.mkdir(parents=True, exist_ok=True)
    dst = ICLOUD_PUBLISH_DIR / "index.html"
    shutil.copy2(src, dst)
    os.utime(dst, None)

    for asset_dir in ("static", "assets"):
        src_dir = WEB_DIST / asset_dir
        if src_dir.exists():
            shutil.copytree(src_dir, ICLOUD_PUBLISH_DIR / asset_dir, dirs_exist_ok=True)

    published_at = datetime.now().astimezone()
    stamp = published_at.strftime("%Y%m%d_%H%M%S_%f")
    snapshot_dir = ICLOUD_PUBLISH_DIR / "snapshots"
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    snapshot = snapshot_dir / f"index_{stamp}.html"
    shutil.copy2(dst, snapshot)
    os.utime(snapshot, None)

    digest = _file_sha256(dst)
    size = dst.stat().st_size
    source_mtime = datetime.fromtimestamp(src_stat.st_mtime).astimezone().isoformat(
        timespec="seconds"
    )
    status = {
        "published_at": published_at.isoformat(timespec="seconds"),
        "index": "index.html",
        "snapshot": f"snapshots/{snapshot.name}",
        "sha256": digest,
        "bytes": size,
        "copied_ok": digest == src_digest and size == src_stat.st_size,
        "source_index_mtime": source_mtime,
        "source_sha256": src_digest,
        "source_bytes": src_stat.st_size,
    }
    (ICLOUD_PUBLISH_DIR / "_sync_status.json").write_text(
        json.dumps(status, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    check_text = (
        f"published_at={status['published_at']}\n"
        f"sha256={digest}\n"
        f"bytes={size}\n"
        f"copied_ok={status['copied_ok']}\n"
        f"source_index_mtime={status['source_index_mtime']}\n"
        f"source_sha256={src_digest}\n"
        "index=index.html\n"
        f"snapshot=snapshots/{snapshot.name}\n"
    )
    (ICLOUD_PUBLISH_DIR / "_sync_check_latest.txt").write_text(
        check_text,
        encoding="utf-8",
    )
    (ICLOUD_PUBLISH_DIR / f"_sync_check_{stamp}.txt").write_text(
        check_text,
        encoding="utf-8",
    )
    _prune_old_files(snapshot_dir, "index_*.html")
    _prune_old_files(ICLOUD_PUBLISH_DIR, "_sync_check_[0-9]*.txt")
    return dst


if __name__ == "__main__":
    # 2026-05-16: CLI 化。GUI (.venv32) から subprocess 経由でこのモジュールを
    # .venv64 として呼ぶことで LightGBM v5 ensemble 予測を反映させる。
    # 詳細は gui/app.py:_run_render_in_venv64 を参照。
    import argparse
    import json as _json
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="from_date", default=None, help="YYYYMMDD")
    ap.add_argument("--to", dest="to_date", default=None, help="YYYYMMDD")
    ap.add_argument("--daily-budget-yen", type=int, default=None,
                    help="daily betting budget in yen for stake display")
    ap.add_argument("--ignore-odds-freshness", action="store_true",
                    help="verification mode: do not suppress buy picks by odds age")
    ap.add_argument("--no-publish", action="store_true",
                    help="iCloud Drive へのコピーをスキップ")
    ap.add_argument(
        "--allow-stale-publish", action="store_true",
        help="--ignore-odds-freshness と publish を併用するセーフティを明示的に解除する "
             "(検証 HTML を意図的に iCloud に出すときだけ使う)",
    )
    ap.add_argument("--json", action="store_true",
                    help="結果を JSON で stdout に 1 行出力")
    args = ap.parse_args()
    # 検証モード × publish の安全判定は web.publish_safety に集約 (CLI/GUI/直 import 共通)。
    from web.publish_safety import assert_safe_to_publish
    publish_decision, safety_warning = assert_safe_to_publish(
        ignore_odds_freshness=args.ignore_odds_freshness,
        publish=not args.no_publish,
        allow_stale=args.allow_stale_publish,
    )
    if safety_warning is not None:
        print(
            f"ERROR: {safety_warning} --no-publish か --allow-stale-publish の"
            f"どちらかを明示してください。",
            file=sys.stderr,
        )
        sys.exit(2)
    p = render(
        from_date=args.from_date,
        to_date=args.to_date,
        daily_budget_yen=args.daily_budget_yen,
        ignore_odds_freshness=args.ignore_odds_freshness,
    )
    published = None
    if publish_decision:
        try:
            published = publish_to_icloud(allow_stale=args.allow_stale_publish)
        except FileNotFoundError as e:
            print(f"publish skipped: {e}", file=sys.stderr)
        except StalePublishRefused as e:
            print(f"publish refused (banner detected): {e}", file=sys.stderr)
            sys.exit(2)
    if args.json:
        # ensure_ascii=True: 日本語パス (例: iCloudDrive/競馬予想/) を Unicode
        # escape にし、Windows console (cp932) と utf-8 parent の codec 差で
        # 壊れる JSONDecodeError を防ぐ (2026-05-16 修正)。
        print(_json.dumps({
            "rendered": str(p),
            "published": str(published) if published else None,
        }, ensure_ascii=True))
    else:
        print(f"wrote {p}")
        if published:
            print(f"published {published}")
