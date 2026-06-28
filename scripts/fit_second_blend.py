"""二段ロジット再ブレンド (Benter 補正) の係数を fit するスクリプト。

設計: docs/SECOND_LOGIT_BLEND_DESIGN.md
背景: deep-research (memory/project_roi_research_2026_06_28) が特定した
      「モデルの value 判定は公開オッズへ regress する」現象を、
      Blend#2 を線形手設定から outcome-fit のロジットへ置換して補正する。

学習する係数 (binary logistic):
    z = b0 + b1 * log(model_prob) + b2 * log(market_prob)
    p_raw = sigmoid(z)
    investment_prob = p_raw / Σ_race(p_raw)   # 適用時にレース内再正規化

入力確率は **production の predict_race / calibrator / market 関数を再利用**して
作るため train-serve skew が無い:
    model_prob  = _apply_calibrator({horse_num: raw_blended_probability})
                  (calibrator 適用後・レース内正規化済み = Blend#2 への入力と同一)
    market_prob = _market_probabilities(...)  (単勝オッズ implied のレース内正規化)
    label y     = 単勝配当 > 0 (= 勝ち馬。同着は複数 1)

walk-forward 規律: **fit 窓と評価窓を重ねないこと**。
    推奨運用 = fit 2025 通年 → 評価 OOS 2026 (calibrator と同じ時系列分離)。

使い方:
    .venv64/Scripts/python.exe -m scripts.fit_second_blend \
        --from 20250101 --to 20251231

出力: predictor/second_blend.json (provenance + 係数 + train 指標)
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np
from sklearn.linear_model import LogisticRegression

from predictor.rules import (
    RULES_VERSION,
    _apply_calibrator,
    _market_probabilities,
    is_tentative,
    predict_race,
)
from scripts.backtest import (
    get_payout_row,
    horses_for_race,
    list_races,
    open_db,
    payout_from_row,
)

OUT_DEFAULT = Path(__file__).resolve().parent.parent / "predictor" / "second_blend.json"


def _build_training_rows(
    conn,
    from_date: str,
    to_date: str,
    jra_only: bool,
    skip_tentative: bool,
    progress_every: int = 200,
) -> tuple[list[list[float]], list[int], int]:
    """各レース×各馬の (log model_prob, log market_prob, y) を集める。

    production の predict_race + calibrator + market 関数を再利用するので、
    serving 時の Blend#2 入力と完全に一致する。
    """
    races = list_races(conn, from_date, to_date, jra_only=jra_only)
    n_total = len(races)
    feature_cache: dict = {}
    X: list[list[float]] = []
    y: list[int] = []
    n_races_used = 0
    started = time.time()
    for i, race in enumerate(races, 1):
        if progress_every and i % progress_every == 0:
            rate = i / (time.time() - started) if time.time() > started else 0
            print(f"  [{i}/{n_total}] {rate:.1f} races/s ...", file=sys.stderr, flush=True)
        horses = horses_for_race(conn, race)
        if not horses:
            continue
        # ラベル元 (払戻行) が無いレースは勝敗を確定できないので除外。
        payout_row = get_payout_row(conn, race)
        if payout_row is None:
            continue
        preds = predict_race(horses, conn=conn, race=race, cache=feature_cache)
        if not preds:
            continue
        if skip_tentative and is_tentative(preds):
            continue
        raw = {p.horse_num: p.raw_blended_probability for p in preds}
        model_prob = _apply_calibrator(raw)
        market_prob = _market_probabilities([(h, 0.0, [], 0.0) for h in horses])
        used = False
        for p in preds:
            mp = model_prob.get(p.horse_num, 0.0)
            kp = market_prob.get(p.horse_num, 0.0)
            if mp <= 0.0 or kp <= 0.0:
                continue
            won = 1 if payout_from_row(payout_row, p.horse_num, "tan") > 0 else 0
            X.append([math.log(mp), math.log(kp)])
            y.append(won)
            used = True
        if used:
            n_races_used += 1
    return X, y, n_races_used


def main() -> int:
    ap = argparse.ArgumentParser(description="二段ロジット再ブレンド係数の fit")
    ap.add_argument("--from", dest="from_date", required=True, help="YYYYMMDD (fit 窓 開始)")
    ap.add_argument("--to", dest="to_date", required=True, help="YYYYMMDD (fit 窓 終了)")
    ap.add_argument("--db", default=None, help="SQLite DB path")
    ap.add_argument("--out", default=str(OUT_DEFAULT), help="出力 JSON path")
    ap.add_argument("--no-jra-only", action="store_true", help="JRA 以外も含める")
    ap.add_argument(
        "--skip-tentative", action="store_true",
        help="暫定 (情報不足) レースを除外して fit する",
    )
    ap.add_argument(
        "--C", type=float, default=1e4,
        help="LogisticRegression の逆正則化強度 (大きいほど near-unregularized)",
    )
    args = ap.parse_args()

    started = time.time()
    with (open_db(args.db) if args.db else open_db()) as conn:
        X, y, n_races = _build_training_rows(
            conn,
            args.from_date,
            args.to_date,
            jra_only=not args.no_jra_only,
            skip_tentative=args.skip_tentative,
        )

    if len(y) < 100:
        print(f"ERROR: 学習サンプルが少なすぎます (n={len(y)})。窓を広げてください。", file=sys.stderr)
        return 1
    n_pos = int(sum(y))
    if n_pos == 0 or n_pos == len(y):
        print(f"ERROR: ラベルが単一クラス (pos={n_pos}/{len(y)})。fit 不能。", file=sys.stderr)
        return 1

    Xa = np.asarray(X, dtype=float)
    ya = np.asarray(y, dtype=int)
    clf = LogisticRegression(C=args.C, max_iter=2000)
    clf.fit(Xa, ya)
    b1, b2 = (float(v) for v in clf.coef_[0])
    b0 = float(clf.intercept_[0])

    # train 指標 (in-sample。採否判断は別窓 OOS で行うこと)。
    proba = clf.predict_proba(Xa)[:, 1]
    eps = 1e-12
    logloss = float(
        -np.mean(ya * np.log(proba + eps) + (1 - ya) * np.log(1 - proba + eps))
    )
    base_rate = float(np.mean(ya))

    payload = {
        "type": "second_logit_blend",
        "rule_version": RULES_VERSION,
        "trained_from": args.from_date,
        "trained_to": args.to_date,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source_count": len(y),
        "races_used": n_races,
        "positive_count": n_pos,
        "base_rate": round(base_rate, 6),
        "C": args.C,
        "skip_tentative": bool(args.skip_tentative),
        "coefficients": {
            "intercept": b0,
            "log_model": b1,
            "log_market": b2,
        },
        "train_logloss": round(logloss, 6),
        "elapsed_sec": round(time.time() - started, 1),
        "apply_note": (
            "z = intercept + log_model*log(model_prob) + log_market*log(market_prob); "
            "p = sigmoid(z); race 内で Σ=1 に再正規化して investment_prob とする。"
        ),
    }
    out_path = Path(args.out)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"fit 完了: n={len(y)} races={n_races} pos={n_pos} base_rate={base_rate:.4f}")
    print(f"  coefficients: b0={b0:.4f}  b1(log_model)={b1:.4f}  b2(log_market)={b2:.4f}")
    print(f"  train_logloss={logloss:.4f}  (in-sample, 採否は OOS で判定)")
    print(f"  -> {out_path}")
    # 解釈ヒント: b1/(b1+b2) が「実効モデル重み」の目安。現行手設定 0.78-0.85 と比較。
    if (b1 + b2) != 0:
        eff = b1 / (b1 + b2)
        print(f"  実効モデル重み目安 b1/(b1+b2)={eff:.3f}  (現行手設定 model_blend=0.78-0.85)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
