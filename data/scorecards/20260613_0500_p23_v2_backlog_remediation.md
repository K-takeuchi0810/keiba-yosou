# 採点 2026-06-13 05:00 — P23: v2 監査バックログ全件是正

**改修内容**: P23 (commits 3835115 / b42ddfd / 7e839c2 / 8ad3767 / 73b8f20 / 4215ae0) — rubric v2 再ベースライン監査 (20260613_0030) の優先課題 9 件をすべて是正
**対象ファイル**: predictor/ (rules, filter, weights, calibrator), jvlink_client/ (client, ingest, state), gui/app.py, web/ (generator, template), scripts/ (backtest, monitor, refit_calibrator, bootstrap, predict), tests/ (+3 ファイル), docs/OPERATION.md

## 総合スコア (v2 同士の比較)

| 専門家 | 今回 | v2 baseline | 差分 |
|---|---|---|---|
| GUI / UX 監査人 | 3.8 | 3.6 | +0.2 |
| モバイル HTML レビュアー | 3.8 | 3.6 | +0.2 |
| 予想ロジック分析官 | 3.8 | 3.2 | +0.6 |
| 収益性 / 投資判断 | 3.2 | 2.6 | +0.6 |
| データパイプライン技術者 | 4.0 | 3.6 | +0.4 |
| コード品質 / 保守性 | 4.2 | 3.9 | +0.3 |
| 検証プロセス監査人 | 4.0 | 3.2 | +0.8 |
| **平均** | **3.83** | **3.39** | **+0.44** |

後退項目なし。全 7 名 GATE: PASS。

## 是正の実績 (バックログ 9 件)

1. ✅ weekly_monitor Task Scheduler 登録 (validation が schtasks で実在確認、次回 6/14 10:00)
2. ✅ calibrator 再 fit: p21 ルールの 2025 通年 records (n=48,058) で Isotonic 再 fit。RULES_VERSION ↔ expected_rules_version 照合機構。out-of-sample 2026 窓 paired 比較: buy_only 47.1%→50.6% (ノイズ域、本質は整合性回復)、all 88.3% 不変 (単調変換ゆえ想定どおり)。fit/eval 重複の自動ガード (calibration_in_sample) 実装・実動確認
3. ✅ dark --grade 上書き削除 (白文字 2.29:1→5.44:1、mobile が全ペア再計算で一致確認) + --accent-bg 分離 (6.29/6.80:1)
4. ✅ オッズ鮮度を filter.py に統合 (now 引数、backtest は skip)。鮮度のみで落ちた件数を HTML 表示 (「うち N 件は…」)。「0.0倍」根絶
5. ✅ tests 3 ファイル新設 (32 passed): is_buy_candidate 回帰 (S5-3/S7-α と同型を境界値固定) / Python↔JS 契約 (FM-1) / node --check の pytest 化
6. ✅ バックアップ runbook (OPERATION.md 6.5) / state.json アトミック書込み / ingest 順序 RACE→マスタ→0B* / busy_timeout / fetch→ingest の only_files 配線 (意味論も回復性重視に変更)
7. ✅ sprint_multiplier 削除 (ablation: 2025val 選定同値 / 2026 は ON を正当化する証拠なし) / 重み 0 シグナルの根拠文混入修正 / dead weights 2 key 削除
8. ✅ 予想生成の経過秒表示 / --text-mute AA (5.02:1+、gui-ux が再計算一致) / Python 側実行ミューテックス (BusyError) / aria-live
9. ✅ monitor baseline を同一経路で凍結 (brier 0.0597, n=3,450)。P23-2 の backtest JSON 案を「経路不一致」と自己検出して棄却 → monitor 自身の計測で凍結 (--freeze-baseline-days)。env_overrides 記録 / サイズ予算 warning

## レビューが新たに発見した欠陥 → P23-6 で即時是正

- **cancel() の TOCTOU → 回復不能ロックアップ経路** (gui-ux 反証): lock 外の running=True 書き戻しがワーカー完了と競合すると BusyError 永続。→ lock 内原子化 + 非実行時 event clear。スモーク確認
- **JS 構文テストの盲点** (code-quality 反証): エスケープ解釈前テキストの node --check は、過去 4 回再発した「\n 実改行展開」機構に盲目。→ ast.literal_eval で解釈後を検査
- test_template_render の dead 2 行 / monitor warning の旧フラグ名

## 採点の所見 (要点)

- **収益性 3.2**: 「P23 は『正しく計測できる状態』への前進であり『勝てる状態』への前進ではない」— 2026 窓 5 構成すべて buy_only 47-51% (all 88% 未満) で**フィルタが価値を破壊**、P05/P12 と同型の崩壊シグナル。**提案 1: filter_sweep --recent-3fold での戦略再選定を最優先**。実弾投入不可の判定継続
- **検証 4.0 (+0.8)**: 「宣言不執行なし。backtest JSON 案を自分で棄却して同一経路凍結に置換した P23-5 は検証プロセスとして正しい自己修正」。残: 監視の heartbeat (PC 未ログオン日曜の無音スキップ検知)
- **gui-ux の誤検出 1 件**: 「venv64 hint 未登録」は誤り — `_error_hint` の venv64 分岐は P22-2 で実装済みで、実テストで発火を確認 (`venv64 render failed` → hint 表示)。スコア影響は軽微として再採点は求めず記録のみ

## 横断的に見た優先課題 (次回)

1. **戦略再選定 (filter_sweep --recent-3fold)** — profitability 筆頭。現 min_kelly 0.05 構成は 2026 レジームで all より悪い。観察専用バナーの常設も
2. **監視 heartbeat** — weekly_monitor の最終実行時刻を記録し 8 日超で GUI 警告 (「動かない監視」の再発防止)。タスクを非対話実行 + StartWhenAvailable に
3. **calibrate→race 内正規化の相互作用検証** (prediction 繰越) + RULES_VERSION の CI tripwire (calibrator 整合の pytest assert 1 本)
4. pipeline: pending-ingest ジャーナル (fetch→ingest 窓の同名更新残穴) / fetch_realtime の filenames 化 (0B31 全量 force の削減) / day-nav 44pt + is-today
