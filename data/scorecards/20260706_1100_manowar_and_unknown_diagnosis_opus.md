# 2026-07-06 11:00 — マンノウォー系追加 + 「その他」原因切り分け診断の expert-review (7名全PASS・Opus代替採点)

## 採点モデル (透明性)

7名の専門家 subagent 定義は `model: fable` だが **Fable 5 利用不可**のため全員 **Opus (claude-opus-4-8)** で代替採点。

## 対象改修

ユーザが「まだその他が残る / 系統国の表示がされていない」を **3 回**繰り返し訴えた件への対処。
辞書の個別追加 (whack-a-mole) では 225k 頭・数十年分の long-tail に収束しないと判断し、方針を転換:

1. **マンノウォー系 (manowar)** を新設 (Man o'War → Fair Play の米国基礎系統。11大系統外)。
   メンバー: マンノウォー/タイテエム/インリアリティ/リローンチ。国系統 usa。FOUNDERS に
   Man o'War/War Relic/Relic/In Reality/Intentionally を遡上停止点として追加 (ND/Nasrullah を
   経由しない独立枝なので末端でのみ発火)。カンパラ(→Grey Sovereign)/パントレセレブル(→Nureyev)も追加。
2. **audit_sire_lines.py で「その他大量残存」の原因を切り分け可視化**: breeding_horses 行数を
   出力し、traversal_hit≒0 かつ unknown 高のとき「(i) BLOD の血統木が浅い or (ii) FOUNDERS 辞書
   不足 — いずれも個別辞書追加では届かない」と診断表示。

## 採点結果 (7名並列・全員 PASS)

| 専門家 | 判定 | スコア | 主要所見 |
|---|---|---|---|
| code-quality-reviewer | PASS | 4.8 | 4メタ辞書 parity で fail-fast 完備・AST dup 0・redundant dup 除去確認。診断が観測性向上 |
| mobile-html-reviewer | PASS | 4.6 | 新色 #607d8b は全4地で 3.68:1↑・最長7字で新規横スクロールなし・最近接距離62で衝突なし |
| gui-ux-auditor | PASS | 4.4 | 新色ラベル併記で識別担保・凡例は系統名非依存で stale 化せず・「その他」脱出で誤読減 |
| prediction-logic-analyst | PASS | 4.4 | **manowar 血統事実全件正確**・FOUNDERS 副作用なし・予測非流入を grep 実証。パントレ父名コメント誤り指摘 |
| validation-process-auditor | PASS | 4.3 | 方針転換 (辞書無限追加→原因切り分け) を検証プロセスとして評価。実機 before/after が2連続持ち越しと降格宣言 |
| data-pipeline-engineer | PASS | 4.0 | normalize 一貫性・遡上整合。audit の open_db 副作用と warning 切り分け漏れを指摘 |
| profitability-judge | PASS | (軸5=5) | 収益経路非流入を grep 実証・多層免責維持・min_n/CI ガードで偽陽性妙味なし |

## 反映した指摘 (本コミット)

| 指摘 (指摘者) | 対処 |
|---|---|
| パントレセレブルの父名コメントが「Sadler's Wells」だが実父は Nureyev (prediction-logic/validation) | コメントを「父 Nureyev → Northern Dancer」に訂正 (分類 northern は元々正しい) |
| COUNTRY_BY_LINE の manowar:usa が eur ブロックのコメント直下で誤読 (prediction-logic/code-quality/data-pipeline) | manowar を usa 群 (nearctic の直後) へ移動 |
| audit が open_db (書込み migration) で開き読取専用診断が書込みロックを取る (data-pipeline、前回積み残し) | **open_db_readonly に切替**。読取専用で GUI/ingest と非競合に |
| audit warning が「未取込」と断定するが n_hn>0 は取込済・浅いだけ + FOUNDERS 不足の逆ケースを判別せず (data-pipeline) | warning を (i)BLOD が浅い / (ii)FOUNDERS 不足 の2原因併記に修正。行数も表示 |
| 新色を near-pair 記録コメントに追記推奨 (mobile) | LINE_COLOR コメントに manowar≈stsimon(距離62) を追記 |

テスト: **277 passed / 3 skipped**。

## 重要 — 「その他」完全解消についての構造的整理 (ユーザ向け)

辞書の個別追加は限界に達した (テストで判明: テスコボーイ/サクラバクシンオー等の有名種牡馬は
**既に辞書収載済**)。残る「その他」の正体は次の 3 つで、辞書追加だけでは解消しない:

1. **真に 11大系統+named 系統の外**の少数派 (Dictus/サッカーボーイ、Man o'War は追加したが
   Monsun/ノヴェリスト等)。これは**正しい「その他」**。
2. **BLOD (繁殖馬データ) の血統木が浅い/未取込** → 父系遡上 (traversal) が founder に届かず
   unknown に落ちる。**この場合、辞書をいくら足しても解消しない**。
3. 辞書未収載かつ確度の低い海外祖先。

**どれが原因かは実機の audit で判定できる**: `python -m scripts.audit_sire_lines --top 40`。
出力の `traversal_hit` が高ければ遡上は効いており残りは真の long-tail、`traversal_hit`≒0 なら
BLOD の取込/深さの問題 (warning が表示される)。

## ユーザ実機の残作業 (2連続持ち越し・次回最優先)

1. **[最優先] 実機 audit の before/after 実行**: `HEAD~1` と `HEAD` で `python -m scripts.audit_sire_lines`
   を実行し、(a) dict_hit/traversal_hit/unknown の内訳、(b) manowar 等追加の unknown 率低下、
   (c) traversal_hit が低ければ BLOD 取込状況の確認。**この測定まで辞書のさらなる追加はしない**
   (validation の降格宣言=過適合防止)。
2. manowar=usa 等の亀谷公式突合 (OPERATION.md §10)。
