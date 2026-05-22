# P18: W oracle + theoretical CI audit (Phase B1 着手前の前提検証)

**日時**: 2026-05-23 20:00
**目的**: Phase A1-S8 後の filter_sweep robust=0 件結果を踏まえ、Phase B1 (LGBM v6 再訓練) 着手前に「採用判定基準そのものの妥当性」「2026 fold underperformance の原因仮説の切り分け」を、解釈バイアスを抑えた状態で記録する。
**実装物**: `scripts/oracle_diagnose.py` (15 秒)、`scripts/theoretical_w.py` (3 秒)、`scripts/filter_sweep.py:466-538` (bootstrap CI 統合済、recent-3fold 限定)、`.gitattributes` (worktree only、未 commit)。
**前提**: 本セッションでの前回解釈「2026 regime shift 確定」「MING > LGBM の robust 性」「P12 wl5_pop_1_2 の再現」はすべて取り下げる (oracle データで支持されない、または証拠不十分)。前々回解釈「LGBM v5 の構造的限界」も、本セッション末時点では「確定でも棄却でもない」状態に格下げ。

---

## 1. 確定事実 (観察)

### filter_sweep --recent-3fold (bootstrap CI 統合、76 戦略 × 3 fold)

| 項目 | 値 |
|---|---:|
| robust=Y (点推定 ≥ 80 かつ CI 下限 ≥ 50) を 3 fold すべて | **0 件 / 73** |
| robust=hold (点推定 ≥ 80 だが CI 下限 < 50) | **0 件** |
| robust=n | 73 件 |
| 全戦略中 min_lo の最大 (= MING `dm_rank_1_3`) | **53.4** |
| 同 (LGBM `kelly_ge_05`) | **24.7** |

* fold 期間: 2025H1 (1740 picks)、2025H2 (1728 picks)、2026P (1380 picks)
* 2026P fold は 1380 picks / 5 ヶ月、他 2 fold より bet 数で 21% 少ない
* CSV: `data/recent_3fold_ci.csv` (sec=8481、実時間 141 分)

### oracle (勝率 100% baseline、`scripts/oracle_diagnose.py`)

| fold | bets | return_rate | CI 下限 | CI 上限 |
|---|---:|---:|---:|---:|
| 2025H1 | 1727 | 1032% | **941%** | 1152% |
| 2025H2 | 1728 |  945% | **865%** | 1025% |
| 2026P  | 1266 | 1103% | **972%** | 1260% |

min_lo across folds = **865%** (2025H2)。
2026P の CI 下限 (972%) は 2025H2 の min より高い。

### 同季節比較 (oracle 月次、2025-01〜05 vs 2026-01〜05)

| 月 | 2025 | 2026 |
|---|---:|---:|
| 01 | 1042 | 1156 |
| 02 | 1012 | 972 |
| 03 | 1099 | 1182 |
| 04 | 1003 | 1052 |
| 05 | 1078 | 1186 |
| avg | **1047** | **1110** |
| range | 1003-1099 (96 pp) | 972-1186 (214 pp) |

### payout 分布特性 (2025-01〜2026-05 通期、JRA 中央、n=4721)

| 項目 | 値 |
|---|---:|
| 単勝払戻 mean (1 着馬、100 円賭け対応) | 1019 yen |
| 単勝払戻 std | 2090 yen |
| CV (std/mean) | **2.05** |

### 理論 CI 下限 = 0.50 達成に必要な n_bets (full-population std 前提、`scripts/theoretical_w.py`)

| hit_rate | return_rate=0.80 | =0.90 | =1.00 |
|---:|---:|---:|---:|
| 0.10 | 2110 | 1224 | 810 |
| 0.20 | 3838 | 2175 | 1404 |
| 0.30 | 5656 | 3191 | 2050 |

### 現存戦略の理論 vs 観察 CI 下限 gap

| 戦略 | fold | hit% | ret% | bets | obs_lo | th_lo | gap |
|---|---|---:|---:|---:|---:|---:|---:|
| dm_rank_1_3 | 2026P | 16.1 | 76.5 | 372 | 53.4 | -10.5 | **+63.9** |
| tm_rank_1_3 | 2026P | 17.2 | 68.2 | 355 | 51.0 | -23.3 | **+74.3** |
| all         | 2026P |  7.5 | 52.1 | 1380 | 37.2 |  20.4 | +16.8 |
| kelly_ge_05 | 2026P |  6.5 | 40.5 |  525 | 24.7 |  -6.9 | +31.6 |
| ev_ge_105   | 2026P |  6.5 | 58.9 |  674 | 32.9 |  15.3 | +17.6 |

---

## 2. 棄却された仮説 (= データが支持しない、と現時点で言える)

### 仮説 R1: 「2026 春に payout 分布レベルの regime shift がある」

**証拠**: oracle (勝率 100% baseline) の return_rate と CI 下限が 2026P で他 fold より高い (1103% / 972%) または同等。**仮に 2026 で勝ち馬構成が崩壊しているなら、oracle 自身が落ちるはず**。落ちていない。

**保留事項**: 「payout 分布レベル」では棄却できるが、「予測精度レベル」での regime shift (= LGBM/MING の 2026 適合度低下) は棄却できない (3 を参照)。

### 仮説 R2: 「normal approximation で見ても、現実的予測者の CI 下限 ≥ 0.50 は理論的に不可能」

**証拠**: theoretical_w grid によれば、hit_rate=0.20、point return_rate=0.80 で必要 n_bets は約 3,838。これは届かない数字ではない (年単位データで達成可能なオーダー)。現状の戦略はこの bets 数を満たしていない、または point return_rate 自体が低い、が原因と考えられる。

**注釈**: ただしこの「3,838 bets」は full-population std=2090 を使った保守値。実際の favorite-focused 戦略では std が小さく必要 bets はもっと少ない (= gap カラム +63 pp 等が示唆)。

---

## 3. 未確定 (= 現データで判定できない、要追加検証)

### 未確定 U1: 2026P fold の predictor 全般 underperformance の原因

* **対立仮説**: (a) 真の regime shift (予測時点で観測可能な特徴の中で 2026 で意味が変わったものがある)、(b) model drift (LGBM v5 が訓練期間 2021-2023 から離れて精度劣化)、(c) sample noise (5 ヶ月 1266-1380 picks は CI を絞るには小)、(d) (a)+(b)+(c) の合成。
* **判定不能の理由**: 5 ヶ月分のデータでは (a)(b)(c) の寄与を分離できない。月次の LGBM Brier / reliability gap が出れば (b) の寄与は推定可能だが、本セッションでは未実施。
* **再評価条件**: 2026 後半 (6 月以降) 3-4 ヶ月分データが揃った時点で再 sweep。

### 未確定 U2: MING (dm_rank_1_3 / tm_rank_1_3) が LGBM 派生戦略より robust か

* **観察**: min_lo は MING のほうが高い (53.4 vs 24.7)。
* **対立仮説**: (a) MING に LGBM が持っていない情報源が含まれる、(b) MING は集約 (TM=10 段階, DM=11 段階) のため variance が小さく見える、(c) MING の取得経路で偶然 2025 期間に強かった (publication bias)、(d) 単に MING が「favorite 寄り = payout 変動が小さい」strategy class に属するので CI 下限が高く出やすい。
* **判定不能の理由**: theoretical_lo の gap カラムが示すように、tm_rank_1_3 / dm_rank_1_3 は payout 変動が小さい属性。これだけで「robust」と読めない可能性。
* **再評価条件**: 同 hit_rate / 同 picking-band (オッズ帯) の LGBM 戦略と直接比較。

### 未確定 U3: 採用判定基準「CI 下限 ≥ 0.50」が現実的に achievable か

* **理論側**: required_n テーブルは「point return_rate ≥ 0.80 なら数千 bets で達成可能」を示唆。
* **観察側**: 現存 73 戦略中 1 つも CI 下限 ≥ 0.50 を 3 fold で達成していない。
* **不一致の解釈余地**: (a) 真の return_rate が 0.80 に届いていない (= 戦略がそもそも黒字ではない)、(b) bets 数不足、(c) fold 間の真値が変動 (時系列構造の問題で、normal approx の i.i.d. 前提が崩れている)。
* **再評価条件**: U1 と同じく追加データ + LGBM monthly Brier。

### 未確定 U4: 同季節 2025-01〜05 vs 2026-01〜05 で oracle return_rate に有意差があるか

* **観察**: 同季節平均 2025=1047% vs 2026=1110%、+6%。range は 2026 で約 2 倍広い。
* **判定不能の理由**: 5 ヶ月平均の +6% は payout 自然変動 (2025 通年 range 735-1162) に対し有意かどうか、t-test 等を実施していない。range の広がりも 5 サンプルでは ergodic か偶然か区別不能。
* **再評価条件**: bootstrap permutation test 1 本で済む (TODO)。

### 未確定 U5: Phase B1 (LGBM v6 再訓練 + Tier 2/3 features) で robust=Y が出るか

* 本検証範囲外。U1 が解けないと「足りない情報」を特定できないので、現状では希望的観測でしか判断できない。

---

## 4. メタ: 本 scorecard の解釈も次回訂正される可能性

本セッションで「regime shift 確定」(過剰確信) を「regime shift は payout レベルで棄却、ただし予測精度レベルでは未確定」(慎重) に格下げした。

しかし P18 時点で「未確定 U1-U5」と書いた項目も、追加 1-2 セッションで以下のいずれかに動く可能性がある:

* U1-(a) "真の regime shift" 側へ転じる: 2026 後半データで oracle 自体が更に変動した場合
* U1-(c) "sample noise" 側へ転じる: 2026 後半データで LGBM 精度が回復した場合
* U2 で MING の優位が消える: 同オッズ帯 LGBM 戦略を直接比較した結果、差が CI 下限の比較によるものと判明した場合

**したがって本 scorecard 自体も、Phase B1 着手後の追加データで再評価される前提**で書かれている。

---

## 5. 副次成果

### `.gitattributes` 修正 (worktree 適用済、master commit 未)

`predictor/*model*.txt -text` を追加。Windows core.autocrlf=true 環境で新規 worktree を切るたびに lgbm_model.txt が CRLF 変換され LightGBM パーサが落ちる事故を構造的に防ぐ。
本 worktree では `cp` で master の LF 版に置換済 (一時対応)。**master へ反映する**ことが新規 worktree 作成前に必要。

### 重い計算前 pre-flight checklist の改善 (CLAUDE.md ルール 1-ter)

本セッションで filter_sweep --recent-3fold を初回起動した際、worktree の `predictor/lgbm_model.txt` が CRLF 化されていることに気付かず約 8000 秒分の計算を失った (LightGBM のフォーマットエラー連発、CSV 出力空、復旧後再走 141 分)。

CLAUDE.md ルール 1-ter は「30 分超過の bg 実行前 checklist」だが、今回は filter_sweep は 30 分超想定だった (5-15 分の見積もりが甘く、実際 141 分) ため checklist 対象だった。実際には起動前の sanity check (model file checksum、または 1 race だけの dry-run) があれば 8000 秒のロスは回避できた。

**改善案 (ルール 1-quater ではなく既存 1-ter (2) sanity の拡張)**: sanity 項目に「外部リソース (LGBM 等) の 1-record dry-run」を追加:

```
□ (2-b) 外部リソース動作確認: 1 race / 1 sample だけの dry-run で
        LGBM や calibrator が load + predict できることを確認した。
        (新規 worktree、predictor/ 改修、依存パッケージ更新の直後は必須)
```

**この記録の本質はルール違反ではなく checklist 改善**。「ルールが増えた」と読むのではなく「既存 sanity 項目 (2) に sub-bullet 追加」と読むのが正しい。

---

## 6. 次のアクション候補 (Phase B1 着手前)

| 案 | 内容 | 所要 | 解ける疑問 |
|---|---|---:|---|
| **N1** | 月次 LGBM Brier / reliability gap を計算 (`scripts/monthly_brier.py` 新規) | 1-2h | U1 の (b) 寄与 |
| **N2** | 同オッズ帯 LGBM 戦略 vs MING の直接比較 sweep | 0.5-1h | U2 (a)-(d) の切り分け |
| **N3** | 同季節 2025-01〜05 vs 2026-01〜05 の permutation test | 30 分 | U4 |
| **N4** | `.gitattributes` を master commit | 15 分 | (副次、優先度高) |
| **N5** | Phase B1 plan の書き直しに入る | 1-2h | (条件 C により U1-U3 が解けるまで実施しない) |

**現セッション継続なら N4 → N3 → N1 → N2** の順が、軽い順 + 解ける疑問の重要度順で妥当に見える。ただし**現セッション終了して別セッションで N1-N3 を実施**する方が、判断バイアスをリセットできる利点がある (今日 1 日で 3 回判定強度を訂正している)。

ユーザ判断を仰ぐ。

---

## 7. Scorecard 自己評価

本 scorecard は条件 A (観察/解釈分離) を試みた最初の版。

* 1. 確定事実 → 数値のみで、解釈なし: **守れた** (と思う)
* 2. 棄却された仮説 → 各々に証拠 + 保留事項を明記: **守れた**
* 3. 未確定 → 対立仮説と「判定不能の理由」と「再評価条件」をすべて書いた: **守れた**
* 4. メタ → 本 scorecard 自体の再評価可能性を明記: **守れた**

ただし「守れた」自体が自己評価なので、次回別セッションで再読したときに「やはり解釈が混入していた」と訂正される可能性は残る。
