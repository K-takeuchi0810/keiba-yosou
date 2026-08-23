"""発走前 / 発走後の列台帳と、backtest 用のマスキング入口 (改革 P0)。

## なぜ台帳が必要か

`horse_races` の行は発走後のレコード (data_div 6/7) で **上書きされる**。よって
同じクエリが「いつ実行したか」で違うデータを返す:

- live (発走前): 着順・脚質・上がり 3F・コーナー通過順・馬体重増減は空
- backtest (発走後): すべて充填済み

この差を各特徴が個別に気をつける運用にしていたため、同じ事故が 2 度起きた:

1. 2026-07: LGBM の `leg_code` 特徴が発走後値を参照 (live で AUC 0.579 ≒ ランダム)。
   LGBM 特徴からは除外して修正した。
2. 2026-08-23: `same_day_bias_score` が当該レースの `leg_quality_code` を
   キーにしており、**間接参照の経路が残っていた**。実測 (2026-08-16、159 頭):
   発火率 backtest 30.2% vs live 0%、ルールスコアが 64% の馬で最大 15 点乖離。

「レビューで気づく」に頼る限り 3 度目が起きる。本モジュールは
**発走後列を 1 箇所で定義し、backtest が必ずマスクを通る**ようにして、
汚染を機械的に不可能にする。

## 使い方

    from predictor.pit_view import live_horses
    horses = live_horses(conn, race)      # backtest でも live と同じ入力になる

`tests/test_pit_parity.py` が「マスク有無で特徴量とスコアが一致すること」と
「未知の列が台帳に無ければ落ちること」を恒久的に保証する。
"""
from __future__ import annotations

import sqlite3

# ---------------------------------------------------------------------------
# 発走後にしか確定しない列 (= 発走前の判断に使ってはいけない)
# ---------------------------------------------------------------------------
POST_RACE_COLUMNS: frozenset[str] = frozenset({
    # 結果そのもの
    "finish_order",       # 着順 (速報)
    "confirmed_order",    # 確定着順
    "same_finish",        # 同着
    "finish_time",        # 走破タイム
    "final_3f",           # 上がり 3F
    "abnormal_code",      # 異常区分 (取消・除外・競走中止)。発走前の取消は
                          # race_scratches / 出馬表側で扱う。この列は結果由来。
    # 走り方 (レース後に判定される)
    "leg_quality_code",   # 脚質。2026-07 の v5 リーク、2026-08 の same_day_bias
                          # リークの原因列。過去走からの推定は
                          # features の estimated_leg_code を使う
    "corner_order_1", "corner_order_2", "corner_order_3", "corner_order_4",
})

# ---------------------------------------------------------------------------
# 発走前に観測できる列。ただし **観測できる時刻が列ごとに違う** ものがある:
#   - horse_weight / weight_change_* : 当日発表 (各レースの 1-2 時間前)。
#     朝 8-9 時の生成では未発表 = 空になりうる。T−10 生成では利用可能。
#   - win_odds / win_popularity / odds_fetched_at / odds_dataspec :
#     時刻依存。**predictor.pit_market が T−n 時点の値に再構成する**ので、
#     本モジュールではマスクしない (二重管理を避ける)。
# ---------------------------------------------------------------------------
PRE_RACE_COLUMNS: frozenset[str] = frozenset({
    # レース識別
    "race_year", "race_month_day", "track_code", "kaiji", "nichiji", "race_num",
    "horse_num", "data_div", "data_created", "waku_num",
    # 馬の属性
    "blood_register_num", "horse_name", "horse_symbol_code", "sex_code",
    "breed_code", "coat_code", "age",
    # 陣営
    "east_west_code", "trainer_code", "trainer_short_name",
    "owner_code", "owner_name", "jockey_code", "jockey_short_name",
    "jockey_apprentice_code",
    # 当日発表 (時刻依存。上のコメント参照)
    "burden_weight", "blinker", "horse_weight",
    "weight_change_sign", "weight_change_diff",
    # 市場 (pit_market が時刻管理)
    "win_odds", "win_popularity", "odds_fetched_at", "odds_dataspec",
    # 事前予想 (JRA-VAN マイニングは発走前配信)
    "mining_time", "mining_predicted_order",
})


class UnclassifiedColumnError(RuntimeError):
    """horse_races に台帳未登録の列がある。分類してから使うこと。"""


def classify_columns(conn: sqlite3.Connection) -> dict[str, list[str]]:
    """実 DB の列を台帳と突き合わせる。未知の列があれば raise。

    新しい列を追加したときに「どちらでもない」状態で黙って特徴に使われるのを
    防ぐための門。テストから呼ばれる。
    """
    cols = [r[1] for r in conn.execute("PRAGMA table_info(horse_races)")]
    unknown = [c for c in cols
               if c not in POST_RACE_COLUMNS and c not in PRE_RACE_COLUMNS]
    if unknown:
        raise UnclassifiedColumnError(
            "horse_races の列が predictor/pit_view.py の台帳に未登録: "
            f"{unknown}. 発走前に観測できるなら PRE_RACE_COLUMNS、"
            "発走後にしか確定しないなら POST_RACE_COLUMNS に追加すること。"
        )
    both = POST_RACE_COLUMNS & PRE_RACE_COLUMNS
    if both:
        raise UnclassifiedColumnError(f"両方に登録された列がある: {sorted(both)}")
    return {
        "post_race": [c for c in cols if c in POST_RACE_COLUMNS],
        "pre_race": [c for c in cols if c in PRE_RACE_COLUMNS],
    }


def mask_post_race(horse: dict) -> dict:
    """発走後列を None にした浅いコピーを返す (入力は破壊しない)。

    live で DB から読んだ行はこれらが元々空なので、マスクしても何も変わらない。
    backtest では充填済みなので、マスクすることで live と同一入力になる。
    """
    out = dict(horse)
    for col in POST_RACE_COLUMNS:
        if col in out:
            out[col] = None
    return out


def live_horses(conn: sqlite3.Connection, race: dict) -> list[dict]:
    """発走前に観測できる情報だけの出走馬リスト (backtest の唯一の入口)。

    `scripts.backtest.horses_for_race` と同じ行を返し、発走後列だけを落とす。
    """
    from scripts.backtest import horses_for_race  # 循環 import 回避のため遅延
    return [mask_post_race(h) for h in horses_for_race(conn, race)]


def post_race_fields_present(horse: dict) -> list[str]:
    """その行に「値が入っている発走後列」を列挙する (汚染検知・デバッグ用)。"""
    return sorted(
        col for col in POST_RACE_COLUMNS
        if horse.get(col) not in (None, "", 0)
    )
