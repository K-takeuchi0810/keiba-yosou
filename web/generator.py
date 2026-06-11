"""SQLite から開催・レース・出走馬を引いて web/dist/index.html を生成する。"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

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
from predictor.filter import is_buy_candidate
from predictor.portfolio import compute_day_portfolio
from predictor.risk import recommended_fraction
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
_mo = BUY_FILTER_DEFAULT.get("min_odds")
BET_MIN_ODDS: float = float(_mo) if _mo is not None else float("-inf")
_xo = BUY_FILTER_DEFAULT.get("max_odds")
BET_MAX_ODDS: float = float(_xo) if _xo is not None else float("inf")
_mv = BUY_FILTER_DEFAULT.get("min_value")
BET_MIN_VALUE: float = float(_mv) if _mv is not None else float("-inf")
_me = BUY_FILTER_DEFAULT.get("min_ev")
BET_MIN_EV: float = float(_me) if _me is not None else float("-inf")
BET_MAX_ODDS_AGE_MIN: int = int(BUY_FILTER_DEFAULT.get("max_odds_age_min") or 30)
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
            for p in preds[:3]:
                if not p.mark:
                    continue
                horse_for_pred = next(
                    (r for r in raws if r["horse_num"] == p.horse_num), None
                )
                if horse_for_pred is None:
                    continue
                tent = tentative_by_race.get(key, False)
                top_picks_for_race.append({
                    "mark": p.mark,
                    "num": p.horse_num.lstrip("0") or "0",
                    "name": horse_for_pred.get("horse_name", ""),
                    "odds": (horse_for_pred.get("win_odds", 0) or 0) / 10.0,
                    "popularity": horse_for_pred.get("win_popularity", 0) or 0,
                    "bet_candidate": is_buy_candidate(
                        p, horse_for_pred, tent, race=race_dict
                    ),
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
    portfolio_info = compute_day_portfolio(buy_candidates)

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
        "version_info": version_info,
        "portfolio_info": portfolio_info,
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
    ap.add_argument("--no-publish", action="store_true",
                    help="iCloud Drive へのコピーをスキップ")
    ap.add_argument("--json", action="store_true",
                    help="結果を JSON で stdout に 1 行出力")
    args = ap.parse_args()
    p = render(from_date=args.from_date, to_date=args.to_date)
    published = None
    if not args.no_publish:
        try:
            published = publish_to_icloud()
        except FileNotFoundError as e:
            print(f"publish skipped: {e}", file=sys.stderr)
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
