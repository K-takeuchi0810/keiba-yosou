"""h_history_truncated をモデル入力から外し、監査用の列にする (2026-10-04、Phase 0.5-4B の後)。

## 固定すること

- `h_history_truncated` は `FEATURES` に無く、`AUDIT_COLUMNS` にある。`FEATURES` は 30 本
- データの行には値が残る。学習の入力の行列には入らない
- 監査用の列の率を計算できる (meta・評価の出力・域外監査に残す)
- 保存済みのモデルを評価するときは **モデル自身の特徴の並び** を使う
  (`predictor.model_schema`)。31 特徴の 4B (凍結) は 31 列で再現でき、30 列のデータでは
  黙って評価せずに止まる。並びとモデル・meta が食い違えば止まる
- 評価スクリプト (`market_offset_eval` / `fundamental_eval`) の `collect()` が、実際にモデル自身の
  並びで入力を作る (今の FEATURES に戻すと、31 特徴の 4B で列が合わずに落ちる)
"""
from __future__ import annotations

import json
import sqlite3
import warnings
from pathlib import Path

import numpy as np
import pytest

from predictor import model_schema as ms
from scripts import fundamental_model as fm

REPO = Path(__file__).resolve().parents[1]
FROZEN = REPO / "data" / "backtest" / "frozen_4b_repaired_31features_20260919"


def _row(features, value=0.5, **extra):
    r = {f: value for f in features}
    r.update(extra)
    return r


# --- 特徴の一覧 -------------------------------------------------------------------

def test_the_flag_is_an_audit_column_not_a_model_feature():
    assert "h_history_truncated" not in fm.FEATURES
    assert fm.AUDIT_COLUMNS == ["h_history_truncated"]
    assert len(fm.FEATURES) == 30
    assert not set(fm.FEATURES) & set(fm.AUDIT_COLUMNS)


def test_the_training_matrix_excludes_the_audit_column():
    """行に監査用の列があっても、学習の入力の行列には入らない (Fundamental / 市場オフセットの両方)。"""
    from scripts import market_offset_model as mom

    rows = [_row(fm.FEATURES, h_history_truncated=1.0, won=0, p_market=0.1),
            _row(fm.FEATURES, value=0.25, h_history_truncated=0.0, won=1, p_market=0.2)]
    X, y = fm._matrix(rows)
    assert X.shape == (2, 30)
    X2, y2, init = mom._matrix(rows)
    assert X2.shape == (2, 30)
    assert mom.FEATURES == fm.FEATURES


def test_audit_rates():
    rows = [{"h_history_truncated": 1.0}, {"h_history_truncated": 0.0},
            {"h_history_truncated": 0.0}, {"h_history_truncated": 1.0}]
    assert fm.audit_rates(rows) == {"h_history_truncated": 0.5}
    assert fm.audit_rates([]) == {"h_history_truncated": None}


# --- モデル自身の特徴の並び ----------------------------------------------------------

CUR = ["a", "b", "c"]


def test_named_model_uses_its_own_names():
    feats, prov = ms.resolve_feature_schema(["a", "b", "c"], 3, ["a", "b", "c"], CUR)
    assert feats == ["a", "b", "c"]
    assert prov["schema_source"] == "booster_feature_name" and prov["matches_current_features"]


def test_unnamed_model_uses_the_meta():
    feats, prov = ms.resolve_feature_schema(["Column_0", "Column_1", "Column_2"], 3, ["a", "b", "c"], CUR)
    assert feats == ["a", "b", "c"] and prov["schema_source"] == "meta_features"


def test_an_older_model_is_kept_with_its_own_columns_and_recorded():
    with pytest.warns(UserWarning):
        feats, prov = ms.resolve_feature_schema(["a", "x", "b", "c"], 4, None, CUR)
    assert feats == ["a", "x", "b", "c"]
    assert prov["matches_current_features"] is False
    assert prov["only_in_model"] == ["x"] and prov["only_in_current"] == []


def test_same_set_in_a_different_order_is_not_silently_reordered():
    with pytest.warns(UserWarning):
        feats, prov = ms.resolve_feature_schema(["c", "b", "a"], 3, None, CUR)
    assert feats == ["c", "b", "a"] and prov["same_set_different_order"] is True


@pytest.mark.parametrize("names,num,meta", [
    (["a", "b", "c"], 3, ["a", "c", "b"]),            # モデルの名前と meta の並びが違う
    (["a", "b", "c"], 3, ["a", "b"]),                 # 本数が違う
    (["Column_0", "Column_1"], 2, None),             # 名前が無く meta も無い
    (["Column_0", "Column_1", "Column_2"], 3, ["a", "b"]),  # meta とモデルの本数が違う
    (["a", "a", "b"], 3, None),                       # 重複
])
def test_schema_conflicts_fail_closed(names, num, meta):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        with pytest.raises(ms.ModelSchemaError):
            ms.resolve_feature_schema(names, num, meta, CUR)


def test_missing_data_columns_fail_closed():
    with pytest.raises(ms.ModelSchemaError, match="b"):
        ms.feature_matrix([{"a": 1.0}], ["a", "b"])
    assert ms.feature_matrix([{"a": 1.0, "b": 2.0, "z": 9.0}], ["b", "a"]).tolist() == [[2.0, 1.0]]


# --- 凍結した 4B (31 特徴) の再現 ---------------------------------------------------

@pytest.mark.parametrize("name", ["market_offset_model", "fundamental_model"])
def test_the_frozen_4b_model_is_reproduced_with_its_31_columns(name):
    path = FROZEN / f"{name}.txt"
    if not path.exists():
        pytest.skip(f"凍結した 4B が無い: {path}")
    with pytest.warns(UserWarning):
        booster, feats, prov = ms.load_model_schema(path, fm.FEATURES)
    meta = json.loads((FROZEN / f"{name}.meta.json").read_text(encoding="utf-8"))
    assert feats == meta["features"] and len(feats) == 31
    assert prov["only_in_model"] == ["h_history_truncated"] and prov["only_in_current"] == []
    rng = np.random.default_rng(0)
    rows = [{f: float(v) for f, v in zip(feats, rng.normal(size=31))} for _ in range(50)]
    direct = booster.predict(np.array([[r[f] for f in feats] for r in rows]), raw_score=True)
    via = booster.predict(ms.feature_matrix(rows, feats), raw_score=True)
    assert np.allclose(direct, via)
    # 30 列 (今の FEATURES) しかないデータでは、黙って評価せずに止まる
    rows30 = [{f: r[f] for f in fm.FEATURES} for r in rows]
    with pytest.raises(ms.ModelSchemaError, match="h_history_truncated"):
        ms.feature_matrix(rows30, feats)


# --- 評価スクリプトの配線 -----------------------------------------------------------

def _empty_races_db(path: Path) -> Path:
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE races (race_year TEXT, race_month_day TEXT, track_code TEXT, "
                 "kaiji TEXT, nichiji TEXT, race_num TEXT, start_time TEXT, data_div TEXT)")
    conn.commit()
    conn.close()
    return path


@pytest.mark.parametrize("module_name,model", [("market_offset_eval", "market_offset_model"),
                                               ("fundamental_eval", "fundamental_model")])
def test_collect_builds_the_input_from_the_model_schema(tmp_path, monkeypatch, module_name, model):
    """collect() が、今の FEATURES (30) ではなくモデル自身の並び (4B は 31) で入力を作ること。

    今の FEATURES に戻す変異では、31 特徴のモデルに 30 列を渡して LightGBM が落ちる。
    レース表は空なので、予測のあとは全行が「レース無し」で外れる (ここで見たいのは入力の組み立て)。
    """
    import importlib

    path = FROZEN / f"{model}.txt"
    if not path.exists():
        pytest.skip(f"凍結した 4B が無い: {path}")
    mod = importlib.import_module(f"scripts.{module_name}")
    feats = json.loads((FROZEN / f"{model}.meta.json").read_text(encoding="utf-8"))["features"]
    rows = [_row(feats, race_id="2026-0712-02-01-01-01", horse_num=f"{i:02d}", won=0,
                 date="20260712", h_history_truncated=float(i % 2)) for i in range(1, 5)]
    monkeypatch.setattr(mod, "build_dataset", lambda f, t: (rows, {}))
    monkeypatch.setattr(mod, "MODEL_PATH", path)
    monkeypatch.setattr(mod, "DB_PATH", _empty_races_db(tmp_path / "races.db"))
    with pytest.warns(UserWarning):
        samples, counts, info = mod.collect("20260601", "20260731")
    schema = info["model_feature_schema"]
    assert schema["n_features"] == 31 and schema["only_in_model"] == ["h_history_truncated"]
    assert schema["matches_current_features"] is False
    assert info["audit_columns"] == ["h_history_truncated"]
    assert info["audit_rates_eval_rows"] == {"h_history_truncated": 0.5}
    assert counts.get("no_race") == 1 and samples == []


# --- 域外監査は監査用の列も監視する -----------------------------------------------------

def test_the_domain_audit_still_monitors_the_audit_column(monkeypatch):
    from scripts import feature_domain_audit as fda
    import db

    monkeypatch.setattr(fda, "snapshot", lambda conn: {})
    monkeypatch.setattr(db, "DB_PATH", ":memory:")
    feats = ["h_starts"]
    splits = {"train": [{"h_starts": 1.0, "h_history_truncated": 1.0}, {"h_starts": 2.0, "h_history_truncated": 0.0}],
              "strategy_dev": [{"h_starts": 3.0, "h_history_truncated": 0.0}]}
    out = fda.run(feats, splits, audit_columns=["h_history_truncated"])
    recs = {r["feature"]: r for r in out["features"]}
    assert recs["h_history_truncated"]["audit_only"] is True and recs["h_starts"]["audit_only"] is False
    assert out["meta"]["audit_rates"] == {"train": {"h_history_truncated": 0.5},
                                          "strategy_dev": {"h_history_truncated": 0.0}}
