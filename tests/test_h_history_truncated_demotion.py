"""h_history_truncated をモデル入力から外し、監査用の列にする (2026-10-04、Phase 0.5-4B の後)。

## 固定すること

- `h_history_truncated` は `FEATURES` に無く、`AUDIT_COLUMNS` にある。`FEATURES` は 30 本
- データの行には値が残る。学習の入力の行列には入らない
- 監査用の列の率を計算できる (meta・評価の出力・域外監査に残す)
- 保存済みのモデルを評価するときは **モデル自身の特徴の並び** を使う
  (`predictor.model_schema`)。31 特徴の 4B (凍結) は 31 列で再現でき、30 列のデータでは
  黙って評価せずに止まる。並びとモデル・meta が食い違えば止まる
- 評価スクリプト (`market_offset_eval` / `fundamental_eval`) の `collect()` が、実際にモデル自身の
  並びで入力を作る (今の FEATURES に戻すと、31 特徴の 4B で列が合わずに落ちる)。行ごと・特徴ごとに
  違う値で、予測値そのものが直接の計算と一致する (列の並べ替えも検出する)
- 学習 (`fit()`) は特徴の名前をモデルに刻み (Fundamental も Column_* にしない)、meta に世代名・本数・
  監査用の列の率 (年別も) を残す
- 評価の出力には、モデルファイルの sha256 と学習時の meta の主な項目が入る
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
    # 非対称な数にする (2/4 だと「立っていない行を数える」変異でも 0.5 になって素通りした)
    rows = [{"h_history_truncated": 1.0}, {"h_history_truncated": 0.0},
            {"h_history_truncated": 1.0}, {"h_history_truncated": 1.0}]
    assert fm.audit_rates(rows) == {"h_history_truncated": 0.75}
    assert fm.audit_rates([]) == {"h_history_truncated": None}
    assert fm.audit_rates([{"x": 1.0}, {"x": 0.0}, {"x": 0.0}], ["x"]) == {"x": pytest.approx(1 / 3)}
    # 列そのものが無い行は 0 として数えない
    with pytest.raises(KeyError):
        fm.audit_rates([{"h_history_truncated": 1.0}, {"other": 0.0}])


@pytest.mark.parametrize("bad", [float("nan"), 0.5, 2.0, None, "x"])
def test_audit_rates_refuse_a_non_binary_value(bad):
    """NaN などを黙って「立っていない」側に数えない。"""
    with pytest.raises(ValueError, match="0/1"):
        fm.audit_rates([{"h_history_truncated": 1.0}, {"h_history_truncated": bad}])


def test_audit_rates_by_year():
    rows = ([{"date": "20220105", "h_history_truncated": 1.0}] * 3
            + [{"date": "20220610", "h_history_truncated": 0.0}]
            + [{"date": "20230301", "h_history_truncated": 1.0}]
            + [{"date": "20230302", "h_history_truncated": 0.0}] * 4)
    assert fm.audit_rates_by_year(rows) == {"h_history_truncated": {"2022": 0.75, "2023": 0.2}}


def test_audit_meta_records_the_generation_and_the_rates():
    train = [{"date": "20220101", "h_history_truncated": 1.0}, {"date": "20230101", "h_history_truncated": 0.0},
             {"date": "20230102", "h_history_truncated": 0.0}, {"date": "20230103", "h_history_truncated": 0.0}]
    valid = [{"date": "20250101", "h_history_truncated": 0.0}]
    m = fm.audit_meta(train, valid)
    assert m["feature_set"] == "post_demotion_repaired_30features" and m["n_features"] == 30
    assert m["audit_columns"] == ["h_history_truncated"]
    assert m["audit_rates"] == {"train": {"h_history_truncated": 0.25}, "validation": {"h_history_truncated": 0.0}}
    assert m["audit_rates_by_year"]["train"] == {"h_history_truncated": {"2022": 1.0, "2023": 0.0}}
    assert m["audit_rates_by_year"]["validation"] == {"h_history_truncated": {"2025": 0.0}}


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


def test_a_model_with_fewer_features_than_now_is_recorded():
    """次に特徴を足したとき (古いモデルの方が少ない) の記録。"""
    with pytest.warns(UserWarning):
        feats, prov = ms.resolve_feature_schema(["a", "b"], 2, None, CUR)
    assert feats == ["a", "b"]
    assert prov["only_in_current"] == ["c"] and prov["only_in_model"] == []
    assert prov["same_set_different_order"] is False


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
    # 欠落が先頭の行ではなく途中の行にあっても止める
    with pytest.raises(ms.ModelSchemaError, match="b"):
        ms.feature_matrix([{"a": 1.0, "b": 2.0}, {"a": 1.0, "b": 2.0}, {"a": 1.0}], ["a", "b"])


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
    # 評価の出力に残す記録: ファイルの sha256 (凍結の manifest と一致) と学習時の meta
    manifest = json.loads((FROZEN / "FREEZE_MANIFEST.json").read_text(encoding="utf-8"))
    sha = {f["frozen_as"]: f["sha256"] for f in manifest["files"]}
    assert prov["model_sha256"] == sha[f"{name}.txt"]
    assert prov["model_meta_file"] == f"{name}.meta.json"
    assert prov["model_meta"]["git_sha"] == meta["git_sha"]
    assert prov["model_meta"]["train"] == meta["train"]
    assert set(prov["model_meta"]) == set(ms.MODEL_META_KEYS) & set(meta)
    assert prov["model_file"] == f"{name}.txt"
    assert "feature_set" not in prov["model_meta"]       # 4B の meta には世代名が無い (入れたふりをしない)


@pytest.mark.parametrize("n_features", [30, 32])
def test_meta_n_features_disagreeing_with_the_model_fails_closed(tmp_path, n_features):
    src = FROZEN / "market_offset_model.txt"
    if not src.exists():
        pytest.skip(f"凍結した 4B が無い: {src}")
    (tmp_path / "m.txt").write_bytes(src.read_bytes())
    meta = json.loads((FROZEN / "market_offset_model.meta.json").read_text(encoding="utf-8"))
    meta["n_features"] = n_features
    (tmp_path / "m.meta.json").write_text(json.dumps(meta), encoding="utf-8")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        with pytest.raises(ms.ModelSchemaError, match="n_features"):
            ms.load_model_schema(tmp_path / "m.txt", fm.FEATURES)


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
    行ごと・特徴ごとに違う値を使い、collect() が書いた予測値 (margin / p_raw) が、モデル自身の並びでの
    直接の計算と一致することも確かめる (全特徴を同じ値にすると、列の並べ替えが見えずに素通りした)。
    レース表は空なので、予測のあとは全行が「レース無し」で外れる (ここで見たいのは入力の組み立て)。
    """
    import importlib

    import lightgbm as lgb

    path = FROZEN / f"{model}.txt"
    if not path.exists():
        pytest.skip(f"凍結した 4B が無い: {path}")
    mod = importlib.import_module(f"scripts.{module_name}")
    feats = json.loads((FROZEN / f"{model}.meta.json").read_text(encoding="utf-8"))["features"]
    rng = np.random.default_rng(7)
    rows = []
    for i in range(1, 41):
        r = {f: float(v) for f, v in zip(feats, rng.normal(scale=3.0, size=len(feats)))}
        r.update(race_id="2026-0712-02-01-01-01", horse_num=f"{i:02d}", won=0,
                 date="20260712" if i <= 30 else "20250712",
                 h_history_truncated=1.0 if i <= 10 else 0.0)
        rows.append(r)
    monkeypatch.setattr(mod, "build_dataset", lambda f, t: (rows, {}))
    monkeypatch.setattr(mod, "MODEL_PATH", path)
    monkeypatch.setattr(mod, "DB_PATH", _empty_races_db(tmp_path / "races.db"))
    with pytest.warns(UserWarning):
        samples, counts, info = mod.collect("20260601", "20260731")
    schema = info["model_feature_schema"]
    assert schema["n_features"] == 31 and schema["only_in_model"] == ["h_history_truncated"]
    assert schema["matches_current_features"] is False
    assert info["audit_columns"] == ["h_history_truncated"]
    assert info["audit_rates_eval_rows"] == {"h_history_truncated": 0.25}
    assert info["audit_rates_by_year_eval_rows"] == {"h_history_truncated": {"2025": 0.0, "2026": 1 / 3}}
    assert schema["model_sha256"] and schema["model_meta"]["train"]
    assert counts.get("no_race") == 1 and samples == []
    # 予測値が、モデル自身の並びでの直接の計算と一致する
    booster = lgb.Booster(model_file=str(path))
    X = np.array([[r[f] for f in feats] for r in rows])
    if module_name == "market_offset_eval":
        got, want = [r["margin"] for r in rows], booster.predict(X, raw_score=True)
    else:
        got, want = [r["p_raw"] for r in rows], booster.predict(X)
    assert np.allclose(got, want)
    assert np.std(want) > 0      # 値が全部同じだと、並べ替えを検出できない


@pytest.mark.parametrize("module_name", ["market_offset_eval", "fundamental_eval"])
def test_collect_refuses_a_model_that_contains_a_market_feature(tmp_path, monkeypatch, module_name):
    """モデル自身の並びに市場由来の特徴があれば、予測する前に止める (今の FEATURES の検査だけでは見えない)。"""
    import importlib

    import lightgbm as lgb

    mod = importlib.import_module(f"scripts.{module_name}")
    names = ["h_starts", "track_recent_30d_avg_winning_pop"]
    rng = np.random.default_rng(0)
    X = rng.normal(size=(200, 2))
    booster = lgb.train({"objective": "binary", "verbose": -1, "min_data_in_leaf": 5},
                        lgb.Dataset(X, label=(X[:, 0] > 0).astype(int), feature_name=names),
                        num_boost_round=3)
    path = tmp_path / "model.txt"
    booster.save_model(str(path))
    # 評価窓と重ならない学習・検証の窓を持たせる (窓のガードは市場特徴の検査より前に効くので)
    (tmp_path / "model.meta.json").write_text(json.dumps({
        "features": names, "train": ["20220101", "20241231"], "validation": ["20250101", "20251231"]}),
        encoding="utf-8")
    rows = [{"h_starts": 1.0, "track_recent_30d_avg_winning_pop": 2.0, "race_id": "r", "horse_num": "01",
             "won": 0, "date": "20260712", "h_history_truncated": 0.0}]
    monkeypatch.setattr(mod, "build_dataset", lambda f, t: (rows, {}))
    monkeypatch.setattr(mod, "MODEL_PATH", path)
    monkeypatch.setattr(mod, "DB_PATH", _empty_races_db(tmp_path / "races.db"))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        with pytest.raises(ValueError, match="track_recent_30d_avg_winning_pop"):
            mod.collect("20260601", "20260731")
    assert "margin" not in rows[0] and "p_raw" not in rows[0]


# --- 学習 (fit) の成果物 -----------------------------------------------------------------

def _synthetic_rows(n: int, year_from: int, seed: int) -> list[dict]:
    rng = np.random.default_rng(seed)
    out = []
    for i in range(n):
        r = {f: float(v) for f, v in zip(fm.FEATURES, rng.normal(size=len(fm.FEATURES)))}
        r.update(race_id=f"{year_from + i % 3}-r{i // 10}", horse_num=f"{i % 10 + 1:02d}",
                 date=f"{year_from + i % 3}0601",
                 won=int(rng.random() < 1 / (1 + np.exp(-r["h_starts"] * 2))),
                 h_history_truncated=1.0 if i % 4 == 0 else 0.0)
        out.append(r)
    return out


def _db_with_ingest_ledger(path: Path) -> Path:
    """学習の meta の data_version を確かめるための、取り込み台帳を 1 行持つ DB。"""
    _empty_races_db(path)
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE ingested_files (path TEXT, ingested_at TEXT)")
    conn.execute("INSERT INTO ingested_files VALUES ('x', '2026-10-04T00:00:00')")
    conn.commit()
    conn.close()
    return path


def _split_data(seed: int) -> dict[str, list[dict]]:
    from config import DATA_SPLIT

    tr, va = DATA_SPLIT["train"]["from"], DATA_SPLIT["validation"]["from"]
    return {tr: _synthetic_rows(900, int(tr[:4]), seed), va: _synthetic_rows(300, int(va[:4]), seed + 1)}


def _check_fitted_artifacts(model_path: Path, meta_path: Path, train: list[dict]) -> None:
    import lightgbm as lgb

    booster = lgb.Booster(model_file=str(model_path))
    assert booster.feature_name() == fm.FEATURES        # Column_* ではなく名前が刻まれる
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    assert meta["features"] == fm.FEATURES
    assert meta["feature_set"] == fm.FEATURE_SET and meta["n_features"] == 30
    assert meta["audit_columns"] == ["h_history_truncated"]
    assert meta["audit_rates"]["train"] == fm.audit_rates(train)
    assert meta["audit_rates"]["train"]["h_history_truncated"] == pytest.approx(0.25)
    assert meta["audit_rates_by_year"]["train"] == fm.audit_rates_by_year(train)
    # どの取り込み状態の DB で学習したかが残る (閉じた接続で取ると "nodata" になっていた)
    assert meta["data_version"] not in (None, "nodata")
    # 名前と meta が揃うので、評価側は名前で並びを決め、今の FEATURES と一致する
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        _, feats, prov = ms.load_model_schema(model_path, fm.FEATURES)
    assert feats == fm.FEATURES and prov["schema_source"] == "booster_feature_name"
    assert prov["matches_current_features"] is True
    assert prov["model_meta"]["feature_set"] == fm.FEATURE_SET


def test_fundamental_fit_names_the_features_and_records_the_audit(tmp_path, monkeypatch):
    data = _split_data(1)
    monkeypatch.setattr(fm, "build_dataset", lambda f, t: (data[f], {}))
    monkeypatch.setattr(fm, "MODEL_PATH", tmp_path / "fundamental_model.txt")
    monkeypatch.setattr(fm, "META_PATH", tmp_path / "fundamental_model.meta.json")
    monkeypatch.setattr(fm, "DB_PATH", _db_with_ingest_ledger(tmp_path / "races.db"))
    with warnings.catch_warnings():
        warnings.simplefilter("error", UserWarning)    # sklearn の「名前が無い」警告を出さない
        fm.fit()
    _check_fitted_artifacts(tmp_path / "fundamental_model.txt", tmp_path / "fundamental_model.meta.json",
                            next(iter(data.values())))


def test_market_offset_fit_names_the_features_and_records_the_audit(tmp_path, monkeypatch):
    from scripts import market_offset_model as mom

    data = _split_data(3)
    market = {(r["race_id"], r["horse_num"]): 0.1 for rows in data.values() for r in rows}
    monkeypatch.setattr(mom, "build_dataset", lambda f, t: (data[f], {}))
    monkeypatch.setattr(mom, "training_market", lambda conn, y, t: market)
    monkeypatch.setattr(mom, "payout_agreement", lambda conn, y, t: 1.0)
    monkeypatch.setattr(mom, "MODEL_PATH", tmp_path / "market_offset_model.txt")
    monkeypatch.setattr(mom, "META_PATH", tmp_path / "market_offset_model.meta.json")
    monkeypatch.setattr(mom, "DB_PATH", _db_with_ingest_ledger(tmp_path / "races.db"))
    mom.fit()
    _check_fitted_artifacts(tmp_path / "market_offset_model.txt", tmp_path / "market_offset_model.meta.json",
                            next(iter(data.values())))


# --- 域外監査は監査用の列も監視する -----------------------------------------------------

def test_the_domain_audit_still_monitors_the_audit_column(monkeypatch):
    from scripts import feature_domain_audit as fda
    import db

    monkeypatch.setattr(fda, "snapshot", lambda conn: {})
    monkeypatch.setattr(db, "DB_PATH", ":memory:")
    feats = ["h_starts"]
    splits = {"train": [{"h_starts": 1.0, "h_history_truncated": 1.0, "flag_x": 0.0, "date": "20220101"},
                        {"h_starts": 2.0, "h_history_truncated": 0.0, "flag_x": 0.0, "date": "20230101"},
                        {"h_starts": 2.0, "h_history_truncated": 0.0, "flag_x": 0.0, "date": "20230102"},
                        {"h_starts": 2.0, "h_history_truncated": 0.0, "flag_x": 1.0, "date": "20230103"}],
              "strategy_dev": [{"h_starts": 3.0, "h_history_truncated": 0.0, "flag_x": 1.0, "date": "20260601"},
                               {"h_starts": 3.0, "h_history_truncated": 1.0, "flag_x": 1.0, "date": "20260602"}]}
    # 既定 (AUDIT_COLUMNS) に無い列名も渡す: 引数を無視して既定の列を数える誤りを検出する
    out = fda.run(feats, splits, audit_columns=["h_history_truncated", "flag_x"])
    recs = {r["feature"]: r for r in out["features"]}
    assert recs["h_history_truncated"]["audit_only"] is True and recs["h_starts"]["audit_only"] is False
    assert out["meta"]["audit_rates"] == {"train": {"h_history_truncated": 0.25, "flag_x": 0.25},
                                          "strategy_dev": {"h_history_truncated": 0.5, "flag_x": 1.0}}
    assert out["meta"]["audit_rates_by_year"]["train"] == {"h_history_truncated": {"2022": 1.0, "2023": 0.0},
                                                           "flag_x": {"2022": 0.0, "2023": 1 / 3}}
    assert out["meta"]["audit_rates_by_year"]["strategy_dev"] == {"h_history_truncated": {"2026": 0.5},
                                                                  "flag_x": {"2026": 1.0}}


@pytest.mark.parametrize("module_name,model", [("market_offset_eval", "market_offset_model"),
                                               ("fundamental_eval", "fundamental_model")])
def test_collect_refuses_an_in_sample_evaluation_window(tmp_path, monkeypatch, module_name, model):
    """モデルの学習・検証窓が評価窓と重なれば、予測する前に止める (fundamental_eval にも当てた)。"""
    import importlib

    src = FROZEN / f"{model}.txt"
    if not src.exists():
        pytest.skip(f"凍結した 4B が無い: {src}")
    mod = importlib.import_module(f"scripts.{module_name}")
    (tmp_path / "m.txt").write_bytes(src.read_bytes())
    meta = json.loads((FROZEN / f"{model}.meta.json").read_text(encoding="utf-8"))
    meta["validation"] = ["20260701", "20260710"]          # 評価窓 (6/01〜7/31) と重なる
    (tmp_path / "m.meta.json").write_text(json.dumps(meta), encoding="utf-8")
    feats = meta["features"]
    rows = [_row(feats, race_id="r", horse_num="01", won=0, date="20260712", h_history_truncated=0.0)]
    monkeypatch.setattr(mod, "build_dataset", lambda f, t: (rows, {}))
    monkeypatch.setattr(mod, "MODEL_PATH", tmp_path / "m.txt")
    monkeypatch.setattr(mod, "DB_PATH", _empty_races_db(tmp_path / "races.db"))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        with pytest.raises(ValueError, match="in-sample"):
            mod.collect("20260601", "20260731")
    assert "margin" not in rows[0] and "p_raw" not in rows[0]


def _meta_file(tmp_path: Path, meta: dict) -> Path:
    (tmp_path / "m.txt").write_text("", encoding="utf-8")
    (tmp_path / "m.meta.json").write_text(json.dumps(meta), encoding="utf-8")
    return tmp_path / "m.txt"


@pytest.mark.parametrize("from_date,to_date,overlaps", [
    ("20251231", "20260331", True),     # 評価の初日 = 検証の最終日 (閉区間なので重なる)
    ("20260101", "20260331", False),    # 翌日からなら重ならない
    ("20210101", "20220101", True),     # 評価の最終日 = 学習の初日
    ("20210101", "20211231", False),
])
def test_window_guard_treats_windows_as_closed_intervals(tmp_path, from_date, to_date, overlaps):
    path = _meta_file(tmp_path, {"train": ["20220101", "20241231"], "validation": ["20250101", "20251231"]})
    if overlaps:
        with pytest.raises(ValueError, match="in-sample"):
            ms.assert_model_window_disjoint(path, from_date, to_date)
    else:
        ms.assert_model_window_disjoint(path, from_date, to_date)


def test_window_guard_fails_closed_without_windows(tmp_path):
    """meta に学習・検証の窓が無ければ、重なりを確かめられないので止める (黙って通さない)。"""
    with pytest.raises(ValueError, match="窓が無く"):
        ms.assert_model_window_disjoint(_meta_file(tmp_path, {"features": []}), "20260101", "20260331")
