# コード品質 / 保守性レビュアー 採点 — b437db3 通知の重複抑止 (notify_dedup)

**改修タイプ宣言**: 運用/通知層 (type-B 相当、予測を変えない)。P25 固有ゲート (env_overrides / market_snapshot / weights) は **N/A (対象外)**。汎用ゲートで採点。
**採点対象**: `scripts/notify_dedup.py` `scripts/auto_predict.py` `tests/test_notify_dedup.py` `tests/conftest.py`。生成側 (web.generator) の不変性は commit 記載の sha256 証跡を再実行しておらず、本採点のスコープ外。

## 判定: HOLD

**理由**: `decide` の契約テストは同語反復ではない (対照変異 4/4 検出)。しかし **自分で植えた 13 変異が全て素通り** し、うち 4 件は commit 本文が「直した」と書いている欠陥クラスそのもの (配線側で `_notify(msg)` に戻す / 4 call site の 1 つで `force=` を落とす) が **再発しても捕まらない**。加えて `record()` の `except Exception: pass` は状態を書けない環境で **元の 3 通バグへ無音で退行** する経路 (実測: WARN 0 行)。停止条件抵触は無し。
**根拠ファイル**: `scripts/notify_dedup.py:107-116,135-142,196-208` / `scripts/auto_predict.py:116-143,238-241,269-271` / `tests/test_auto_predict_artifacts.py:131-139` / `tests/conftest.py:23-26`
**次アクション**: 下記改善提案 1-2 (配線テスト + record の WARN + 値レベル自己修復) を入れて再採点。1 時間規模。

## 総合: 3.6 / 5 (参考スコア)

## 項目別

- **DRY / 単一出典: 4/5** — `_key()` 一本化は実装済 (CTRL1 で検出確認)。`_notify` は `notify_discord` の薄い wrapper で正当 (テストの差替え点)。留保: (a) `Decision.reason` が文字列プロトコルで、`auto_predict.py:133` が `startswith("fail_open")` で分岐 = モジュール境界をまたぐ文字列契約 (`fail_open` の綴りを片方で変えると WARN だけ黙って消える)。bool フィールド (`degraded: bool`) にすべき。(b) `_completion_payload` / `_completion_message` は同じ 3 引数を別々に受ける。分離自体は妥当 (payload から時刻/URL を排除する構造的保証) だが「1 キー追加」は payload / message / `test_completion_payload_has_no_time_or_url` / call site の **4 箇所** で、payload だけ忘れると新項目の変化が **無音で抑止される**。(c) 参考所見 (既存): `scripts/check_fresh_odds_health.ps1:134-188` に `fresh_odds_alert_state.json` + `last_notified_at` の **別実装の通知抑止** が PowerShell 側に存在。言語境界またぎの平行記述で、今回の導入で 2 系統になった。
- **dead code / 未使用シンボル: 4/5** — `--force-notify` の幻引数は実装され 4 call site に配線済 (`auto_predict.py:241,259,271,318`)。留保: `_notify_once` の戻り値は 4 呼び出しとも捨てられており、かつ抑止時に `True` を返す (「送った」ではなく「処理した」の意味) — 変異 MI (抑止時 False) が素通りするので契約として存在していない。`Decision.changes` は本番で参照なし (テスト専用)。`tests/test_notify_dedup.py:348` の `__import__("sys")` は `monkeypatch.setattr(sys, "argv", ...)` で足りる。
- **マジックナンバー / 設定外出し: 4/5** — `RETENTION_DAYS` は根拠コメント付き、`JST` は定数、状態パスは `NOTIFY_STATE_PATH` で差替え可。`.gitignore:24-26` で `data/runtime/*` 除外を確認。留保: `RETENTION_DAYS` を 0 にしても全テスト通過 (MN) = 保持期間はテストで固定されていない。
- **テスト容易性 / 変更失敗モード: 3/5** — 変異結果は下表。契約層 (decide/record) は堅い。**配線層が穴**: `test_main_aborts_without_publishing_when_entries_missing` は `notify_discord` を差し替えて 1 通の本文だけ見るので、coverage_abort を `_notify(msg)` に戻しても (MC)、`force=` を落としても (MB) 通る。commit が「16/16 検出」と書く検証は、この 2 経路を含んでいない。差替え点も 2 系統 (`wired` は `_notify`、artifacts テストは `notify_discord`) で統一されていない。
- **エラー処理 / 観測可能性: 3/5** — 良: fail-open の非対称性、原子的置換、stdout は `data/logs/auto_predict_daily_<date>.log` に落ちる (`auto_predict_daily.bat:6-7`)、OPERATION.md に確認手順。悪: (a) `record()` は失敗を **一切出力しない**。状態ディレクトリが書けない実測 (`path.parent` がファイル): 例外なし・状態なし・次回 `first_time` = **元の 3 通バグに無音退行**、ログには何も残らない。(b) `_load` は top-level dict しか検証しない。値が dict でない (`{"k": "garbage"}`) と `_prune` の `.get` が AttributeError → decide は毎回 `fail_open` で送る (可)、**record も毎回失敗して自己修復しない** (実測)。`test_8` の「壊れたファイルは書き直され、次回から判定が効く」は構文破損にしか成立しない。(c) `_notify_once` の WARN 文言は日本語 + 絵文字混在で、過去 2 回指摘した cp932 クラッシュ経路と同型 (`print` が `notify` の前)。今回は `PYTHONIOENCODING`/bat のリダイレクト経由で再現せず未実測、留保のみ。

### 自分で植えた変異 (`tests/test_notify_dedup.py` + `test_auto_predict_artifacts.py`, 32 件)

| # | 壊し方 | 結果 | 実害 |
|---|---|---|---|
| CTRL1-4 | `_key` が type を落とす / sort_keys 無し / 送信前に record / `force` 無視 | **検出** | (runner 妥当性の対照) |
| MC | `main()` の coverage_abort を `_notify(msg)` に戻す | 素通り | 中止通知が再び 3 通 |
| MB | coverage_abort の call site だけ `force=` を落とす | 素通り | `--force-notify` が中止経路で幻に戻る |
| MA | `record` が `date_jst` を書かない | 素通り | 永久に prune されない (無音で育つ) |
| MD | `_diff` が削除キーを報告しない | 素通り | 「変更あり」見出しだけで変更点が空 |
| MG | generation_failed の payload を `{}` に | 素通り | 無し (本文が rc を含まないため実質同じ) |
| MK | `_save` を非原子的に | 素通り | commit の「原子的」主張がテスト未固定 |
| MF / MN / MJ | prune 境界 `>` / RETENTION 0 / 基準日を subject に | 素通り | 境界未固定 |
| MH / MI / ML | fail_open 時に record しない / 抑止時 False / drift 未 sort | 素通り | 契約として存在しない (実害小) |

## 変更失敗モード分析

1. **5 つ目の通知を足すとき**: `_notify_once("new_type", day, payload, msg, force=args.force_notify)` を書く人が `force=` を忘れる → 例外なし、`--force-notify` がその経路だけ効かない、テストは全部通る (MB 実証)。防ぐには `force` を引数ではなく `_notify_once` が `args`/モジュール状態から読むか、`main()` を通す配線テストで `--force-notify` を 2 回起動して 2 通を要求する。
2. **状態ディレクトリの権限/ロック事故**: `record` が無音で失敗 → 3 通に退行 → 「重複が戻った」と気付くのはユーザの Discord だけ。ログに WARN が 1 行あれば `grep WARN data/logs/*.log` で 1 手。今は絶対に出ないので、原因特定は「ログに suppressed が無い」という **不在からの推論** になる。
3. **A→B→A**: 実測 `generation_failed(rc=1)` → `generation_complete` → `generation_failed(rc=1)` の 3 回目が **duplicate で抑止**。種類ごとに独立キーを持つため、成功を挟んだ再失敗が同日中は届かない。キーを `day` だけにして `payload` に `type` を入れれば状態遷移が全て通知される (「中止→完了」も diff として出る)。

## 依頼への回答

- **decide / record 2 段**: 正しい。`record` は `ok` のときだけ (CTRL3 検出)。`except Exception: pass` は範囲より **出力ゼロ** が問題 (上記 (a))。
- **4 call site の payload**: coverage_abort に `min_coverage` を含めるのは妥当 (閾値変更で再通知)。`generation_failed` が rc だけなのは本文が rc 以上の情報を持たないので妥当。ただし A→B→A の穴は payload ではなくキー設計の問題。
- **conftest**: `os.environ.pop` は冗長 (pytest `monkeypatch.py:419-424` が未設定→設定の undo で `del` + `KeyError` 吸収)。無害だが「二重に消す」意図が読めないので削除。autouse の副作用は 651 テストで `tmp_path` を毎回作る程度。実害より、`wired` fixture が env ではなく `state_path` を直接差し替えており **隔離手段が 2 系統** になっていることの方が保守上の問題。
- **通知が来ないと言われた時**: 設計どおりの抑止なら 2 手 (ログの `suppressed` 行 → state の `sent_at`/`payload`)。record 失敗ループなら不在推論、値破損なら毎回 WARN が出るが `--force-notify` か手動削除しか出口が無い。

## 停止条件チェック

- [ ] git_sha / env_overrides / market_snapshot / payout — **N/A** (予測・backtest に無関係)
- [x] 汎用: 新規経路に回帰テストあり (契約層)。配線層は上記の通り不足だが停止条件ではない
- [x] 汎用: 例外の握り潰しで **観測不能な失敗** が 1 経路 (`record`) — 「中止通知の消失」ではなく「重複への退行」なので停止条件 (実害) には至らないと判断

## 反証の試み

- 「16 変異 / 16 検出」→ 別の 13 変異で 0 検出。対照 4 件は検出されたので runner は妥当。主張は真だが **検出力は契約層に偏っている** → 部分成立
- 「壊れたファイルは書き直され次回から効く」→ 構文破損は成立、値破損は不成立 (実測: 2 回連続 `fail_open:AttributeError`)
- 「送信失敗は記録せず再送」→ 成立 (`test_wiring_does_not_record_a_failed_send`、CTRL3)

## 主な改善提案

1. **配線テストを `main()` 経由で 2 本追加** — `test_auto_predict_artifacts.py` に (a) coverage_abort を同条件で 2 回 `main()` して `notify_discord` 呼出が 1 回、(b) `--force-notify` 付きで 2 回して 2 回、を要求。MB/MC が落ちる。差替え点は `_notify` に統一。
2. **`record` の失敗を 1 行出す + 値レベルの自己修復** — `notify_dedup.py:207-208` を `print(f"WARN: notification state not saved: {exc}")` に。`_load` で `{k: v for k, v in data.items() if isinstance(v, dict)}` に絞る (`notify_dedup.py:111`)。`test_8` に値破損版を足す。
3. **キーを対象日単位にし type を payload に** — `_key(subject)`、payload に `"type"` を入れる。A→B→A が届き、「中止→完了」の遷移も diff で見える。`Decision.reason` の文字列分岐は `degraded: bool` に置換。

## 前回からの差分 (直近 code-quality: 20260919_1100 phase05_4b = 3.0 / HOLD、同系 auto_predict: 20260808 = 4.2 / PASS)

- DRY 3→4 (+1、`_key` 一本化・言語境界の新規平行記述なし) / dead code 3→4 (+1、幻引数の解消) / マジックナンバー 4→4 / テスト容易性 3→3 (契約層は前回より強いが配線層で同型の素通り) / 観測可能性 2→3 (+1、cp932 の実クラッシュは無し。ただし無音 record が新規)
- 判定 HOLD→HOLD。理由変更: 前回は「同型欠陥の再発」、今回は「commit が直したと宣言した欠陥クラスが再発しても検出されない + 無音退行経路」。
