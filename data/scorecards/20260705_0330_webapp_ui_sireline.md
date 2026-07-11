# 2026-07-05 03:30 — webapp 実機 iPhone 指摘 3 点対処 (commit 0e6ff06 + 追補)

## 対象改修

実機スマホ確認で受けた指摘 3 点への対処 (rubric v4 分類: type-B/D):

1. 「文字が青色で見づらい」→ ブラウザ既定リンク色の全面上書き、チップのボタン化
2. 「UI/UX に問題あり」→ 馬ペア行 zebra、印列の馬番直後への移動、系統セル 2 段化
3. 「父系統しか出ない・サンデー系以外はその他」→ 母父系統の追加 + LINE_BY_SIRE 拡充 (66 件)

## 採点結果 (7 名、Fable 定義どおり並列実行)

| 専門家 | 判定 | スコア | 主要所見 |
|---|---|---|---|
| prediction-logic-analyst | PASS | 4.6 | **追加 66 件の父系分類は全件正確 (誤り 0/66)**。前回 12 件誤検出と同基準で突合 |
| gui-ux-auditor | PASS | 4.2 | 印左寄せ・zebra は指摘に正対。「データ無 -」と「その他」の混同を指摘 |
| mobile-html-reviewer | PASS* | 4.2 | 全コントラスト AA 実測パス。M1: zebra 帯差 1.04:1 は知覚限界 → 要是正 |
| data-pipeline-engineer | PASS | 4.1 | readonly 縮退は規律一貫。writer 側 _ensure_column の非対称を指摘 |
| profitability-judge | PASS | 4.0 | 買い目/EV 経路に不接触を grep 実証。誤読誘発なし |
| code-quality-reviewer | PASS | 4.0 | dead キー line_label、縮退 SELECT 未テスト、静かな劣化を指摘 |
| validation-process-auditor | HOLD | 3.5 | 事実検証の循環性 (解除条件: prediction-logic 独立監査 + 実 DB 突合) |

\* mobile は「M1 対処を条件とする PASS」。

## validation HOLD の解除状況

- **条件 1 (prediction-logic 独立監査通過)**: 達成。同時実行の prediction-logic-analyst が
  全 66 件を父系チェーンで突合し **誤り 0 件 / PASS 4.6** (本 scorecard に記録)。
- **条件 2 (breeding_horses との独立突合)**: `scripts/audit_sire_lines.py` を新設。
  辞書照合を使わず FOUNDERS 停止の父系遡上のみで分類し辞書値と突合 + unknown 率の
  内訳 (辞書 hit / 遡上 hit / unknown) を定量報告する。**実行はユーザ実機 DB 残作業**
  (BLOD=HN レコード取込が前提)。unknown 率の before/after は HEAD~1 checkout で再実行して比較。

## 指摘 → 追補反映 (本コミット)

| # | 指摘 (指摘者) | 対処 |
|---|---|---|
| 1 | zebra 帯差 1.04:1 で知覚不能 (mobile M1・必須) | --rowalt を light #eceff3 / dark #1d222a へ (帯差 1.085/1.115、muted/accent/warn 全 AA 維持の実測推奨値) |
| 2 | nth-child zebra は行の条件レンダで縞ズレ (mobile S2, gui-ux 4, profitability 3) | loop.cycle 相当の alt クラスを mainrow/subrow 両方に付与する方式へ変更 + ペア/縞の整合テスト |
| 3 | データ無と分類不能の混同 (gui-ux 1・中) | 父/母父の名前が空なら「-」(dot なし) を表示、「その他」= 分類不能に限定 |
| 4 | 縮退 SELECT 経路が未テスト (code-quality 2, data-pipeline 2, validation 3) | 旧スキーマ (列なし) DB での render_race regression テスト追加 |
| 5 | dead キー line_label (code-quality 1) | views.py の行 dict から削除 (import も除去) |
| 6 | 静かな劣化にログなし (code-quality 3) | sire_lines: 1 回限り warning / views: 縮退時 warning + "no such column" 以外は raise (data-pipeline 3 も同時解消) |
| 7 | writer 側の自己修復欠如 (data-pipeline 1) | init_db に horse_masters.dam_sire_breeding_num の _ensure_column 追加 |
| 8 | 系統=儲かる指標の誤帰納リスク (profitability 1,2) | 凡例に「血統の分類表示であり成績・期待値の指標ではない (集計軸は父系のみ)」を追記 |
| 9 | 375px で横スクロール ~170px (mobile M2) | 「単オッズ→オッズ」+ ≤480px の cell padding 7px 4px |
| 10 | damline 11px は CJK 実用下限 (mobile S1, gui-ux 3) | 12px へ |
| 11 | 非リンク chip の擬似アフォーダンス (mobile S3) | span.chip を破線枠に |
| 12 | インラインリンク下線ガード (mobile S4, gui-ux 2) | main p a:not(.backlink):not(.chip) に下線 + コメントで制約明文化 |
| 13 | :focus-visible なし (mobile S5) | a/button/select に outline 追加 |
| 14 | トニービン注記の世代飛ばし (prediction-logic) | Zeddaan を補記 (分類は元から正) |
| 15 | サウスヴィグラス未収載 (prediction-logic) | mrprospector で追加 (父エンドスウィープ) |
| 16 | aggregate の系統グルーピングも変わる旨の明記 (validation 5) | 本 scorecard に明記: **辞書拡充により /trends・/today の sire_line 軸のセル構成が変わる** (min_n=30 ゲート・Wilson CI・n_values 開示は自動追従することを profitability が確認済) |

テスト: 240 passed / 3 skipped (追補後、フル実行)。

## ユーザ実機の残作業 (次回セッションで案内)

1. `python -m scripts.audit_sire_lines` — 辞書 vs 独立遡上の突合 + unknown 率定量
   (BLOD 未取込なら先に取込)。不一致が出たら辞書を是正。
2. 従来からの hard gate: probe_corner_offsets --expect/--ra 緑化 → corner backfill →
   実 DB bias_scan → 先行力 ablation。
