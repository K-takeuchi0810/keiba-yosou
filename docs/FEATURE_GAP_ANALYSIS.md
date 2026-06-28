# 特徴量ギャップ調査 (2026-06-28)

## 0. 背景

LGBM v5 は 98 特徴のみで、**騎手系が gain の 66%** を独占 (`predictor/lgbm_meta.json`)。
特徴が少なく偏っているため、市場 (公開オッズ) に既に織り込まれた「騎手人気」を再学習するだけになり、
市場残差 (= 唯一の +EV 源) を捉えられていない (memory: project_logit_reblend_refuted / project_roi_research)。
本書は「現状特徴の棚卸し」と「不足している特徴ファミリ」を、ドメイン定石・deep-research・
利用可能 JV-Data に照らして洗い出す。

## 1. 現行 98 特徴の構成 (棚卸し)

| ファミリ | 数 | 例 |
|---|---|---|
| 近走フォーム | 14 | recent_avg_finish, recent_trend_delta, horse_recent_90d_top3_rate |
| 血統 (sire/dam_sire) | 14 | sire_distance_top3_rate, dam_sire_going_top3_rate |
| 騎手 | 8 | jockey_win_rate, jockey_track_top3_rate, jockey_recent_90d_* |
| 厩舎 | 6 | trainer_win_rate, trainer_track_top3_rate |
| クラス | 6 | class_level_top3, class_drop_points |
| 馬場/コース実績 | 6 | same_track_type_top3, horse_track_top3_rate |
| 持ちタイム | 5 | best_time_per_100m, best_final_3f, best_relative_time_diff |
| 同コース実績 | 5 | same_course_top3, same_course_distance_top3 |
| 脚質 | 4 | leg_code, estimated_leg_code (※データ疎) |
| マイニング (JRA-VAN AI) | 4 | mining_dm_time, mining_tm_score |
| 馬場状態/距離/その他 | 計~26 | same_going_top3, same_distance_top3, days_since_last, burden_delta |

**特徴**: ほぼ全てが「対象馬単体の絶対量 (率・回数)」。**レース内での相対位置 (競争相手との比較) がほぼ無い**。
これが「単独で強い絶対シグナル = 騎手率」への一極集中を生む構造的要因。

## 2. 構造的欠落 (実測で確認)

`predictor/features.py` を走査した結果、以下は **完全に未実装**:

- 枠順/draw (`waku`/`draw`/`枠` = 0 ヒット)
- オッズ変動/票数 (`odds_drift`/`opening_odds`/`vote`/`票` = 0)
- レース内相対化 (`rank_in_race`/`field_mean`/`z_score`/`deviation` = 0。`relative` は 10 あるが
  best_relative_time_diff 等の限定用途のみ)
- ペース/展開 (`pace`/`front_runner`/`nige`/`sectional`/`lap` = 0)
- 馬体重の特徴量化は部分的 (weight_change の参照はあるが 98 特徴に体重系は burden_delta=斤量差 のみ)

## 3. 不足している特徴ファミリ (優先順)

価値 = 「市場残差になりやすい / 既知の強シグナル / 現状欠落」で評価。

### ★最優先 (構造改善・偏り是正に直接効く)

**F1. レース内相対化 (race-relative normalization)** — 構造的処方
- 既存の全絶対特徴を「レース内 rank / z-score / 偏差」に変換した派生特徴を追加。
- 例: jockey_win_rate_rank_in_race, best_time_z_in_race, sire_distance_rate_minus_field_mean。
- 効果: 何が「相対的に強いか」をモデルに渡し、単一絶対特徴 (騎手率) への一極集中を緩和。
- データ: 既存特徴から計算可能 (新規取り込み不要)。**最も費用対効果が高い**。

**F2. 枠順・内外バイアス (draw bias)** — 既知の強シグナル・市場残差
- waku_num / horse_num、枠 × 競馬場 × 距離 × 馬場 の過去 top3 率/バイアス。
- 内外有利は開催・コースで変動し、一般購入者が定量化しづらい = 市場残差。
- データ: horse_races.waku_num/horse_num + races (既存)。**取り込み不要**。

**F3. 市場オッズ動態・票数 (market microstructure)** — 市場残差の直接源
- 始値→直前オッズのドリフト、オッズ順位 vs モデル順位、単勝票数シェア (H1)、3連単票数 (H6)。
- 「お金がどこに動いたか」は確定オッズに均される前の情報 = 残差候補。
- データ: O1 時系列 + **H1/H6 (取り込み中: B2 バッチ)**。リーク注意 (発走後値を使わない、Step1 ゲート準拠)。

### ★高 (定石の強シグナル・現状データ疎)

**F4. ペース/展開シナリオ (pace scenario)**
- レースの逃げ/先行頭数、想定ペース、対象馬の脚質×想定ペースの相性。
- 個馬の脚質 (leg_quality) は現状疎 → final_3f/脚質の再取得 (G1/G2) で改善後に有効化。
- データ: leg_quality_code + final_3f (再取得後) + レース内集計。

**F5. スピード指数 (track-variant-adjusted speed figure)**
- 馬場差補正済みの走破時計指数 (Beyer/Timeform 相当)。same_day_bias を使い基準化。
- 現状 best_time_per_100m は粗い絶対値。区間タイム (sectional) も欲しい。
- データ: finish_time + final_3f (再取得後) + same_day_bias (現状疎、要拡充)。

**F6. 馬体重・増減トレンド (body weight)**
- 発走前馬体重 (絶対)、前走比増減、長期トレンド、適正体重との乖離。
- データ: horse_races.horse_weight/weight_change_diff (既存) + 速報 WH (B4 バッチ)。

### ★中 (取り込み新データで可能になるもの)

**F7. 調教 (training)** — training_times 再取り込み後 (G3)
- 直前追切の強さ・本数・坂路/W タイムの相対順位、好調パターン。

**F8. 厩舎・騎手の意図シグナル (connections, via KS/CH masters・取り込み済)**
- 騎手乗り替わり (前走→今走)、上位騎手の人気薄騎乗 (厩舎の勝負気配)、騎手×厩舎相性、所属/フリー。
- データ: jockey_masters/trainer_masters (バッチ1で取得済) + 過去 SE。

**F9. 血統の深掘り (pedigree depth)**
- 距離/馬場適性指数 (率でなくモデル化)、ニックス (父×母父配合)、系統 (BT、B3 バッチ) 別適性。

**F10. 出走間隔・ローテ・季節 (campaign/seasonality)**
- 在厩/放牧明け本数、連闘/中週、季節・開催替わり、昇級初戦フラグ。

## 4. 偏り是正の核心メッセージ

騎手 66% 偏重は「騎手が特別強い」のではなく **他に競争力のある特徴を作っていない** ことの裏返し。
最も効くのは:
1. **F1 レース内相対化** (既存特徴の作り直し・取り込み不要・即着手可)
2. **F2 枠順バイアス** (既存データ・取り込み不要)
3. **F3 市場動態/票数** (B2 取り込み後)

この 3 つで「市場が定量化しづらい残差」を新規に供給でき、jockey 一極集中を構造的に崩せる見込み。

## 5. データ可用性マッピング

| 特徴ファミリ | 必要データ | 現状 |
|---|---|---|
| F1 相対化 | 既存特徴 | **即可** |
| F2 枠順 | horse_races.waku_num (既存) | **即可** |
| F3 市場動態 | O1時系列 + H1/H6 | B2 取り込み待ち |
| F4 ペース | leg_quality + final_3f | G1/G2/G3 再取得後 |
| F5 スピード指数 | finish_time + final_3f + 馬場差 | G1 後 + same_day_bias 拡充 |
| F6 馬体重 | horse_weight (既存) + WH | 一部即可 / WH は B4 |
| F7 調教 | training_times | G3 再取り込み後 |
| F8 連対者 | jockey/trainer_masters | **取得済 (バッチ1)** |
| F9 血統深掘り | sire/dam + BT | 一部即可 / BT は B3 |
| F10 ローテ | 過去 SE 日付 | **即可** |

## 6. 推奨着手順序 (取り込みと並行)

1. **F1 (相対化) + F2 (枠順) + F10 (ローテ)** — 取り込み不要・即着手・偏り是正に直結。
2. データ取り込み完了 (B2 オッズ/票数, G1 final_3f, G3 調教) を待って **F3/F4/F5/F7**。
3. **F8 (連対者・取得済マスタ)** はバッチ1完了で即着手可。
4. 各特徴追加は walk-forward でリーク検査必須 (Step1 ゲート / keiba-feature スキル準拠)。
   追加後は特徴量重要度を再可視化し、jockey 比率の低下と新特徴の寄与を確認する。

## 7. 留意

- 特徴を増やすこと自体が目的ではない。**市場が織り込めていない残差**を供給することが目的
  (deep-research: 公開オッズはほぼ情報完備、増分のみが利益源)。
- リーク厳禁: 発走後情報 (確定オッズ/着順/上がり) を特徴に混ぜない。Step1 の odds 鮮度ゲートと同じ規律。
- 実装は `.claude/skills/keiba-feature/` の型・落とし穴に従う。
