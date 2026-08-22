# GUI / UX 監査人 — 20260822_1210 fresh_odds_recovery

**判定**: HOLD → (是正後 follow-up 済み。次回再評価)
**総合**: 3.4 / 5 (前回 3.6、-0.2)

| 項目 | 今回 | 前回 |
|---|---|---|
| タスクフロー / 発見性 | 4 | 4 |
| エラーの人間化 / 回復支援 | 3 | 4 |
| システム状態の可視性 | 4 | 3 |
| 状態整合性 / 誤読防止 | 3 | 4 |
| レイアウト / 入力効率 / a11y | 3 | 3 |

**HOLD 事由**: 公開 HTML はサスペンドを開示するのに、GUI (`gui/app.py`) は 0 件理由を
「EV/信頼度条件を満たすレースは見送り」と虚偽表示し、フィルタパネル注記も稼働中に見える
(Nielsen 1 / 9 違反)。同一状態を web と GUI が別の理由で説明する分裂。検証モード警告
「オッズ鮮度を無視して買い目を表示」もサスペンド短絡で必ず 0 件になり自己矛盾。

**評価された良い点**: サスペンド判定は `config.buy_filter_suspended()` 単一出典で
filter/generator が共用、判定順序 0 の短絡で決定的。GUI から suspension を突破する経路は
無いことを実測 (`gui/app.py` の bet_filter は `dict(BUY_FILTER_DEFAULT)`、GUI 上書きは 4 キーのみ)。
watchdog + 日付別ログ + health の Discord 通知は過去 2 回の提案「異常の能動通知」への応答。

**改善提案** (3 件すべて本セッションで是正済み):
1. GUI の 0 件理由をサスペンド開示に切替 → `gui/app.py` の警告 + JS 空状態を config 分岐に
2. フィルタパネル注記に「⚠ サスペンド中 (常に 0 件)」を前置 → `_filter_base_note()` 是正
3. 検証モード警告の自己矛盾解消 → サスペンド時は別文言

**是正後の実測**: CONTROL_HTML の JS `node --check` PASS、`tests/test_gui_js_contract.py` に
GUI 開示の契約テストを追加 (4 経路が config を参照していることを固定)。
