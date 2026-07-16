# Codex 作業指示: カナリア仕上げ + 取消偽陽性是正 + data 属性化 (完走型・全 5 ステージ)

前提: 第 3 サイクル (PR #6) は main へマージ済み (main=`cef45c4`、353 tests green)。
本作業は正規 expert-review (`data/scorecards/20260716_2104_alerting_and_hardening.md`) の
横断課題 3 件 + **3 サイクル連続繰越の data-odds 属性化のクローズ** を 1 セッションで完走する
第 4 サイクル。**7/18 (土) の開催日前にマージしたい**ため、本日中の完走を想定。

起動前の推奨設定:

```
cd C:\Users\kizun\dev\keiba-yosou
codex            # 新規セッション
codex> /model    # reasoning effort = medium
# ステージ間で /compact を実行して履歴を圧縮すること
```

---

## ここから Codex へのプロンプト本文

競馬予想パイプラインの監視・答え合わせ基盤の仕上げをします。**途中で人間に確認を求めず、
ステージ 1→5 を順に完走**してください。各ステージ末尾の受入ゲートを満たせない場合は
自力で診断・修正して再試行 (最大 3 回)。それでも満たせない場合のみ、そのステージを
スキップ理由つきで最終報告に記載し、依存しない残ステージを続行すること。
説明文は最小限、差分ではなく実ファイルに書く。

### 全体ルール

- **最初に `git status --short` を確認**。tracked ファイルに未コミット変更があれば
  **作業を開始せず**内容を報告して終了 (別ストリーム保護。唯一の走り抜け例外)。
  untracked のみなら続行してよい
- **`git checkout -b codex/cycle4-polish main` で新ブランチを切る**。push はしない
- コミットは最終ステージのみ、`git add <個別パス>` で明示指定 (git add -A / -u 禁止)
- **触ってはいけない untracked**: `data/backtest/20260703_*.json`・`predictor/_v5_backup/`・
  `docs/handoff_20260716_sireline_session.md`
- **専門家レビュー / scorecard の作成禁止** (正規機構は Claude Code 側のみ)
- **Discord 実送信禁止** (`data/discord_webhook.txt` は本物の secret。テストは mock)
- `data/keiba.db` (19GB) 直 read 禁止 (sqlite3 CLI 可)。**DB の中身を変更しない**
- 既存の `data/results/2026-07-12|06-21/` の CSV・manifest は**再生成しない** (監査履歴)
- bat / ps1 は ASCII のみ。テストは `.venv64/Scripts/python.exe -m pytest`

### ステージ 1: カナリアの仕上げ (アラート→復旧ループの収束 + FN 補完)

対象: `db.py` / `scripts/cleanup_placeholder_horse_rows.py` / `scripts/monitor.py` / tests

1-1. **cleanup 走査述語の一元化**: `cleanup_placeholder_horse_rows.py` の
   `inspect_placeholders` (25-52 行付近) と件数表示の走査条件を、raw `horse_num='00'` から
   `db.sql_invalid_horse_num()` ベースへ拡張する。**DELETE 本体は '00' 限定を維持**
   (非 '00' の invalid 行は自動削除せず、inspect の報告で「手動判断が必要」と明示)。
   これで monitor が NULL/空文字 violation を警告した際に、案内先の cleanup --dry-run が
   「0 件 / クリーン」という誤った健全報告を返してアラートが永久収束しないループが消える。
1-2. **過去日 all-'00' の FN 補完 (第 2 述語)**: `db.count_horse_num_violations` に
   「race_date < 基準日の invalid 行は、正規行との共存がなくてもカウントする」条件を追加。
   根拠: 枠順確定前の正当な過渡 '00' は**未来日にしか存在し得ない**ため、過去日に残る
   invalid 行は取込欠落などの真の異常であり、FP ゼロのまま旧 raw-count 検査の検知力を回復
   できる。基準日は引数注入可能にし (`today: str | None = None` 等)、テストで固定日を渡す。
   monitor の警告文はどちらの述語で発火したか判別できる形に。
1-3. **`--dry-run` no-op 引数の誠実化**: cleanup の `--dry-run` は parse されるが未参照。
   参照して「dry-run mode (default)」を明示 print するか、既定動作の説明を実挙動と一致させる。
1-4. **monitor 残り 2 経路の read-only 化**: `monitor.py:91` (measure_recent_brier) と
   `:136` (measure_mining_coverage) の `open_db` を `open_db_readonly` へ。変更後に
   `python -m scripts.monitor --days 30` を実行して従来どおり動くこと (read-only で
   壊れる書込が紛れていないこと) を確認。
1-5. **テスト**: (a) NULL/空文字行が inspect の報告に現れる、(b) 過去日単独 '00' が
   violation として数えられる、(c) 未来日単独 '00' は数えられない (既存挙動の維持)、
   (d) DELETE が '00' 以外を消さないこと。

**受入ゲート 1**: 新旧テスト全 green + 実 DB (read-only) で `scripts.monitor --days 30` が
exit 0 (現 DB は未来日の過渡 72 行のみなので警告なしのはず)。

### ステージ 2: 品質ゲートの取消偽陽性是正 (7/18 前に必須)

対象: `scripts/build_daily_results.py` / tests

背景: 現行ゲートの人気上限 = `starter_count` (取消**後**の出走頭数)。朝オッズ取得後に
競走除外・発走除外が出ると「morning_popularity の最大値 > starter_count」となり、
**当日の台帳 CSV 全体が exit 1 で生成されない** (答え合わせの欠測日が生まれる)。
取消は正常イベントなので、これは偽陽性。

2-1. races の SELECT に `registered_count` (登録頭数) を追加し、人気上限を
   `max(starter_count, registered_count)` に変更 (どちらか欠損時は他方、両方欠損時は 18)。
   エラーメッセージにも採用した上限と根拠を明示。
2-2. テスト: 取消シナリオ (starter_count=13、morning_popularity 最大 14、
   registered_count=14) でゲートを**通過**すること + 真の異常 (popularity 20 等) は
   引き続き exit 1 で遮断されること。

**受入ゲート 2**: 新テスト 2 件 + 既存テスト全 green。

### ステージ 3: 通知・staging の堅牢化 (小粒 5 点)

対象: `scripts/notify_discord.py` / `scripts/auto_predict.py` / `web/generator.py` /
`weekly_monitor.bat` / `scripts/auto_predict_daily.bat` / tests

3-1. **notify の except 網完成**: `notify_discord.py:36` の捕捉を `except Exception` に拡大
   (`http.client.HTTPException` 系の漏れで、push 成功後の通知失敗が偽の「prediction
   failure」になる穴の封鎖)。best-effort 契約をコードで完成させる。
3-2. **staging の実測パス駆動**: `auto_predict.py` の `_stage_publish_artifacts` を、
   日付規約の glob 依存から「iCloud の `_sync_status.json` の `repository_archive` /
   実際に生成されたアーカイブパス」を読んで stage する方式へ (取得不能時は現行 glob に
   fallback)。generator と auto_predict の 2 ファイルに平行記述された日付規約が
   ずれた場合に「アーカイブ未 push の静かな失敗」となる経路を封鎖。
3-3. **archive 失敗の通知**: `web/generator.py` の archive except 節 (731-737 行付近) から
   `notify_discord` を best-effort 呼出し (import 失敗や webhook 不在でも publish を
   落とさない)。
3-4. **weekly Discord に bit 復号**: 通知文を
   `WARN: weekly monitor alert (monitor=%MONCODE% pytest=%TESTCODE% gap=%GAPCODE%; see <log>)`
   形式へ。あわせて ACTION 1-3 (Brier 復旧手順) の echo を MONCODE 非ゼロ時のみに限定。
3-5. **daily gap 通知に詳細埋め込み**: gap 警告行 (日付付き) をログから 1 行捕捉して
   Discord メッセージに含める (bat での実装が煩雑なら、`fresh_odds_coverage.py` に
   `--notify` フラグを追加して python 側で警告文つき通知を送る方式でもよい —
   簡潔な方を選ぶ)。
3-6. テスト: except 拡大 (HTTPException を投げる mock)、staging の実測パス駆動 +
   fallback、archive 失敗通知 (mock)。

**受入ゲート 3**: テスト全 green、bat の ASCII 維持、errorlevel 伝播の非破壊
(既存の exit bit テスト or 目視確認を報告に記載)。

### ステージ 4: テンプレート data 属性化 (3 サイクル繰越のクローズ)

対象: `web/templates/index.html.j2` / `scripts/build_daily_results.py` (IndexHtmlParser) / tests

背景: パーサはオッズ列を「class の無い td」として消去法で識別しており、テンプレートに
class 無し td を追加すると誤爆する契約が 3 サイクル前から繰り越されている。

4-1. テンプレートのオッズ td (724 行付近) を
   `<td class="col-odds" data-odds="{{ h.odds }}" data-popularity="{{ h.popularity }}">`
   に変更 (欠損時は属性自体を出さない: `{% if h.odds %}data-odds="{{ h.odds }}"{% endif %}` 等)。
4-2. パーサは **data 属性を優先読取**し、属性が無い場合のみ既存の span 分離方式へ fallback
   (過去にアーカイブ済みの旧形式 HTML — data/results/ 配下の答え合わせ入力 — を
   引き続きパースできることが必須)。
4-3. **contract test**: 実テンプレートを render した HTML 断片を IndexHtmlParser に食わせ、
   odds/popularity が一致することを検証するテスト (テンプレートとパーサの契約を固定)。
   旧形式 HTML (data 属性なし) の fallback テストも 1 件。
4-4. **実 HTML での回帰確認**: `data/results/2026-07-12/predictions_source_20260712_git2642e8c.html`
   (旧形式) に対しパーサを実行し、従来と同じ 470 頭 / 非空人気 169 件 / 値域 1-17 を維持
   していることを確認して報告に記載。
4-5. `web/dist/index.html` を再生成し、サイズ増 (data 属性分) が +50KB 以内であることと、
   `>00<` 混入 0 件を確認。

**受入ゲート 4**: contract test + fallback test + 実 HTML 回帰の 3 点 green。

### ステージ 5: 最終検証 + コミット

5-1. `pytest tests/ -q` 全 green (353 passed / 4 skipped + 新規分)。
5-2. 実データ確認: (a) `scripts.monitor --days 30` exit 0、(b) 07-12 実 HTML のパース回帰
   (4-4)、(c) bat/ps1/テンプレートの ASCII・エンコーディング確認。
5-3. **コミット (1 回)**: 変更ファイル + `docs/codex_fix_20260716_cycle4_polish.md` を
   明示 add。メッセージは英語 1 行 + 本文数行。
5-4. `git status --porcelain --untracked-files=no` が空、指定外 untracked 3 件不変、
   push なし、DB 不変 (violation 0 / 未来日 '00' 72 行のまま) を確認。

**受入ゲート 5**: 1 コミット、全テスト green、DB 不変。

### 最終報告 (15 行以内)

1. ステージごとの完了/スキップ
2. カナリア第 2 述語のテスト結果 (過去日単独 '00' 検知 / 未来日は非検知)
3. 取消シナリオのゲート通過確認
4. 実 HTML 回帰 (470 頭 / 169 件 / 1-17) と dist サイズ増
5. monitor 実行結果 (exit code)
6. コミット sha / push なし / untracked 不変

---

## (Claude Code 側メモ — Codex には渡さない)

- Codex 完了後、**正規 expert-review (D1) を実行** — 重点: ①第 2 述語 (過去日) の
  基準日境界 (当日開催中のレースを「過去」と誤判定しないか — race_date < today は
  当日を含まないので安全なはず)、②data 属性化で mobile-html-reviewer の全ゲート適用
  (dist 再生成 + サイズ実測)、③staging の実測パス駆動が GUI 手動 publish 経路でも
  整合するか
- **PASS 後は 7/18 より前にマージしたい** (取消偽陽性の是正が週末の台帳を守る)
- 週末検収 4 項目 (gap 誤警報 0 / schema:2 / アーカイブ自動 commit / Discord 実着弾) は
  本サイクルとは独立に実施
- 残課題: 累計 P/L 台帳 (F3 設計相談が先、ユーザと要相談) / dist 1.58MB (type-D) /
  古い worktree 3 件の掃除 (ユーザ判断)
