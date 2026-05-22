# P18 → 次セッション 引き継ぎメモ

**書いた日**: 2026-05-23 22:30
**書いた理由**: 本セッションで 4 回判定強度を訂正した (解釈の慣性が強い状態)。N1-N3 + N6-N8 を本セッションで続けて実施すると判断バイアスが残るため、**意図的に別セッションへ送る**。新鮮な頭で数値を見るための引き継ぎ。
**参照すべき先行 doc**:
- `data/scorecards/20260523_2200_p18_w_oracle_theoretical_ci_audit_v2.md` (v2 scorecard、これを起点に読む)
- `data/scorecards/20260523_2000_p18_w_oracle_theoretical_ci_audit.md` (v1、欠陥版、参考用)
- `data/recent_3fold_ci.csv` (filter_sweep --recent-3fold 結果、bootstrap CI 統合済)
- `data/oracle_diagnose.log` (oracle CI per fold + per month)
- `data/theoretical_w.log` (理論 CI grid + 現存戦略マッピング)

---

## 次セッション開始時の最初の作業

1. **`git status` 確認** (CLAUDE.md ルール 0)。
   - 本セッション末で worktree (`sweet-villani-2e3823`) に以下が commit 済:
     - filter_sweep bootstrap CI 統合 commit
     - 診断スクリプト 2 本 commit (oracle_diagnose.py, theoretical_w.py)
     - scorecard 3 本 + 計算ログ commit (recent_3fold_ci.csv/log, oracle_diagnose.log, theoretical_w.log は -f で gitignore 越え add 済)
   - 未 commit (= 残っているはずの状態):
     - `predictor/lgbm_model.txt` (EOL artifact のみの diff、commit せず維持)
   - master には `bde7915 Add .gitattributes` が既に commit 済。
   - worktree に一時置いた `.gitattributes` は削除済 (master 側にあるため、worktree branch が master から merge を受けるときに自然に取り込まれる)。
2. **scripts/filter_sweep.py の bootstrap CI 統合範囲**: 現状は `--recent-3fold` のみ。N1-N8 着手前に `--walk-forward`、`--walk-forward-3fold`、`--by-track-3fold`、`--holdout` への統合判断が要る。これらに CI 必要なら別 commit で追加。
3. **scorecard v2 を読む**。特に §3 各 U と §4 メタ部分。**「未確定」を「確定」と読み替えないこと**が本日 4 回の訂正から得た最大の学び。

---

## 解くべき問い (= scorecard v2 §3 の U リスト)

| ID | 問い | 関連 N | 工数 | 判定基準 |
|---|---|---|---:|---|
| U1 | 2026P fold underperformance の原因 (a)〜(e) のどれか | N1, N8 | 1-3h | 月次 LGBM Brier の trend + fold sensitivity |
| U2 | MING > LGBM の robust 性が真か、それとも payout 変動小さい strategy class 効果か | N2 | 0.5-1h | 同オッズ帯 LGBM 戦略の min_lo を MING と比較 |
| U3 | 採用判定基準 "0.80/0.50" が現実的に achievable か | N7 | 30 分 | 閾値 sensitivity 表で robust=Y 件数の変化 |
| U4 | 同季節 2025/2026 で oracle return_rate に有意差 | N3 | 30 分 | permutation test p-value |
| U5 | Phase B1 で robust=Y が出るか | — | (B1 後) | (U1-U3 後に再評価) |
| U6 | 「現実的予測者でも CI 下限 ≥ 0.50 は理論的に不可能」か | N6 | 30 分 | 戦略別 std で required_n を再計算 |

---

## 推奨実行順 (新鮮な頭での進め方)

### Phase H1: 軽量検証 3 本 (合計 1.5h)

これらは 30 分ずつの軽量検証で、終わると U3 / U4 / U6 が解ける (= 判定基準そのものの妥当性が確定)。**Phase H1 終了時点で Phase B1 plan を書き直してよい状態**に到達する可能性が高い。

1. **N3 (30 分) — 同季節 permutation test**
   - 問い: U4
   - スクリプト案: `scripts/season_permutation.py`
   - 入力: `oracle_diagnose` で取れる月次 return_rate データ (= `data/oracle_diagnose.log` から再抽出 or 同等の SQL 再走)
   - 出力: 2025-01〜05 と 2026-01〜05 の平均差 +63 pp が、月内 shuffle で得られる差分分布の何%-tile か
   - 判定: p < 0.05 → U4 採用 (有意差あり、regime shift か少なくとも payout drift)、p >= 0.05 → U4 棄却 (natural variation の範囲内)

2. **N6 (30 分) — 戦略別 std 逆算 + required_n 再計算**
   - 問い: U6
   - 計算: §1.6 gap カラムから各戦略の effective std を逆算 → §1.5 grid を戦略別に再描画
     - 逆算式: theoretical_lo に observed_lo を代入し、payout_std を解く
     - `theoretical_lo = return_rate - z * sqrt((p_hit * std^2 + p_hit * (1-p_hit) * mean_on_hit^2) / n) / 100`
     - 既知: theoretical_lo (= observed_lo), return_rate, p_hit, n, mean_on_hit。未知: std
   - 出力: 戦略 × fold で effective std と required_n の表
   - 判定: favorite 戦略 (dm_rank_1_3 等) で required_n が観察 bets 数より小さい → U6 (a) 採用、大きい → U6 (c) 採用

3. **N7 (30 分) — 判定基準 sensitivity**
   - 問い: U3-(d)、§4
   - 入力: `data/recent_3fold_ci.csv`
   - 計算: 閾値を (0.75, 0.45), (0.80, 0.50) [現状], (0.85, 0.55), (0.70, 0.40), (0.80, 0.40), (0.75, 0.50) で振り、各組み合わせで robust=Y 件数を集計
   - 出力: 閾値マトリクス
   - 判定: 現状 (0.80, 0.50) の周辺で robust=Y 件数が急変するなら「閾値が選択バイアス位置にある」可能性高い、滑らかなら「妥当」

### Phase H2: 中重量検証 3 本 (合計 3-5h)

Phase H1 で判定基準が確定したら進む。H1 で「判定基準そのものが疑わしい」と判明したら H2 をやる前に Phase B1 plan の根本から見直す。

4. **N1 (1-2h) — 月次 LGBM Brier**
   - 問い: U1-(b)
   - 月次でレースを回し、LGBM 予測 vs 実結果から Brier score を計算
   - 判定: 2026 月次 Brier が 2025 平均より +0.005 以上 → drift 仮説 (U1-b) 支持、未満 → drift 仮説 (U1-b) 棄却

5. **N8 (1h) — fold 分割 sensitivity**
   - 問い: U1-(e)
   - filter_sweep を異なる fold (例: 12 ヶ月 rolling、Q1-Q4 分割) で再走
   - 判定: "2026P のみ崩壊" パターンが他の分割でも残るか
   - 注意: 既存 filter_sweep に新しい fold モードを追加する必要あり、実装 30 分 + 走行 30 分

6. **N2 (0.5-1h) — 同オッズ帯 LGBM vs MING**
   - 問い: U2-(a)〜(d)
   - 各 fold で MING dm_rank_1_3 が picking した馬の平均オッズを計算 → LGBM 戦略のうち同じオッズ帯にいるものを選んで比較
   - 判定: 同オッズ帯 LGBM 戦略の min_lo が MING と同等 → U2-(d) 採用 (favorite class 効果)、MING が依然優位 → U2-(a) or (c) 採用

---

## 解釈バイアスへの注意 (本セッションの 4 回訂正から)

次セッションで N1-N8 の結果を見るとき、以下のパターンに注意:

- **「観察 = 解釈」と混同しない**: 「2026 oracle が高い」(観察) → 「2026 で何かが変わった」(解釈) を即書かない
- **対立仮説リストを必ず複数列挙**: 結果が 1 仮説に整合的に見えても、他の仮説を排除した証拠か必ずチェック
- **数字の方向ではなく強度に注意**: 本日 4 回、判定方向は変えても「確定的に語る癖」は維持していた。次回 v3 scorecard でこのパターンが再発しないか確認

---

## Phase B1 plan に進む条件 (本セッション末時点での提案、次セッションで再評価)

- Phase H1 が完了 (U3, U4, U6 が確定)
- かつ判定基準 (0.80, 0.50) が現実的 (sensitivity で滑らか)
- かつ規範外バイアス (fold 選択、season selection) が H1 で否定されている

この 3 条件すべてを満たすまで Phase B1 plan は書き換えない (= 元 plan のままだが、着手しない)。1 つでも崩れたら、Phase B1 の前提自体を再構築。

---

## このメモの自己評価

このメモも「未確定」を多用しているが、Phase H1/H2 の判定基準は「= XX なら採用」と決め打ち気味。**判定が結果次第で別方向に動くタイプの問い** (例: U1 はあらゆる方向への解釈余地が大きすぎる) に対しては、判定基準の決め打ちが新たな選択バイアスを生む。次セッションで判定基準を実行前に固定するか、結果を見てから議論するかは、ユーザ判断を仰ぐべき。
