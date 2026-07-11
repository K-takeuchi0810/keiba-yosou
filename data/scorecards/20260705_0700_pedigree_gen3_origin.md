# 2026-07-05 07:00 — 3代血統 (父母父/母母父) + 産地/産国の追加 (type-C/D)

## 対象改修

ユーザ指摘「父・母父・父母父・母母父の系統と国の項目は追加したか」への対応。
従来は父・母父の 2 系統のみ。今回 3 代血統の残り 2 頭 (父母父・母母父) と
祖先の産地/産国を追加 (SmartRC パリティ)。

1. jvlink_client/parser.py — UM 3 代血統配列から idx8=父母父/idx12=母母父 を抽出
   (idx0=父/idx4=母父は実運用検証済みアンカー、2 点が base=205/stride=46 を拘束)。
   HN に 205 持込区分/206-209 輸入年/210-229 産地名を追加。
2. data/schema.sql + db.py — horse_masters +4 列 / breeding_horses +3 列 (後置
   _ensure_column、新列への INDEX 禁止コメント)。
3. webapp/views.py + race.html.j2 — 父/母父列に産地サフィックス、補助行に
   「父母父 X(系統/産地) ・ 母母父 Y(系統/産地)」。

## 採点結果 (7 名並列)

| 専門家 | 判定 | スコア | 主要所見 |
|---|---|---|---|
| profitability-judge | PASS | 4.5 | 買い目/EV への非流入を grep + features whitelist で確認 |
| mobile-html-reviewer | PASS | 4.4 | 全コントラスト AA 実測合格・横スクロール発生なし |
| prediction-logic-analyst | PASS | 4.4 | idx8=父母父/idx12=母母父 が日本語血統慣習と完全一致 |
| code-quality-reviewer | PASS | 3.9 | probe 単一出典化は模範的。origins broad except を指摘 |
| gui-ux-auditor | HOLD | 4.0 | 凡例が実表示と不一致 (丸括弧の意味) → 対処済 |
| validation-process-auditor | HOLD | 3.9 | offset の暫定確定表記 + 実機検証手順の文書化 → 対処済 |
| data-pipeline-engineer | HOLD | 3.5 | HS クロバー拡大 + force 再取込手順の欠落 → 対処済 |

## HOLD 3 件 + 全指摘の対処

| # | 指摘 (指摘者) | 対処 |
|---|---|---|
| R1 | **HS が UM フル行を空文字 REPLACE (data-pipeline、既存欠陥の拡大)** | `insert_horse_master_if_absent` 新設 (INSERT OR IGNORE)。ingest の HS 分岐をこれに切替。取込順 DIFN<HOSE でも UM 行が潰れず順序非依存に収束。回帰テスト `test_hs_skeleton_does_not_clobber_um_row` (両順序) |
| R1(migration) | force 再取込手順の運用開示ゼロ (data-pipeline) | docs/OPERATION.md §9 に手順明記: `ingest_all(force=True, dataspecs=['DIFN','BLOD'])`、dataspec 無指定 force を避ける旨 |
| 必須 (validation) | offset の過大主張・暫定確定表記欠落 | parser の `_pedigree_item`/`parse_hn` docstring を「暫定確定」+「gen3 順列ミス/数字入替は無音」に是正。test docstring に「synthetic 往復=自己整合であり実位置の証拠でない」明記 |
| 必須 (validation/gui-ux/mobile/prediction-logic) | 凡例が実表示と不一致 | 「父/母父の丸括弧=産地」「補助行の丸括弧は 系統/産地」を分離明記。凡例文字列を test_webapp で固定 (2 連続再発の機械的防止) |
| R3/P1 (data-pipeline/code-quality/prediction-logic) | origins の broad except | no such table/column のみ縮退・他は raise + warning (masters probe と同規律)。回帰テスト `test_render_race_breeding_horses_without_birthplace` |
| R5/P3 (data-pipeline/code-quality) | 旧スキーマ warning のリクエスト毎発火 | `_warn_once_missing_cols` で列セットごと 1 回に |
| S2 (mobile) | pedline の項目途中折返し | `.peditem { display:inline-block }` で項目境界折返し |
| S1/軽微 (profitability/mobile/gui-ux) | 免責が産地に及ばない・最小フォント下限 | 免責を「系統・産地は…出自表示であり成績指標でない」に拡張。.origin 11px 下限コメント。狭幅非対称の意図をテンプレコメント |
| P3 (code-quality) | `_MASTER_COLS` 関数内ローカル | module-level へ移動 |
| R4/実機 (data-pipeline/validation) | 実 .jvd での位置確定 | docs/OPERATION.md §9-2 に手順化 (ディープ産駒の父母父=Alzao 突合、産地の数字混入チェック、充填率) — **ユーザ実機残作業** |

テスト: **254 passed / 3 skipped** (+新規 test_pedigree_gen3.py / HS クロバー / origins 縮退 / 凡例固定)。

## 残存負債 (悪化なし・follow-up)

- parse_hs の (22,8)/(30,8) が「母父」でなく「父/母」の可能性 (仕様書未照合)。
  INSERT OR IGNORE 化で既存行は汚さないため実害は限定。OPERATION.md §9-2 の
  実機確認で仕様書 §13 と照合。
- 縮退イディオムの完全収斂 (existing_columns 共有ヘルパ) は次回 webapp 改修時。

## ユーザ実機の残作業 (次回セッション冒頭)

1. `ingest_all(force=True, dataspecs=['DIFN','BLOD'])` で 3 代血統・産地を反映。
2. docs/OPERATION.md §9-2 の暫定確定→確定の検証 (血統表突合・産地目視・充填率)。
3. 既存の hard gate (probe_corner_offsets / bias_scan / audit_sire_lines) は据置き。
