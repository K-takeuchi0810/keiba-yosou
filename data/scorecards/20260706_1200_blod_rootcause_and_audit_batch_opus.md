# 2026-07-06 12:00 — 「その他」根本原因=BLOD未取込の特定 + 実測unknown辞書追加の expert-review

## 採点モデル (透明性)
7名の専門家 subagent 定義は `model: fable` だが **Fable 5 利用不可**のため全員 **Opus (claude-opus-4-8)** 代替採点。

## 経緯 — 3度目の「その他残る/系統国出ない」訴えに対する根本原因特定

ユーザが実機で `python -m scripts.audit_sire_lines --top 40` を実行し、決定的データを取得:

```
breeding_horses 行数: 6957
dict_hit        365016 (43.5%)
traversal_hit        0 (0.0%)   ← 血統遡上が完全に死んでいる
unknown         475033 (56.5%)
```

→ 「その他」大量残存は**辞書不足ではなく、血統遡上データ (BLOD=繁殖馬 HN) の欠落**が根本原因と判明。
実測 artifact: `data/audit_sire_lines/20260706_before_blod.txt`。

## 対処
1. **bootstrap.py に `--dataspecs` 追加**: `python -m scripts.bootstrap --dataspecs BLOD` で BLOD (HN
   繁殖馬マスタ) だけを option=4 一括取得し breeding_horses を埋め直せる (全 5-15GB を再取得せず)。
2. **実測 unknown 上位 20 数件を辞書追加**: 父系 founder まで確度の高いもののみ (ネヴァービート/
   ヴェンチア/フォルティノ→既存系統、Le Fabuleux/Law Society/ヒンドスタン/シンザン/ファバージ→
   stsimon、Kris/Bering→native、チャイナロック/シャトーゲイ→hyperion 等)。英語+大書き仮名で解決。
3. **audit に原因切り分け診断**: breeding_horses 行数を出力し、traversal_hit≒0 のとき原因を明示。

## 採点結果 (7名並列)

| 専門家 | 判定 | スコア | 主要所見 |
|---|---|---|---|
| prediction-logic-analyst | PASS | 4.5 | **追加20数件の父系 founder 全件正確 (誤帰属0)**。深い遡上 (ヒンドスタン→Bois Roussel→St.Simon 等) も検証。予測非流入を grep 実証 |
| gui-ux-auditor | PASS | 4.5 | 新系統が「その他」から脱出し可視性改善・凡例無矛盾。Grey Sovereign 枝の国系統不整合を指摘 |
| mobile-html-reviewer | PASS | 4.7 | 新色・新ラベル増ゼロで AA/フォント床/折り予算に回帰なし。unknown 脱出でスキャン価値向上 |
| code-quality-reviewer | PASS | 4.3 | AST dup 0・len parity 維持・非tautology回帰。`--dataspecs` 空値→全取得 footgun を指摘 |
| profitability-judge | PASS | (軸5=5) | 収益経路非流入を grep 実証・多層免責維持・min_n/CI-lo>100 で偽陽性妙味なし |
| validation-process-auditor | PASS | 4.1 | measurement 先行で前回降格を正当解除・audit の独立遡上=循環検証回避を評価。artifact化/再audit runbook 明文化を宿題化 |
| data-pipeline-engineer | **HOLD** | 3.7 | 診断が traversal_hit=0 を「行不足」に断定し、HN offset(230)バイトずれ可能性を棄却した過信を指摘 |

## HOLD (data-pipeline) と全指摘の反映 (commit 456379a)

| 指摘 (指摘者) | 対処 |
|---|---|
| **[HOLD] traversal_hit=0 の原因を行不足に断定。HN sire_breeding_num offset(230) のバイトずれ(§9-2 で既知の疑い)なら BLOD 取込しても遡上は 0% のまま (data-pipeline)** | audit warning を3原因併記に修正 ((i)行不足/(ii)HN offset ずれ/(iii)FOUNDERS不足)。OPERATION.md §9-4 に「BLOD 取込前に probe_hn_offsets で 230/240 を確定」する順序を明文化。「真の解決=BLOD」の過信を「BLOD + offset 確定 + 深祖は辞書が恒久担保」に是正 |
| Grey Sovereign 欧州枝の国系統不整合 (gui-ux/mobile): クリスタルパレス/フォルティノ が usa だが同枝トニービン/タマモクロスは eur | COUNTRY_OVERRIDE に カンパラ/フォルティノ/クリスタルパレス → eur を追加 (同枝整合)。test 更新 |
| `--dataspecs ",,"` が空リスト素通し→ fetch_all で全 dataspec(5-15GB) 無音取得 (code-quality) | 空なら parser.error で fail-fast |
| 実測 audit 出力が commit にしか無く第三者再現不能 (validation) | `data/audit_sire_lines/20260706_before_blod.txt` に artifact 化 |
| BLOD 再取込→再audit の確認ループ未明文化 (validation) | OPERATION.md §9-4 に閉ループ runbook (before/after audit で traversal_hit 上昇を確認) |
| ボールドリック のカナ→原名 (Bold Ruckus) 同定に不確実性 (prediction-logic) | コメントに「原名 BLOD で要確認・Bold Ruler 系なら line は安全」を明記 |

テスト: **278 passed / 3 skipped**。

## 結論 — ユーザ向けの正直な整理

- **「その他」56.5% の主因は BLOD(繁殖馬)未取込で traversal_hit=0.0%**。辞書の個別追加では
  long-tail に届かない (有名種牡馬は既に収載済と判明済)。
- **恒久解決の手順** (OPERATION.md §9-4):
  1. `probe_hn_offsets` で HN の sire_breeding_num offset(230) を確定 (ずれていれば parser 修正)。
  2. `python -m scripts.bootstrap --dataspecs BLOD` で繁殖馬マスタを一括取込。
  3. `python -m scripts.audit_sire_lines --top 40` を再実行し traversal_hit の上昇・unknown 低下を確認。
- 深祖 founder (Nasrullah/Man o'War 等) は JRA-VAN 繁殖馬マスタに個別行が無いのが通例なので、
  辞書 (FOUNDERS) 併用は恒久的に必要 (辞書=深祖終端、BLOD=中間 chain 充填で役割分担)。
- 今回辞書追加した 20 数件と、真に少数派の系統 (Dictus/Man o'War/Monsun/Teddy 枝等=正しい「その他」)
  を除けば、上記 BLOD 取込で unknown は大幅に下がる見込み。

## ユーザ実機の残作業 (次回・最優先)
1. **HN offset 確定 → BLOD 一括取込 → 再audit** (OPERATION.md §9-4 の閉ループ)。これで
   traversal が復活し「その他」「系統国なし」が構造的に解消する見込み。
2. 亀谷公式リスト突合で国系統 (Grey Sovereign 枝 eur 等) を確定 (§10)。
