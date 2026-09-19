# 採点 2026-07-26 17:20 (fresh_odds coverage 混入誤検知の是正)

**改修**: 朝アンカー (keiba-morning-odds 08:45) が発走直前バッチと同じ coverage JSONL に書くため、
healthcheck の時刻窓判定 (08:55-16:50) が 08:45 entry を混入誤検知し**開催日は毎回 FAIL** していた
(常に赤い監視=無視され本当の混入を見逃す害)。混入判定を time-window → **source 属性ベース**へ。
**branch `fix/coverage-source-attribution`**、commit `05c09ce` (実装) + `b2d52ee` (review 是正)。
ai-builder セッションの read-only 調査を受け keiba-yosou セッション (Claude) が実装。

## 診断の裏取り (鵜呑みにせず確認)
- 現行 main の `evaluate_coverage` を実 JSONL に適用 → `contamination_detected=True`、lineno 1659 =
  指示書の実例と一致。**main は実際に壊れていた**。`latest.json` の PASS は ai-builder 未コミット
  パッチ由来の stale と判明。

## expert-review: 該当3名 (他4名 N/A=GUI/HTML/rules/backtest 無変更)

| 専門家 | 判定 | スコア | 要点 |
|---|---|---:|---|
| data-pipeline-engineer | PASS | 4.0 | source 帰属で根因解消。反証A/B: 既知source時刻不問=検知軟化。WARN 化を提案 |
| validation-process-auditor | CONDITIONAL→解除 | 3.6→~4.2 | 「検知力維持」は over-claim (tagged 行が時刻不問)。3条件提示 |
| code-quality-reviewer | PASS | 4.0 | 二重定義は正当 (health は stdlib-only)。silent 経路 (--source morning assert 欠落) 指摘 |

## CONDITIONAL の解除 (validation 3条件、commit `b2d52ee` で充足・全て検証済)
1. **source↔時刻 mismatch を WARN 可視化** (source別窓の FAIL でなく、data-pipeline #2 の WARN 案採用=
   alert fatigue 再発防止)。fresh/morning が窓外なら `source_time_mismatch_examples` に記録、decision 不変。
   manual は時刻不問。現実の混入ベクタ (pytest が default fresh で深夜書込) が可視化される。
2. **後方互換テスト** 「無タグ 08:40-08:54 を混入としない」追加。
3. **commit message 事実誤認の訂正**: 「回帰テスト4件」→実3件、「検知力は維持」→「untagged/unknown は
   維持、tagged は当初 time-unrestricted だったのを WARN 化」。

## 収束是正 (3名の共通指摘)
- **producer 側テストで `payload["source"]` を断言** (3名言及の最大の穴=源泉から source が落ちる silent
  退行を固定)。`--source morning` variant も。
- **dry-run 行を判定除外** (私の検証 dry-run 由来 `morning@17:02` 汚染も自然解消)。
- **`--source morning` assert** を bat テストに (唯一の silent 失敗経路封鎖)。

## 検証
- 5パターン + 追加分すべて期待どおり。実 JSONL: contamination=False / mismatch=[] (dry_run除外) /
  by_source={untagged:50, fresh:1, morning:1} / ok=True。
- healthcheck ps1: **decision=PASS / exit=0**。**pytest 409 passed / 4 skipped** (回帰テスト計8件)。
- ASCII 維持 (当初日本語 REM を入れ ASCII テストで検出→英語修正、という検出機構の実効性も確認)。

## スコープ厳守
- `keiba-yosou-weekly-monitor` 0x4 (gap) は正しい検出 (07-19 pytest 中断 + `--last 7` で 08-02 自然解消)
  → 不触。窓を広げる安易策は不採用。live `fetch_fresh_odds.bat` は不触 (%* 欠落は別チケット)。

## 残課題 (next-cycle・非ブロッカー)
- contract テスト (argparse choices == KNOWN_COVERAGE_SOURCES の CI 照合、code-quality)。
- 窓4定数の module 定数化 + reason 文字列の動的生成 (code-quality)。
- untagged 互換分岐の日付ゲート (2026-08-01 以降 untagged=無条件混入、data-pipeline #3)。
- **weekly-monitor 0x4 の 08-02 自然解消を次セッションで確認** (放置=監視形骸化の同型事故、validation)。
- **merge するまで live healthcheck は main の旧コードで FAIL し続ける** (開催日)。

平均 (是正後) ~4.07。
