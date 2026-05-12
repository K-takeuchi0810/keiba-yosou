"""LightGBM 推論レイヤ。

`scripts/train_lgbm.py` で保存された model.txt + features.json + meta.json を
ロードし、`predict_lgbm_probs(horses, race, conn)` を提供する。

設計方針:
- ロードは mtime キャッシュ。ファイルが更新されたら次回呼出しで自動再読込。
- LightGBM がインストールされていない、または model.txt 不在の環境では
  `load_lgbm()` が None を返し、`predict_lgbm_probs` は空 dict を返す。
  → 呼び出し側 (predictor.rules) で rule のみ運用にフォールバック。
- 確率は race 内で normalize (合計 1) して返す。Σp=1 制約はレース内ゼロサム性
  (∃ winner) と整合する。
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

_MODEL_DIR = Path(__file__).resolve().parent
MODEL_PATH = _MODEL_DIR / "lgbm_model.txt"
FEATURES_PATH = _MODEL_DIR / "lgbm_features.json"
META_PATH = _MODEL_DIR / "lgbm_meta.json"

# (mtime, booster, features_dict, meta_dict) のキャッシュ
_CACHE: tuple | None = None


def load_lgbm() -> tuple[object, dict, dict] | None:
    """LightGBM model を読み込む。失敗時は None。

    戻り: (booster, features_dict, meta_dict) または None。
    """
    global _CACHE
    if os.environ.get("PRED_DISABLE_LGBM") == "1":
        return None
    if not MODEL_PATH.exists() or not FEATURES_PATH.exists():
        return None
    try:
        mtime = MODEL_PATH.stat().st_mtime
    except OSError:
        return None
    if _CACHE and _CACHE[0] == mtime:
        return (_CACHE[1], _CACHE[2], _CACHE[3])
    try:
        import lightgbm as lgb  # type: ignore[import-not-found]
    except ModuleNotFoundError:
        logger.warning("lightgbm not installed; LGBM disabled. Run from .venv64.")
        return None
    try:
        booster = lgb.Booster(model_file=str(MODEL_PATH))
        features = json.loads(FEATURES_PATH.read_text(encoding="utf-8"))
        meta = (
            json.loads(META_PATH.read_text(encoding="utf-8"))
            if META_PATH.exists() else {}
        )
    except Exception as e:
        logger.warning("failed to load LGBM model: %s", e)
        return None
    tf, tt = meta.get("trained_from"), meta.get("trained_to")
    if tf and tt:
        logger.info(
            "lgbm loaded: trained %s-%s (val_brier=%s, val_logloss=%s)",
            tf, tt, meta.get("val_brier"), meta.get("val_logloss"),
        )
    _CACHE = (mtime, booster, features, meta)
    return booster, features, meta


def _encode_categorical(name: str, value, categorical_maps: dict) -> int:
    mapping = categorical_maps.get(name, {})
    return mapping.get(str(value or ""), len(mapping))


def _feature_vector(feat: dict, features_def: dict) -> list[float]:
    """compute_features dict → features.json の順序で flat list。"""
    import math
    vec: list[float] = []
    for k in features_def.get("numeric", []):
        v = feat.get(k)
        if v is None:
            vec.append(math.nan)
        elif isinstance(v, bool):
            vec.append(1.0 if v else 0.0)
        else:
            try:
                vec.append(float(v))
            except (TypeError, ValueError):
                vec.append(math.nan)
    for k in features_def.get("boolean", []):
        vec.append(1.0 if feat.get(k) else 0.0)
    cat_maps = features_def.get("categorical_maps", {})
    for k in features_def.get("categorical", []):
        vec.append(float(_encode_categorical(k, feat.get(k), cat_maps)))
    return vec


def predict_lgbm_probs(
    horses: list[dict],
    race: dict,
    conn=None,
    feature_cache: dict | None = None,
) -> dict[str, float]:
    """各馬の P(win) を返す。LightGBM が無効なら空 dict。

    引数の `horses` は dict (DB 行)、`race` は dict (DB 行)、`conn` は SQLite 接続。
    feature_cache は呼出し側が用意する compute_features キャッシュ。
    """
    loaded = load_lgbm()
    if loaded is None:
        return {}
    booster, features_def, _meta = loaded
    try:
        from predictor.features import compute_features
    except ImportError:
        return {}
    try:
        import numpy as np  # type: ignore[import-not-found]
    except ModuleNotFoundError:
        return {}
    cache = feature_cache if feature_cache is not None else {}
    rows: list[list[float]] = []
    horse_nums: list[str] = []
    for h in horses:
        try:
            feat = compute_features(conn, h, race, cache=cache)
        except Exception as e:
            logger.warning("compute_features failed: %s", e)
            continue
        rows.append(_feature_vector(feat, features_def))
        horse_nums.append(h.get("horse_num", ""))
    if not rows:
        return {}
    X = np.array(rows, dtype=np.float32)
    try:
        raw = booster.predict(X)
    except Exception as e:
        logger.warning("LGBM predict failed: %s", e)
        return {}
    raw = np.clip(np.asarray(raw, dtype=np.float64), 1e-9, 1.0)
    norm = raw / raw.sum() if raw.sum() > 0 else raw
    return {hn: float(p) for hn, p in zip(horse_nums, norm)}


def blend(p_rule: dict[str, float], p_lgbm: dict[str, float], w_rule: float = 0.5) -> dict[str, float]:
    """rule prob と LGBM prob の重み付き平均。p_lgbm 空なら rule をそのまま返す。

    両方に存在する horse_num についてのみ blend。片方にしかないキーは
    その値をそのまま返す (= 欠落側を 0 として重み付けせず、頑健にする)。
    """
    if not p_lgbm:
        return dict(p_rule)
    if not p_rule:
        return dict(p_lgbm)
    w_rule = max(0.0, min(1.0, w_rule))
    w_lgbm = 1.0 - w_rule
    keys = set(p_rule) | set(p_lgbm)
    return {
        k: w_rule * p_rule.get(k, 0.0) + w_lgbm * p_lgbm.get(k, 0.0)
        for k in keys
    }
