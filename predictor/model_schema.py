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
  (`scripts/fundamental_model.py` の Fundamental モデルがこれ)。その場合は meta が正本
- 名前を持つモデル (`scripts/market_offset_model.py`) は、名前と meta が一致することを確かめる
- 食い違い・本数の不一致・データに列が無い、はすべて止める (fail-closed)
"""
from __future__ import annotations

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


def load_model_schema(model_path: Path, current_features: Sequence[str]):
    """モデルファイルと同じ場所の `<名前>.meta.json` を読み、Booster・並び・記録を返す。"""
    import lightgbm as lgb

    booster = lgb.Booster(model_file=str(model_path))
    meta_path = Path(model_path).with_suffix(".meta.json")
    meta_features = None
    if meta_path.exists():
        meta_features = json.loads(meta_path.read_text(encoding="utf-8")).get("features")
    features, provenance = resolve_feature_schema(
        booster.feature_name(), booster.num_feature(), meta_features, current_features)
    provenance["model_file"] = Path(model_path).name
    return booster, features, provenance


def feature_matrix(rows: Iterable[dict], features: Sequence[str]) -> np.ndarray:
    """行から、指定した並びで入力の行列を作る。列が 1 つでも無ければ止める (黙って 0 で埋めない)。"""
    rows = list(rows)
    missing = sorted({c for r in rows for c in features if c not in r})
    if missing:
        raise ModelSchemaError(f"データにモデルの特徴が無い: {missing}")
    return np.array([[r[c] for c in features] for r in rows], dtype=float)
