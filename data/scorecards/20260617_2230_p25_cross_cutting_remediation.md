# 採点 2026-06-17 22:30

**改修内容**: P25 横断課題 5 件対応 (commit `f8a786e`) — 発火帯限定 reliability 計測 / 互換テーブル失効トリガ機械化 / publish ガード単一出典化 / docstring symbolic 参照化 / scroll-margin verification-mode 化

**対象ファイル**: `web/publish_safety.py` (新規), `predictor/rules.py`, `scripts/backtest.py`, `gui/app.py`, `web/generator.py`, `web/templates/index.html.j2`, tests/test_publish_safety.py (新規), tests/test_calibrator_compat.py, tests/test_backtest_market_snapshot.py, tests/test_template_render.py

## 総合スコア (項目平均) の推移

| 専門家 | 今回 | 前回 (20260617_0930) | 差分 |
|---|---:|---:|---|
| GUI / UX 監査人 | **4.06** | 4.0 | +0.06 |
| モバイル HTML レビュアー | **4.5** | 4.4 | +0.1 |
| 予想ロジック分析 | **4.2** | 3.9 | +0.3 |
| 収益性 / 投資判断 | **2.2** | 2.0 | +0.2 |
| データパイプライン | **4.5** | 4.32 | +0.18 |
| コード品質 | **4.4** | 4.2 | +0.2 |
| 検証プロセス | **3.96** | 3.8 | +0.16 |

**7 役平均: 3.97 / 5** (前回 3.80 比 **+0.17**)。CLAUDE.md の -0.3 警告は不発火。

## 各専門家の所見

### GUI / UX (4.06)

- publish ガードが CLI / GUI / Python 直 import の 3 経路で純関数 `assert_safe_to_publish` に集約 → Nielsen #4 (一貫性) と #5 (エラー予防) で「ある日 warning が出ない」リグレッションをテストが検知可能に
- 状態整合性 4.0 → 4.3 (+0.3): 9 ケースで判定マトリクスを回帰固定化
- 改善提案: GUI publish() の StalePublishRefused をユーザ向け案内文に変換 (`gui/app.py:1099-1109`)

### モバイル HTML (4.5)

- scroll-margin worst case 計算: 検証モード + filter-summary 1 行で **+2.5px クリアランス**、worst (2 行) で ~18px 食い込み残存。前回主因 (28px 食い込み) は解消
- `body[class]` セレクタは iOS Safari 1.0+ 互換 (リスクゼロ)
- HTML 418.4 KB (1MB 警戒の 41.8%)
- **唯一の懸念**: vb-sub「実弾運用には使えません」が **11.5px / weight 400** で最重要 safety message に対して最小フォント (HIG キャプション 14.7px 下回り) → 改善余地
- 改善提案: vb-sub を 0.82rem / weight 600 に / scroll-margin を 14rem に / nav-buy 実測コメント 6.40:1 訂正

### 予想ロジック (4.2)

- 失効トリガ閾値 (fresh_rate 0.05 / bonus_candidate_rate 0.01 / expires_on 2026-09-30) は **12-14 倍マージン**で統計力的に妥当
- docstring symbolic 参照化は「事実は 1 箇所、参照は symbolic」のベストプラクティス
- `_horse_bonus_candidate` で発火判定を 3 箇所で同一定義、`test_horse_bonus_candidate_matches_market_snapshot_definition` で property test 化
- 改善余地: max_bonus_candidate_rate の根拠コメント「aggregate で見え始める」を「subset 主指標切替の境界 n=463」に書き換え / popularity weight の paired ablation backtest 未実行 (継続)

### 収益性 (2.2)

- backtest 再実行なし、buy_only 65.77% / CI [47.95%, 83.19%] は不変。**「実弾投入可」は依然書けない**
- EV 計算整合性 2.5 → 3 (+0.5): 失効トリガ機械化で「calibrator が静かに歪む」事故クラスが構造化
- 校正済み確率信頼性 2 → 3 (+1): bonus_subset_metrics で次回 backtest から refit 判断の一次資料が自動取得される
- 改善提案 (優先): bonus_subset_metrics 入り backtest を 1 回 sample 実行 / out-of-sample backtest (from=20260101) で buy_only CI 再導出 / publish_safety 発火を JSON ログ化

### データパイプライン (4.5)

- データ鮮度管理 (SLO) 4.5 → 5.0 (+0.5): calibrator compat 判定が **SLO 数値駆動の自動失効** に進化、「人間が忘れたら永久に info」の構造盲点を機械化で塞いだ
- `_latest_backtest_market_snapshot` の実測コスト: 6.15ms (36 files、mtime キャッシュで amortized ~0ms)
- フォールバック 4 層 (glob/stat OSError, JSONDecodeError, isinstance) で production 経路の例外伝播ゼロ → プロが本番承認できる水準
- 改善提案: bonus_subset_metrics の証明実行 (実 backtest で生成) / scandir で stat 走査 O(N) を 1 回に縮約 / 複合キー `(latest_path, mtime)` で TTL 強化

### コード品質 (4.4)

- DRY / 単一出典 4 → 5 (+1): publish 3 経路 + bonus_candidate 定義 + docstring symbolic 参照の 3 領域で構造的単一出典化を **1 commit で同時達成**
- テスト容易性 4 → 5 (+1): `evaluate_calibrator_compat(today=...)` の DI 化 + property test (発火帯判定 2 経路の count 一致) で「変更失敗モード」の自動検出を構造化
- エラー処理 5 → 4 (-1): StalePublishRefused 型導入は加点だが GUI publish() で型名 (`StalePublishRefused: ...`) が UI に露出する経路を新設、ユーザ向け観測性で減点
- 改善提案: `VERIFICATION_BANNER_MARKER` 定数化 + integration test / GUI publish() で StalePublishRefused を日本語案内化 / preview_head[:5000] の根拠コメント追加

### 検証プロセス (3.96)

- calibration 項目 2.8 → 4.3 (**+1.5**): 前回マイナス項目を直接是正
- 前回優先指摘 #1 (失効トリガ機械化) PASS / #2 (発火帯 reliability) PASS / #3 (3 層 factorial Plan 追記) **未対応で持ち越し 2 回目リスク**
- リーク分類学チェック: time leak は `calibration_in_sample=true` で残存 (本コミット範囲外、out-of-sample backtest 必要)
- 反証: `bonus_subset_metrics` の実証ファイルは現時点 0 件 (`grep` 確認)、設計点で 4.3、実証は次の backtest 再実行待ち
- 改善提案 (持ち越し宿題、優先順): docs/P25_MARKET_POP_VALIDATION_PLAN に 3 層 factorial 設計追記 / fold 3-4 限定 backtest で subset Brier を rationale に追記 / max_bonus_candidate_rate の根拠書き換え / `_latest_backtest_market_snapshot` integration test 追加 / weekly_monitor に bonus_candidate 累積を追加

## 横断的に見た優先課題

1. **bonus_subset_metrics 入りの backtest を 1 回 sample 実行** (担当: profitability + pipeline + validation)
   - 現在 `grep "bonus_subset_metrics" data/backtest/*-filtered.json` は 0 件。互換テーブル閾値 (0.05 / 0.01) の妥当性は机上のまま。1 回 backtest 走らせれば閾値が現実から何倍離れているか定量化できる

2. **真の out-of-sample backtest (`from=20260101`)** (担当: profitability + validation)
   - calibrator `trained_to=20251231` 以降のみで buy_only CI を再導出。CI 下限が現行 47.95% から大きく劣化したら pop1-3 戦略を `whitelist_tracks=[]` でサスペンドする判断材料に

3. **docs/P25_MARKET_POP_VALIDATION_PLAN に 3 層 factorial 設計を追記** (担当: validation)
   - 前回優先 #3、今回未着手で持ち越し 2 回目。`{on, off}^3` の 8 セルから最低 4 セル paired run の明示が必要。CLAUDE.md「持ち越し宿題は次回必ず執行」規律に従う

## 残リスク (前回比)

- ✓ **解消**: docstring 数値ズレ / 互換テーブル「永久 info」構造 / publish ガード 3 経路分散 / scroll-margin verification-mode 食い込み / 発火帯定義の単一出典化
- ✗ **継続**: 収益性 2.2 (フィルタ pop1-3 利益エッジ未確認) / calibrator out-of-sample 化 / 3 層 factorial Plan 追記 / popularity weight の paired ablation backtest
