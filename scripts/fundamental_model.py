"""市場情報を完全に除いた Fundamental Model (憲法 Phase 0.5-3)。

## 何をするか

オッズ・人気・支持率・市場順位、およびそれらから作った派生特徴を **一切使わず**、
競走能力だけから勝率を推定する。教師は **実際のレース結果のみ**。
最終市場 (P_final / final_odds / final_rank) は教師にも特徴にも使わない。

## 学習と評価の分離

  学習   2021-01-01〜2023-12-31  (DATA_SPLIT.train)
  検証   2024-01-01〜2025-12-31  (DATA_SPLIT.validation)
  評価   2026-05-09〜2026-08-31  (DATA_SPLIT.strategy_dev)

**モデル構造・特徴選択・ハイパーパラメータは 2025 以前で決める**。
2026 は評価対象であって、見ながら調整すると 933 レースに過学習する。

## 合格条件ではないこと

Fundamental が T−10 市場より悪くても問題ない (憲法 Phase 0.5-3)。
ここで確定させたいのは「市場情報なしで AI がどの程度の確率推定能力を持つか」。
本番は 0.5-4 (市場 + Fundamental 由来補正) で、そこで初めて
LogLoss < 0.21183 になるかを検査する。

usage:
    .venv64/Scripts/python.exe -m scripts.fundamental_model --fit    # 学習
    .venv64/Scripts/python.exe -m scripts.fundamental_model --eval   # 評価
"""
from __future__ import annotations

import argparse
import json
import math
import sqlite3
import sys
from collections import Counter
from datetime import date
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import DATA_SPLIT, guard_analysis_window  # noqa: E402
from db import DB_PATH  # noqa: E402
from predictor.feature_manifest import assert_no_market_features  # noqa: E402
from predictor.provenance import snapshot  # noqa: E402

MODEL_PATH = Path(__file__).resolve().parent.parent / "predictor" / "fundamental_model.txt"
META_PATH = MODEL_PATH.with_suffix(".meta.json")

# 使う特徴。**市場由来は 1 つも入れない** (feature_manifest が検査する)。
FEATURES = [
    # 当該馬の実績 (すべて当該レースより前のみ)
    "h_starts", "h_wins", "h_winrate", "h_top3rate", "h_last_finish",
    "h_days_since", "h_best_finish", "h_recent3_avg_finish",
    "hd_starts", "hd_winrate",              # 同距離帯
    "ht_starts", "ht_winrate",              # 同競馬場
    # 人的要因
    "j_rides", "j_winrate", "t_runs", "t_winrate", "s_winrate",
    # レース条件 (市場ではない)
    "age", "sex", "burden", "waku", "starters", "dist", "surface", "cond",
    "weather", "grade", "w_abs", "w_delta", "blinker",
]


def _rate(w: int, n: int, pw: float = 1.0, pn: float = 12.0) -> float:
    return (w + pw) / (n + pn)


def _dband(d: int) -> int:
    return 0 if d < 1400 else (1 if d < 1800 else (2 if d < 2200 else 3))


# 1 = 出走取消。**発走前に取り消され、T−10 のオッズ配信からも消えている**ので、
# 決定時点の候補ではない。落としても PIT 違反にならない (2026-09-18 実データ確認)。
#
# 2 = 発走除外 / 3 = 競走除外 は **ゲート前後で除外** されるため、T−10 時点では
# まだ買える候補だった。実際 2026 年のデータでは 50 件中 49 件にオッズが付いている。
# 「その後除外された」は T−10 に知りえない情報なので、これを理由に標本から
# 落とすと後知恵の選択になる。**敗者として残す**。
# 4 = 競走中止 は走った上で止めたので当然残す。
DID_NOT_START = frozenset({"1"})


def build_dataset(from_date: str, to_date: str,
                  db_path: str | None = None) -> tuple[list[dict], Counter]:
    """時系列に積み上げて特徴を作る。**すべて当該レースより前の情報のみ**。

    着順を読む関数なので、封印窓の門はここで通す。呼び出し側の作法に任せると
    新しい呼び出しが増えたときに抜ける (2026-09-18 に tests が実際に検出)。
    db_path を渡したときも例外にしない。抜け道を 1 つ作ると必ずそこを通る。
    """
    from_date, to_date, _sealed = guard_analysis_window(
        from_date, to_date, context="fundamental_model.build_dataset")
    conn = sqlite3.connect(f"file:{db_path or DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT (h.race_year||h.race_month_day) d, h.race_year ry, h.race_month_day rmd,
               h.track_code tc, h.kaiji ka, h.nichiji ni, h.race_num rc,
               h.horse_num hn, h.blood_register_num bn, h.jockey_code jc,
               h.trainer_code trc, h.age, h.sex_code sex, h.burden_weight bw,
               h.waku_num waku, h.horse_weight hw, h.weight_change_sign wsg,
               h.weight_change_diff wdf, h.blinker bl, h.confirmed_order fin,
               h.abnormal_code abn,
               r.distance dist, r.track_type_code tt, r.turf_condition tcond,
               r.dirt_condition dcond, r.weather_code wc, r.grade_code gr,
               r.starter_count starters, m.sire_breeding_num sire
          FROM horse_races h
          JOIN races r ON r.race_year=h.race_year AND r.race_month_day=h.race_month_day
           AND r.track_code=h.track_code AND r.kaiji=h.kaiji AND r.nichiji=h.nichiji
           AND r.race_num=h.race_num
          LEFT JOIN horse_masters m ON m.blood_register_num = h.blood_register_num
         WHERE (h.race_year||h.race_month_day) <= ?
           AND CAST(h.track_code AS INTEGER) BETWEEN 1 AND 10
           AND h.horse_num NOT IN ('', '00')
         ORDER BY d, h.track_code, h.race_num, h.horse_num
        """, (to_date,)).fetchall()
    # 結果が未取込のレース。勝ち馬がいないのに全頭 won=0 として学習すると
    # 「このレースでは誰も勝たない」を教えることになる (2026-09-18 検出: 57 レース)。
    finished_races = {
        (r[0], r[1], r[2], r[3], r[4], r[5])
        for r in conn.execute(
            """SELECT race_year, race_month_day, track_code, kaiji, nichiji, race_num
                 FROM horse_races
                WHERE confirmed_order = 1
                  AND (race_year||race_month_day) <= ?
                  AND CAST(track_code AS INTEGER) BETWEEN 1 AND 10""",
            (to_date,)).fetchall()}
    conn.close()

    hn_ = Counter(); hw_ = Counter(); ht3 = Counter(); hbest: dict = {}
    hrec: dict = {}
    hdn = Counter(); hdw = Counter(); htn = Counter(); htw = Counter()
    jn = Counter(); jw = Counter(); tn = Counter(); tw = Counter()
    sn = Counter(); sw = Counter()
    hlast: dict = {}; hlastfin: dict = {}
    out: list[dict] = []
    stats = Counter()

    for r in rows:
        # 出走取消の馬と、結果が取り込まれていないレースは使わない。
        # 前者は T−10 の市場にも居ない。後者は勝ち馬が存在せず、
        # 全頭 won=0 として学習すると「誰も勝たない」を教えることになる。
        if str(r["abn"] or "").strip() in DID_NOT_START:
            stats["skip_did_not_start"] += 1
            continue
        if (r["ry"], r["rmd"], r["tc"], r["ka"], r["ni"], r["rc"]) not in finished_races:
            stats["skip_race_without_result"] += 1
            continue
        bn, jc, trc, sire = r["bn"], r["jc"], r["trc"], r["sire"]
        db = _dband(int(r["dist"] or 0))
        tc = r["tc"]
        try:
            fin = int(r["fin"] or 0)
        except (TypeError, ValueError):
            fin = 0
        try:
            dd = int(str(r["wdf"]).strip() or -1)
        except ValueError:
            dd = -1
        delta = (-dd if str(r["wsg"] or "").strip() == "-" else dd) if dd >= 0 else np.nan
        try:
            hwt = float(str(r["hw"]).strip())
        except (TypeError, ValueError):
            hwt = np.nan
        days = np.nan
        if bn in hlast:
            try:
                a, b = hlast[bn], r["d"]
                days = (date(int(b[:4]), int(b[4:6]), int(b[6:]))
                        - date(int(a[:4]), int(a[4:6]), int(a[6:]))).days
            except Exception:
                pass
        surface = str(r["tt"] or "").strip()[:1]
        cond = str((r["dcond"] if surface == "2" else r["tcond"]) or "").strip()
        recent = hrec.get(bn, [])

        if r["d"] >= from_date:
            out.append({
                "race_id": f"{r['ry']}-{r['rmd']}-{r['tc']}-{r['ka']}-{r['ni']}-{r['rc']}",
                "horse_num": str(r["hn"]).strip(), "date": r["d"],
                "won": 1 if fin == 1 else 0,
                "h_starts": hn_[bn], "h_wins": hw_[bn],
                "h_winrate": _rate(hw_[bn], hn_[bn]),
                "h_top3rate": _rate(ht3[bn], hn_[bn], 3.0, 12.0),
                "h_last_finish": hlastfin.get(bn, np.nan),
                "h_days_since": days,
                "h_best_finish": hbest.get(bn, np.nan),
                "h_recent3_avg_finish": (sum(recent[-3:]) / len(recent[-3:])
                                         if recent else np.nan),
                "hd_starts": hdn[(bn, db)], "hd_winrate": _rate(hdw[(bn, db)], hdn[(bn, db)]),
                "ht_starts": htn[(bn, tc)], "ht_winrate": _rate(htw[(bn, tc)], htn[(bn, tc)]),
                "j_rides": jn[jc], "j_winrate": _rate(jw[jc], jn[jc], 1.0, 20.0),
                "t_runs": tn[trc], "t_winrate": _rate(tw[trc], tn[trc], 1.0, 20.0),
                "s_winrate": _rate(sw[sire], sn[sire], 1.0, 30.0) if sire else np.nan,
                "age": float(str(r["age"] or 0).strip() or 0),
                "sex": float(str(r["sex"] or 0).strip() or 0),
                "burden": float(str(r["bw"] or 0).strip() or 0),
                "waku": float(str(r["waku"] or 0).strip() or 0),
                "starters": float(r["starters"] or 0),
                "dist": float(r["dist"] or 0),
                "surface": float(surface or 0), "cond": float(cond or 0),
                "weather": float(str(r["wc"] or 0).strip() or 0),
                "grade": float({"A": 3, "B": 2, "C": 1}.get(
                    str(r["gr"] or "").strip(), 0)),
                "w_abs": hwt, "w_delta": delta,
                "blinker": 1.0 if str(r["bl"] or "").strip() == "1" else 0.0,
            })
            stats["rows"] += 1

        # 更新 (このレースの結果は次以降にだけ使う)
        hn_[bn] += 1; hdn[(bn, db)] += 1; htn[(bn, tc)] += 1
        jn[jc] += 1; tn[trc] += 1
        if sire:
            sn[sire] += 1
        if fin == 1:
            hw_[bn] += 1; hdw[(bn, db)] += 1; htw[(bn, tc)] += 1
            jw[jc] += 1; tw[trc] += 1
            if sire:
                sw[sire] += 1
        if 0 < fin <= 3:
            ht3[bn] += 1
        if fin > 0:
            hbest[bn] = min(hbest.get(bn, 99), fin)
            hrec.setdefault(bn, []).append(fin)
            hlastfin[bn] = float(fin)
        hlast[bn] = r["d"]
    return out, stats


def _matrix(data: list[dict]) -> tuple[np.ndarray, np.ndarray]:
    X = np.array([[d[c] for c in FEATURES] for d in data], dtype=float)
    y = np.array([d["won"] for d in data])
    return X, y


def fit() -> dict:
    """2021-2023 で学習し、2024-2025 で検証する。2026 は一切見ない。"""
    import lightgbm as lgb

    assert_no_market_features(FEATURES)
    tr_from, tr_to = DATA_SPLIT["train"]["from"], DATA_SPLIT["train"]["to"]
    va_from, va_to = DATA_SPLIT["validation"]["from"], DATA_SPLIT["validation"]["to"]

    print(f"学習データ構築 {tr_from}〜{tr_to} ...", flush=True)
    train, s_tr = build_dataset(tr_from, tr_to)
    print(f"  {len(train):,} 頭 (除外 {dict(s_tr)})", flush=True)
    print(f"検証データ構築 {va_from}〜{va_to} ...", flush=True)
    valid, s_va = build_dataset(va_from, va_to)
    print(f"  {len(valid):,} 頭 (除外 {dict(s_va)})", flush=True)

    Xtr, ytr = _matrix(train)
    Xva, yva = _matrix(valid)
    model = lgb.LGBMClassifier(
        n_estimators=2000, learning_rate=0.03, num_leaves=63,
        min_child_samples=100, subsample=0.8, subsample_freq=1,
        colsample_bytree=0.8, random_state=20260918, verbose=-1)
    model.fit(Xtr, ytr, eval_set=[(Xva, yva)], eval_metric="binary_logloss",
              callbacks=[lgb.early_stopping(100, verbose=False)])
    model.booster_.save_model(str(MODEL_PATH))

    from predictor.evaluation import evaluate_probabilities
    rep = evaluate_probabilities(list(yva), list(model.predict_proba(Xva)[:, 1]))
    meta = {**snapshot(), "features": FEATURES,
            "train": [tr_from, tr_to], "validation": [va_from, va_to],
            "n_train": len(train), "n_valid": len(valid),
            "excluded_train": dict(s_tr), "excluded_valid": dict(s_va),
            "best_iteration": int(model.best_iteration_ or model.n_estimators),
            "validation_log_loss": rep.log_loss, "validation_brier": rep.brier,
            "validation_calibration_error": rep.calibration_error,
            "market_features": 0}
    META_PATH.write_text(json.dumps(meta, ensure_ascii=False, indent=1),
                         encoding="utf-8")
    print(f"\n保存: {MODEL_PATH.name} (best_iteration={meta['best_iteration']})")
    print(f"  検証 LogLoss {rep.log_loss:.5f} / Brier {rep.brier:.5f} / "
          f"較正誤差 {rep.calibration_error:.5f}")
    return meta


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--fit", action="store_true")
    args = ap.parse_args()
    if args.fit:
        fit()
        return 0
    ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
