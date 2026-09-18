"""特徴量の出所台帳 (憲法 Phase 0.5-3)。

## なぜ要るか

> 特徴量名検索だけではなく、特徴量生成経路まで追跡してください。

`能力指数 = 元能力指数 + 人気補正` のように、名前に odds が無くても中身が
市場情報である特徴がありうる。実際 2026-09-18 の棚卸しで
`track_recent_30d_avg_winning_pop` / `_90d_` が **過去レースの勝ち馬の人気**
から作られていることが分かった。名前に odds も popularity も含まれない。

そこで
  (1) 特徴ごとに market_dependency を宣言する
  (2) **市場列を読むコード経路を機械的に検出**し、宣言と突き合わせる
  (3) Fundamental Model に market_dependency=True が入ったらテストを落とす
の 3 段で守る。

## market_dependency の定義

「その特徴の値が、**いずれかのレースの市場 (オッズ・人気・支持率・投票)** に
依存するか」。当該レースの市場でなくても True。過去レースの人気から作った
特徴も市場情報なので True。
"""
from __future__ import annotations

import ast
import re
from dataclasses import asdict, dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# DB 上の市場に関する語。**部分一致で拾う**。
#
# 以前は `\b` 付きの完全語一致で照合していたが、正規表現では `_` が語文字なので
# `win_odds` を登録しても `place_odds` や `odds_low` に当たらなかった。
# 逆に `betting_share` `market_rank` のように **スキーマに存在しない名前** を
# 想像で並べていた (専門家レビューで両方指摘)。
#
# 市場語は部分一致で拾い、誤検出は NOT_MARKET_DESPITE_NAME に理由付きで登録する。
# 「拾いすぎて理由を書く」方が「漏れて気づかない」より安全。
MARKET_TOKENS = frozenset({
    "odds", "popularity", "votes", "vote_count", "payout", "pop1", "pop2",
    "pop3", "_pop", "win5", "betting_share", "market_rank",
})

# 実スキーマに存在する市場列 (schema_market_columns() で検証する)。
MARKET_TABLES = frozenset({"odds_snapshots", "payouts", "win5_payouts",
                           "exotic_odds", "vote_counts"})


@dataclass(frozen=True)
class FeatureSpec:
    """1 特徴の出所。"""

    feature_name: str
    source_table: str
    source_columns: tuple[str, ...]
    transformation: str
    market_dependency: bool
    available_at_prediction_time: bool
    note: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


# 市場に依存する特徴 (本番 112 特徴のうち該当するもの)。
# **Fundamental Model には入れてはいけない。**
MARKET_DEPENDENT: tuple[FeatureSpec, ...] = (
    FeatureSpec(
        feature_name="track_recent_30d_avg_winning_pop",
        source_table="horse_races",
        source_columns=("confirmed_order", "win_popularity"),
        transformation="直近 30 日・同一競馬場の 1 着馬の平均人気",
        market_dependency=True,
        available_at_prediction_time=True,
        note="当該レースではなく過去レースの人気だが、市場情報であることに変わりない。"
             "名前に odds も popularity も含まれないので、名前検索では見つからない。",
    ),
    FeatureSpec(
        feature_name="track_recent_90d_avg_winning_pop",
        source_table="horse_races",
        source_columns=("confirmed_order", "win_popularity"),
        transformation="直近 90 日・同一競馬場の 1 着馬の平均人気",
        market_dependency=True,
        available_at_prediction_time=True,
        note="同上",
    ),
)

MARKET_DEPENDENT_NAMES = frozenset(f.feature_name for f in MARKET_DEPENDENT)

# 名前に市場らしき語を含むが **市場由来ではない** もの。
# 誤検出を黙って無視せず、理由を明記して登録する。
NOT_MARKET_DESPITE_NAME: dict[str, str] = {
    "best_final_3f_rank": "上がり 3F タイムのレース内順位。タイムであって市場ではない",
    "mining_dm_rank": "JRA が提供する DM マイニング予想の順位。JRA のモデル出力で市場ではない",
    "mining_tm_rank": "同上 (TM マイニング)",
    "mining_dm_time": "同上 (予測タイム)",
    "mining_tm_score": "同上 (予測スコア)",
    "mining_dm_time_rank_in_race": "マイニング予測タイムのレース内順位",
    "mining_dm_time_z": "同上 (z 化)",
    "jockey_win_rate_rank_in_race": "騎手勝率のレース内順位。成績であって市場ではない",
    "recent_avg_finish_rate_rank_in_race": "着順率のレース内順位",
    "best_time_per_100m_rank_in_race": "タイムのレース内順位",
    "sire_distance_top3_rate_rank_in_race": "父の距離別成績のレース内順位",
    "horse_track_top3_rate_rank_in_race": "当該馬のコース別成績のレース内順位",
}


def market_reading_functions(path: Path | None = None) -> dict[str, list[str]]:
    """コードの中で **市場に関する語を読んでいる関数** を機械的に洗い出す。

    文字列 (SQL) の中に市場語が出てくる関数を返す。名前検索では見つからない
    派生特徴を捕まえるための第 2 の網。

    **限界 (誤検出しない側に倒れるので、これだけに頼らない)**:
    関数の外で定義したモジュール定数経由の列名、f-string のプレースホルダで
    組み立てる列名、`row.win_odds` のような属性アクセスは検出できない。
    """
    src_path = path or (PROJECT_ROOT / "predictor" / "features.py")
    tree = ast.parse(src_path.read_text(encoding="utf-8"))
    found: dict[str, list[str]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        hits: set[str] = set()
        for sub in ast.walk(node):
            if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
                low = sub.value.lower()
                hits.update(t for t in MARKET_TOKENS if t in low)
                hits.update(t for t in MARKET_TABLES if t in low)
        if hits:
            found[node.name] = sorted(hits)
    return found


def schema_market_columns(conn) -> dict[str, list[str]]:
    """実スキーマの中で市場語を含む列を洗い出す (台帳の裏取り用)。

    想像で列名を並べると、存在しない名前を守った気になる。実際 2026-09-18 の
    初版は `betting_share` `market_rank` を登録していたがどちらも DB に無く、
    逆に `sale_votes` `odds_low` は集合から漏れていた。
    """
    out: dict[str, list[str]] = {}
    for (table,) in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'").fetchall():
        cols = [c[1] for c in conn.execute(f"PRAGMA table_info({table})")]
        hit = [c for c in cols if any(t in c.lower() for t in MARKET_TOKENS)]
        if hit or table in MARKET_TABLES:
            out[table] = sorted(hit)
    return out


def assert_no_market_features(feature_names: list[str],
                              source_module: Path | None = None) -> None:
    """特徴に市場依存が混じっていないか、**名前と経路の両方で**検査する。

    名前照合だけでは素通りする。台帳の名前 (`track_recent_*`) と Fundamental の
    特徴名 (`h_*` `j_*`) は名前空間が交わらないので、集合積は原理的に空になる。
    実際レビューで `build_dataset` の SQL に `win_popularity` を植え込んでも
    テストが全部通ることが実証された。**そこで生成コード自体も走査する**。
    """
    bad = sorted(set(feature_names) & MARKET_DEPENDENT_NAMES)
    if bad:
        raise ValueError(
            f"Fundamental Model に市場依存の特徴が入っている: {bad}\n"
            "憲法 Phase 0.5-3 は市場情報の完全排除を要求する。"
            "predictor/feature_manifest.MARKET_DEPENDENT を参照")
    if source_module is not None:
        reading = market_reading_functions(source_module)
        if reading:
            raise ValueError(
                f"{source_module.name} が市場列を読んでいる: {reading}\n"
                "憲法 Phase 0.5-3 は市場情報の完全排除を要求する。")


def manifest_rows() -> list[dict]:
    return [f.as_dict() for f in MARKET_DEPENDENT]
