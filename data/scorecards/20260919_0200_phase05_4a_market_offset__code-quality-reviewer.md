# コード品質 / 保守性レビュアー 採点 — efe611c Phase 0.5-4A 市場オフセットモデル

**改修タイプ宣言**: type-B (検証/診断スクリプト)。P25 固有ゲートは N/A。

## 判定: HOLD

**理由**: 科学的結論 (不合格) は HEAD から全数値を再現でき揺るがないが、この diff の見出しである「数値修正 + 回帰テスト 2 件」が実態と食い違う。(1) **旧コードが新テスト 2 件を両方 PASS する** = 発散の再発を検出しない、(2) 修正の根本原因診断 (スケール差 → 条件数) が **誤り** で、実効成分はステップ制限のみ、(3) `main()` が既定の Windows コンソール (cp932) で **UnicodeEncodeError で落ち JSON を保存しない** (実走で再現、85 秒の計算が消える)。
**根拠ファイル**: `scripts/fundamental_eval.py:138-172` / `scripts/market_offset_eval.py:289,321` / `tests/test_feature_manifest.py:162-217`

## 総合: 2.6 / 5 (前回 2.8、−0.2)

## 項目別

- **DRY / 単一出典: 3/5** — (a) `market_offset_eval.py` が CLI スクリプト `fundamental_eval` から 8 関数 (うち 4 つは underscore 私有名) を import。**依頼 4 への回答: 今切り出すべき**。消費者が 2 本になり純関数でテストも付いた今が最安。(b) `logit` が学習側 (clip 1e-6) と評価側 (clip 1e-9) で別実装。(c) race_id の文字列連結が SQL 3 箇所 + f-string で 4 重定義。(d) `BONFERRONI_Z` と print 内リテラルの二重記述。
- **dead code: 3/5** — `BONFERRONI_Z` は **定義のみで参照ゼロ**。`meta.run_index: 1` はハードコードだが本 artifact は **2 回目** の実行 = 偽の来歴。`final_odds_confirmed` は計算するが `run()` で未使用。`_add_price_polynomial(fresh)` は二重適用。
- **マジックナンバー: 3/5** — `n_boot=300` が他の CI (1000) と異なるのに理由コメント無し・**meta に未記録**。`conditional_logit` の `2.0` / `1e-8` / `100` は根拠無し (2.0 は唯一の実効パラメータなのに)。
- **テスト容易性 / 変更失敗モード: 2/5** (前回 3) — **mutation 実測**:

  | variant | T1 (既知係数) | T2 (共線列) |
  |---|---|---|
  | 旧コード (efe611c^) | PASS | PASS |
  | 標準化なし / ステップ制限なし / リッジなし / 符号反転 / リッジ 1e-2 | PASS | PASS |
  | `beta / scale` 戻しなし | **FAIL** | PASS |

  → T1 が捕まえるのは scale 戻しの算術だけ、T2 は **何も捕まえない**。理由は Newton 法のアフィン不変性。実データ (z3 が −227 まで、margin std 0.08) では旧コード −2.728e9、bootstrap 40 回中 38 回が反復上限に到達し 1e21 を返す。

- **エラー処理 / 観測可能性: 2/5** — (a) **`main()` が cp932 で落ちる** (U+2265)。JSON 書き出しは print の **後** → 例外時に artifact 消失。実走: 1m24.7s 後 `UnicodeEncodeError`、JSON 未生成。(b) `run()` は `guard_analysis_window` の info を捨てる。(c) `fit()` の `snapshot()` は conn 無し → `data_version: None`。(d) `conditional_logit` は 100 反復上限でも **収束フラグ無しで値を返す**、`_block_boot` は NaN/None しか弾かないので未収束値が CI に混入する。

## 依頼 5 点への回答

1. **実走で壊れる箇所**: 上記 cp932 クラッシュ。`collect()` / `attach_market()` / `training_market()` の数値バグは無し (`win_odds` は INTEGER、異常値 0 件、`<=0` は abn 0/1/3 で 205/366/496 = `skip_no_market_price=496` と整合)。HEAD 再走で 626/8,279/931/12,533、β +0.9614/+0.3862、棄却 1 +0.4015、LogLoss 0.21351/0.21363 が **artifact と完全一致**。
2. **conditional_logit の修正**: リッジ符号は正しい (LL の Hessian は NSD)。ただし勾配側に −λβ が無いので真のリッジではなく減衰項で、**任意の λ で解を動かさない** (1e-2 でも bit 一致)。1e-8 は本データで **無効果**。ステップ制限は収束を壊さない (9 反復で 1e-9)。scale 戻しは正しい。**しかし標準化は実効成分ではない**: 標準化なし → +0.4015 に 8 反復収束、ステップ制限なし → −4.5e11 発散、旧 + ステップ制限のみ → +0.4015。コード注釈と PREREG の「条件数が跳ねた」は誤診断。
3. **新テスト**: 2 件とも本バグに対し **vacuous**。非 vacuous なレシピを検証済: レース内確率を softmax(N(0,1.5)) から作り logit(p) の 2 乗・3 乗と極小列 → 旧コード 1e278 発散 / 新コード有限。
4. **DRY**: 切り出すべき。
5. **verdict vs 事前登録 4-3**: 部分一致。棄却 1 は primary pass を前提にしているが 4-3 本文は無条件。棄却 2 は LogLoss 差で運用化だが 4-3 は指標未指定。金額は 4-2 に購入集合が無く、コードは `edge or all` のフォールバックで docstring と不一致、**最小件数ガード無し**。棄却 3 は例外で停止し JSON に記録されない。

## 変更失敗モード分析 (核心)

「将来の run で 5pt 超の馬が数頭だけ出る」場合: 3 レース 3 頭 (全勝 1.5 倍) で `roi_ci95=[1.5,1.5]` → `money_pass=True` (実測)。**3 点で「金額合格」が静かに立つ。**

「`if big > 2.0` を"標準化したので不要"として消す」場合: 注釈が標準化を主因と説明しているので自然な改修だが、全テスト PASS のまま実データで発散が再発し、`_block_boot` は上限到達値を CI に取り込む。**静かに壊れる。**

## 停止条件チェック

- [x] git_sha / git_dirty 記録あり (`dirty_paths` 6 件で正しく申告)
- [ ] baseline paired / market_snapshot counts / payout 欠損 — N/A (type-B)
- [x] 専門領域別 — 「誤読を招く出力」に **抵触寄り** (Bonferroni の閾値を見出しに出しつつ実際の区間は 95% パーセンタイル)。合否に使わない補助指標のため HOLD 止め

## 反証の試み

- 「標準化 + リッジ + ステップ制限で発散を修正」→ 成分分離で標準化・リッジは無効、ステップ制限のみ実効。**主張の因果は不成立**、結果 (+0.4015) は成立
- 「回帰テストを追加」→ 旧コードが両方 PASS。**不成立**
- 「artifact は HEAD の数値」→ 全項目 bit 一致。**成立**

## 主な改善提案

1. **T2 を発散再現レシピに差し替え + 注釈の誤診断を訂正**。`conditional_logit` は `(beta, converged)` を返し `block_boot` で未収束を除外。テストは `tests/test_eval_stats.py` へ移す
2. **artifact を print より先に保存、非 cp932 文字を排除**。`meta` に `n_boot_primary` / `guard_analysis_window` の info / `run_index` を CLI 引数化
3. **評価部品の切り出しと金額判定の固定**。`predictor/eval_stats.py` へ。`money_pass` は「edge 集合が最低件数未満なら `None` (判定不能)」に変え最低件数を事前登録へ

## 前回からの差分 (前回 2.8 / HOLD)

- DRY 3 → 3 / dead code 3 → 3 / マジックナンバー 3 → 3
- テスト容易性 3 → 2 (−1): 前回提案 1 (本命経路の AST 強制) は **実装確認済**だが、この diff の主題である回帰テスト 2 件が mutation で vacuous と実証
- 観測可能性 2 → 2: provenance の untracked 検出は改善、cp932 クラッシュによる artifact 消失が新規
- 判定 HOLD → HOLD。理由変更: 前回は「強制」主張と実装の乖離、今回は「修正の因果・回帰テスト」主張と実測の乖離 + 実走クラッシュ
