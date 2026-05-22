# P18 v2: W oracle + theoretical CI audit (Phase B1 着手前の前提検証)

**日時**: 2026-05-23 22:00
**v1 との差分**: critic 第三者チェックで以下 4 点を修正
1. §2 R2 を §3 U6 へ移動 (R2 の「棄却」根拠が theoretical_w の前提 = full-population std と一致せず、論理的に成立していなかった)
2. §1 末尾の gap 表に「theoretical_w 前提と戦略実態のずれを反映している」という強い注釈追加
3. §3 U1 と U3 に「judging procedure 自体の選択バイアス」対立仮説追加
4. §1 冒頭に robust=Y/hold/n 判定基準の用語定義と、picks/bets 数差注釈を追加

**v1 §2 R2 の規律失敗 (記録目的、スコープ限定)**: v1 で §2 R2「現実的予測者でも CI 下限 ≥ 0.50 は理論的に不可能」を棄却したが、根拠の theoretical_w は full-population std (= 全勝ち馬の払戻 std=2090 yen) を使っていた。注釈で「実際の favorite-focused 戦略では std はもっと小さい」と認めながら、判定は「棄却」のまま残した。これは前回まで指摘されていた「**判定強度が変わっただけで、確定的に語る癖が残っている**」パターンの典型。v2 で R2 を §3 U6 へ降格させる。

ただし v1 全体を否定するものではない: v1 でも観察/解釈分離 (§1/§3)、未確定の operational な再評価条件、メタの自己訂正可能性 (§4) は前進していた。瑕疵は **§2 R2 の判定残置という局所的な規律失敗** に限定される。

**目的**: Phase A1-S8 後の filter_sweep robust=0 件結果を踏まえ、Phase B1 (LGBM v6 再訓練) 着手前に「採用判定基準そのものの妥当性」「2026 fold underperformance の原因仮説の切り分け」を、解釈バイアスを抑えた状態で記録する。

**実装物**: `scripts/oracle_diagnose.py` (15 秒)、`scripts/theoretical_w.py` (3 秒)、`scripts/filter_sweep.py:466-538` (bootstrap CI 統合済、recent-3fold 限定)、`.gitattributes` (master commit `bde7915` 済、worktree の untracked コピーは削除して master からの merge 待ち)。

---

## 0. 用語定義 (v2 追加)

### filter_sweep --recent-3fold の robust 3 値判定 (案 Z、2026-05-20 採用)

```python
point_robust = (
    all(r["bets"] >= 10 for r in results)
    and all(r["return_rate"] >= 0.80 for r in results)
)
ci_robust = min_lo >= 0.50  # 3 fold の CI 下限の最小値
label = "Y"    if point_robust and ci_robust else \
        "hold" if point_robust else \
        "n"
```

* Y    = 3 fold すべてで点推定 ≥ 80% (= JRA 単勝控除率超え) かつ 3 fold すべてで bootstrap 95% CI 下限 ≥ 50%
* hold = 3 fold で点推定 ≥ 80% だが CI 下限 < 50% (= サンプル不足の可能性、PRODUCTION 期間で再判定保留)
* n    = 点推定で控除率超え未達

### picks vs bets の語彙差

* `filter_sweep` で言う **picks** = 1 race につき rank=1 かつ mark の予測が出た件数 (LGBM 推論経由)
* `oracle_diagnose` で言う **bets** = 1 race につき 1 件 (実勝ち馬の払戻取得、LGBM 経由なし、payouts テーブル直接)
* picks 数 (1740/1728/1380) と bets 数 (1727/1728/1266) の差は、tentative race スキップ条件と、payouts.tan_payout1 が NULL or 0 のレース (= 中止、無効) の扱いの違い。filter_sweep は前者でだけ落とし、oracle_diagnose は後者でも落とす。

---

## 1. 確定事実 (観察のみ。解釈は §3 を参照)

### 1.1 filter_sweep --recent-3fold (bootstrap CI 統合、76 戦略 × 3 fold)

| 項目 | 値 |
|---|---:|
| robust=Y (定義は §0 参照) を 3 fold すべて | **0 件 / 73** |
| robust=hold | **0 件** |
| robust=n | 73 件 |
| 全戦略中 min_lo の最大 (= MING `dm_rank_1_3`) | **53.4** |
| 同 (LGBM `kelly_ge_05`) | **24.7** |

* fold 期間: 2025H1 (1740 picks)、2025H2 (1728 picks)、2026P (1380 picks)
* 2026P fold は 1380 picks / 5 ヶ月、他 2 fold より bet 数で 21% 少ない
* CSV: `data/recent_3fold_ci.csv` (sec=8481、実時間 141 分)

### 1.2 oracle (勝率 100% baseline、`scripts/oracle_diagnose.py`)

| fold | bets | return_rate | CI 下限 | CI 上限 |
|---|---:|---:|---:|---:|
| 2025H1 | 1727 | 1032% | **941%** | 1152% |
| 2025H2 | 1728 |  945% | **865%** | 1025% |
| 2026P  | 1266 | 1103% | **972%** | 1260% |

min_lo across folds = **865%** (2025H2)。
2026P の CI 下限 (972%) は 2025H2 の min より高い。

### 1.3 同季節比較 (oracle 月次、2025-01〜05 vs 2026-01〜05)

| 月 | 2025 | 2026 |
|---|---:|---:|
| 01 | 1042 | 1156 |
| 02 | 1012 | 972 |
| 03 | 1099 | 1182 |
| 04 | 1003 | 1052 |
| 05 | 1078 | 1186 |
| avg | **1047** | **1110** |
| range | 1003-1099 (96 pp) | 972-1186 (214 pp) |

### 1.4 payout 分布特性 (2025-01〜2026-05 通期、JRA 中央、n=4721)

| 項目 | 値 |
|---|---:|
| 単勝払戻 mean (1 着馬、100 円賭け対応) | 1019 yen |
| 単勝払戻 std | 2090 yen |
| CV (std/mean) | **2.05** |

### 1.5 理論 CI 下限 = 0.50 達成に必要な n_bets (full-population std 前提、`scripts/theoretical_w.py`)

| hit_rate | return_rate=0.80 | =0.90 | =1.00 |
|---:|---:|---:|---:|
| 0.10 | 2110 | 1224 | 810 |
| 0.20 | 3838 | 2175 | 1404 |
| 0.30 | 5656 | 3191 | 2050 |

**注釈 (重要)**: この表は full-population std=2090 yen を使った保守値。実際の予測戦略は payout 分布が full-population と異なる (favorite 戦略は std が小さい、long-shot 戦略は大きい) ため、**この required_n は対象戦略の真の必要 bets 数と一致しない**。「現実的予測者がこの bets で達成可能/不可能」を結論するには戦略別 std での再計算が必要。

### 1.6 現存戦略の理論 vs 観察 CI 下限 gap (診断目的、§3 U6 の根拠)

**この表は v1 で §1 に置いていたが、批判を受けて v2 では §1 末尾に降格し、「§3 U6 の診断材料」として位置づけ直した**。表だけ見て「MING gap +63.9 = robust」と誤読しないこと。

| 戦略 | fold | hit% | ret% | bets | obs_lo | th_lo | gap |
|---|---|---:|---:|---:|---:|---:|---:|
| dm_rank_1_3 | 2026P | 16.1 | 76.5 | 372 | 53.4 | -10.5 | +63.9 |
| tm_rank_1_3 | 2026P | 17.2 | 68.2 | 355 | 51.0 | -23.3 | +74.3 |
| all         | 2026P |  7.5 | 52.1 | 1380 | 37.2 |  20.4 | +16.8 |
| kelly_ge_05 | 2026P |  6.5 | 40.5 |  525 | 24.7 |  -6.9 | +31.6 |
| ev_ge_105   | 2026P |  6.5 | 58.9 |  674 | 32.9 |  15.3 | +17.6 |

**最重要注釈**: gap = obs_lo − th_lo (パーセンテージポイント)。**この gap は theoretical_w の前提 (= full-population std を全戦略に適用) と戦略実態 (= 戦略別に異なる payout 分布) のずれを反映している人工的な数値であり、戦略の robust 性を測る指標ではない**。gap が大きい (+63 等) のは、その戦略の hits が full-population より低 std な (= 高 favorite な) 払戻分布から来ているためで、戦略が「**理論より頑健**」ではなく「**理論計算の前提が当該戦略に合っていない**」を意味する。

正しい使い方: gap の大小で戦略別 std を逆算する diagnostic 材料 (§3 U6 で利用)。

---

## 2. 棄却された仮説 (= データが支持しない、と現時点で言える)

### 仮説 R1: 「2026 春に payout 分布レベルの regime shift がある」

**証拠**: oracle (勝率 100% baseline) の return_rate と CI 下限が 2026P で他 fold より高い (1103% / 972%) または同等。**仮に 2026 で勝ち馬構成が崩壊しているなら、oracle 自身が落ちるはず**。落ちていない。同季節 2025-01〜05 vs 2026-01〜05 比較でも、2026 各月は 2025 同月レンジから極端に外れていない (2025/03=1099, 2026/03=1182; 2025/05=1078, 2026/05=1186 と上振れだが、2025 通年 range [735, 1162] 内)。

**保留事項**: 「payout 分布レベル」では棄却できるが、「予測精度レベル」での regime shift (= LGBM/MING の 2026 適合度低下) は棄却できない (§3 U1 参照)。

**v2 で R2 を削除**: R2 (「現実的予測者でも CI 下限 ≥ 0.50 は理論的に不可能」を棄却) は v1 で「棄却」と判定したが、根拠の theoretical_w が戦略別 std を使っていなかったため、論理的に棄却の証拠にならなかった。v2 では §3 U6 に移動し、未確定として扱う。

---

## 3. 未確定 (= 現データで判定できない、要追加検証)

### 未確定 U1: 2026P fold の predictor 全般 underperformance の原因

* **対立仮説**:
  - (a) 真の regime shift (予測時点で観測可能な特徴の中で 2026 で意味が変わったものがある)
  - (b) model drift (LGBM v5 が訓練期間 2021-2023 から離れて精度劣化)
  - (c) sample noise (5 ヶ月 1266-1380 picks は CI を絞るには小)
  - (d) (a)+(b)+(c) の合成
  - **(e) fold 分割選択バイアス (v2 追加)**: 「2025H1 / 2025H2 / 2026P」という分割は P12 hold-out 失敗の文脈で 2026-05-15 に選ばれた。他の分割 (例: 2025Q1-Q4 / 2026Q1-Q2、または 12 ヶ月 rolling) で評価したら "2026P だけ崩壊" が消える可能性は検証されていない
* **判定不能の理由**: 5 ヶ月分のデータでは (a)(b)(c) の寄与を分離できない。月次の LGBM Brier / reliability gap が出れば (b) の寄与は推定可能だが、本セッションでは未実施。fold 分割の sensitivity 分析も未実施。
* **再評価条件**: 2026 後半 (6 月以降) 3-4 ヶ月分データ + 異なる fold 分割での再 sweep。

### 未確定 U2: MING (dm_rank_1_3 / tm_rank_1_3) が LGBM 派生戦略より robust か

* **観察**: min_lo は MING のほうが高い (53.4 vs 24.7)。
* **対立仮説**:
  - (a) MING に LGBM が持っていない情報源 (パドック、馬体重、当日馬場、人間判断) が含まれる
  - (b) MING は集約 (TM=10 段階, DM=11 段階) のため variance が小さく見える
  - (c) MING の取得経路で偶然 2025 期間に強かった (publication bias)
  - (d) **MING は「favorite 寄り = payout 変動が小さい」strategy class に属するので CI 下限が高く出やすい** (§1.6 gap +63.9, +74.3 がこの仮説を強く支持)
* **判定不能の理由**: theoretical_lo の gap カラムが示すように、tm_rank_1_3 / dm_rank_1_3 は payout 変動が小さい属性。これだけで「robust」と読めない可能性。(d) が真なら、同オッズ帯の LGBM 戦略は同等の CI 下限になるはず。
* **再評価条件**: 同 hit_rate / 同 picking-band (オッズ帯) の LGBM 戦略と直接比較 (Phase B1 別セッション N2)。

### 未確定 U3: 採用判定基準「点推定 ≥ 80% かつ CI 下限 ≥ 50%」が現実的に achievable か

* **理論側**: §1.5 required_n テーブルは「point return_rate ≥ 0.80 なら数千 bets で達成可能」を示唆。**ただし full-population std 前提なので、戦略別 std で再計算が必要 (= U6 の問い)**。
* **観察側**: 現存 73 戦略中 1 つも CI 下限 ≥ 0.50 を 3 fold で達成していない。
* **対立仮説**:
  - (a) 真の return_rate が 0.80 に届いていない (= 戦略がそもそも黒字ではない)
  - (b) bets 数不足
  - (c) fold 間の真値が変動 (時系列構造の問題で、normal approx の i.i.d. 前提が崩れている)
  - **(d) judging procedure 自体の選択バイアス (v2 追加)**: 「点推定 ≥ 80%、CI 下限 ≥ 50%」という閾値は本セッションで提案された (案 Z)。「JRA 控除率超え」「最悪でも半額返り」という意味付けは合理的だが、**閾値の具体値 (0.80, 0.50) が過去のデータに「丁度通る/通らない」位置に偶然 (または意識的に) 置かれていないか**は検証していない。閾値を 0.75/0.45 等にしたら robust=Y が複数出る可能性は否定できない
* **再評価条件**: 閾値 sensitivity 分析 (各閾値で robust=Y 件数を出す)、または independent な PRODUCTION 期間で先に判定基準を fix してから sweep。

### 未確定 U4: 同季節 2025-01〜05 vs 2026-01〜05 で oracle return_rate に有意差があるか

* **観察**: 同季節平均 2025=1047% vs 2026=1110%、+6%。range は 2026 で約 2 倍広い (96 pp vs 214 pp)。
* **判定不能の理由**: 5 ヶ月平均の +6% は payout 自然変動 (2025 通年 range 735-1162) に対し有意かどうか、permutation test 等を実施していない。range の広がりも 5 サンプルでは ergodic か偶然か区別不能。
* **再評価条件**: bootstrap permutation test 1 本で済む (別セッション N3)。

### 未確定 U5: Phase B1 (LGBM v6 再訓練 + Tier 2/3 features) で robust=Y が出るか

* 本検証範囲外。U1 が解けないと「足りない情報」を特定できないので、現状では希望的観測でしか判断できない。U3-(d) を満たすために閾値を緩めれば robust=Y は出るかもしれないが、それは「成功」ではなく「定義変更」。

### 未確定 U6 (v2 新規、v1 R2 から降格): 「現実的予測者でも CI 下限 ≥ 0.50 は理論的に不可能」か

* **観察**: §1.5 theoretical_w で hit_rate=0.20、point return_rate=0.80 で必要 n_bets ≈ 3,838 (full-population std=2090 前提)。これは届かない数字ではない。
* **しかし**: theoretical_w は **full-population std** を使っていて、これは大穴勝ちを含む全分布の std。実際の favorite-focused 戦略 (dm_rank_1_3 等) は std がもっと小さい (= §1.6 gap +63.9 が示唆) し、long-shot 戦略は逆に std がもっと大きい。戦略別に std を逆算するか、戦略実データから直接 bootstrap で必要 bets を見積もる必要がある。
* **判定不能の理由**: 戦略別 std を §1.6 gap から逆算する方法は思いつくが、本セッションでは未実施。
* **対立仮説**:
  - (a) achievable: 戦略別 std で再計算したら required_n は §1.5 表より小さくなる (favorite 戦略でほぼ確実)
  - (b) unachievable for some classes: long-shot 戦略 (oddhigh) は std が大きいため、現実的 bets 数では到達不能
  - (c) 戦略の return_rate 0.80 が真値に届いていないため、bets を増やしても CI 下限は 0.50 に到達しない (= U3-(a))
* **再評価条件**: §1.6 gap から各戦略の effective std を逆算 → required_n を戦略別に再計算 (30 分で実施可能、N3 と並行 OK)。

---

## 4. メタ: 本 scorecard の解釈も次回訂正される可能性

### 本セッション内訂正履歴 (前進したが慣性がある証拠)

| ターン | 訂正前 | 訂正後 |
|---|---|---|
| t1 | 「LGBM v5 の構造的限界」 | (本セッション末まで保留) |
| t2 | 「2026 regime shift 確定」 | 「payout レベルでは棄却、予測精度レベルでは未確定」 |
| t3 | 「sample noise が主因」 | 「sample noise 主因も棄却または支持の証拠なし、未確定」 |
| t4 (v1) | 「R2 棄却: 現実的予測者で CI 下限 ≥ 0.50 は achievable」 | (v2) 「U6 未確定: 戦略別 std で再計算するまで判定不能」 |

**本日 4 回判定強度を訂正**。次セッションで以下のいずれかに動く可能性が依然ある:

* U1 が (a) "真の regime shift" に転じる: 2026 後半データで oracle 自体が更に変動 + LGBM monthly Brier が悪化
* U1 が (c) "sample noise" に転じる: 2026 後半データで LGBM 精度が回復
* U2 の (d) 「favorite 戦略 class 効果」が支持される: 同オッズ帯 LGBM 戦略が MING と同等 CI 下限
* U3 (d) の判定基準選択バイアスが verifyされる: 閾値 sensitivity で「採用基準は過去議論を反映していた」と判明
* **v2 自体の解釈も誤りと判明**: 例えば U6 (b) "long-shot 不可能" が真なら、Phase B1 のスコープが strategy class 制約付きになる

### 判定基準そのものの選択バイアスについて (v2 追加 §4 補強)

本セッションで設定した判定基準群 ("点推定 ≥ 80%"、"CI 下限 ≥ 0.50"、"robust 3 fold AND") は、いずれも本対話の中で議論を経て選ばれた。**過去データを見ながら閾値を選ぶ過程で、暗黙的に「今のデータで丁度通らない位置」に閾値が collapse している可能性**がある。これは researcher degrees of freedom の典型で、PRODUCTION での再現性を独立に検証するまで脱出できない。Phase B1 着手前にこの sensitivity 分析を最低 1 度通す必要がある (= 別セッション N3 の拡張 or 新規 N6)。

---

## 5. 副次成果

### `.gitattributes` 修正 (master commit `bde7915` 済)

`predictor/*model*.txt -text` を追加。Windows core.autocrlf=true 環境で新規 worktree を切るたびに lgbm_model.txt が CRLF 変換され LightGBM パーサが落ちる事故を構造的に防ぐ。

worktree (`sweet-villani-2e3823`) には untracked コピーを一時的に置いたが、master commit 後に削除済 (二重 commit を避け、worktree branch が将来 master から merge する際に正しく取り込まれるようにするため)。`git check-attr text -- predictor/lgbm_model.txt` で `text: unset` (= binary 扱い) を master 側で確認済。

### 重い計算前 pre-flight checklist の改善 (CLAUDE.md ルール 1-ter の sanity 項目拡張)

本セッションで filter_sweep --recent-3fold を初回起動した際、worktree の `predictor/lgbm_model.txt` が CRLF 化されていることに気付かず約 8000 秒分の計算を失った。

**改善案 (ルール 1-quater 新設ではなく既存 1-ter (2) sanity の拡張)**: sanity 項目に「外部リソース (LGBM 等) の 1-record dry-run」を追加:

```
□ (2-b) 外部リソース動作確認: 1 race / 1 sample だけの dry-run で
        LGBM や calibrator が load + predict できることを確認した。
        (新規 worktree、predictor/ 改修、依存パッケージ更新の直後は必須)
```

ルールが増えるのではなく、既存 sanity 項目の sub-bullet 追加。

---

## 6. 次のアクション候補

| 案 | 内容 | 所要 | 解ける疑問 |
|---|---|---:|---|
| **N1** | 月次 LGBM Brier / reliability gap を計算 (`scripts/monthly_brier.py` 新規) | 1-2h | U1 の (b) 寄与 |
| **N2** | 同オッズ帯 LGBM 戦略 vs MING の直接比較 sweep | 0.5-1h | U2 (a)-(d) の切り分け |
| **N3** | 同季節 2025-01〜05 vs 2026-01〜05 の permutation test | 30 分 | U4 |
| **N4** | `.gitattributes` を master commit | 5-10 分 | (副次、本セッション末で実施) |
| **N5** | Phase B1 plan の書き直し | 1-2h | (条件 C により U1-U3 が解けるまで実施しない) |
| **N6 (v2 新規)** | §1.6 gap から戦略別 std 逆算 → required_n 再計算 | 30 分 | U6 |
| **N7 (v2 新規)** | 判定基準 (0.80, 0.50) の sensitivity 分析 | 30 分 | U3-(d), §4 |
| **N8 (v2 新規)** | fold 分割の sensitivity 分析 (異なる切り方で robust=Y 件数比較) | 1h | U1-(e) |

**本セッション末で N4 のみ実施、N1-N3 + N6-N8 は別セッションへ送る**。理由: 本日 4 回判定強度を訂正しており、解釈の慣性が強い。N1-N3 + N6-N8 は数値出力作業なので、新鮮な頭で結果を見るほうが解釈バイアスが入りにくい。

### 別セッションでの優先順序

新鮮な頭での実行順 (推奨):

1. **N3 (30 分)**: 同季節 permutation test。U4 を確定または棄却。最軽量で最初の頭ならし。
2. **N6 (30 分)**: 戦略別 std 逆算。U6 を確定または棄却。N3 と並行可能。
3. **N7 (30 分)**: 閾値 sensitivity。U3-(d) と §4 を確定または棄却。
4. **N1 (1-2h)**: 月次 LGBM Brier。U1-(b) の寄与を見る。
5. **N8 (1h)**: fold 分割 sensitivity。U1-(e) を確定または棄却。
6. **N2 (0.5-1h)**: 同オッズ帯比較。U2-(d) を確定または棄却。

**N3+N6+N7 (1.5h) で U3、U4、U6 の 3 つが解ける** ので、まずここで止めて Phase B1 plan に進めるか再判定するのが筋。N1+N8+N2 まで進めれば U1-U5 すべて解けるが、解釈の慣性を避けるならその前に再評価を挟む。

---

## 7. v2 自己評価 (v1 から何が改善したか / 残課題)

### v1 → v2 で改善した点

* §2 R2 を §3 U6 へ移動し、論理的整合性を回復
* §1.5 と §1.6 に強い注釈 (theoretical_w の前提と実態のずれ)
* §3 U1 に (e) fold 分割選択バイアス、U3 に (d) 判定基準選択バイアス追加
* §4 に判定基準そのものの選択バイアスについての独立段落追加
* §0 に robust 判定の用語定義、picks/bets 数差の説明追加

### v2 で依然残る可能性のある瑕疵

* §3 各 U の対立仮説は「思いついたもの」を列挙しているが、網羅的かどうかは検証していない。critic が次回 v3 で更に追加を求める可能性がある
* §1.5 と §1.6 の注釈は「読者が文脈を理解する」前提で書かれている。注釈を読み飛ばす読者にはやはり誤解を招く構造
* §0 用語定義は本 scorecard 内のみの定義。他の scorecard との整合性は未検証
* §4 メタの再訂正可能性リストは「思いついたもの」で、「次回まったく別方向に訂正される可能性」を網羅していない

**v2 も次回再読時に「やはり何かが混入していた」と訂正される前提**で書かれている。
