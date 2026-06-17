# 採点 2026-06-17 09:30

**改修内容**: P25 scorecard 残リスク 6 件対応 (commit `a00a93c`) — calibrator 互換テーブル / 検証モード警告強化 / 二重取り込みリスク監査 + ablation test / GUI 操作ヘルプ + unit_yen 連動 / day-nav 44pt + バッジコントラスト / JVStatus 2 段タイムアウト

**対象ファイル**: `predictor/rules.py`, `jvlink_client/client.py`, `gui/app.py`, `web/generator.py`, `web/templates/index.html.j2`, `tests/test_calibrator_compat.py`, `tests/test_jvlink_download_timeout.py`, `tests/test_market_popularity_scoring.py`, `tests/test_template_render.py`

## 総合スコア (項目平均) の推移

| 専門家 | 今回 | 前回 (20260616_2147) | 差分 |
|---|---:|---:|---|
| GUI / UX 監査人 | **4.0** | 3.7 | +0.3 |
| モバイル HTML レビュアー | **4.4** | 4.2 | +0.2 |
| 予想ロジック分析 | **3.9** | 3.6 | +0.3 |
| 収益性 / 投資判断 | **2.0** | 2.0 | ±0 |
| データパイプライン | **4.32** | 4.2 | +0.12 |
| コード品質 | **4.2** | 4.0 | +0.2 |
| 検証プロセス | **3.8** | N/A (shutdown) | — |

**7 役平均: 3.80 / 5** (前回 6 役平均 3.62 比較不可だが改善方向)。CLAUDE.md の -0.3 警告は発火せず。

## 各専門家の所見

### GUI / UX (4.0)

- 主要 9 ボタン (取得→予想→公開 / Ⅰ〜Ⅳ / 血統 / 確認 / プリセット / 中止) に動詞主語の title 付与。Nielsen #10 を「ツールチップでインラインに置く」形で実装
- 検証モード処理を Python 側で予防+説明、role=alert の赤バナーで誤運用ガード
- step→unit_yen 連動で UI と Python の二重管理を 80% 解消 (placeholder のみ静的残)
- 改善提案: placeholder も unit_yen 連動 / 主要ボタンに aria-label 併記 / verification-warning に aria-describedby 双方向リンク

### モバイル HTML (4.4)

- day-nav 実効タップ高 44px (Apple HIG 充足)、`display:inline-flex` で flex 仕様の min-height 効果を確認
- verification-banner 実測コントラスト: light 6.15:1 / dark 7.69:1 (AA 余裕)
- buy-reco-label 5.74:1 → 10.0:1 / 10.4:1 で AAA 到達
- HTML サイズ 415 KB / 9088 行 (1 MB 警戒の 41%)、+30 行 / +2 KB
- **新規発見の懸念**: `scroll-margin-top: 11rem` (176px) は verification-mode + 複数日同時で約 28px 食い込み (本番経路では当たらない)
- 改善提案: body.verification-mode で scroll-margin を 13.5rem 化 / nav-buy コメントの実測値を 6.40:1 に訂正 / vb-sub を clamp 化

### 予想ロジック (3.9)

- 互換テーブル設計 + rationale 60 文字以上テストガード + Plan Step 7 への遅延を「fresh rate 0.4%、Brier 差 -0.000」根拠で正当化
- 多段経路 (A/B/C) docstring が「どの層で何回市場を取り込むか」を初めて明示
- ablation env (PRED_W_popularity_first=0 等) は `_w()` 規約と整合、test 化済
- **減点**: docstring の「(B) model_weight 0.30〜0.72」は fallback 値で実 weights.json (0.30〜0.85) と乖離、シンボリック参照に変更すべき
- 改善提案: docstring の数値を weights.json への参照に置換 / rationale に閾値表現 (delta_brier < 5e-4) と削除トリガー追加 / 互換テーブル登録 ≠ 実弾採用承認を明示

### 収益性 (2.0)

- buy_only n=385 / hits=52 / **回収率 65.77%** (CI [47.95%, 83.19%]) — **CI 上限でも控除率 80% を辛うじてかすめる程度**、実弾投入不可
- pop_0_0_0 と pop_7_4_2 の buy_only stats が完全一致 = 市場人気 A 層加点は A/B 期間で実質ノイズ (有害も無いが期待効果も無い)
- 本 commit はバックテスト再実行・戦略変更を伴わず、収益数値は不変
- 検証モード公開セーフティ (3 多重防御: CLI / GUI / テンプレ赤バナー) は意思決定の摩擦が正しい方向に設計されている
- 改善提案 (順): holdout (out-of-sample) backtest の必須化 / pop1-3 フィルタの robust 再選定 (`--recent-3fold`) / `--allow-stale-publish` の使用ログ化

### データパイプライン (4.32)

- 2 段タイムアウト設計 (全体 1800s / stall 120s) は setup 取得・差分取得の両方に耐える
- sleep/clock 注入による単体テスト 5 ケースは「教科書通り」、msec 単位で完了
- 例外メッセージに dataspec / 達成度 / 経過秒 / 関連 env 名すべて含まれ「SRE ポストモーテム品質」
- fetch_realtime + only_files は経路分離で退行なし、`fetch_state.json` の冪等性も維持
- **残リスク**: `_wait_download_complete` raise が `fetch()` の try/finally 外側で起きる (with 文を使わない経路では JV-Link セッション leak リスク、本 commit が増やしたものではない)
- 改善提案: stall pre-warn イベント (`stall_timeout/2` 経過で on_progress 通知) / env 不正値フォールバックのテスト追加 / timeout メッセージに fromtime/option を含める

### コード品質 (4.2)

- 互換テーブルの rationale 60 文字以上必置 + `test_compat_known_version_logs_info` で「現行版が table に登録されている」を assert = **触り忘れが静かに壊れず fail-fast 化**
- `_wait_download_complete` の sleep/clock keyword-only DI は教科書通り
- ablation env テストは「ablation したつもりが reason 出力だけ残って嘘表示」失敗モードを直接検出
- **減点**: publish ガードが 3 箇所 (CLI / GUI / テンプレ) に分散、純関数 `assert_safe_to_publish` で集約推奨。Python 直 import 経路 (`render()` 直呼) は未防御
- 改善提案: publish ガード単一出典化 / stall pre-warn / compat テストの skip 化 (登録不要ケース区別)

### 検証プロセス (3.8)

- バックテスト設計の事前固定 (主/副窓、4-fold、bootstrap race 単位 10,000 回、採用条件 ROI 180% + CI 下限 100% + 4-fold MIN 80%) は前々回までに整備済
- Plan Step 7 への正式遅延は walk-forward 規律と整合
- **calibration 項目で -1**: 「Brier 差 -0.000 だから流用 OK」は **発火帯 (33 horses / 11 races) に限定した subset metrics が無い** ため希釈された aggregate での「検出力不足」に過ぎず、「差が無い」の立証ではない
- 層 (A)/(B)/(C) の **直交実験計画 (factorial design) が Plan に未明示** — ablation 可能性と ablation 実施計画は別物
- 改善提案 (優先順):
  1. **互換テーブルに「失効トリガ」を機械化** (`max_fresh_rate=0.05` 等で自動 warning 昇格)
  2. **発火帯限定 Brier / reliability の自動算出**を `scripts/backtest.py` に追加 (`market_snapshot.bonus_subset_metrics`)
  3. **3 層 factorial 設計を Plan に追記** ({on,off}^3 の 8 セルから最低 4 セル paired run)

## 横断的に見た優先課題

1. **発火帯限定 reliability 計測の追加** (担当: validation-process-auditor + prediction-logic-analyst)
   - 互換テーブルの根拠は集約 Brier 差 -0.000 だけ。発火 11 race の subset Brier / logloss / reliability bin を `scripts/backtest.py` の `market_snapshot.bonus_subset_metrics` に保存し、Plan 合格条件「reliability curve が高p帯で過剰自信を悪化させない」と紐付ける。これが整わないうちは互換テーブルの数値根拠は薄い。

2. **互換テーブルの失効トリガを機械化** (担当: validation-process-auditor + code-quality-reviewer)
   - `CALIBRATOR_COMPATIBLE_RULES_VERSIONS` の dict 値を `{rationale, max_fresh_rate, max_bonus_horse_ratio}` に拡張し、直近 backtest JSON の `market_snapshot.fresh_horses / horses_total` を `_load_calibrator` で読んで閾値超過なら強制 warning に昇格。現状は「人間が忘れたら永久に info」。

3. **採用構成の真の holdout backtest** (担当: profitability-judge)
   - 現状 backtest は `calibration_in_sample=true`。p21 calibrator (trained_to=20251231) **以降の 2026-01-01〜2026-06-14 のみ** で buy_only 回収率と CI を再導出。65.77% / CI [47.95%, 83.19%] は in-sample 値である可能性を直視する。

## 残リスク (前回比)

- **収益性 (横ばい 2.0)**: pop1-3 フィルタは buy_only 65.77% で控除率割れ、実弾運用不可は継続。本 commit は悪さしていない確認のみ
- **calibration 信頼性 (-1)**: warning ノイズを info に降格しただけで calibrator の鮮度 / out-of-sample 化は未着手
- **3 層 factorial 計画未明示**: ablation env はテスト化されたが実行計画 (paired backtest) は未策定
