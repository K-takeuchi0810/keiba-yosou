# 採点ルーブリック v3 (全専門家共通) — 2026-06-17 改訂

各専門家は **その分野の世界最高水準の実務家として、自分の名前で署名できる評価のみ** を出す。
項目別スコア + 総合スコア (= 項目平均、小数 1 桁) を必ず出す。

**v3 (2026-06-17 改訂) の趣旨**: v2 までは「5 段階スコア」が中心だったが、P25 検証期では
スコアの高低より「採用判断に進めるかどうか (停止条件への抵触)」が重要。v3 では
**スコアと併せて `PASS / FAIL / HOLD / NOT_EVALUABLE` の 4 択判定を必須化**し、
**停止条件を 1 つでも満たしたら高スコアでも FAIL or NOT_EVALUABLE** とする。
スコアは「実装品質を表すレポーティング指標」、判定は「採用判断の出力」と役割分離する。

## 改修タイプ別ゲート適用 (v4, 2026-06-30 追加) — 最重要

**背景**: v3 までの Hard Fail / Required Evidence は P25 (市場人気補正の backtest A/B 採用判断)
を前提に固定されていた。そのため診断ツール追加・データ層修正・GUI 修正など **P25 採用判断
ではない改修** に対しても market_snapshot / factorial C1-C5 / fresh odds / popularity_bonus_candidate
等の証拠を要求してしまい、本来 N/A であるべき項目を欠落として NOT_EVALUABLE 乱発する誤発火が
起きていた (2026-06-29 bias_scan 採点で表面化)。

**ルール**: 各 agent は採点に着手する前に、`git show HEAD --stat` 等で **改修タイプを分類・宣言**
し、そのタイプに該当するゲートのみ適用する。

| タイプ | 定義 | 適用するゲート |
|---|---|---|
| **type-A** | backtest A/B 採用判断。`predictor/weights.json` `calibrator.json` `filter.py` `BUY_FILTER_DEFAULT` `scripts/backtest.py` 等を変更し、確率品質・収益性の **改善や採用を主張** する | P25 固有の全 Hard Fail / Required Evidence (market_snapshot / factorial C1-C5 / paired baseline / fresh odds / bonus_candidate / calibrator refit) を **適用** |
| **type-B** | 検証/診断ツール・分析スクリプト。予測を変えず計測/診断のみ (例: `scripts/bias_scan.py` `analyze_*.py`) | P25 backtest 採用ゲートは **N/A (対象外)**。適用するのは汎用ゲート: 再現性メタ (artifact 出力時の git_sha/rule_version)、リーク規律 (raw vs calibrated prob・期間既定・in-sample 警告)、統計的正しさ (クラスタ相関を無視した CI 過小・多重比較未補正)、コード品質 (DRY/dead code/テスト/変更失敗モード)、誤精度・誤読を招く出力がないか |
| **type-C** | データ層/取得。`jvlink_client/` `ingest` `schema.sql` `db.py` | クラッシュ一貫性・冪等性・スキーマ進化・鮮度・復旧。P25 収益性/確率ゲートは N/A |
| **type-D** | GUI/HTML 表示。`gui/app.py` `web/templates/` `web/generator.py` | Nielsen/HIG/WCAG/誤読防止・JS パース。backtest 採用ゲートは N/A |
| **type-E** | ドキュメントのみ (`*.md`) | expert-review skip (CLAUDE.md 既定) |

**N/A と NOT_EVALUABLE の峻別 (誤用禁止)**:
- 改修タイプに **該当しない** P25 固有 Required Evidence の欠如は **「N/A (対象外)」**。
  これを理由に NOT_EVALUABLE を出してはならない。
- NOT_EVALUABLE は「**そのタイプで本来必要な証拠**が決定的に欠ける」場合のみ
  (例: type-A なのに baseline backtest が無い / type-B の診断ツールが artifact を出すのに
  git_sha を記録しない / type-C で ingest 結果が確認できない)。

**環境非依存の自己検証 (v4)**: 各 agent 定義の「採点時の必須確認」bash は
`.venv32/.venv64/Scripts/python.exe` 固定や `schtasks`/`cygpath` 前提を**そのまま実行しない**。
利用可能な `python` (または `python3`) を使い、Windows 専用ツール (schtasks 等) が無い環境では
当該確認を read-only な代替 (ファイル/コードの直接確認) に切替え、**「実環境で未実行・read-only
確認に切替」と所見に明記**する。環境差で「数値を自分で実測する」証拠規律を静かに失わないこと。

## v2 改訂の趣旨 (履歴)

v1 の「5 = 同種アプリの中でも上位」は基準が内輪比較で甘かった。v2 は **外部の絶対基準**
(一流実務家が本番承認できるか) に錨を変える。

## 5 段階スコアの意味 (v2 維持)

| 点 | レベル | 外部基準 |
|---|---|---|
| **5** | 一流の本番水準 | その分野のトップ実務家 (プロのシンジケート / スタッフエンジニア / 一流デザイナ) が**自分の責任で本番承認**できる。世界のベストプラクティスと照合した上で一致を確認済み |
| **4** | プロ水準 | 軽微な留保つきでプロが承認できる。留保は具体的に列挙されている |
| **3** | 有能なアマチュア水準 | 動いていて大きな欠陥は無いが、プロの基準では承認しない理由が 1 つ以上ある |
| **2** | 運用リスク | 実害が出る欠陥がある。本番投入は不適 |
| **1** | 致命的 | 即修正。これが残る限り他の長所は無意味 |

**5 を出す条件**: 「世界のベストプラクティスは X であり、本実装は X を満たす」と
具体的に書けること。書けないなら 4 以下。

## P25 検証期の前提 (全 agent 共有) — 2026-06-17 追加

各 agent は採点・判定の前に、以下を **暗黙の前提として受け入れる**。揺らがせない。

1. **P25 は利益戦略ではなく観察対象**。「市場人気による逆張り抑制の検証対象」であり、
   実弾投入候補ではない。
2. **ROI 180% は採用条件 (本番投入を許可する閾値) であって、現時点の達成見込みではない**。
   JRA 控除率 (約 20%) 超えの累積 +80% を要求する非現実的な水準。これを達成見込みとして
   表現する agent コメントは却下する。
3. **改善 ≠ 採用条件**。Brier / subset Brier / ranking の改善は「観察を続ける条件」であって、
   採用判断の根拠にしてはいけない。

## 4 択判定 (v3 で必須化) — 全 agent 共通

5 段階スコアとは別に、最終出力に必ず **以下の 4 択** を 1 つだけ書く。

| 判定 | 意味 | スコアとの関係 |
|---|---|---|
| **PASS** | 採用候補として次段階に進めてよい。改善余地はあっても本質的欠陥なし | スコア 4 以上 + 停止条件抵触なし |
| **FAIL** | 採用候補に進めない。**実害のある欠陥か、停止条件 1 件以上に抵触**している | スコアに関係なく停止条件抵触で FAIL。または スコア 2 以下 |
| **HOLD** | 現段階で採用判断を保留。**追加観察・追加 run・実装補完で再評価**できる | スコア 3 程度、または停止条件は抵触しないが Required Evidence が一部不足 |
| **NOT_EVALUABLE** | **そもそも採点不能**。Required Evidence が決定的に欠けており、改修を批評しても意味がない | データ不足・未実装・run 不足・再現性不足 |

### HOLD と NOT_EVALUABLE の使い分け (混同禁止)

- **HOLD**: 「あと数開催ぶん観察したら判定できる」「追加 fold が走れば判定できる」
  → 軽い不足。次のサイクルで再評価できる
- **NOT_EVALUABLE**: 「そもそも比較対象が paired でない」「git_sha が無い」「rule_version
  が記録されていない」「fresh odds が 0」「baseline backtest が存在しない」
  → 採点行為自体が成立しない。追加 run を依頼してから再評価
- **FAIL**: 「実装が間違っている」「採用条件を満たしていない」「実害がある」
  → 改修が必要

NOT_EVALUABLE を FAIL や HOLD と混同しない。「データが無い」は「失敗」ではなく「未評価」。

## 共通 Hard Fail (停止条件) — v3 追加

以下のいずれか 1 件でも該当すれば、スコアに関わらず **FAIL または NOT_EVALUABLE** を選ぶ。
「注意」「留保」ではなく **停止条件**として扱う。

### 再現性・監査証跡の不足 (→ NOT_EVALUABLE)

- backtest JSON / scorecard に `meta.git_sha` が記録されていない
- `rule_version` が記録されていない
- `meta.env_overrides` が記録されていない (env による挙動変更の追跡不能)
- `meta.git_dirty` または `meta.git_status_short` が未確認 (uncommitted 変更の混入リスク)
- 評価期間 (`from_date` / `to_date`) または fold 境界が明示されていない

### 比較設計の不成立 (→ FAIL または NOT_EVALUABLE)

- 主張する差分について baseline (例: `pop_0_0_0`) との **paired** 比較になっていない
  (期間ズレ、コードパスズレ、フィルタズレを含む)
- 期間が違う 2 つの backtest を並べて「改善」と表現している
- fold 境界が結果を見た後に変更されている / 評価窓が事後選択されている

### 市場 snapshot 品質の不足 (→ NOT_EVALUABLE)

- backtest JSON に `market_snapshot.fresh_horses / stale_horses / unknown_horses` が無い
- post-start snapshot 混入の有無が確認できない (`races_with_post_start_snapshot` が無い)
- payout 欠損 race の扱いが不明 (`races_missing_payouts` / `bets_missing_payouts` カウンタが無い)

### P25 固有の不足 (→ NOT_EVALUABLE)

- `popularity_bonus_candidate_horses == 0` の run で P25 重みの良否を判断しようとしている
- `fresh_horses == 0` で fresh odds 効果を語ろうとしている
- calibrator refit 前に「確率品質が改善した」と表現している
- C1 (baseline) / C5 (現状) のいずれかが欠けている状態で A/B/C 寄与を断定している

## 共通 禁止事項 — v3 追加

以下は agent 自身が **やってはいけない** こと。違反は監査結果そのものの信頼性を毀損する。

1. 結果を見てから評価窓 / fold / 閾値を選び直すこと (post-hoc filtering)
2. 期間ズレ・コードパスズレのある backtest を「比較」として並べること
3. fresh odds 不足の run で P25 重みの良否を判断すること
4. calibrator refit 前の P25 を「確率品質改善」と表現すること
5. GUI / HTML 上の「市場人気補正 ON」と「実際に補正が発火した」を混同すること
6. 5 段階スコアだけを書いて 4 択判定を書かないこと
7. 停止条件抵触を「軽微な指摘」に降格して PASS を出すこと
8. 改善提案を「次セッションで」と先送りして判定だけ PASS にすること

## 証拠規律 (v2 から維持)

1. **すべての主張に出典をつける**: `file:line` への参照、または **自分がこのセッションで実測した数値**。どちらも無い主張は書かない
2. **鍵となる数値は自分で再導出する**: 過去 scorecard や改修サマリの数値を鵜呑みにしない。回収率・件数・サイズ・コントラスト比などは可能な限り再計算 / 再実行で確認
3. **事実 / 推論 / 憶測を区別する**: 確認した事実はそのまま、推論は「〜と推定 (根拠: …)」、未確認は「未検証」と明記。「良さそう」「妥当そう」「期待できる」のような根拠の弱い表現は使わない
4. **反証を 1 回試みる**: 改修が主張する効果について「これが嘘になるシナリオ」を最低 1 つ立てて潰す (または潰せないことを報告する)
5. **1 点を超える上下動には再現可能な証拠を要求する** (自分の前回スコアに対して)
6. **褒めるレビューは禁止**。「素晴らしい」「秀逸」など、停止条件と無関係な賛辞を書かない

## 共通 Required Evidence

各 agent は採点に着手する前に、以下を **必ず** 確認する。1 つでも欠けたら NOT_EVALUABLE を選ぶ。

- `data/backtest/<ts>_<rule>-filtered.json` の最新 2 件以上 (採用構成 + baseline)
- 各 JSON の `meta` セクション (git_sha / rule_version / env_overrides / calibrator_* / lgbm_*)
- `meta.git_dirty` / `meta.git_status_short` (uncommitted 混入チェック)
- `market_snapshot` セクション (fresh/stale/unknown counts, snapshot_age 分布, popularity_bonus_candidate counts)
- 直近 scorecard (`data/scorecards/*.md`) で前回判定 / 残課題を確認
- `docs/P25_MARKET_POP_VALIDATION_PLAN.md` の合格条件 / 棄却条件
- 自分の専門領域別の Required Evidence (各 agent 定義参照)

## 出力フォーマット (v3 で更新)

```markdown
# <専門家名> 採点

## 判定: PASS | FAIL | HOLD | NOT_EVALUABLE

**理由**: <1 行サマリ。停止条件抵触ならその条件名を引用>
**根拠ファイル**: <file:line または data/backtest/<ts>...json>
**次アクション**: <次サイクルで何が必要か。NOT_EVALUABLE なら追加 run の具体的指定>

## 総合: X.X / 5 (参考スコア)

## 項目別

- **<項目1>: N/5** — 所見 (出典つき)
- (5 項目)

## 停止条件チェック (該当の有無を全項目明記)

- [ ] / [x] git_sha / rule_version / env_overrides 記録あり
- [ ] / [x] baseline paired 比較成立
- [ ] / [x] market_snapshot counts あり
- [ ] / [x] payout 欠損 race の扱い明示
- [ ] / [x] 専門領域別の停止条件 (各 agent 定義参照) すべて不抵触

## 反証の試み

- 改修の主張「…」に対し「…」を確認 → 成立 / 不成立 (根拠)

## 主な改善提案 (優先 1 件、最大 3 件)

1. **<タイトル>** — 何を変えるか / 期待効果。`file:line` 粒度

## 前回からの差分 (前回スコアがあれば)

- 項目1: 3 → 4 (+1) 改善: <理由>
- 前回判定: <PASS/FAIL/HOLD/NOT_EVALUABLE>、今回判定変更の理由
```

## ルール

1. **対象ファイルだけを読む**。専門範囲外を読み込んでトークンを浪費しない
2. **下駄を履かせない**。迷ったら辛口側。停止条件抵触を見逃して PASS を出す方が
   甘い 4 を出すよりはるかに重い罪
3. **改善提案は実装可能な粒度**。「`gui/app.py:1234` の N を M に」レベル
4. **過去 scorecard を確認** (`data/scorecards/`) し差分を出す。ただし数値は鵜呑みにしない (証拠規律 2)
5. **採点対象とスコープ外を冒頭で宣言する**。スコープ外への越権採点はしない (隣接領域への観察は「参考所見」として分離)
6. **判定 (PASS/FAIL/HOLD/NOT_EVALUABLE) を出力先頭に書く**。読み手はまず判定を見る
