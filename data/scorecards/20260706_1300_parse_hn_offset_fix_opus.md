# 2026-07-06 13:00 — parse_hn の HN -2 バイトずれ確定・修正の expert-review (7名, 6PASS + validation HOLD→解消)

## 採点モデル (透明性)
7名の専門家 subagent 定義は `model: fable` だが Fable 5 利用不可のため全員 **Opus (claude-opus-4-8)** 代替採点。

## 対象改修 — traversal 不通の主因を実 .jvd で特定・修正

ユーザ実機の `probe_hn_offsets` が HN 繁殖馬レコード (HNVM2020…) の生バイトをダンプ。国内産
レコードの産地が旧 210 では `平町…11`(先頭欠け+繁殖番号"11"混入) だが **208 で `安平町`** と
正しく読め、**HN の birth_year 以降 tail 全体が -2 バイトずれ**と確定。この -2 は
`sire_breeding_num` (230→228) にも及び、**血統遡上 (traversal) が繋がらず「その他」大量発生
していた主因の一つ**。parse_hn を全 tail フィールド -2 補正。

証拠 artifact: `data/audit_sire_lines/20260706_probe_hn_offsets_dump.txt`。

## 採点結果 (7名)

| 専門家 | 判定 | スコア | 主要所見 |
|---|---|---|---|
| gui-ux-auditor | PASS | 4.5 | fail-safe (再取込前は誤産地非表示) が UX 上正しい・多重ガード・views コメント整合 |
| prediction-logic-analyst | PASS | 4.3 | **予測経路への非流入を grep 実証** (parse_hn→breeding_horses、features は horse_masters 別系統) → 再学習不要。遡上ロジック整合 |
| data-pipeline-engineer | PASS | 4.2 | **-2 補正を実バイトから独立再導出** (旧混入"11"=新sire_bn先頭2桁のバイト一致)。冪等再取込 OK。effectiveness の defer が誠実 |
| code-quality-reviewer | PASS | 4.2 | 旧 tautology roundtrip の是正を実測確認 (-2 revert で loud fail)。doc drift 2件を指摘 |
| profitability-judge | PASS | (軸2/4/5=5) | 収益経路 (EV/Kelly/BUY_FILTER) 不変をテーブル分離+import グラフで grep 実証 |
| mobile-html-reviewer | PASS | 維持 | HTML/CSS 無変更・産地非表示据え置きで視覚影響ゼロ。反転時の予算も opt-col 畳みで安全 |
| validation-process-auditor | **HOLD→解消** | 3.66 | offset 根拠が実データで閉じていること・deferral の誠実さは評価。dirty tree/doc矛盾/切り分け不足を HOLD 根拠に |

## validation HOLD + 全 doc 指摘の反映 (commit 246baba)

| 指摘 (指摘者) | 対処 |
|---|---|
| test が write==read の半 tautology (validation/data-pipeline/prediction-logic/code-quality 4名) | test_parse_hn_real_record_offsets を「実 .jvd 観測ストリームを byte195 に 1 本流す」真の非tautology 回帰へ書換。-2 revert で birthplace/sire_bn が崩れ loud fail |
| §9-4 step2 が「HN offset を確定せよ」= §9-2 の確定済と矛盾 (validation) | §9-4 を「確定・修正済/再probe不要/再取込で置換」へ。矛盾除去 |
| 再取込後も 0% の切り分けが HN 内部 offset にしか戻さない (validation) | §9-4 step4 と audit warning に UM 入口 (UM.sire_breeding_num ⇔ HN.breeding_num 採番系突合) 分岐を追加 |
| probe 証拠が repo 未保存 (validation) | data/audit_sire_lines/20260706_probe_hn_offsets_dump.txt に artifact 化 |
| test module docstring / views.py / config.py の HN コメントが旧「位置未確定」で stale (code-quality/gui-ux) | 全て「位置確定・DB再取込/目視検証待ちで False 据え置き」に統一 |

テスト: **279 passed / 3 skipped**。

## 効果の発火条件 (honest な整理)
parse_hn 修正は**コード上完了**だが、既存 breeding_horses は旧オフセットの garbage を保持する
ため、**実機での BLOD 再取込 (`scripts.bootstrap --dataspecs BLOD`) まで実効化しない**。
再取込後 `audit_sire_lines` で **traversal_hit が 0% から上昇**することを確認して初めて
「traversal 復活 = その他の構造的解消」を主張できる (据え置きが正しく、過信しない)。

## ユーザ実機の残作業 (次回・最優先)
1. `git pull` → `.venv32\Scripts\python.exe -m scripts.bootstrap --dataspecs BLOD` → `python -m scripts.audit_sire_lines --top 40`。
   traversal_hit 上昇・unknown 低下を数値確認。
2. 上がらなければ §9-4 step4 の切り分け ((a)行数増えず=BLOD取得失敗 / (b)UM 入口採番系突合)。
3. 産地目視検証 → `HN_BIRTHPLACE_VERIFIED=True` 反転。
4. 亀谷公式リスト突合 (国系統確定、§10)。
