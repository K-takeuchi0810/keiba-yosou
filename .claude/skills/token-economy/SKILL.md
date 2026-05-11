---
name: token-economy
description: Claude のトークン消費を抑えるためのスキル。「トークン消費が多い」「コンテキスト節約して」「ファイル読みすぎ」「効率よく作業して」のような明示的要求はもちろん、それ以外でも全コーディング作業で「常に裏で意識すべき」運用ルール集として使う。大きいファイル・PDF・生成物・バイナリを不用意に読むと無駄が大量発生するので、このプロジェクトの罠 (`data/keiba.db` 288MB, `docs/JV-Data4901.pdf` 100+ ページ, `data/raw/*.jvd` バイナリ等) を踏まないよう常に意識する。
---

# トークン節約スキル

## 何のためのスキル？

Claude のコンテキストウィンドウとコストを節約する。読み方・検索の仕方・出力の出し方を「最初から効率的な手段で」やる癖をつけるためのチェックリスト。

このスキルはユーザが明示的に呼ばなくても **常に裏で適用** すること。Claude Code はトークンに対して支払いが発生するので、無駄な消費はそのままユーザの損失。

## 7 つの基本原則

### 1. **検索してから読む** (Grep > Read)

ファイル全体を読まないと分からない情報は実は少ない。シンボル・キーワードがあるなら先に Grep。

```
NG: Read(file_path="predictor/rules.py")  # 全部読んで関数を探す
OK: Grep(pattern="def predict_race", glob="predictor/*.py")
```

Grep の `output_mode="content"` + `-C 5` で必要な前後だけ取れる。

### 2. **狭く読む** (offset / limit / pages)

ファイルが 200 行を超えたら、関連箇所だけ読む。

```
NG: Read(file_path="predictor/rules.py")  # 200 行全部
OK: Read(file_path="predictor/rules.py", offset=140, limit=40)
```

PDF はページ指定:
```
NG: Read("docs/JV-Data4901.pdf")  # 100+ ページ → エラー or 巨大消費
OK: Read("docs/JV-Data4901.pdf", pages="13")  # 1 ページだけ
OK: Read("docs/extracted/JV-Data4901_p013.txt")  # さらに軽い (テキスト抽出済み)
```

### 3. **編集には Edit を使う** (Edit > Write)

Edit は差分だけを送るので極めて軽量。Write はファイル全体を再送する。

```
NG: 既存 200 行ファイルを 1 行直すために Write(content=<200 行全体>)
OK: Edit(old_string="...", new_string="...")
```

新規ファイル作成・全面書き換えのときだけ Write。

### 4. **再読み込みしない**

一度読んだファイルは要点をメモして、次は読み直さず参照する。同じ Grep を 2 度しない。

```
NG: 30 ターン後にまた Read(file_path="config.py")
OK: 「config.py の DATA_DIR は data/、JVLINK_SID は環境変数」と覚えておく
```

### 5. **生成物・バイナリ・巨大ファイルは絶対に読まない**

このプロジェクトで踏みやすい地雷:

| パス | 理由 | 代替 |
|---|---|---|
| `data/keiba.db` | SQLite バイナリ 288MB | `sqlite3` で SELECT |
| `data/raw/*/*.jvd` | バイナリ JV-Data | `scripts/probe_record.py` |
| `docs/JV-Data4901.pdf` 全頁 | 100+ ページ | `pages=` 指定 or `docs/extracted/*.txt` |
| `web/dist/index.html` | 生成済 HTML、レース多数で巨大化 | `web/templates/index.html.j2` (テンプレ側) |
| `.venv32/`, `__pycache__/` | 大量の依存物 | 開かない |
| 大きいログ・データダンプ | 全文読み込み = 即死 | `head` `tail` `Grep` |

`Glob` でも `**` 配下を取り込むときは `data/`, `.venv32/`, `__pycache__/` を含まないようにパターンを切る。

### 6. **直接ツールを優先、subagent は適材適所**

Subagent は **広域探索を並列化** したい時、または **大量出力を主コンテキストから隔離** したい時に使う。それ以外は直接ツールの方が安い。

| やりたいこと | 推奨 |
|---|---|
| 既知の関数定義を読む | Read |
| 既知のシンボルを探す | Grep |
| 「どこに何があるか」を広く探索 | Agent (Explore) |
| 大量のテストを並列実行 | Agent (parallel) |
| 1 ファイルの軽い編集 | 自分で Edit |

「軽い質問に Agent を投げる」は数倍の浪費。

### 7. **応答を短く保つ**

ユーザに見せるテキストは「結果と次の一手」だけで十分。やったことを長々と説明しない。

```
NG: 「まず ○○ ファイルを開いて、その中で ×× を探して、次に △△ を…(中略)…これで完了です」
OK: 「parser.py:230 に parse_hr を追加。動作確認は次のメッセージで。」
```

## このプロジェクト特有のショートカット

### JV-Data 仕様書を引きたい
- まず [.claude/skills/jvdata-record/references/spec-locations.md](../jvdata-record/references/spec-locations.md) でページ番号を引く
- 該当ページの `docs/extracted/JV-Data4901_p<NNN>.txt` を読む (PDF より軽い)
- それで足りないときだけ `docs/JV-Data4901.pdf` を `pages=` 指定

### JV-Link API のリターンコード
- [.claude/skills/jvlink-com/references/return-codes.md](../jvlink-com/references/return-codes.md) を見る (PDF を漁らない)

### dataspec の組み合わせ確認
- [.claude/skills/jvlink-com/references/dataspecs.md](../jvlink-com/references/dataspecs.md)

### DB の中身を見る
- `data/keiba.db` を直接 Read しない
- `python -c "import sqlite3; ..."` か `Bash` で `sqlite3 data/keiba.db ".schema"` 等

### raw ファイルを見る
- バイナリの `.jvd` を Read しない
- `python -m scripts.probe_record data/raw/RACE/<file>.jvd` で先頭バイトと長さを確認

## TodoWrite と Plan の使いどころ

軽い作業 (1-3 ステップで終わる) では `TodoWrite` も `Plan` も使わない。それ自体がトークンを食う。

使う基準:
- **TodoWrite**: 6 ステップ以上の連続作業、または並行ストリームの管理が必要なとき
- **Plan / ExitPlanMode**: ユーザが「実装前に確認したい」と明示したとき

「念のため」で使うのは無駄。

## 並列化のコツ

独立したツール呼び出しは **同じメッセージ内で並列発行** する。逐次に出すとラウンドトリップだけで損。

```
NG (逐次): 
  ターン 1: Read file A
  ターン 2: Read file B
  ターン 3: Read file C
OK (並列): 
  ターン 1: Read A, Read B, Read C を 1 メッセージで
```

ただし「A の結果を見ないと B の引数が決まらない」場合は順次でいい。**依存があるかどうかを判断してから**。

## ToolSearch の使い方

deferred tools (`AskUserQuestion`, `WebFetch`, `mcp__*` 等) は最初は schema が読み込まれていない。本当に使うときだけ `ToolSearch` で 1〜数個を取り込む。

```
NG: 念のため WebSearch / WebFetch / TodoWrite を全部先に load
OK: 必要になった瞬間に select:<name> で 1 個だけ load
```

## サマリ: コードを書く前のチェックリスト

1. [ ] そのファイル、本当に全部読む必要ある? → 行範囲指定できないか
2. [ ] そのファイル、生成物 / バイナリ / 巨大じゃない? → 別の見方ない?
3. [ ] その編集、Edit で済む? → Write を選ばない
4. [ ] その情報、前のターンで既に得てない? → 覚えているなら再取得しない
5. [ ] その探索、既知の参照ファイルで済む? → スキルの references を先に見る
6. [ ] そのツール呼び出し、並列にできる? → 1 メッセージにまとめる
7. [ ] その応答、もっと短くできる? → 結果と次手順だけに絞る
