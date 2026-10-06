---
name: obsidian-vault
description: keiba-yosou の過去の知見 (研究の結論・撤回・データの罠・検証手法・競馬の一般知識) を Obsidian 保管庫から最小のコンテキストで引き、作業の結論を書き戻すスキル。「前に何を試した」「この仮説は検証済みか」「この列・レコードの罠は」「なぜ勝てないのか」「どの手法で判定した」など過去の経緯や知識が要るとき、docs/ やメモリの大きなファイルを読む前に必ず使う。検証の結論が出た・撤回した・データの罠を見つけたとき (作業の最後) にも使う。
---

# Obsidian 保管庫 (競馬)

保管庫: `C:\Users\kizun\Documents\Obsidian Vault\競馬\` (git の外。Obsidian Sync の対象になり得るので秘密情報は書かない)

| フォルダ | 中身 |
|---|---|
| `00 索引` | `競馬 索引` (地図)、`研究年表`、`ノートの書き方` (約束とノート名の台帳) |
| `01 一般知識` | 馬券・控除率・オッズ・コース・馬場・脚質・血統・先行研究 |
| `02 データ仕様` | JV-Link / JV-Data / keiba.db / 確定オッズと発走前オッズ / 既知の欠陥 |
| `03 検証手法` | 条件付きロジット・2 段結合・事前登録・検出力・PIT・変異テスト |
| `04 研究成果` | 1 仮説 1 ノート。frontmatter に `状態` (確定/暫定/撤回/進行中) と `日付` |
| `05 教訓` | 事故から得た作業の規律 |

## 引き方 (上の段で足りたら止める)

1. **要点を引く** — 本文を開かずに、名前・タグ・要点 (3 行) だけを返す:
   ```bash
   python .claude/skills/obsidian-vault/vault_lookup.py <語> [<語> ...]   # 全語を含むもの
   python .claude/skills/obsidian-vault/vault_lookup.py --body <語>       # 本文も探し、該当行を 3 行まで
   python .claude/skills/obsidian-vault/vault_lookup.py --status 撤回      # 状態で絞る
   python .claude/skills/obsidian-vault/vault_lookup.py --list            # ノート名の一覧 (約 3KB)
   ```
2. **ノート本文を読む** — 要点で足りないノートだけ `Read` (1 本 40〜180 行)。
3. **原典を読む** — ノートの frontmatter `出典` にある docs / メモリ / コミットを、必要な節だけ `Grep` で。docs には 60〜96KB の文書がある (PHASE05_5_PREREG.md など) ので丸読みしない。

`00 索引/競馬 索引.md` (約 5KB) は全体の地図が要るときだけ読む。

注意: ノートは 2026-10-06 に docs とメモリから作った要約。**数字を判断や主張に使うときは出典で確かめる** (ノートの誤りは 1 件見つかって直した前例あり)。ノートと原典が食い違ったら原典が正で、ノートを直す。

## 書き戻し (作業の最後)

次のどれかが起きたら、セッションを閉じる前に保管庫を更新する:

| 起きたこと | 更新先 |
|---|---|
| 検証の結論が出た | `04 研究成果` に新規ノート (または既存を更新) + `研究年表` に 1 行 + 台帳に名前 |
| 結論を撤回・修正した | 該当ノートを消さずに `状態: 撤回` と撤回理由。参照している他ノートの数字にも注記 (`vault_lookup.py --body <数字>` で探す) |
| データの罠を見つけた | `02 データ仕様/データ品質の既知の欠陥` か該当レコードのノートに `> [!warning]` |
| 事故・やり直しから規律を得た | `05 教訓` |
| 今の結論が変わった | `04 研究成果/市場に勝てるかの現状結論` と `研究の全体像` |

書式は `00 索引/ノートの書き方.md` に従う (frontmatter・`> [!summary] 要点` 3 行以内・`## 関連`)。要点は `vault_lookup.py` が返す唯一の中身なので、**それだけ読めば結論と数字と期間が分かる** ように書く。リンク `[[...]]` は台帳にある名前だけ。数字は出典から写し、出典を frontmatter に書く。

書いた後のリンク切れの検査:
```bash
python .claude/skills/obsidian-vault/vault_lookup.py --list > /dev/null && python - <<'EOF'
import re, pathlib, sys
sys.stdout.reconfigure(encoding="utf-8")
root = pathlib.Path(r"C:\Users\kizun\Documents\Obsidian Vault\競馬")
names = {p.stem for p in root.rglob("*.md")}
for p in root.rglob("*.md"):
    body = re.sub(r"```.*?```|`[^`]*`", "", p.read_text(encoding="utf-8"), flags=re.S)
    for t in re.findall(r"\[\[([^\]|#]+)", body):
        if t.strip() not in names:
            print(f"{p.stem} -> [[{t}]]")
EOF
```

## メモリとの分担

- メモリ (`MEMORY.md`) は毎セッション自動で読まれるので、研究結果の行は **名前と保管庫ノートへの案内だけ** にする。詳細は保管庫が正本。
- 作業の規律 (feedback 系) はメモリに残す (事故防止のため常に見えている必要がある)。保管庫の `05 教訓` は経緯の詳しい版。
