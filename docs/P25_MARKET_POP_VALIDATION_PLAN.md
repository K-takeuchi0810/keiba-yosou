# P25 市場人気補正 検証設計書

作成日: 2026-06-14 (改訂: 2026-06-17 外部レビュー反映)

## 目的

P25 は、予想◎が市場オッズを見ずに逆張り寄りになる問題を抑えるための検証対象である。

上位ゴールは `docs/OPERATION.md` の「年間 180%, 月次変動は許容」。ただし、P24/P25 時点では利益エッジは未確認であり、実弾投入ではなく観察・検証フェーズに置く。

この設計書の目的は、重い全期 dump や追加コード改修の前に、P25 をどの条件で採用・棄却・保留するかを固定すること。

## ROI 180% の位置付け (2026-06-17 外部レビュー追記)

「年間 180%」は **採用条件 (本番投入を許可する閾値)** であって、**P25 単体で達成する見込みのある数値ではない**。混同しないこと。

- JRA 公式: WIN5 以外の馬券は払戻率 70〜80% (=控除率 20〜30%)。市場平均はマイナス期待値スタート。
- P25 補正は「逆張り◎を抑える市場アンカー」にすぎず、市場残差ではない。控除率 20% を超えて連続 +80% を出すには、本来「市場が織り込めていない情報」を識別する必要がある。
- したがって P25 単体で 180% に到達するなら、それは過適合か計測ミスを疑うべきサイン。
- 180% は「P25 を含む複数施策の累積で、forward holdout かつ bootstrap CI 下限が控除率を超える状態」を意味する。

この位置付けを忘れると、「subset Brier が改善 → 即採用」のような前のめりな判断を生む。**改善は採用条件ではなく、観察を続ける条件**。

## 検証順序の優先度 (2026-06-17 外部レビュー追記)

評論家フィードバックに基づく順序の確定:

1. **fresh odds coverage 実測の安定稼働確認** (最優先)
   - スケジューラが意図通り動いているか、`scripts/fresh_odds_coverage.py` で 2〜4 開催日ぶん検証する
   - eligible_races / fetched_races / ingested_races / failed_reason のリアルな比率を見る
   - **これが安定するまで他のチューニングをしない** (補正発火 race 数が少ないままで A/B を回しても無意味)
2. fresh odds が十分に蓄積されたら (popularity_bonus_candidate ≥ 500 馬 or races ≥ 150)、paired A/B (本書「検証対象」表 + 3 層 factorial 設計) を実行
3. raw_blended 分布比較・subset Brier 比較・calibrator refit 検証

サンプル n=33 馬で「差がない」「採用する」のどちらも判断できない。サンプルが集まる前の A/B チューニングは雨乞いと同じ。

## 背景

P24 診断では以下が確認された。

- 現行モデルの EV / Kelly / value 信号は anti-predictive。高EVほど実回収が悪化した。
- `min_kelly` フィルタは反選択で、4-fold 単勝回収 MIN が all ◎ベタより悪かった。
- 唯一頑健な正信号は市場人気 `pop1-3` だった。
- ただし `pop1-3` でも 2026 holdout は 100% 未満で、利益エッジは未確認。

P25 では、`win_popularity` 1-3 番人気を◎決定前スコアへ加点する補正を追加した。レビュー中に freshness guard も追加し、発走30分超過または欠損 snapshot では市場人気補正を効かせないようにした。

P25 scorecard の結論は「ランキング補助として観察対象、正式採用には長期 paired A/B、calibrator refit、fold 検証が必要」。

## 直近の軽量検証メモ

重い dump 前の DB 直接集計では、以下を確認済み。

### クリーンオッズ窓

2025 年は 6 月を境に全頭オッズ付き race の性質が変わる。

| 期間 | 所見 |
|---|---|
| 2025-01〜05 | clean 2.6%〜3.0%。検証主窓には使わない |
| 2025-06 | clean 73.3%。移行月として扱う |
| 2025-07〜12 | clean 92.5%〜96.9%。主検証窓 |
| 2026-01〜06 | clean 83.0%〜97.6%。forward holdout |

したがって P25 の主評価窓は `2025-07-01` 以降の clean odds window とする。必要に応じて `2025-06-01` 以降を副窓にする。

### 人気別回収率

2025-2026 clean 限定では、以前見えた「2人気だけが極端に良い」は弱まった。

- 1-3人気は、穴側を避ける市場アンカーとしては有効。
- 10人気以下は単複とも弱く、抑制対象として安定。
- `1人気 / 2人気 / 3人気` を過剰に細分化して最適化する根拠はまだ弱い。

### 3連複 E5

単勝人気ベースの3連複 BOX は、主窓 `2025-07-01〜2026-06-14` で ROI 72%〜81% 程度に収束した。

現時点では P25 の主検証から外す。3連複は払戻分布の観察対象に留め、採用判断には使わない。

## 検証対象

正式 A/B では、同一期間・同一コード経路で以下の popularity weights を比較する。

| variant | first | second | third | 用途 |
|---|---:|---:|---:|---|
| `pop_0_0_0` | 0 | 0 | 0 | P25 無効 baseline |
| `pop_4_2_1` | 4 | 2 | 1 | 弱い市場アンカー |
| `pop_7_4_2` | 7 | 4 | 2 | 現 P25 |
| `pop_10_6_3` | 10 | 6 | 3 | 強い市場アンカー |

比較はフィルタ変更と交絡させない。`BUY_FILTER_DEFAULT` の戦略変更とは別セッション、別 rule_version、別 scorecard で扱う。

### 3 層 factorial 設計 (二重取り込みリスクの単離)

`predictor/rules.py` の docstring (A/B/C の多段経路) で示した通り、市場シグナルは
3 経路から取り込まれる。利益・損失への寄与を **独立に**測るためには、popularity
weights の 4 値を試すだけでは不足で、3 層 (A/B/C) を on/off で切り換えた
factorial 設計が必要。`(A, B, C) ∈ {on, off}^3` の 8 セルから、最低 4 セルを
paired run する。

| セル | 層 (A) `_market_score` 人気加点 | 層 (B) `_investment_probability` blend | 層 (C) `_value_score` odds-band | 設定方法 |
|---|---|---|---|---|
| C1 (baseline) | OFF | OFF | OFF | `PRED_W_popularity_first/second/third=0` + `PRED_DISABLE_BLEND=1` + `PRED_W_discount_*=0` |
| C2 (A only) | ON | OFF | OFF | (A デフォルト) + (B/C は env で OFF) |
| C3 (B only) | OFF | ON | OFF | (A を env で OFF) + (B デフォルト) + (C を env で OFF) |
| C4 (A+B) | ON | ON | OFF | (A/B デフォルト) + (C を env で OFF) |
| C5 (A+B+C = 現状) | ON | ON | ON | env override なし (現状値) |
| C6 (B+C) | OFF | ON | ON | (A を env で OFF) + (B/C デフォルト) |
| C7 (A+C) | ON | OFF | ON | (A デフォルト) + (B を env で OFF) + (C デフォルト) |
| C8 (C only) | OFF | OFF | ON | (A を env で OFF) + (B を env で OFF) + (C デフォルト) |

**最低限走らせる 4 セル**: C1 (baseline) / C2 (A only) / C3 (B only) / C5 (現状)
→ A 単独寄与・B 単独寄与・両ON 寄与 (二重取り込み) を 3 種の paired 差分で測定可能。

**理想は 8 セル全数**: C4 / C6 / C7 / C8 を追加すれば odds-band C の寄与も含めた
完全 ANOVA 分析が可能。各セルは独立 backtest 出力 (`*-filtered.json`) として保存
し、`buy_only_return_rate` / `bonus_subset_metrics.brier_score` / aggregate Brier
の 3 系列を比較する。

**注意点**:

- 各セルの env override は `meta.env_overrides` フィールドに自動記録 (P21 で
  実装済み) → 再現性監査に使う。
- C1 (baseline) では `_market_popularity_is_fresh` が True でも weight=0 なので
  rationale に「市場N人気」が出ない (虚偽表示防止のテスト済み)。
- C3 / C6 で `PRED_DISABLE_BLEND` は現状 env として実装されていない。実装
  必要なら本書追記後の TODO として `predictor/rules.py:_investment_probability`
  に追加する。代替として `PRED_W_model_blend_*=1.0` を全 confidence に設定し
  blend を実質無効化する経路も可。
- factorial 比較は 同一期間 paired backtest が前提。期間ズレで loss を起こす
  ことが多いので、4-fold 境界と評価窓は本 Plan の主窓を使う。

**現状の進捗**:

- C1 (pop_0_0_0) / C5 (pop_7_4_2): 通期 (`2025-07-01〜2026-06-14`) で完了済
  (`20260615_095016_*-filtered.json` / `20260615_110607_*-filtered.json`)
- 他セルは未実行。次の重い backtest を起動するときに C2 / C3 から追加する。
- factorial の数値解析 (ANOVA, 主効果分解) は scorecard `validation-process-auditor`
  領分で、scripts/backtest 出力 JSON を後段の集計スクリプトで処理する。

## 評価窓

### 主窓

- fit / design: `2025-07-01` 〜 `2025-12-31`
- forward holdout: `2026-01-01` 〜 現在取得済み最終日

### 副窓

- `2025-06-01` 〜 `2025-12-31`
- `2025-07-01` 〜 `2026-06-14` の通期 clean window

### 除外

- 2025-01〜05 の市場オッズ clean 率が極端に低い期間
- 全頭 `win_odds > 0` かつ `win_popularity > 0` を満たさない race
- `payouts` 欠損 race
- 中止・異常 race が検出できる場合は除外

## 評価指標

### 予測品質

- Brier score
- logloss
- reliability curve
- top-1 `win_probability` の calibration gap
- raw_blended 分布の変化

### 馬券品質

- ◎単勝 hit rate / return rate
- ◎複勝 hit rate / return rate
- `BUY_FILTER_DEFAULT` 適用後の buy_only return
- 4-fold MIN return
- bootstrap CI

### fold 定義

4-fold は以下の期間境界で固定する。結果を見てから fold を選び直すことは禁止。

| fold | 期間 |
|---:|---|
| 1 | 2025-07-01 〜 2025-09-30 |
| 2 | 2025-10-01 〜 2025-12-31 |
| 3 | 2026-01-01 〜 2026-03-31 |
| 4 | 2026-04-01 〜 取得済み最終日 |

fold 1-2 が design 窓、fold 3-4 が forward holdout に対応する。
合格条件の「4-fold MIN」は上記 4 fold のうち最低の回収率を指す。

### bootstrap 仕様

- サンプリング単位: **race 単位** (horse 単位ではない)。1 race 内の出走馬・賭け結果をまとめてリサンプリングする。
- 理由: 同一 race 内の horse は相関が強く、horse 単位だと CI が過小評価される。
- リサンプル回数: 10,000 回。
- CI 報告: 2.5 パーセンタイル / 97.5 パーセンタイル (95% CI)。

### 市場 snapshot 品質

backtest JSON には以下を保存する。

- fresh / stale / unknown snapshot counts
- `market_snapshot.snapshot_age_min` の分布
- 市場人気補正を実際に使えた頭数
- race 単位で市場人気補正が有効だった頭数

P25 は freshness guard に依存するため、これらを記録できない状態では正式評価に進まない。

#### snapshot age 4 段階記録 (2026-06-17 外部レビュー追記)

「30 分以内なら fresh」は粗い。締切直前のオッズと 25 分前のオッズでは意味が違うため、本格検証では以下 4 段階を分けて記録する。

| age (分) | tier 名 | 扱い |
|---:|---|---|
| 0〜10 | `tier_a_critical` | 最重要 fresh (締切直前) |
| 10〜20 | `tier_b_primary` | 準 fresh |
| 20〜30 | `tier_c_secondary` | 弱 fresh (現行 fresh 判定の上限帯) |
| 30 超 | `tier_d_stale` | stale (補正対象外) |

`market_snapshot.age_tier_horses.{tier_a_critical,tier_b_primary,...}` と
`market_snapshot.bonus_subset_metrics.by_age_tier.{...}` を JSON に保存。

**重要**: 30 分以内の閾値自体は **事前固定** (`weights.json popularity.max_snapshot_age_min=30`)。tier 区分は **観測用** であり、tier ごとに最適な閾値を後から選び直すことは禁止 (multiple testing で偽陽性を量産する)。tier 別 Brier はあくまで「30 分以内 fresh の中でも age が浅いほど補正効果が強いか」を**確認**するための観測値。

### 取得運用 coverage 記録 (2026-06-17 外部レビュー追記)

スケジューラ稼働中の `scripts/fetch_fresh_odds.py` が **実際にどれだけのレース・馬を fresh 状態で運用に乗せたか** を見るための独立した監査メトリクス。backtest 側 (= 既存 race データの再評価) とは別経路で記録する。

| 項目 | 意味 |
|---|---|
| `eligible_races` | スケジューラ起動時、発走 2〜25 分前で取得対象判定だったレース数 |
| `fetched_races` | `JVRTOpen("0B31")` が成功したレース数 |
| `ingested_races` | DB ingest まで成功したレース数 |
| `fresh_races_before_start` | 取り込んだ snapshot が発走前 fresh 判定で使えたレース数 |
| `fresh_horses` | fresh 判定された頭数 |
| `bonus_candidate_horses` | starter_count>=min_field かつ pop 1-3 で fresh、つまり補正候補となった頭数 |
| `snapshot_age_min` の p50 / p90 / max | 鮮度の実態 |
| `failed_reason` | COM 失敗 / 認証失敗 / 0 byte / 取込失敗 などの分類カウンタ |

出力先: `data/logs/fresh_odds_coverage.jsonl` (1 起動 = 1 行 append)。
集計: `scripts/fresh_odds_coverage.py` で直近 N 開催日の中央値・最悪値を表示。

Plan Step 4 の「fresh odds 取得を運用化する」は **これらの coverage が 2〜4 開催日で安定すること** を完了条件にする。期待値 (1 開催日あたり 36 race × 平均 13 頭 ≈ 468 fresh 馬) は **目安**であり、実測 coverage が目安の 50% 未満なら、補正発火サンプルが十分溜まる前に Plan Step 5 (paired A/B 再実行) に進んではならない。

#### 初日実測 (2026-06-20 土曜、11:45 時点の進捗)

scheduler 登録後の初稼働で coverage 取得が確認された。詳細は
`data/scorecards/20260620_1145_p25_step4_health_snapshot.md`。

| 項目 | 実測 | Plan 期待値 | 比 |
|---|---:|---:|---:|
| 09:00 以降の scheduler 発火回数 | 17 | 46 (全日) | 11:45 時点で 37% |
| eligible_races (累計) | 26 | 36 (全日) | 11:45 時点で 72% |
| ok_races (累計、= 取得成功率) | 26 (100%) | 100% | ✓ |
| error_races / no_data / timeout / empty | 全 0 | - | ✓ |
| lock_skipped | 0 | - | ✓ |
| `failed_reason` 分類 | 空 | - | ✓ |
| contamination_detected | False | - | ✓ |
| DB `odds_fetched_at >= 2026-06-20T09:00:00` 行数 | **505** | 468 (1 日目安) | **1.08 倍 (途中で既に超過)** |
| health check decision | **PASS** (×10 回連続) | - | ✓ |

初日の実測は Plan 期待値を 11:45 時点で既に達成。完了条件「2-4 開催日で安定」を厳守するため、明日 (2026-06-21 日) も同様に稼働することを観察してから Plan Step 5 (paired A/B 再実行) に進む判断を行う。OOS auto task は **ユーザの明示承認まで Disabled 維持**。

## 合格条件

P25 variant を採用候補に昇格する条件は以下のすべて。

1. 2026 holdout の Brier または logloss が baseline `pop_0_0_0` より悪化しない。
2. reliability curve が高p帯で過剰自信を悪化させない。
3. ◎単勝 / 複勝の 4-fold MIN が baseline より悪化しない。
4. buy_only の return が baseline より悪化しない。
5. fresh snapshot が十分に存在し、補正が実際に発火していることを JSON で確認できる。
6. calibrator mismatch を残したまま本番採用しない。

利益エッジ採用の条件はさらに厳しく、以下をすべて満たすこと。

- 2026 holdout ROI が 180% 以上。
- bootstrap CI 下限が 100% 以上。
- 4-fold MIN が 80% 以上。
- `market_snapshot.popularity_bonus_candidate_horses` が 500 頭以上、または `market_snapshot.races_with_popularity_bonus_candidate` が 150 race 以上。

100% 超に留まる場合は「損益分岐超えの観察候補」であり、年間目標達成候補とは扱わない。
`fresh_horses=0` または `popularity_bonus_candidate_horses=0` の run は、freshness guard の確認には使えるが、P25 の収益効果検証からは除外する。

## 棄却条件

以下のいずれかに該当した variant は棄却する。

- 2026 holdout の Brier / logloss が baseline より明確に悪化する。
- 1-3人気への過加点で◎が市場人気へ寄りすぎ、回収率が低下する。
- fresh snapshot が少なく、補正発火 race が評価に足りない。
- stale / unknown snapshot を使っている疑いが残る。
- 2025 design だけ良く、2026 forward で崩れる。
- 2026 holdout ROI が 180% 未満で、年間目標達成候補としての根拠がない。

## 実行順序

1. backtest / dump に市場 snapshot 観測性を追加する。 ← **完了 (2026-06-14)**
2. `pop_0_0_0` baseline を同一コード経路で保存する。 ← **完了 (2026-06-15)**
3. `pop_7_4_2` を同一コード経路で保存する。 ← **完了 (2026-06-15)**
4. **fresh odds 取得を運用化する** (下記参照)。 ← **スクリプト作成済み、スケジューラ登録は次開催日**
5. fresh odds が蓄積された期間 (数週間) で A/B を再実行する。
6. raw_blended 分布を比較し、calibrator refit が必要な variant を特定する。
7. 2025 fit / 2026 holdout で calibrator refit 検証を行う。
8. 結果を scorecard に保存し、expert-review を通す。

30分以上の重い dump / backtest を起動する場合は、AGENTS.md の 1-ter pre-flight checklist を完了してから実行する。

### A/B 中間結果 (Step 2-3)

2025-07-01 〜 2026-06-14 の全期間 backtest では P25 補正の差がほぼゼロだった。

| 指標 | pop_0_0_0 | pop_7_4_2 | diff |
|---|--:|--:|--:|
| all return % | 67.12 | 67.17 | +0.05 |
| buy_only return % | 65.77 | 65.77 | 0.00 |
| Brier | 0.0631 | 0.0631 | -0.000 |
| bonus_candidate_horses | 0 | 33 | +33 |
| races_with_bonus | 0 | 11 | +11 |
| fresh_horses | 193 | 193 | 0 |

原因: 全 46,287 頭のうち fresh (発走30分以内) はわずか 193 頭 (0.4%)。
P25 補正が発火したのは 33 頭 / 11 レースのみで、評価に足りない。

**結論**: P25 の重み値の良否を判断する前に、fresh odds の供給量を増やす必要がある。

## fresh odds 取得の運用

### 背景

P25 市場人気補正は `odds_fetched_at` が発走 30 分以内のときだけ発火する。
現状のオッズ取得は手動実行 (GUI「Ⅱ最新オッズ取得」) であり、発走の数時間前に
1 回だけ取得するため、ほぼ全馬が stale/unknown になっている。

### 解決: `scripts/fetch_fresh_odds.py`

発走 2〜25 分前のレースだけを対象に `JVRTOpen("0B31")` で再取得するスクリプト。
Windows Task Scheduler で 10 分おきに自動実行する。

```
schtasks /create /tn "keiba-fresh-odds" /tr ^
  "C:\Users\kizun\dev\keiba-yosou\scripts\fetch_fresh_odds.bat" ^
  /sc minute /mo 10 /st 09:00 /et 16:40 ^
  /sd 2026/06/20 /f
```

### 期待効果

- 各レースが発走前に最低 1〜2 回 fresh odds を取得
- 1 開催日あたり 36 レース × 平均 13 頭 ≈ 468 頭が fresh になる
- 4 週間 (8 開催日) で約 3,744 頭の fresh データが蓄積
- P25 の bonus_candidate が数百頭規模に達し、A/B 評価が可能になる

### 前提条件

- PC が開催時間中に起動していること
- JV-Link が認証済みで COM 接続可能なこと
- `.venv32` (32bit Python) が利用可能なこと

## GUI / HTML 可視化の follow-up

P25 は最新オッズ依存が強いため、正式A/B後に採用候補へ進む場合は GUI / HTML 側にも以下を出す。

- 「市場人気補正は発走30分以内の最新オッズのみ有効」の説明
- fresh / stale / unknown snapshot counts
- popularity bonus candidate counts
- `Odds最新` が `MAX(odds_fetched_at)` だけで誤解されないための警告表示

## 生成物

想定する成果物:

- `data/backtest/<timestamp>_tan_p25-pop-<variant>-filtered.json`
- `data/diag/dump_p25_pop_<variant>_picks_*.csv`
- `data/diag/dump_p25_pop_<variant>_races_*.csv`
- `data/scorecards/<timestamp>_p25_market_pop_ab.md`

JSON / CSV には `rule_version`, `git_sha`, `variant`, `popularity_weights`, `clean_window`, `snapshot_counts` を含める。

## 実装状況

- 2026-06-14: `scripts/backtest.py` に `market_snapshot` 集計を追加。
  - fresh / stale / unknown horse counts
  - post-start snapshot counts
  - clean market race counts
  - snapshot age min / p50 / p90 / max
  - popularity bonus candidate horse / race counts
  - `weights.json` の `popularity.min_field`, `max_snapshot_age_min`, `first/second/third` を記録
- 2026-06-16: fresh odds 運用と検証証跡を強化。
  - `scripts/fetch_fresh_odds.py` を `records_total` 判定に修正し、取得成否ログの誤判定を防止。
  - `fetch_realtime()` の `filenames` を `ingest_all(only_files=...)` に接続し、10分ごとの全量 0B31 再取込を回避。
  - 0 byte raw 削除、レース単位の例外継続、取得直前の発走時刻再判定、lock heartbeat を追加。
  - `scripts/backtest.py` に `meta.git_dirty` / `meta.git_status_short` と払戻欠損カウンタを追加。
  - fresh odds fake test、market snapshot env override test、payout missing test を追加。

## 現時点の判断

P25 は、年間 180% へ直接到達する利益戦略ではまだない。

現時点の正しい位置づけは、P24 で確認された「逆張り◎」「anti-predictive EV」を緩和するための市場アンカー候補である。

したがって次の作業は、重い全期 dump ではなく、まず市場 snapshot 観測性を検証ログに追加し、正式 A/B を再現可能な形で走らせること。
