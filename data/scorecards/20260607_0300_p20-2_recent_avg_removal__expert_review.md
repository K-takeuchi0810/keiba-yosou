# 採点 2026-06-07 03:00 — P20-2 raw 平均着順 rule 項削除 + portfolio 日別集計

**改修内容**: アブレーション backtest に基づき raw 平均着順 (recent_avg) の rule スコア項を削除 + 買い候補ボードの推奨投資率を開催日ごとに集計
**対象ファイル**: predictor/rules.py, predictor/weights.json, web/generator.py, web/templates/index.html.j2
**コミット**: 5d30d44 (P20-2), 05c2724 (portfolio 日別)

---

## 総合スコア (項目平均) の推移

| 専門家 | 今回 | 前回 | 差分 |
|---|--:|--:|--:|
| 予測ロジック分析家 | 4.2 | 4.1 | +0.1 |
| **収益性判定家** | **2.6** | **3.5** | **-0.9 ⚠ 後退** |
| **検証プロセス監査人** | **4.0** | **4.55** | **-0.55 ⚠ 後退** |
| コード品質レビュアー | 4.0 | 3.9 | +0.1 |
| モバイル HTML レビュアー | 4.4 | 4.6 | -0.2 |
| データパイプライン技術者 | 4.0 | 4.0 | ±0 |
| GUI / UX 監査人 | 3.6 | 3.6 | ±0 |

**平均**: 3.83 / 5

---

## ⚠ 最重要: 統計的過剰主張の訂正 (収益性 -0.9 + 検証 -0.55 の共通根)

収益性判定家と検証プロセス監査人が**独立に同じ核心**を指摘:

**commit message の「rank-1 べた買い +7.6pt・的中 +10」は統計的に有意でない。**
- two-proportion z = **1.10** (有意水準 95% 未達)
- return CI95: (a) [38.8%, 132.7%] vs (b) [45.4%, 151.6%] = **大幅重複**、両者とも 100% を跨ぐ
- = 「この窓で偶然 +10 的中」の可能性が十分ある (P12「TEST robust≠PROD」が最も刺さる)

**訂正後の正しい主張** (scorecard_ops_v2 invariant 1 = power/CI 公表に準拠):
> raw 平均着順 rule 項の削除は回収率を**悪化させず** (非有意に +、Brier 0.065533→0.065449 でほぼ中立)、削除の正当化根拠は **+7.6pt ではなく構造的理由** — (1) finish_rate (頭数正規化)/class_level_top3/LGBM 特徴との冗長、(2) Brier 中立 = 校正に寄与せず、(3) 「直近3走」固定ラベル + 1走2着満点付与の rationale バグ。

**buy_only 50.6%→47.6% の扱い訂正**: これは「ノイズ」ではなく、recent_avg 削除で**買い候補集合が変わった (140→92件)** ための**別集合比較**。同一馬集合の悪化ではない (検証監査人指摘)。n=92/的中4 は意思決定に使わない (A1 期の「n=5 戦は使うな」規律と整合)。

**判定**: 全 reviewer が「削除のロジック判断自体は妥当」「gate fail には当たらない」と評価。**改修は維持してよいが、根拠の記述を「+7.6pt 改善」から「非有害 + 構造的冗長」へ格下げするのが誠実**。

---

## 各専門家の所見 (要点)

### 予測ロジック分析家 (4.2, +0.1)
finish_rate + class/condition top3 + recent_best/top3 + LGBM `recent_avg_finish_rate` で代替十分、網羅性に穴なし。magic number 1 ブロック削減 + ablation 証拠 + caveat 明記を評価。**指摘**: `_stability_score` (rules.py:599-610) に recent_avg の hardcoded 8/5/2/-4 が残置 = primary score から消したのに secondary sort key + 高信頼ゲートには裏口で残る**非対称性**。ablation (b) はこの stability 経路を残したまま測ったので「校正に寄与しない」結論は primary 経路限定。→ 次の ablation 対象に確定すべき。

### 収益性判定家 (2.6, -0.9)
ルーブリック「控除率 80% 未達なら総合 3 未満」を厳格適用 (buy_only 47.6% で控除率割れ)。+7.6pt は CI 重複で非有意、buy_only は母数縮小で測定不能。**改善方向は正しいが実弾観点で net で喜べる結果ではない**。改善提案: ①別窓 (2025同期 or 2026Q1) で符号確認、②buy_only に Wilson 下限 + 最小有効 n 警告、③kelly_weighted_return_rate 実装 (積み残し)。

### 検証プロセス監査人 (4.0, -0.55)
ablation 手続きは模範的 (単一変数切替・同窓同 n・rule_version タグ保存・weights0化≡コード削除の等価性を別 run で実証)。**最大減点 (過適合監視 4.4→2.8)**: 1 窓 1 dataset で**永久削除 commit**、別季節再現 (2025 Apr-May 等) 未実施 = scorecard_ops_v2 dataset 上限 invariant 違反。+7.6pt 有意性 (z=1.10/CI 重複) を headline 化したまま未開示。改善提案: ①z値・CI を scorecard に明記し回収率改善を「悪化していない確認」に格下げ、②別季節 1 fold 追加、③backtest_diff.py (継続宿題)。

### コード品質レビュアー (4.0, +0.1)
**dead code 削除の正攻法** (dead variable / dead path 懸念を grep で完全否定: `avg` は finish_rate 補助判定で実使用、`_w("recent_avg.*")` 呼び出し 0 件)。**指摘**: ①`_stability_score` の recent_avg が weights 外出しされず hardcode 残置 = rule 層内で同 feature の扱いが二分、②portfolio 日別集計が build_view_model にインライン (純粋 helper 未分離)、③weights.json 末尾改行喪失 (→ **本 review 後に修正済**)。

### モバイル HTML レビュアー (4.4, -0.2)
portfolio 日別化の機能は正しい。**減点 (情報密度 5→4)**: 4 開催日が 1 行直列で 320px 折り返し時に `（…）` が語境界無視で割れる。8 日窓で ~180字/5-6行に膨張。改善提案: ①日別を `<span>` チップ化 + `flex-wrap` で語境界折り返し、②超過日のみ強調 (現状 1 日超過で全日赤太字)、③5日以上で max-day サマリ行を先頭に (max_day_pct は既に算出済・j2 未使用)。

### データパイプライン技術者 (4.0, ±0)
担当範囲無編集で維持。**新規確認**: `training_times` 0 行 = parse_hc/parse_wc 実装済なのに実データゼロ (ingest 未配線 or byte offset 不一致)。新馬戦予想強化 (ユーザー要望の調教データ) の前提が崩れている = jvdata-record 領域の最優先課題。odds_fetched_at HTML 非露出も継続。

### GUI / UX 監査人 (3.6, ±0)
gui/app.py 無編集 (JS len 12824 byte 一致)、node --check PASS。**新規乖離**: P20 で追加した config.BET_KELLY_* を GUI から確認/変更する導線が皆無。継続宿題: input 既定値の config 乖離 (P05 から 3 期)。

---

## 横断的に見た優先課題

1. **【最優先・記述訂正】+7.6pt の非有意性を開示** (収益性 + 検証の共通指摘) — commit/scorecard で「+7.6pt 改善」を「非有害 + 構造的冗長による削除」に格下げ。z=1.10 / CI 重複を明記。**本 scorecard §「最重要」で実施済**。
2. **【削除の堅牢化】2025 同季節で再現確認** (検証 #2 + 収益性 #1) — 1 窓 permanent delete のリスク低減。`--from 20250401 --to 20250510` で a/b 符号一致を見れば「2 シーズンで非有害」と言える。~15分×2。
3. **【非対称性解消】`_stability_score` の recent_avg も ablation 対象に** (予測ロジック + コード品質) — primary score だけ消した非対称を解消。stability 経由で ◎ tie-break + 高信頼ゲートに残存しているため、これを含めた再 ablation で初めて「recent_avg 無害化済み」と言える。
4. **【新馬戦・別タスク】training_times 0 行の根因切り分け** (データパイプライン) — ユーザー要望の調教データ取込。parse_hc/wc の byte offset 検証 (jvdata-record skill)。

---

## メタ: 本 review の自己評価

profitability -0.9 / validation -0.55 は「改修が間違い」ではなく「**commit message が統計的根拠を過剰主張した**」ことへの正当な減点。これは本セッションが制定した scorecard_ops_v2 invariant 1 (power/CI 必須公表) に著者自身が違反した事例であり、self-aware に留めず本 scorecard で記述を訂正した。「self-aware は防御線ではない」(P19 critic 観点) の実践。

改修自体 (冗長・Brier 中立・rationale バグの signal 削除) は全 reviewer が妥当と評価しており revert は不要。ただし「1 窓 permanent delete」の堅牢性は別季節再現 (優先課題 2) で担保すべき宿題として残る。
