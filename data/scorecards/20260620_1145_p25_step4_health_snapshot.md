# Plan Step 4 健全性スナップショット (2026-06-20 11:45)

**改修内容**: P25 Plan Step 4 (fresh odds 取得運用化) の初日稼働。Task Scheduler に `keiba-fresh-odds` (10 分おき) + `keiba-fresh-odds-healthcheck` (15 分おき) を登録し、09:00 以降の自動稼働を観測。

**対象ファイル**: なし (運用観測のみ、コード変更無し)

## 判定: PASS (Plan Step 4 初日達成)

**理由**: scheduler / coverage / DB の 3 セクションすべて ok=True、汚染検出なし、Plan 期待値 (468 fresh 馬/日) を 11:45 時点で既に超過 (505 行)

**根拠ファイル**: `data/runtime/fresh_odds_health_latest.json`、`data/logs/fresh_odds_coverage.jsonl`、`data/logs/fresh_odds_health_20260620.log`

**次アクション**: 16:40 まで継続稼働を観測。明日 (2026-06-21 日曜) も同様に稼働すれば Plan Step 4 完了条件 (1-2 開催日で安定) を満たすため、ユーザ判断で OOS auto を enable して Plan Step 5 へ進める

## 各セクションの実測値 (rubric v3 形式)

### scheduler

| 項目 | 値 |
|---|---|
| Task name | `keiba-fresh-odds` |
| State | Ready |
| LastRunTime | 2026-06-20 11:40:01 |
| LastTaskResult | **0** (正常終了) |
| NextRunTime | 2026-06-20 11:50:00 |
| 09:00 以降の発火回数 | 17 (10 分おき) |
| Missed runs | 0 |
| ok | **True** |

### coverage JSONL

| 項目 | 値 |
|---|---|
| ファイル | `data/logs/fresh_odds_coverage.jsonl` |
| 当日エントリ数 (runs_today) | 17 |
| eligible_races (累計) | 26 |
| fetched_races (累計) | 26 |
| ok_races (累計) | **26** (= 100%) |
| error_races (累計) | **0** |
| no_data_races / timeout_races / empty_races | 0 / 0 / 0 |
| lock_skipped | 0 |
| failed_reason 分類 | 空 |
| contamination_detected | **False** (テスト混入なし) |
| 時間別 ok_races | 09 時=7, 10 時=12, 11 時=7 (途中) |
| ok | **True** |

### DB (horse_races.odds_fetched_at)

| 項目 | 値 |
|---|---|
| パス | `data/keiba.db` |
| reachable | True |
| `odds_fetched_at >= 2026-06-20T09:00:00` の行数 | **505** |
| Plan 期待値 (1 開催日 36R × 平均 13 頭 ≈ 468 馬) との比 | **1.08 倍 (既に超過)** |
| ok | **True** |

## 停止条件チェック (rubric v3 共通)

- [x] git_sha / rule_version は本セッションでスナップショットの対象外 (運用観測のみ、コード変更無し)
- [x] baseline paired 比較は対象外 (健全性チェックは A/B 比較ではない)
- [x] market_snapshot counts は coverage JSONL 上で記録あり
- [x] payout 欠損 race は対象外 (健全性チェック範囲外)
- [x] **専門領域別の停止条件 (data-pipeline-engineer)** すべて不抵触:
  - [x] スケジューラが開催日に実測で動いている (LastResult=0、17 回正常 fire)
  - [x] `fresh_horses` > 0 (= 505)
  - [x] `popularity_bonus_candidate_horses` の集計は backtest 時に行う (健全性チェックは取得経路のみ)
  - [x] post-start snapshot 混入の疑いなし
  - [x] 取得ログ (coverage JSONL) と DB の整合が確認可能
  - [x] 失敗理由 (failed_reason) 分類のスキーマ存在 (今日は失敗 0 件)
  - [x] fresh odds 供給量は Plan 期待値以上

## 反証の試み

- 主張「Plan Step 4 達成」→ **半成立**
  - 実成立: 初日 (1 開催日目) の coverage は完璧。eligible=fetched=ok=26、error=0、lock_skipped=0、汚染なし
  - 半留保: Plan 完了条件は「2-4 開催日で安定」。1 開催日では決定的でないため「達成見込み」と言うべき。明日 (2026-06-21) も同様に稼働すれば完全達成
- 主張「fresh_rows=505 で Plan 期待値超過」→ **成立**
  - 11:45 時点で既に超過。16:40 まで稼働すれば 700-900 行に到達見込み
  - ただし、これは scheduler が「動いている」ことの証明であって「補正発火数 (popularity_bonus_candidate_horses)」の十分性は別途 backtest で測定する必要がある
- 主張「scheduler 自動失効トリガが機能する状態」→ **未検証**
  - `evaluate_calibrator_compat` の `max_fresh_rate=0.05` トリガは bonus rate / fresh rate ベース
  - 今日 1 日のデータだけで bonus_candidate_horses が増えるかは backtest 後でないと分からない

## 自動化チェーンの動作証拠

```
09:00 → keiba-fresh-odds が発火 (1 日 46 回想定 × 10 分おき)
09:15 → keiba-fresh-odds-healthcheck が発火 (1 日 32 回想定 × 15 分おき)
        ↓
        data/runtime/fresh_odds_health_<ts>.json + _latest.json (atomic write)
        data/logs/fresh_odds_health_20260620.log への append
        ↓
        decision=PASS が確認できれば OOS auto (今は Disabled) が起動可能になる
        17:30 → (Disabled なので発火しない)
```

実測ログ統計 (`data/logs/fresh_odds_health_20260620.log`):
- 09:00 前: HOLD=3 (scheduler 未稼働状態の正しい判定)、NOT_EVALUABLE=1 (修正前ロジックの run、ノイズ)
- 09:00 以降: PASS=10、HOLD=0、FAIL=0、NOT_EVALUABLE=0

## 主な改善提案

1. **完了確認は 2026-06-21 (日) も観察してから** — Plan の「2-4 開催日で安定」条件は厳格に守る。1 開催日だけの完了宣言は早計
2. **OOS auto を enable する判断はユーザに委ねる** — 日曜まで観察して PASS が継続するなら、月曜以降に `Enable-ScheduledTask -TaskName keiba-oos-backtest-auto` をユーザ判断で実行
3. **coverage の汚染検出を継続テスト** — 本日は contamination=False で問題なし。autouse fixture が将来も漏れを防ぐかを CI で監視

## 前回からの差分

- 前回 (2026-06-17 22:30 / `20260617_2230_p25_cross_cutting_remediation.md`) は **設計段階**: 機構は実装したが実 backtest なし
- 今回 (2026-06-20 11:45): **初日実機稼働**で機構が動くことを実証
- Plan Step 4 が「設計済み・未稼働」→「初日達成見込み」に進んだ

## 関連 commit

- `2546dd4`: fresh odds health check + 条件付き OOS 自動化
- `091e17b`: register PS1 の schtasks /query 落ち修正
- `fa56feb`: P25 外部レビュー反映 (Plan + coverage 監査 + age tier 4 段階)
