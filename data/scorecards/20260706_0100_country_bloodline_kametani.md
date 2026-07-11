# 2026-07-06 01:00 — 亀谷敬正「国別血統」タイプ (日本型/米国型/欧州型) の追加

## 対象改修

ユーザ指摘「産地ではなく亀谷敬正の国別血統で分類してほしい」への対応。産地
(地理的生産地・前コミット) とは別軸として、系統を日本型/米国型/欧州型に分類する
亀谷氏の枠組みを実装。

1. predictor/sire_lines.py — COUNTRY_BY_LINE (系統既定) + COUNTRY_OVERRIDE (種牡馬
   個別) + classify_country / country_label / country_color。2022 改訂ルール
   「日本型=SS系のみ」に準拠。
2. webapp/views.py + race.html.j2 — 出馬表の系統セルに国系統バッジ。
3. webapp/aggregate.py + trends.html.j2 — 傾向集計に父国系統/母父国系統軸。

公式リスト取得不可 (会員サイト・全ソース 403) のため founder 由来の**暫定**分類
とし、ユーザ承認済み (既定案+暫定マーク・種牡馬単位で解決)。

## 採点結果 (7 名並列)

| 専門家 | 判定 | スコア | 主要所見 |
|---|---|---|---|
| data-pipeline-engineer | PASS | 4.4 | 純導出・DB 経路不変を実証。dam_sire_country 縮退テスト要 |
| profitability-judge | PASS | 4.2 | 収益経路への非流入を grep 実証。trends 暫定注記要 |
| code-quality-reviewer | PASS | 4.2 | ヘルパ抽出は良。parity テスト欠如・虚偽コメント指摘 |
| validation-process-auditor | HOLD | 4.3 | 暫定開示は良も OPERATION.md 突合節が宙吊り参照 |
| gui-ux-auditor | HOLD | 3.5 | コントラスト/フォント床違反・系統dotとの色相衝突 |
| prediction-logic-analyst | HOLD | 4.3 | **確定誤分類: クロフネ等ND北米枝・ナダルが欧州型** |
| mobile-html-reviewer | FAIL | 3.4 | **バッジ白文字が3色ともAA未達 + 虚偽の実測コメント** |

## FAIL/HOLD の対処 (全解除)

| 指摘 (指摘者) | 対処 |
|---|---|
| **バッジ白文字 AA 未達 (mobile FAIL: 赤4.23/青3.68/緑3.30) + 10.5px 床違反 + 虚偽「実測」コメント** | gui-ux 提案の構造的解決を採用: 塗り潰し→**枠線+テーマ色テキストのニュートラルチップ** (.ctag-jpn/usa/eur が var(--warn/accent/good) を使用、light/dark 両対応の既存 AA 実測済変数)。11px 化。コメントを実測値付きの正直な記述に。系統 dot との色相衝突も同時解消 |
| **確定誤分類 (prediction-logic HOLD)** | COUNTRY_OVERRIDE に追加: クロフネ/フレンチデピュティ/マインドユアビスケッツ/デクラレーションオブウォー/アメリカンペイトリオット/ザファクター → usa (ND 北米発展枝)、ナダル → usa (Kris S. 米国残留枝)、タマモクロス → eur (Grey Sovereign スタミナ枝)。regression テスト固定 |
| OPERATION.md 突合節が宙吊り (validation HOLD) | docs/OPERATION.md §10「亀谷公式リスト突合」を新設 (未突合枝の優先順・突合手順・2022改訂追随・確定済み一覧)。docstring 参照を実在化 |
| trends に暫定開示なし (validation/profitability/gui-ux) | 国系統軸選択時に「暫定分類・公式リスト未突合・セル境界に誤差」チップ。degrade チップ文言を国系統軸対応 (「その他」「判別不能」) に |
| parity テスト欠如 (code-quality F3) | COUNTRY_BY_LINE キー==LINE_LABEL / COUNTRY_OVERRIDE⊆LINE_BY_SIRE の 2 本追加 |
| `'—'` マジックストリング判定 (code-quality F1/mobile) | country_key 駆動 (`!= 'unknown'`) に変更、views が country_key を渡す |
| need_dam_bn 触り忘れ (code-quality F4) | `_DAM_BN_FACTORS` 定数化 + dam_sire_country 縮退テスト (data-pipeline #1) |
| unknown ラベル (mobile/gui-ux/profitability) | 「—」→「判別不能」(sire_line の「その他」と区別) |
| テスト循環性 (validation e) | country テスト docstring に「実装既定値の回帰であり事実検証でない」明記 |
| 凡例ドリフト防止 (gui-ux) | 新凡例文言 (暫定注記・軸一覧) を test_webapp の固定 assert に追加 |

テスト: **262 passed / 3 skipped**。

## 残存負債 (暫定・follow-up)

- **公式リスト未突合の暫定枝** (docstring + OPERATION.md §10-1 に明記): キングマンボ系の
  米/日 split、マクフィ、チーフベアハート/タリスマニック、プリンスリーギフト枝、
  ノーザンテースト。**ユーザ実機で会員サイト突合が必要** (JV-Link 内に独立ソース無し)。
- override は種牡馬名完全一致のみで枝伝播しない (prediction-logic 提案 2)。辞書外の
  子孫種牡馬は遡上で line 既定値に落ちる。classify_sire_country のペア返し化は次回課題。
- 縮退 helper 一元化 (code-quality F5) が 3 連続繰延 — 次回 webapp 改修で消化 or 恒久受容判断。

## ユーザ実機の残作業

1. OPERATION.md §10 の亀谷公式リスト突合 (特にキングマンボ系)。
2. 既存: 系統辞書 audit_sire_lines / 3代血統 verify_pedigree / probe_corner_offsets。
