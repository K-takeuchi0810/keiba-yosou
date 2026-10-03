"""保存済みの LightGBM モデルの「特徴の並び」を、モデル自身から決める (2026-10-04)。

## なぜ要るか

評価スクリプトは、これまで **今の `FEATURES`** から入力の行列を組み立てていた。
Phase 0.5-4B の後に `h_history_truncated` をモデル入力から外す (31 → 30 特徴) と、
31 特徴で学習した過去のモデル (4B) を評価し直したときに、列の数や並びが合わなくなる。
列が合わないまま黙って評価すると、別の特徴の値をその特徴として読ませることになる。

そこで、モデルを評価するときの特徴の並びは **そのモデル自身の契約** (LightGBM の
`feature_name()`、名前が無ければ meta の `features`) を正本にする。過去のモデルは過去の
並びで再現でき、今の `FEATURES` と違えば、それを記録に残す (黙って列を足したり、
削ったり、並べ替えたりしない)。

- LightGBM は名前を渡さずに学習すると `Column_0`, `Column_1`, ... という名前を付ける
  (4B 以前の Fundamental モデルがこれ。2026-10-04 以降の学習は名前を渡す)。その場合は meta が正本
- 名前を持つモデル (`scripts/market_offset_model.py`) は、名前と meta が一致することを確かめる
- 食い違い・本数の不一致・データに列が無い、はすべて止める (fail-closed)
"""
from __future__ import annotations

import hashlib
import json
import re
import warnings
from pathlib import Path
from typing import Iterable, Sequence

import numpy as np

_AUTO_NAME = re.compile(r"^Column_\d+$")


class ModelSchemaError(ValueError):
    """モデルの特徴の並びが決められない、またはデータと合わない。"""


def _has_real_names(names: Sequence[str]) -> bool:
    return bool(names) and not all(_AUTO_NAME.match(n) for n in names)


def resolve_feature_schema(booster_feature_names: Sequence[str], num_feature: int,
                           meta_features: Sequence[str] | None,
                           current_features: Sequence[str]) -> tuple[list[str], dict]:
    """モデルが期待する特徴の並びと、その出どころの記録を返す。

    - モデルが名前を持つ: その名前。meta にも一覧があれば、完全一致でなければ止める
    - モデルが名前を持たない (`Column_*`): meta の一覧。無ければ止める
    - 本数が `num_feature` と違えば止める
    - 今の `current_features` との違いは記録に残し、警告を出す (止めない。過去のモデルの再現のため)
    """
    names = list(booster_feature_names)
    meta = list(meta_features) if meta_features is not None else None
    if _has_real_names(names):
        if meta is not None and names != meta:
            raise ModelSchemaError(
                "モデルの feature_name() と meta の features が一致しない "
                f"(モデル {len(names)} 本 / meta {len(meta)} 本、"
                f"モデルだけ {sorted(set(names) - set(meta))} / meta だけ {sorted(set(meta) - set(names))})")
        features, source = names, "booster_feature_name"
    else:
        if meta is None:
            raise ModelSchemaError(
                "モデルが特徴の名前を持たず (Column_*)、meta にも features が無い。並びを決められない")
        features, source = meta, "meta_features"
    if len(features) != num_feature:
        raise ModelSchemaError(
            f"特徴の本数が合わない: 並び {len(features)} 本 / モデル {num_feature} 本 ({source})")
    if len(set(features)) != len(features):
        raise ModelSchemaError(f"特徴の並びに重複がある: {features}")
    current = list(current_features)
    provenance = {
        "schema_source": source,
        "n_features": len(features),
        "features": features,
        "matches_current_features": features == current,
        "only_in_model": [f for f in features if f not in current],
        "only_in_current": [f for f in current if f not in features],
        "same_set_different_order": set(features) == set(current) and features != current,
    }
    if not provenance["matches_current_features"]:
        warnings.warn(
            f"モデルの特徴の並びが今の FEATURES と違う (モデルだけ {provenance['only_in_model']} / "
            f"今だけ {provenance['only_in_current']})。モデル自身の並びで評価する",
            stacklevel=2)
    return features, provenance


# 評価の出力に写す、学習時の meta の項目。`predictor/*_model.txt` は同じ名前で上書きされるので、
# ファイル名だけでは「どの学習のモデルを評価したか」を後から辿れない
MODEL_META_KEYS = ("feature_set", "n_features", "git_sha", "git_dirty", "code_version",
                   "train", "validation", "n_train", "n_valid", "best_iteration")


def load_model_schema(model_path: Path, current_features: Sequence[str]) -> tuple[object, list[str], dict]:
    """モデルファイルと同じ場所の `<名前>.meta.json` を読み、Booster・並び・記録を返す。

    記録には、モデルファイルの sha256 と、学習時の meta の主な項目 (`MODEL_META_KEYS`、
    古い meta に無い項目は入れない) も入れる。
    """
    import lightgbm as lgb

    model_path = Path(model_path)
    booster = lgb.Booster(model_file=str(model_path))
    meta_path = model_path.with_suffix(".meta.json")
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
    features, provenance = resolve_feature_schema(
        booster.feature_name(), booster.num_feature(), meta.get("features"), current_features)
    if "n_features" in meta and meta["n_features"] != len(features):
        raise ModelSchemaError(
            f"meta の n_features ({meta['n_features']}) とモデルの特徴の本数 ({len(features)}) が違う")
    provenance["model_file"] = model_path.name
    provenance["model_sha256"] = hashlib.sha256(model_path.read_bytes()).hexdigest()
    provenance["model_meta_file"] = meta_path.name if meta_path.exists() else None
    provenance["model_meta"] = {k: meta[k] for k in MODEL_META_KEYS if k in meta}
    return booster, features, provenance


def assert_model_window_disjoint(model_path: Path, from_date: str, to_date: str) -> None:
    """モデルの学習・検証窓が評価窓と重なっていないことを **実行時に** 確かめる。

    `config.SPLIT_DIVERGENCE` は文書化の強制であって実行時の防御ではない。
    新 train (2022-2024) で学習した booster を旧 `DATA_PERIODS["test"]`
    (2024-2025) で評価すると 2024 が in-sample になるが、宣言制の guard は
    それを落とさない (専門家レビュー指摘)。モデル meta に学習窓が記録して
    あるので、ここで突き合わせる。市場オフセット / Fundamental の評価が共通で使う
    (2026-10-04 に market_offset_eval から移した)。
    """
    meta_path = Path(model_path).with_suffix(".meta.json")
    if not meta_path.exists():
        raise FileNotFoundError(f"モデルの meta が無い: {meta_path}")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    for key in ("train", "validation"):
        span = meta.get(key)
        if not span:
            continue
        lo, hi = span
        if lo <= to_date and from_date <= hi:
            raise ValueError(
                f"モデルの {key} 窓 ({lo}〜{hi}) が評価窓 "
                f"({from_date}〜{to_date}) と重なっている = in-sample。"
                f"モデル: {Path(model_path).name}")


def feature_matrix(rows: Iterable[dict], features: Sequence[str]) -> np.ndarray:
    """行から、指定した並びで入力の行列を作る。列が 1 つでも無ければ止める (黙って 0 で埋めない)。"""
    rows = list(rows)
    missing = sorted({c for r in rows for c in features if c not in r})
    if missing:
        raise ModelSchemaError(f"データにモデルの特徴が無い: {missing}")
    return np.array([[r[c] for c in features] for r in rows], dtype=float)
