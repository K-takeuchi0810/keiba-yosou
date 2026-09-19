# GUI / UX 監査人 採点 — b437db3 予想生成通知の同日重複抑止 (notify_dedup)

## 判定: HOLD (前回維持 + 自己提案の消化を確認 — 本改修由来の GUI 減点なし / 降格 1 件を復元)

**理由**: type-B (通知層スクリプト + テスト + 運用ドキュメント)。`git show HEAD --stat` = 5 files、`gui/` `web/` に差分ゼロ (`git diff HEAD~1 HEAD --stat -- gui/ web/` 空)。GUI 経路への不到達を下記 6 経路で実測。前回 (0919_1100) で「3 回目の持ち越し」として降格した同日重複通知の件が本 commit で消化されたため、当該項目を復元。
**根拠ファイル**: `gui/app.py:54-57,69,109,1142,1218` / `scripts/auto_predict.py:116,315,319` / `scripts/notify_dedup.py:58-70,150-208` / `tests/conftest.py:14-26` / `scripts/auto_predict_daily.bat` (LOGFILE リダイレクト) / `docs/OPERATION.md` 「通知が来ないときの確認手順」
**次アクション**: `auto_predict.py:319` の無条件 `print("notified. push_ok=")` を `_notify_once` の結果 (sent / suppressed / failed) に応じた 1 行に変える (ログの 2 行が矛盾するのを解消)。

## 総合: 3.3 / 5 (前回 3.1、+0.2)

## 依頼: GUI 経路に到達しないことの実測 — 到達しない (6 経路)

1. **gui/ から通知層への参照ゼロ**: `grep -rn "auto_predict|notify_dedup|notify|discord|webhook" gui/` → 0 件
2. **GUI の予想生成は `web.generator` を直接 subprocess 起動**: `_run_render_in_venv64` (`gui/app.py:69-`) は `[.venv64 python, "-m", "web.generator", "--json"]` (`:109`) を kick する。`run_prediction` (`:1142`) / `publish` (`:1218`) とも `scripts.auto_predict` を経由しない。**GUI から予想生成しても以前から Discord 通知は一切出ない**ので、「抑止されて何も起きないように見える」経路は存在しない (通知は Task Scheduler 経路専用)
3. **gui.app import 後の `sys.modules` に `scripts.notify*` / `scripts.auto_predict` なし** (.venv32 実測 False)
4. **通知層の import 元は `scripts/auto_predict.py` と tests のみ** (`grep -rln` 実測、bat/ps1 は `scripts.auto_predict` をモジュール起動するだけ)
5. **conftest autouse fixture の副作用**: `NOTIFY_STATE_PATH` 環境変数を tmp_path に向けるだけ。GUI 側はこの変数を読まない (gui/ に参照 0)。`tests/test_gui_js_contract.py` + `tests/test_webapp.py` + 通知 3 テスト群を同一プロセスで実走 → **65 passed** (.venv64)。teardown の `os.environ.pop` は monkeypatch の復元と重複するが、pytest の undo は KeyError を握るので無害 (冗長なだけ)
6. **JS パース**: CONTROL_HTML 無変更のため必須ではないが回帰確認として実施 → 22,428 chars、`node --check` OK

**反証の試み**: 「GUI の publish が `web.generator` 経由で Pages push し、auto_predict の `push_ok` payload と食い違って翌朝『変更あり』が誤発火する」→ payload のキーは `(種類, 対象日)` で auto_predict 自身の直近記録とのみ比較する。GUI 側は state file を読みも書きもしない。棄却。
**本番状態ファイル**: `data/runtime/notification_state.json` は現時点で不在 (commit message にあるテスト汚染 `total: 2` は除去済)。`.gitignore:25` `data/runtime/*` で追跡外。

## 項目別

- タスクフロー / 発見性: 3/5 (変動なし — GUI 無変更)
- エラーの人間化 / 回復支援: 3/5 (変動なし。参考: OPERATION.md の「通知が来ないときの確認手順」4 ステップは Nielsen 9/10 に沿う良い追加だが、GUI 内の `_error_hint` は無変更)
- **システム状態の可視性: 2.5 → 3.5/5** (下記)
- 状態整合性 / 誤読防止: 3/5 (変動なし)
- レイアウト / 入力効率 / a11y: 4/5 (変動なし)

### システム状態の可視性 (+1.0 の内訳)

- **+0.5 復元**: 0913 → 0918 → 0919_1100 と 3 回持ち越した「同日 3 回起動で完了通知が重複」を本 commit が消化。前回宣言どおり降格分を戻す
- **+0.5 加点 (設計品質)**: Nielsen 1 (システム状態の可視性) に照らして、(a) 「中身が変わった」ときに **変更点を頭に付けて全文を送る** (差分だけ送って文脈を落とさない)、(b) 判定失敗は **送る側に倒す** (fail_open)、(c) **送信成功後にのみ記録** (POST 失敗 → 次の起動 09:00 / 11:00 で再送)。中止通知の消失 = 「その日の予想を失ったことに誰も気付けない」を最悪事故と定義して設計している点は、通知 UX として正しい優先順位。抑止時も stdout に `notify suppressed (...): duplicate` を出し、bat が `data/logs/auto_predict_daily_YYYYMMDD.log` に全リダイレクトするので **抑止の痕跡は必ずログに残る** (サイレント失敗ではない)
- **4 に届かない留保**: `auto_predict.py:319` の `print("notified. push_ok=", push_ok)` が `_notify_once` の戻り値を見ずに無条件で出るため、抑止時のログは「notify suppressed ... duplicate」の直後に「notified.」と続き **2 行が矛盾する**。送信失敗時も同じ (WARN の後に notified.)。OPERATION.md の手順 1 は「suppressed が出ていれば抑止」と正しく案内しているが、ログ本文が嘘をつく行を残すのは Nielsen 4 (一貫性) 違反。1 行の修正で消える

## 参考所見 (将来 GUI に露出する場合)

- GUI は現状 Discord 通知を出さない。将来 GUI から `auto_predict` 相当を起動するなら、`_notify_once` の `Decision.reason` (first_time / duplicate / changed / fail_open) を **そのまま GUI ステータス行に出す**こと。「送信済 (重複のため抑止)」と「送信失敗 (次回再送)」を同じ「完了」表示にすると、ユーザは Discord を見て「壊れた」と誤読する
- 「変更あり」本文の差分行は Python repr (`None -> 12`, `False -> True`) をそのまま出す。単独運用者向けなら可だが、GUI に載せる際は `push_ok: False -> True` を「Pages 公開: 失敗 → 成功」に翻訳する
- `--force-notify` は CLI のみ (bat / ps1 に配線なし)。GUI に載せるなら「必ず通知」トグルは低頻度・非破壊なので Fitts 原則上は遠くの詳細設定で良い

## 停止条件チェック

- [x] GUI / HTML 差分なし (`gui/` `web/` 0 file)
- [x] 6 経路で GUI 不到達 (実測)
- [x] JS `node --check` PASS / gui.app import OK (.venv32)
- [x] GUI テスト + 通知テスト同居実走 65 passed (.venv64)
- [x] 本番状態ファイルにテスト汚染なし (不在を確認)
- [x] 専門領域別 Hard Fail 不抵触 (P25 固有ゲートは type-B のため N/A)

## 過去提案の消化追跡

- **同日重複通知の差分化 (0913 起点、3 回持ち越し) → 本 commit で消化**。降格 2.5 → 3 を復元し、設計品質で +0.5
- 「`predictor/experiments/` 分離」: 未消化 (3 回目)。ただし本項目は他領域の参考所見でユーザ可視の UX 差が無いため、GUI 軸の降格には用いない (記録のみ)
- **新規提案**: `auto_predict.py:319` の "notified." 行を結果別 1 行に (次回未消化なら「システム状態の可視性」3.5 → 3.0 に戻す)

## 前回からの差分

- 総合 3.1 → 3.3 (+0.2)。変動は「システム状態の可視性」のみ (2.5 → 3.5)。GUI 回帰は 0 件
- 判定 HOLD 維持 (総合 4 未満。GUI 自体の課題 — 進捗 ETA / キャンセル全ステージ / 買い候補と観察候補の視覚分離 — は本改修の対象外で残存)
