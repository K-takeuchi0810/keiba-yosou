# 採点 2026-07-19 10:31 (正規版・出力欠陥是正)

**改修内容**: 公開予想 HTML の 3 欠陥是正 (①観察専用開示の常時表示 ②印↔勝率 P の表示整合 ③スケジュール逆転+完全性ゲート) + レビュー是正 4 件。**表示層のみ、rules.py/BUY_FILTER/weights/calibrator 無変更**
**対象 commit**: `171685d` (Codex 実装、指示書 `docs/codex_fix_20260719_output_defects.md`) + `f45a13a` (レビュー是正、Claude)、branch `codex/output-defects`
**経緯**: 2026-07-19 に公開中 HTML (`552e949`) を 4 専門家が精査し全員 HOLD (`project_output_audit_2026_07_19` メモリ) → Codex 是正 → 正規 expert-review 7 名 → mobile FAIL の鮮度可視化 + hazard を Claude 是正 → mobile 再検証 publish

## 総合スコア推移

| 専門家 | 是正前 (公開版 552e949) | 是正後 (f45a13a) | 判定 |
|---|---:|---:|---|
| 収益性ジャッジ | 2.0 (FAIL/hold) | 4.0 (PASS/**publish**) | PASS |
| 予想ロジック分析官 | 2.8 (HOLD) | 3.9 (PASS/**publish**) | PASS |
| モバイル HTML | 2.8 (FAIL/hold) | 4.0 (PASS/**publish**、再検証で転換) | PASS |
| データ基盤エンジニア | 2.8 (HOLD) | 3.5 (HOLD、**運用適用待ち**) | HOLD(運用) |
| コード品質 | — | 3.6 (HOLD、指摘 2 件は f45a13a で是正) | HOLD(保守性) |
| 検証プロセス監査人 | — | 4.1 (PASS/**publish** 条件付き) | PASS |
| GUI / UX 監査人 | — | 4.0 (PASS、HTML 参考採点) | PASS |
| **平均 (是正後)** | | **3.87** | |

## 3 欠陥の是正確認 (全て実 dist 実測)

1. **① 観察専用開示 (安全・最重要)** — 「⚠ 本ページは観察専用です。OOS 検証で利益エッジは確認されていません
   (回収率 CI 上限 <100%)。表示中の EV・印は購入推奨ではなく、実際の馬券購入には使用できません。」を
   `ignore_odds_freshness` 非依存で **body に常時レンダリング**。`<body>` は素タグ、verification-banner
   マーカー不在で publish 拒否も起きない。見送りバナーの論理反転も是正。**7 名全員が解消を追認**
   (収益性: 2.0→4.0、資金喪失経路の遮断を確認)。
2. **② 印↔P 整合 (信頼)** — argmax(P) が ◎ と異なるレースに「最高勝率」バッジ (7/19 dist で 15-16 件、
   42% と整合) + 凡例明記。バッジの argmax は表示 P と同一フィールド (`win_probability`)、15/15 で
   badge-P ≥ ◎-P を prediction-logic が機械検証。**rules.py 無変更** (戦略保護)、印の P 順一本化は
   type-A 戦略変更として次サイクル送り (backtest/封印ホールドアウト規律のため正しい降格)。
3. **③ スケジュール+完全性** — ps1 に 11:30 第 2 トリガー (日曜出馬表の土曜 11:00 着に対応、ASCII)、
   完全性ゲート (本日/翌日の空率>20% で警告+`_sync_status.json`記録+Discord通知)、メタ行を
   「予想N/未確定N/買い候補N」に分解。7/19 dist は空率 0%。

## レビュー是正 4 件 (f45a13a、指摘者再検証済み)

1. **オッズ鮮度の可視化** (mobile FAIL 解消) — 取得時刻が title 属性のみ (iOS で不可視) だったのを、
   race-head に可視テキスト「オッズ HH:MM 時点」で出力 (6 件)。コントラスト 5.74:1/6.1:1 AA 合格。
   mobile 再検証で **FAIL→publish/4.0**。
2. **no-buy 文言の config 単一出典化** (収益性+コード品質+GUI+検証の 4 名一致) — テンプレート直書きを
   `_build_buy_condition_text()` (config.BUY_FILTER_DEFAULT 由来) に。フィルタ変更時の嘘表示を構造防止。
3. **auto_predict の push branch guard** (データ基盤ハザード) — `HEAD != main` なら push 中止。
   共有 checkout が feature ブランチのままスケジュール実行→未レビュー commit が main へ流入する
   ハザードを封鎖 (11:30 トリガー追加で露出が 2 倍になる問題への対処)。
4. **完全性 meta の roundtrip 統合テスト** (コード品質+検証の 2 名一致) — 実テンプレ→実 reader
   (`_read_completeness_meta`) を通し、gate の fail-open ドリフトを検知。

テスト 378 passed / 4 skipped。

## 公開可否の統合判定: **publish 可 (観察専用ページとして)** — ただし運用 3 前提

出力成果物そのものの publish ブロッカー (mobile FAIL) は解消、収益性・予想ロジック・モバイル・検証の
4 名が publish。データ基盤/コード品質の HOLD は**成果物の欠陥ではなく運用適用・保守性**:

1. **main マージ + Pages 再 publish** — 現公開版 `552e949` には欠陥①② が残存。マージ+再 publish
   するまで是正は利用者に届かない (検証プロセス監査人)。
2. **`register_auto_predict_task.ps1` の手動再実行** — ps1 のコミットだけでは稼働中タスクは
   09:30 単発のまま。再登録して 11:30 トリガーを実機反映する必要がある (データ基盤が実機実測)。
3. **branch guard は本 commit で封鎖済み** だが、main へマージして初めて全経路で有効。

## 残課題 (次サイクル)

- **印を investment_probability 順に一本化** (根本策、type-A 戦略変更 → backtest + 封印ホールドアウト
  規律に沿って要ユーザ相談。表示整合は済)
- `.race-time` nowrap で 375px の head-pick 幅圧縮 (odds-time を block 化)、sticky ヘッダ肥大の緩和、
  top-p バッジ 0.72rem 化 (mobile)
- 凡例文言「オッズ確定前の P はモデル単独値」→基準割引 0.92 適用の明記、LGBM fallback 時の凡例動的化
  (prediction-logic)
- `_read_completeness_meta` の欠落時 None 化 + 警告、閾値 20% の重複解消、`_odds_fetched_time` の日跨ぎ
  日付併記 (code-quality/data-pipeline)
