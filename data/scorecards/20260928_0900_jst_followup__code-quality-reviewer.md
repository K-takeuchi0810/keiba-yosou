# code-quality-reviewer — JST 最終ゲート follow-up (テスト衛生 + 時計台帳)

- 対象: worktree `C:\Users\kizun\dev\keiba-yosou\.claude\worktrees\jst-followup`, branch `jst-followup-20260928`, HEAD `0291dc6` (main `6e101c7` の上に 1 commit)
- 評価方式: **subagent CWD 限定運用での評価** (すべて `git -C <worktree>` / 絶対パス)。開始・終了とも HEAD `0291dc6`、porcelain 空を確認
- 改修タイプ: **type-C (テスト / 文書 / pytest 設定のみ)**。P25 固有項目 (meta.env_overrides / market_snapshot / PRED_DISABLE_BLEND 等) は **N/A (対象外)**。汎用ゲートで採点
- 本番 DB は `mode=ro` でのみ参照。変異は scratchpad 配下の `git archive` コピーで `scripts.mutation_sandbox` 経由のみ

## 判定: PASS

## 総合: 4.3 / 5

| 軸 | 点 | 要点 |
|---|---|---|
| DRY / 単一出典 | 4.5 | テスト側の `date.today()` 9 か所を `jst` ヘルパへ寄せ、本体と同じ時計に。`_freeze` は `test_generator_today.py` と同形 (共通 fixture 化は次回でよい) |
| dead code / 未実装前提 | 4.5 | 追記した台帳 A9 / B5-B7 / C5-C7 の行番号 9 か所を全件目視照合、**すべて一致**。分類 (A: 鮮度判定 / B: 対象日 / C: 刻印) も妥当。V3 の変異は spec で実在確認 |
| マジックナンバー / 設定外出し | 4.0 | `live_db` marker を pyproject に登録 (説明付き)。凍結日付 `2026-01-15` は「現実と離れた日付」と根拠明記 |
| テスト容易性 / 変更失敗モード | 4.5 | 下記「検証した事実」参照。同義反復ではない (前日ずらし・ローカル時計の 2 種を区別する DB 種付け) |
| 例外処理 / 観測可能性 | 4.0 | live DB カナリア失敗時に DB パスと内訳を出す / metrics.json 欠如は理由付き skip (存在して再現できなければ従来どおり失敗) |

## 検証した事実 (自分で実行)

1. `git diff 6e101c7 0291dc6`: 8 ファイル +220/−22、本体 (`db.py` / `predictor/` / `scripts/*.py` / `gui/app.py`) に変更なし。**スコープ逸脱なし**
2. 変更 6 ファイルを直接実行: 123 passed / 2 skipped。`tests/test_clock_behaviour.py` を **`TZ=UTC0` と `TZ=EST5EDT` でも 16/16 pass** (UTC0 でローカル now が 23:25 = JST 前日を指すことを確認済 → ホスト TZ 非依存)
3. 全体: `1003 passed / 11 skipped / 1 deselected (live_db)`、rc=0、2:43。著者の 1004/11 は worktree に dry-run DB があった時点の数と整合
4. 変異の再現: scratchpad の `git archive 0291dc6` コピーで `followup_spec.py` (M2/M3/M3b/M4/M4b/M8/V3) → **7/7 KILLED, rc=0** (著者の `followup_mut_result.txt` と一致)
5. 本番 DB `mode=ro` で `horse_num_violation_counts(conn, today=JST)` と既定 (`date.today()`) を両方実行 → いずれも total 0。今日は JST = ローカルなので差は出ない
6. `gui.app` の import 副作用: module top-level は `sys.path.insert` と **`config.ensure_dirs()`** (mkdir のみ) の 2 つ。import 後の worktree に追跡/無視ファイルの新規生成なし

## 所見

- **変更失敗モード (良い方向)**: 従来の AST ガード (`test_today_single_source.py`) は「独自の時計を作ったか」を綴りで見るため、`current_jst_daystamp()` の結果を 1 日ずらす変異は静かに通っていた。新テストは前日 / 当日 / 未来にレースを置いた DB で `_date_range` を呼ぶので、前日ずらしは `20260114`、ローカル時計は最新日 `20260120` に落ちて **どちらも即座に落ちる**。`JST_EARLY` (JST 00:30 = UTC 前日) の系列は UTC ホストでの回帰も拾う
- **webview スタブ**: `monkeypatch.setitem(sys.modules, "webview", ...)` はテスト終了時に元へ戻るが、`gui.app` 自体は sys.modules に残り、その中の `webview` 参照はスタブのまま。現状 `gui.app` を import する他テストは無い (test_gui_js_contract / test_sealed_holdout は意図的に AST で読む) ので漏れの実害なし。ただし **`gui.app` の import は `config.ensure_dirs()` を走らせ `~/iCloudDrive/競馬予想` を含む 3 dir を mkdir する** (既存なら no-op、ファイルは書かない)。fixture の docstring「代えても挙動は変わらない」はこの副作用に触れていないので 1 行追記が望ましい
- **live_db の意味変化**: テストは JST の今日を明示、`scripts/monitor.py:211` のカナリアは依然ローカル時計 (台帳 B5)。JST ホストでは同値だが、**テストが監視の呼び出し経路そのものを再現しなくなった**点は意識しておく。B5 を直せば解消する設計上の一時的な乖離で、台帳に理由が残っているので許容
- **flakiness**: 時計は全て固定、`sent_at` の照合は固定時刻の分単位、`test_an_unknown_value_is_rejected_at_configure_time` は子プロセス pytest (120s timeout) で環境変数を明示注入。不安定要素は見当たらない。skip 理由の日本語が cp932 コンソールで化けるのは既存テストと同じで対象外
- **軽微**: `test_clock_behaviour.py` が `JST = timezone(timedelta(hours=9))` を自前定義している (単一出典 `jst.JST` がある)。テストの独立性のためと読めるが、`jst.JST` を使う方が台帳 C3 の趣旨と揃う

## 次アクション

1. (任意・小) `gui_app` fixture の docstring に「import は `config.ensure_dirs()` で 3 dir を mkdir する (ファイルは書かない)」を追記
2. (任意・小) `test_clock_behaviour.py` の `JST` を `from jst import JST` へ
3. 本体側 (台帳 B5: `db.py:239` の既定 + `monitor.py:211`) の JST 化は本ブランチのスコープ外。着手時は本テストの `today=` 明示を戻して呼び出し経路そのものを検証する形へ
