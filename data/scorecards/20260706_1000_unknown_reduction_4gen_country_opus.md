# 2026-07-06 10:00 — その他の追加削減 + 4世代国系統表示の expert-review (7名全PASS・Opus代替採点) + 反映

## 採点モデル (透明性)

7名の専門家 subagent 定義は `model: fable` だが **Fable 5 利用不可**のため全員 **Opus (claude-opus-4-8)**
で代替採点。各所見冒頭に代替採点の旨を明記済。

## 対象改修 (HEAD 5b4cab7 → 本反映後)

ユーザ指摘「まだその他が残る / 系統国の表示がされていないものがある」への構造的対処:

1. **その他 (unknown) の追加削減**: 実機 unknown 上位 40 件のうち、父系 founder まで血統事実の
   確度が高い **歴史的種牡馬 15 件** を LINE_BY_SIRE に収載。
   - nasrullah: ミルジョージ/ブレイヴエストローマン/キンググローリアス/ロイヤルスキー/アローエクスプレス/イエローゴッド
   - northern: モガミ/ノーザンディクテイター/ホリスキー/ヤマニンスキー/アサティス/スリルショー/ロドリゴデトリアーノ
   - sunday: マツリダゴッホ/タヤスツヨシ
   - DB の大書き仮名スペルでも _normalize 経由で解決することを regression 固定。
   - 確度の低い/名の通らない少数系統 (Dictus/Man o'War/Monsun 枝、スキャン等) は「誤答より
     unknown が誠実」の house standard に従い unknown 継続 (実機では breeding_horses 遡上が
     founder に届けば拾う)。
2. **系統国の表示欠落の解消**: これまで国系統バッジは **父のみ**だった。**母父 (damline)・
   父母父・母母父** にも国系統を併記し、父・母父・父母父・母母父の **4世代すべて**で系統+国が
   読めるように。凡例も4世代・「バッジ無し=判別不能」を明記。

## 採点結果 (7名並列・全員 PASS)

| 専門家 | 判定 | スコア | 主要所見 |
|---|---|---|---|
| mobile-html-reviewer | PASS | 4.6 | ≤400px の .ctag block 折りが母父バッジにも効き横スクロール非誘発を実測。gen3 折り予算内。全6ペア AA 達成 |
| prediction-logic-analyst | PASS | 4.5 | **15件の父系 founder 全件正確 (誤帰属0)**。予測経路非流入を grep 実証。Never Bend 欧州枝の国系統不整合を指摘 |
| code-quality-reviewer | PASS | 4.5 | 母父/gen3 が父と同一 classify_country 経路 (重複なし)。regression が DB 実スペルで非tautology。AST dup 0件 |
| data-pipeline-engineer | PASS | 4.5 | 15件が大書きスペルで全解決・traversal fallback 健全・founder 遡上と無矛盾。国系統枝内不整合を指摘 |
| validation-process-auditor | PASS | 4.3 | 暫定性を凡例で全世代開示・DB実スペル regression。Never Bend 枝の country 不整合を残課題化 |
| gui-ux-auditor | PASS | 4.1 | 凡例↔実装3点一致・凡例ドリフトなし。gen3 の ・/ 入れ子区切りと母父バッジ視覚従属を軽微指摘 |
| profitability-judge | PASS | 4.0 | 収益経路非流入を grep 実証。多層免責 (footer/banner/凡例) で買いシグナル誤読防止 |

## 反映した指摘 (本コミット)

| 指摘 (指摘者・複数) | 対処 |
|---|---|
| **国系統の枝内不整合**: ミルジョージ(父ミルリーフ=eur override)・イエローゴッド(Red God 欧州枝)が nasrullah 既定 usa に落ちる (prediction-logic/code-quality/data-pipeline/validation の4名が指摘) | COUNTRY_OVERRIDE に ミルジョージ→eur・イエローゴッド→eur を追加。test 期待値も eur へ更新 (コメントに親 override 由来を明記) |
| Never Bend 直系枝 (ブレイヴエストローマン/アローエクスプレス) の usa/eur 判断 (validation 残課題) | Never Bend 自体は米国馬で eur は Mill Reef 枝固有と判断し usa 既定を維持。OPERATION.md §10-1 項5 に公式突合の宿題として明文化 |

**留保 (次回・実機残作業)**:
- 実機 audit (`python -m scripts.audit_sire_lines`) を HEAD~1 と HEAD で実行し、15件追加の
  unknown 率 before/after を定量化 (validation 指摘。JV-Link DB は実機側のため本セッション実行不可)。
- gen3 テキストの ・(系統・国系統) と /(産地) 入れ子区切りは show_origin 有効化時に再設計検討 (gui-ux)。
- 母父 damline バッジの視覚的従属化 (彩度/サイズ一段抑え) は次回検討 (gui-ux、非ブロック)。

テスト: **277 passed / 3 skipped**。

## 「その他」完全解消の正直な整理

- 実機 unknown 上位の大半を系統名+国系統付きで解消。残る unknown は (a) 真に 11大系統+3
  named 系統の外 (Dictus/Man o'War/Monsun 枝 = 正しい「その他」)、(b) 辞書未収載かつ確度の
  低い海外祖先。(b) は実機 audit 出力が一次資料で、確度が立てば随時追記する。
- 国系統は父・母父・父母父・母母父の4世代すべてで表示。判別不能な系統のみバッジ無し (凡例明記)。
