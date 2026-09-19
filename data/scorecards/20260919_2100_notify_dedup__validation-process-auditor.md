# 検証プロセス監査人 採点 — b437db3 通知の同日重複抑止 (notify_dedup)

## 判定: HOLD

**理由**: 実装の機能面は自分の変異 10 種 (うち 8 種撃墜) と全 suite 645 passed で欠陥を見つけられなかった。しかし依頼者が「予測側に影響なし」の主柱に据えた HTML 3 連続生成は、**改修したファイルが generator の実行経路に乗っていない** (web/ predictor/ の diff 0、generator は auto_predict / notify_dedup を import しない) ため、B==A は構成上の必然で「コードの影響」を測っていない = 同語反復。加えて自己検出欠陥 3 件のうち **(2) テストの本番状態汚染は回帰テストで固定されていない**: conftest の autouse を外すと 0 件の失敗のまま `data/runtime/notification_state.json` に架空 `total: 2` が書かれる事故が**そのまま再現**した (実測)。`--force-notify` も argparse 定義と `_notify_once(force=True)` は固定済だが **main() の配線 `force=args.force_notify` は無テスト** (`force=False` に変えても 0 失敗)。停止条件抵触は無いので FAIL ではなく HOLD。
**改修タイプ**: type-B (運用通知層。予測・backtest・GUI 非接触)。P25 固有ゲート / 6 agent 統合は N/A。参考: 兄弟 6 名は HOLD 3 (code-quality 3.6 / data-pipeline 3.6 / gui-ux 3.3) + PASS 3 で、本判定と整合。
**採点対象**: HEAD `b437db3` のみ。採点中に作業ツリーへ未コミットの追補 (scripts/notify_dedup.py +72 / tests/test_auto_predict_artifacts.py +79 / tests/test_notify_dedup.py +167、main() 配線テストの追加) が現れたが、本採点には **含めていない**。次回 commit で再評価する。
**根拠ファイル**: `scripts/notify_dedup.py:150-208`、`scripts/auto_predict.py:116-154,235-318`、`tests/conftest.py:14-26`、`tests/test_notify_dedup.py:215-236,327-356,390-417`、`web/generator.py:66-81,300,311,394-419,469,668`、scratchpad `exp.py` / `mutate2.py` / `index.{ORIGINAL,BEFORE,AFTER,FINAL}.html`
**次アクション**: (a) 「本番状態を汚さない」の回帰テスト追加 — `auto_predict.main()` を通す既存テスト (`tests/test_auto_predict_artifacts.py:114`) の後で本番 path の mtime / 存在が不変であることを assert、または autouse fixture 内で `notify_dedup.state_path()` が `tmp_path` 配下に解決することを assert。(b) `main()` に `--force-notify` を渡し `_notify_once` が `force=True` で呼ばれることを固定するテスト。(c) 主張の書き換え: 「bit-identical」→「生成時刻行 1 行を除き一致」、「通知層を 1 つも import しない」→「auto_predict / notify_dedup を import しない (notify_discord は generator.py:69,79 が失敗経路で遅延 import)」。(d) 実験成果物 (4 HTML / exp.py / mutate2.py) を揮発 scratchpad から `data/backtest/` 相当の永続 path へ (feedback_tmp_volatile)。

## 総合: 3.0 / 5 (参考スコア)

## 項目別

- **検証設計の正しさ (主張 1 の A1→B→A2): 3/5** — 自分で 4 HTML を再 hash・diff。BEFORE(19:52:41) vs AFTER(19:54:06) の差は `<div class="updated">` の 2 行だけ、FINAL(20:08:07) は 1,092 行差 (依頼者の「432 ハンク」と整合)。対照 A1==A2 は「窓内ドリフト 0」を示す設計として正しく、時間順 (A, B, A) も B を挟む配置として妥当。**しかし比較の前提が崩れている**: `git diff --stat HEAD~1 HEAD -- web predictor config.py` は空、generator は `scripts.auto_predict` / `scripts.notify_dedup` を import しない。つまり「変更前コード」と「変更後コード」で generator プロセスが実行する命令列は同一であり、B==A は仮説検定ではなく恒等式。この実験が測ったのは **ドリフトのみ**。より強い設計: 本番経路 (`auto_predict.main()` → subprocess generator) を通し、DB を read-only コピーに固定 (`?mode=ro` / コピー) + 時刻を固定して B vs A を回す = ドリフトを「対照で確認」でなく「除去」する。あるいは正直に「経路外である事実 (import graph + diff stat) が証拠で、HTML 生成は smoke test」と書く。未報告の観察: ORIGINAL(18:59:58, HEAD 99eec68) vs AFTER は 4 行差 (時刻 + `git:` 行) で 55 分空いても内容一致、逆に 19:54→20:08 の 14 分で 1,092 行ずれた。20:00 に `keiba-trend-collect-raceday` が DB を更新するので、ずれの原因は「オッズが live で動く」でなく **20:00 バッチ**の公算が高い (推定、未検証)。
- **同語反復の検出 (主張 2・3・4): 3/5** — 主張 2: `prediction_log` 18,893 行 (自分で count 一致) は generator.py:394-419 が `--log-predictions` 下でのみ書くため、フラグ無し実行では **不変が自明 = 同語反復**。auto_predict は `--log-predictions` を付けて呼ぶ (auto_predict.py:265-267) ので、本番経路を通さなかった証明にもなっている。主張 3: SEALED 6 点は diff stat で predictor/ 非接触なので自明だが、安価な不変条件として残す価値はある。主張 4: OPERATION.md の表現 (auto_predict / notify_dedup を import しない) は正確、commit message の「通知層を 1 つも import しない」は **over-claim** (generator.py:69,79 は `scripts.notify_discord` を遅延 import)。「bit-identical」は 1 行除外した時点で使えない語。除外自体は generator.py:668 の生成時刻行に限定して宣言されており正当だが、generator.py:311 (`today`)・:469 (`filter_spec ... now=datetime.now()`) にも時刻依存があり、85 秒の窓で反転しなかっただけである点を明記すべき。
- **変異テストの設計 (主張 5): 3/5** — `mutate2.py` を読了: 16 種すべて **担当 guard テスト 1 本だけ**を実行して撃墜判定。「他のテストが落ちないこと」は kill の必要条件ではないので不要だが、**選び方に偏りあり**: M13 は `state_path()` の env 読取を潰す、M15 は `_notify_once` 内の `if force:` を潰す — いずれも単体の関数面で、テストが存在する場所を狙っている。自分の 10 変異 (独立設計): M1 record-before-send → 撃墜 (test_wiring_does_not_record_a_failed_send)、M2 record 側キー逆順 → 撃墜 (10 本)、M5 sort_keys=False → 撃墜、M6 fail-open 反転 → 撃墜 (2 本)、M7 prune 無効 → 撃墜、M8 ローカル時刻 → 撃墜、M9 抑止経路で送信 → 撃墜 (2 本)、M10 payload に時刻 → 撃墜。**生存 2 種**: M3 `conftest` autouse 解除 → 0 失敗 + 本番 state が実際に生成 (`coverage_abort:20260919 total:2` を確認後に削除)、M4 main の `force=args.force_notify`→`force=False` → 0 失敗。配線層の欠陥が 2/2 素通り。
- **自己検出欠陥 3 件の回帰固定: 3/5** — (1) 送信前記録: **固定済** (`test_wiring_does_not_record_a_failed_send` が実配線を見る、M1 で撃墜確認)。(3) キー 2 箇所: **固定済** (症状レベル; `_key()` 一本化 + M2 で 10 本撃墜)。(2) テストの本番汚染: **未固定**。`test_state_path_can_be_redirected` は自分で env を set するので autouse fixture が消えても通る。汚染経路は `tests/test_auto_predict_artifacts.py:114-139` (main() を通し notify_discord を True で mock → `record()` が本番 path に書く)。導入直後に実際に起きた事故と同じものが無音で再発する状態。
- **再現性 / 運用 / 統合: 3/5** — 全 suite を `.venv64` で独立再実行: **645 passed / 6 skipped (455s)** vs 主張 646 / 5。1 本が skipped に移った (候補: test_pit_parity の実レース依存 / test_gui_js_contract の node / test_exotic_odds_votes)。非阻害だが、次回は `-rs` 付きログを残すこと。実験成果物はすべて揮発 scratchpad にあり、`c0782ff493fc0eba` の正規化手順が未記載 (自分の正規化では `b17b40aa5a809e88`) → 第三者が再生成できない。本番 `notification_state.json` は**未存在** = 抑止は本番でまだ 1 度も発火しておらず、最初の live 証拠は 09/20 (08:00/09:00/11:00 の 3 起動、Task 実測) 以降。parent の E2 実験結果 (`e2_*.json`) を自分で読むと同時 4 書込みで **生存キー 1/4** = lost update。1 時間間隔の scheduler では実害なしだが OPERATION.md に既知制約として無記載。他の通知経路 (generator.py:71,81 / fresh_odds_coverage.py:55 / ps1 watchdog) は非抑止 — スコープ外で妥当だが文書化されていない。ルール 1-ter: generator 1 回 ≈ 85 秒、bg 30 分超の計算なし → **非該当の判断は妥当**。

## 停止条件チェック

- [x] git_sha: HTML に `git:` 行で刻印 (generator.py:668 付近)、commit `b437db3` 単一。backtest JSON / rule_version は N/A (type-B)
- [x] paired 比較 / market_snapshot / payout 欠損 — N/A (type-B)
- [x] 専門領域の停止条件 (比較設計の不成立・統計手法・再現性不足) — 抵触なし。実験は「不成立」ではなく「主張に対して証拠力がない」
- [x] 前回 (4B) の降格宣言 — 対象は Group A 着手 commit であり本改修は別トピック → 執行判定は次の Group A commit に持ち越し (免除ではない)

## 反証の試み

- 「HTML 3 本一致は改修の無影響を示す」→ 改修ファイルは generator 経路外 (diff stat 空 + import なし) → **同語反復、不成立** (ドリフト 0 の確認としては成立)
- 「prediction_log 不変」→ 書込フラグ無し → **同語反復、不成立**
- 「テストは同語反復でない (16/16)」→ 独立変異 10 種で 8 撃墜・**2 生存 (配線層)** → 部分的に成立
- 「3 欠陥は是正済」→ 是正は 3/3 事実、回帰固定は **2/3**
- 「送信失敗時は記録しない」→ notify_discord.py:36-39 は例外で False → 経路成立 (HTTP 4xx/5xx は urlopen が raise)。Webhook 未設定時の戻り値は未確認

## 主な改善提案

1. **本番汚染の回帰テスト** — `tests/conftest.py` の fixture 内で `from scripts import notify_dedup; assert str(notify_dedup.state_path()).startswith(str(tmp_path))` を yield 前に置く、かつ `tests/test_auto_predict_artifacts.py:114` のテスト末尾で `PROJECT_ROOT/data/runtime/notification_state.json` の (存在, mtime) が実行前後で不変であることを assert
2. **`--force-notify` 配線テスト** — `main()` を `["auto_predict", "--force-notify"]` で通し、`_notify_once` を mock して `force=True` を受けたことを assert (`tests/test_auto_predict_artifacts.py` の `_entry_db` fixture 流用で 15 行)
3. **主張の再表現 + 成果物の永続化** — docs/OPERATION.md:119-130 の「sha256 一致」を「生成時刻行を除き一致 / 改修ファイルは generator 経路外」に書き換え、hash の正規化手順を併記。4 HTML と exp.py / mutate2.py を `data/runtime/` か `docs/` 配下へ移す

## 前回からの差分

- 直近 (別トピック 4B, 2026-09-19 11:00): 3.4 / HOLD → 今回 3.0 / HOLD。同タイプ前例 (auto_predict watchdog type-C, 08-08): 4.0 / PASS。−1.0 の主因は「検証の主柱が同語反復」+「自己検出欠陥の回帰未固定 1 件」で、実装欠陥ではない
- 宣言: 次回この topic の commit で **提案 1 の回帰テストが無いまま (= autouse 解除で本番 state が書かれる状態が残っていたら) FAIL に降格**。提案 2 は HOLD 継続要因
