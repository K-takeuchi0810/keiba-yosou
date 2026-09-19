# 予想ロジック分析官 採点

## 判定: HOLD

**理由**: readiness計測はcanonical PIT gateを正しく再利用しているが、Phase 1の7モデル比較に使えるのは19レース、wide driftは0レースであり、現時点の着手母集団として不足する。
**根拠ファイル**: `scripts/f3_phase1_readiness.py:110-165`, `data/f3_phase1_readiness/dev_odds_coverage.json`, `docs/F3_phase1_readiness.md:9-32`
**次アクション**: 09:30等の早期アンカー取得を人間承認後に運用化し、少なくとも数百レース規模のdrift-computable母集団と、非ゼロのwide-drift母集団を再計測してからPhase 1を開始する。

## 総合: 4.2 / 5（前回 4.2 → 今回 4.2、±0.0）

> 改修タイプ: **type-B（read-only診断・readiness計測）**。最終HEAD `cb56778` は `scripts/f3_phase1_readiness.py` とそのtestだけを変更し、`predictor/rules.py` / `features.py` / `weights.json` / `calibrator.json` / `pit_gate.py` は変更していない。P25固有の採用ゲートはN/A。本判定は診断実装の品質ではなく、診断結果に基づくPhase 1着手可否をHOLDとしている。

## 項目別

- **シグナル網羅性: 4.5/5** — 予想シグナルの追加・削除はない。今回の計測は市場残差候補を新シグナルとして採用せず、PIT時点の存在量だけを測る (`scripts/f3_phase1_readiness.py:1-5`, `:110-165`)。前回のcontrol 112列 / exact-3 treatment 109列という評価を変更する差分はない。
- **重み妥当性 / 過適合リスク: 4.0/5** — `weights.json` と学習成果物は無変更。readiness結果を見て閾値・特徴・重みを変更しておらず、4週外挿も「reference-only」と明記して設計判断に昇格させていない (`scripts/f3_phase1_readiness.py:496-498`)。ただし外挿はactive day 2日だけに基づくため、計画値としては使用不可。
- **信頼度判定 / 確率推定: 4.0/5** — `_confidence`・softmax・calibrator経路は無変更。`drift_computable` は確率品質の改善主張ではなく「異なる2時点以上」の可用性ラベルに限定されている (`scripts/f3_phase1_readiness.py:133-144`)。calibrationやROI採用判断へ越権していない。
- **デッドコード / 設計整合性: 4.7/5** — 独自SQLでPIT条件を再実装せず、`usable_snapshots` / `pit_cutoff` を唯一の入口にしている (`scripts/f3_phase1_readiness.py:19-21`, `:110-130`)。時刻は馬行数ではなくdistinct `fetched_at` で数え、unit testも同一時刻の複数馬を1点として検証する (`tests/test_f3_phase1_readiness.py:50-77`)。artifactにgit dirty/statusとscript SHAがない点は軽微な監査証跡不足。
- **本番運用との乖離リスク: 3.8/5** — T-10、NULL除外、read-only/query-only、一貫read transaction、封印窓拒否をfail-closed化している (`scripts/f3_phase1_readiness.py:40-50`, `:371-424`)。一方、実測は225レース中usable 71、drift-computable 19、wide 0で、早期アンカーなしでは§4.2の市場ドリフト特徴を安定してtrain/serveできない。

## 停止条件チェック

- [x] `git_sha=cb56778119b3998510820116510d2fc87bad8f0d`、窓 `20260704-20260719`、T-10 gate、生成時刻をartifactに記録。rule_version / env_overridesは予測非変更のtype-BなのでN/A。git dirty/statusは未記録（改善対象）。
- [x] baseline paired比較、market_snapshot採用指標、payout欠損はreadiness可用性計測なのでN/A。
- [x] sealed holdoutは `to_date >= 20261001` をquery前に拒否し、testあり (`tests/test_f3_phase1_readiness.py:80-85`)。
- [x] production 4成果物と凍結設計書の前後SHAを比較し、不一致なら停止 (`scripts/f3_phase1_readiness.py:372-424`)。
- [x] 予想ロジック・重み・校正器の変更なし。必須確認ではweights top-level 24 keys、magic-number検出は既存 `predictor/rules.py:580 score -= 1000` の1件のみ。

## PIT / drift / wide定義の確認

- **PIT: PASS** — `usable_snapshots` は `fetched_at IS NOT NULL AND fetched_at <= 発走-T10` を実装し、本scriptは返却時刻のleadも再検算してT-10違反を停止する (`predictor/pit_gate.py:35-65`, `scripts/f3_phase1_readiness.py:110-131`)。
- **drift_computable: PASS** — レース内のdistinct適格時刻が2点以上。自分のread-only反証クエリで19/19レースについて全時点の馬集合が出走馬集合と一致し、部分snapshot同士を誤って計上する現物ケースはなかった。
- **wide_drift: PASS** — distinct 2点以上かつearliest lead >=60分、latest lead <=25分 (`scripts/f3_phase1_readiness.py:137-144`)。実測0/225は定義どおりで、午前・午後のearliest中央値も19.9/20.0分のため早期アンカー不足を示す。

## 反証の試み

- 「19レースは、別々の馬しか存在しない2時点を数えただけ」という反証をread-only DBで確認した。19/19レースで全distinct時点のhorse集合の共通部分が出走馬全体と一致（共通8〜18頭）し、この反証は不成立。
- 「coverageは継続改善しており直ちに着手できる」という反証は成立。drift計測は7/18・7/19の2 active daysに限られ、それ以前の8 race daysは0件。`improving` と+76外挿は取得開始の段差を表す記述統計で、安定トレンドの証拠ではない。

## 主な改善提案

1. **Phase 1開始を保留し早期アンカーを先行** — `wide_drift=0` のため、09:30アンカー取得を人間承認後に実装・監視し、wide driftを非ゼロかつ数百レース規模にする。
2. **active期間のtrendを分離表示** — `scripts/f3_phase1_readiness.py:198-225` でcollector稼働前の0日を含む全期間trendと、`races_with_usable > 0` のactive-day trendを別々に出し、「improving」の誤読を防ぐ。
3. **監査メタを補強** — artifactに `git_status_short` / `git_dirty`、evaluator SHA-256、Python/SQLite versionを保存し、後日の同一計測再現性を上げる。

## 前回からの差分

- シグナル網羅性 4.5 → 4.5、重み 4.0 → 4.0、確率構造 4.0 → 4.0: predictor非変更。
- 設計整合性 4.9 → 4.7 (-0.2): canonical gate再利用は適切だが、type-B artifactのdirty/script provenanceが不足。
- 本番乖離 3.6 → 3.8 (+0.2): train-serve前提を初めてPIT実測した一方、wide drift 0のため着手可能水準には未到達。
- 前回判定 PASS → 今回 HOLD: 実装品質の後退ではなく、readiness実測がPhase 1母集団不足を示したため。

## 検証メモ

- `git log --stat -3`: HEAD `cb56778`、先行 `5ba3808`。変更はreadiness script/testのみ。
- `pytest tests/test_f3_phase1_readiness.py -q`: **5 passed in 0.32s**。
- JSON再集計: 225 races / 71 usable / 19 drift-computable / 0 wide。JRA centralは216 / 19、otherは9 / 0。
- このレビューで編集したのは本scorecardのみ。他agent・ユーザの未追跡ファイルは変更していない。
