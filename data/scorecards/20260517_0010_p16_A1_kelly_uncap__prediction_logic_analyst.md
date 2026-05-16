# 予想ロジック分析官 採点 — P16 Phase A1 (Kelly cap 撤廃)

**改修対象**: `predictor/rules.py:910` / `config.py:96-110` / `scripts/predict.py:233-238`
**評価日**: 2026-05-17 00:10 JST
**評価対象 commit**: `881698f` (worktree branch `claude/goofy-heyrovsky-e54180`)
**未編集**: `predictor/features.py` / `predictor/weights.json` / `predictor/calibrator.json`

---

## 総合: 4.0 / 5 (前回 4.1 → 4.0, -0.1)

スコアそのものはほぼ横ばい。改修内容は **数値的に正しく**、責務分離も合理的。ただし「calibrator 更新待ち」「絞り運用 5 戦/0 勝の機会極小化」という構造的な未解決課題が前面化したため、本番運用との乖離リスクの項目が一段下がる。

## 項目別

### 1. シグナル網羅性: 4 / 5 (前回 4 → 4, ±0)

- `predictor/rules.py` `features.py` 本体は無編集。距離/コース/血統/脚質/上がり3F/騎手/馬体重/同種T/長距離 6 軸 + 当日傾向 + class_level + 道悪 + 時計系 という 12 namespace 構成は据え置き。`weights.json` トップキーも 25 個から変化なし。
- Kelly fraction は **シグナルではなく bet sizing 指標** なので、本軸の点数には直接影響しない。`_bet_metrics` の出力解像度が増えた (cap 0.05 張り付き → 連続値 7 種) ことで、下流の bet sizing と min_kelly フィルタが Kelly を「ランクシグナル」として利用可能になった点はプラスだが、`predict.py:172` で `kelly_fraction * 100` を表示・記録するのみで、`_score_one` や `_value_score` には Kelly を逆流させていない (= スコアリングに混入しない)。これは過適合回避として正しい設計判断。
- 据え置き。

### 2. 重み妥当性 / 過適合リスク: 4 / 5 (前回 4 → 4, ±0)

- `weights.json` 無編集 (mtime 据え置き)。直書き magic number は `score -= 1000` (異常区分 = 最下位確定マーカー、意図的直書き) の 1 件のみ。
- `min_kelly: 0.05` の妥当性: cap 撤廃前の閾値をそのまま流用しており、**uncap 後の Kelly レンジ (0〜0.0904) に対して 0.05 が「フル Kelly で資金 5% を賭けるべきと判断したエッジ」を意味するかは未検証**。検証 1 で得た分布 (max=0.0904) は cap 0.05 直上にあり、0.05 閾値は実質「全体の上位 30%」を拾うだけのカットラインに化けている可能性がある。`config.py:107` のコメント自体が「A1 マージ後に backtest で kelly_uncapped 分布を見て再 sweep」と明示しており、現状は **plan 上の暫定値** であることが文書化されている。
- 過適合リスクは A1 改修内では追加されていない (calibrator/weights 据え置き)。将来 min_kelly を再 sweep する際、**uncap 後の Kelly は LGBM v5 出力 × 古い bin calibrator × 市場 blend という多段の合成結果** なので、Kelly 単体閾値が `weights.json` で吸収できない確率歪み (項目 3 参照) を吸い込む懸念がある。

### 3. 信頼度判定 / 確率推定: 3.5 / 5 (前回 4 → 3.5, -0.5)

- `_confidence` (rules.py:682-707) と `_score_probabilities` (rules.py:710-740) は無編集。閾値 `confidence.min_score=110 / min_gap=25 / min_stability=12 / negative_gap=28` は前回 P05 から維持。
- `_score_probabilities` の温度 (`PRED_PROB_TEMPERATURE=30.0`) と shrink (高信頼 0.20 / 暫定 0.70) は二重がけだが、温度と shrink の役割が直交しているので「二重がけ」自体は問題なし。
- **calibrator 古さによる Kelly 信頼性の劣化** (★ ユーザ依頼の評価ポイント 3):
  - `calibrator.json`: `type=bin`, `trained_from=20210101`, `trained_to=20231231`, `generated_at=2026-05-12T23:12:38`, `rule_version=p07-train-21-23`, `source_count=142713`.
  - `lgbm_meta.json`: `generated_at=2026-05-16T08:54:23`, `val_brier=0.0606`, `rule_version=lgbm-v5-tier23`.
  - パイプライン: rule prob → LGBM v5 blend (`PRED_BLEND_W_RULE=0.5`) → **20210101-20231231 期間で fit した bin calibrator** → `_investment_probability` で市場 blend & odds discount → `_bet_metrics` で Kelly 計算。
  - 問題: LGBM v5 出力分布は (a) v4 → v5 で Brier 0.0604 → 0.0606 微改善、(b) Tier 2.3 で 98 features に増えた、(c) val 期間が calibrator fit 期間と異なる、の 3 重で **校正データの根拠とずれている**。bin calibrator の上位 bin (>=0.4) は count 93/15/2/0/0/... と既に少数 bin の恒等寄せ (`min_count=20`) が支配的で、`_apply_calibrator` の安全弁が頻発し、結果として「**LGBM が >=40% と判断した馬は raw 確率がそのまま投資確率に通る**」状態。
  - Kelly = `(b·p − (1−p))/b` の `p` が calibrator を素通り → odds × p が直接 Kelly に効く → **LGBM の自信過剰が cap 撤廃で増幅される**。検証 1 で観測した K=9.04% は odds 6 倍前後 + p≈18% を仮定すると合致するレンジで、現状の校正状態では「LGBM 信頼度がそのまま Kelly に伝播」している。Phase A2 の Isotonic 再 fit までは Kelly 値はやや上振れ気味と読むべき。
- 信頼度ラベルは現状の絞り運用 (場 04+09 + min_kelly>=0.05) で **5 戦中 0 件が「混戦/暫定」除外** されている可能性が高い (`exclude_confidence=[]` のまま)。`_confidence` の出力がフィルタに効いていないのは P12 → P15 と継続する課題で、A1 では未着手。
- -0.5。

### 4. デッドコード / 設計の整合性: 4.5 / 5 (前回 4.5 → 4.5, ±0)

- ★ ユーザ依頼の評価ポイント 1 (Kelly cap 二段構えの責務分離):

  | レイヤ | 場所 | cap 値 | 役割 |
  |---|---|---|---|
  | 内部表現 | `rules.py:916` `_bet_metrics` | `min(kelly, 1.0)` | **数値安全弁** (NaN/異常入力対策、理論最大) |
  | 投資意思決定 | `config.py:108` `min_kelly: 0.05` | 下限フィルタ | **絞り条件** (買うかどうか) |
  | 賭金算出 | `predict.py:55-57` `compute_bet_size` | `min(1.0, kelly)` + `min(size, bet_unit)` | **資金管理** (1/4 Kelly + bet_unit 上限) |

  この 3 段は責務が直交しており、改修前 (`_bet_metrics` で 0.05 cap → min_kelly 0.05 でフィルタ) の二値縮退バグを正しく解消している。**1.0 cap が「実 Kelly がそこに張り付かない安全弁」として機能している** ことは検証 1 (max=0.0904) で確認済。設計として妥当。

  唯一の引っかかり: `compute_bet_size` 側の `min(1.0, ...)` は `_bet_metrics` 側の cap が既に 1.0 なので冗長 (理論上 kelly_fraction が 1.0 を超えることはない)。**防御的多重 cap として残すのは可だが、コメントで「`_bet_metrics` 側で既に cap 済、ここは念のため」と明示するともっと良い**。

- features.py で生成し rules.py で参照していない feature: `mining_dm_rank`, `mining_tm_rank/score`, `jockey_track_top3_rate`, `horse_track_top3_rate`, `sire_track_top3_rate`, `race_month`, `track_recent_30d_top3_rate`, `track_recent_90d_*`, `jockey_recent_30d/90d_top3_rate` 等。これらは **`predictor/lgbm_features.json` に列挙され LGBM 入力として使われている** ことを確認 (rules.py で使わないのが正しい設計、dead ではない)。

### 5. 本番運用との乖離リスク: 3 / 5 (前回 3 → 3, ±0 ただし内訳変化)

- ★ ユーザ依頼の評価ポイント 4 (機会極小化):
  - 1.5 ヶ月 backtest 408 レース中、絞り運用は **5 戦 / 的中 0 / 回収率 0%**。WL 単独 (場 04+09 のみ) では 120 戦 / 15 的中 / 161% という素地があり、**min_kelly>=0.05 がレース数を 1/24 に絞っている**。
  - これは P15 採用時 (recent-3fold で min_return 86.4%) と P16 backtest (5 戦/0 勝) の間に大きな**サンプル不足**があり、回収率の点推定が分散爆発レンジで、まだ判断材料不足。Phase A2 (Isotonic 再 fit) と閾値再 sweep 後でないと「機会の薄さ」自体は評価できない。
  - ただし「絞り運用 5 戦中 1 勝出れば 200% 超え、0 勝なら 0%」という分散構造は構造的にハイリスクであり、**月次監視 (CLAUDE.md 必須ルール 4) で Brier ではなく "betting opportunity count" もチェック必要**。Brier 警告だけだと「機会ゼロで Brier も計算できない」状態を見逃す。
- `leg_quality_code` / `same_day_*_bias` は本番朝〜午前で取得不可な後付けデータ。`features.py:1059-1066` で `estimated_leg_code` フォールバックを生成し、`rules.py:197-199, 389-390` で「(推定 N 走)」と reasons に明示している。良い設計だが、`feature_warnings` (`leg_quality_unavailable`, `leg_quality_estimated`, `same_day_bias_unavailable`) が `Prediction.feature_warnings` に伝播するのみで、**買い目選別 (`_is_bet_candidate`) では使われていない**。本番運用で「leg_quality_unavailable な馬を Kelly>=5% で買う」ことが許容されている。
- A1 改修自体は本番運用乖離を増やしていない (Kelly 計算経路の純粋な数値変更)。3 据え置き。

## 改修前後の比較記録

| 項目 | 前 (P15 採用直後) | 後 (P16 A1) | 差分 |
|---|---|---|---|
| `_bet_metrics` Kelly cap | `min(kelly, 0.05)` | `min(kelly, 1.0)` | uncap 連続値化 |
| Kelly 観測分布 (top1, 2026-05-10, 36 R) | `{0.0, 0.05}` 二値 | `{0, 0.0126, 0.0163, 0.0355, 0.0359, 0.0624, 0.0904}` 連続 7 種 | 解像度回復 |
| Kelly max | 0.05 (cap) | 0.0904 (実値) | cap を超えた 9.04% を観測 |
| `config.BUY_FILTER_DEFAULT["min_kelly"]` | 0.05 (cap 後比較) | 0.05 (uncap 後比較) | **意味が変わった** (実 5% Kelly エッジ) |
| `_bet_metrics` コメント | なし | 6 行 (cap 撤廃の根拠 + bet sizing 段階の責務) | 文書化 |
| `--bet-unit` help text | 100 円推奨のみ | `bet_unit >= 1000` 円推奨 + Kelly 解像度の注記 | 運用ガイド追加 |
| `min_kelly` コメント (`config.py:96-108`) | wl_kelly_ge_05 採用根拠のみ | + uncap 後の意味 + bet_unit ガイド + 再 sweep planned | 引き継ぎ品質 ↑ |
| backtest 1.5 ヶ月 (2026-04-01〜2026-05-15) ◎ベタ買い | — (P15 既知) | 77.0% (408 戦) | 全体傾向確認用 |
| backtest 1.5 ヶ月 WL 単独 | — | 161% (120 戦/15 的中) | 場フィルタの威力確認 |
| backtest 1.5 ヶ月 絞り運用 | — | **0% (5 戦/0 勝)** | サンプル極小、要観察 |
| Brier (1.5 ヶ月) | — | 0.0616 (val_brier 0.0606 と整合) | 全体校正は健全 |
| calibrator.json (mtime) | 2026-05-12 | 同左 | **未更新** (Phase A2 で対応) |
| lgbm_model.txt (mtime) | 2026-05-16 08:54 | 同左 | LGBM v5 本日訓練 |

## 主な改善提案 (優先度順 3 件)

### 1. Phase A2 の Isotonic 再 fit を最優先

LGBM v5 で本日 (2026-05-16) Brier 0.0606 達成 / Tier 2.3 で 98 features に拡張済。bin calibrator は 2026-05-12 時点で v4 出力 + 21-23 ground truth で fit。**校正対象モデルがズレている**ため、Kelly が高 p 帯で構造的に上振れている可能性。`scripts/backtest --save-calibrator --calibrator-type isotonic --from 20240101 --to 20251231` で TEST 期間を使った fit に切り替え、isotonic の段差吸収で高 p 帯 (>=0.20) の局所校正を回復させる。所要 1-2 時間。

### 2. `compute_bet_size:55` の重複 cap にコメント追加 (10 分)

```python
# _bet_metrics 側で既に min(kelly, 1.0) 済。ここは防御的多重 cap (将来
# kelly_fraction を別経路で算出する場合の保険) として残す。
kelly = max(0.0, min(1.0, float(pred.kelly_fraction or 0)))
```

二段構えの責務分離を明示化することで、`_bet_metrics` 側の 1.0 cap を将来「実 Kelly はあり得るから外そう」と動かしても compute_bet_size が落ちないと保証できる。

### 3. `weekly_monitor.bat` に "betting opportunity count" チェックを追加

5 戦/1.5 ヶ月 = 月平均 3.3 戦の絞り運用は、Brier drift 警告 (>+20%) だけでは「機会ゼロでサンプル不足」状態を検知できない。`scripts.monitor` に `--min-opportunities 5` 等を追加し、直近 30 日で買い候補 < 5 件なら「絞りすぎ警告」を出す。

## 前回からの差分

- シグナル網羅性: 4 → 4 (±0)
- 重み妥当性 / 過適合リスク: 4 → 4 (±0)
- 信頼度判定 / 確率推定: 4 → 3.5 (-0.5) — LGBM v5 と bin calibrator の入力分布ずれが Kelly 信頼性に直撃 (Phase A2 で解消予定)
- デッドコード / 設計の整合性: 4.5 → 4.5 (±0)
- 本番運用との乖離リスク: 3 → 3 (±0)

## 補足

A1 改修は **数値的に正しい uncap** + **責務分離が読める cap 二段構え** + **コメント/help text による意味の再定義** の 3 点で構成されており、コード品質としては良改修。総合 0.1 ポイントの低下は A1 の責任ではなく、(a) P15 採用時から残る calibrator 古さ問題が Kelly cap 撤廃で「Kelly 値の信頼性」として可視化された、(b) 絞り運用のサンプル極小化がプリプロのまま残ったことの 2 点。Phase A2 (Isotonic 再 fit) + min_kelly 再 sweep 後に再採点で +0.3〜+0.5 戻る見込み。
