---
name: codex-token-economy
description: OpenAI Codex CLI (codex コマンド) のトークン消費を抑えるためのスキル。「codex のトークンが多い」「codex の料金が高い」「codex を効率よく使いたい」「codex のコンテキストが膨らむ」「gpt-5-codex / model_reasoning_effort をどうするか」「AGENTS.md / .codex/config.toml をどう書くか」「/compact / /model」のような Codex CLI の利用時に使う。Claude Code の利用に対する `token-economy` スキルとは別物で、こちらは外部ツール `codex` を呼ぶときの省トークン運用ルール集。Codex は毎ターン履歴 + AGENTS.md + ファイルツリーを再送するので、「session を切る」「reasoning effort を下げる」「スコープを狭める」だけで体感的に倍以上節約できる。
---

# Codex CLI トークン節約スキル

## 何のためのスキル？

OpenAI Codex CLI (`codex` コマンド、`gpt-5-codex` 系) を使うときに発生する無駄なトークン消費を抑える。Codex CLI は **毎ターン (= 毎メッセージ)、それまでの会話履歴 + `AGENTS.md` + 走査したファイル一覧を全部送り直す** ので、長いセッションほどコストが指数的に増える。

このスキルが扱うのは「ユーザが自分で `codex` を起動する場面」。Claude Code (= 私) のトークンは別スキル `token-economy` で管理しているので、こちらは Codex CLI 固有の節約手段に集中する。

## 真っ先に効く 4 つの対策

### 1. **session を切る** (これが一番効く)

Codex は 1 セッション内で履歴をすべて再送する。10 ターン目には 1 ターン目の自分の発言と Codex の長い思考も全部一緒に送られている。**話題が切り替わったら新しい session を開く**。

```
NG: 1 つの session で「特徴量追加 → バックテスト → GUI 修正 → README 直し」を全部やる
OK: 各タスクで一旦 codex を抜けて (Ctrl-D)、別セッションで開き直す
```

長いセッションを継続する必要がある場合は **`/compact`** で履歴を要約に置き換える。Codex はこれを内蔵している。

```
codex> /compact
```

5〜10 ターンに 1 回は `/compact` を意識する。逆に 2〜3 ターンで終わる質問なら新セッションで十分。

### 2. **reasoning effort を下げる**

`gpt-5-codex` は推論用の thinking トークンを大量に出す。デフォルトの `medium` 以上だと、回答 1 件に数千トークンの思考が乗る。**作業内容に対して reasoning effort を調節する**。

```
codex> /model
# → minimal / low / medium / high の中から選ぶ
```

| 作業の質 | 推奨 effort |
|---|---|
| 既知の文字列置換、import 追加、型ヒント補完 | `minimal` |
| 1 ファイル内のリファクタ、関数追加 | `low` |
| 複数ファイルにまたがる仕様変更、バグ調査 | `medium` (デフォルト) |
| 設計レベルの相談、アルゴリズム選定 | `high` |

または `~/.codex/config.toml` で恒常的に下げる:
```toml
model = "gpt-5-codex"
model_reasoning_effort = "low"
```

毎日のコーディングは `low` で困らないことが多い。`medium` 以上は「これは考えてもらう価値がある」と判断したときだけ。

### 3. **reasoning summary を切る / 圧縮する**

Codex は思考の要約を表示するために `reasoning_summary` を別途生成する。表示が嬉しいだけで作業には不要なら切れる。

```toml
# ~/.codex/config.toml
model_reasoning_summary = "none"   # auto / concise / detailed / none
```

`none` にすると画面はそっけなくなるが、出力トークンが目に見えて減る。「動いてる感」が欲しいときだけ `concise` に戻す。

### 4. **スコープを狭めて起動する**

Codex はカレントディレクトリ配下を走査する。プロジェクトルートで起動すると、関係ないファイルツリーまで毎ターン送られる。**触る予定のフォルダで起動するか、`--cd` で限定する**。

```
NG: cd C:\Users\kizun\dev\keiba-yosou && codex
    # → predictor も gui も jvlink_client も scripts も全部スコープに入る

OK: cd C:\Users\kizun\dev\keiba-yosou\predictor && codex
    # → predictor 配下だけがツリーに乗る

OK: codex --cd C:\Users\kizun\dev\keiba-yosou\predictor
```

特に `data/raw/` を含むフォルダで起動しないこと。`.gitignore` で `data/` は除外されているのでツリーには出ないが、誤って `cd data/raw && codex` した場合は数千ファイルが走査対象になる。

## このプロジェクトで踏みやすい地雷

| 地雷 | 何が起きる | 回避 |
|---|---|---|
| プロジェクト直下で `codex` 起動 | predictor / gui / jvlink_client / scripts / web 全部がスコープ | サブフォルダで起動 or `--cd` |
| `codex` に `data/keiba.db` を read させる | 288MB バイナリを読もうとして即死 | `sqlite3 data/keiba.db "..."` の結果だけを Codex に渡す |
| `codex` に `docs/JV-Data4901.pdf` を読ませる | 100+ ページの PDF が context に乗る | `docs/extracted/JV-Data4901_p<NNN>.txt` 抽出済テキストを渡す |
| `data/raw/*.jvd` をパースさせる | バイナリ生 dump がコンテキストを爆破 | `python -m scripts.probe_record <file>` の出力だけ渡す |
| 出馬表/オッズの巨大 JSON を貼る | 1 レース 1KB × 36 レース = 数十 KB をコピペ | DB から特定レースだけ SELECT して渡す |
| 1 つの session で複数タスクをまたぐ | 履歴が肥大化する | タスクごとに新 session、または `/compact` |
| reasoning_effort = high のまま放置 | 思考トークンが本回答の数倍 | 普段は `low`、相談だけ `medium` |

## AGENTS.md の設計ルール

`AGENTS.md` (プロジェクト直下、または `~/.codex/AGENTS.md`) は **毎ターン全文が送られる**。長く書くほど全ターンで損をする。

このプロジェクトには現状 `AGENTS.md` が無い (= 0 トークン) ので、作るときは次を守る:

- **150 行以内** に収める。常に必要な情報だけ。
- **個別タスクの背景や履歴を書かない**。それは session ローカルで言えばいい。
- **既知の地雷だけ書く**: 「`data/keiba.db` は 288MB バイナリ、直接読まないこと」など。
- **コマンドはコピペで動く形** で書く。
- **コードスニペットは最小限**。本物のコードは Codex がファイルから読める。

NG 例 (冗長):
```
# プロジェクトの歴史
このプロジェクトは 2026 年初頭にスタートし...
```

OK 例 (実用):
```
# 環境
- Python 3.11 (32-bit、JV-Link COM の制約)
- DB: data/keiba.db (288MB、直接 Read 禁止)
- 仕様: docs/extracted/JV-Data4901_p<NNN>.txt を参照、PDF 直読み禁止
```

## ~/.codex/config.toml の推奨設定

`%USERPROFILE%\.codex\config.toml` (Windows) に下記を入れておくとデフォルトで節約モードになる:

```toml
model = "gpt-5-codex"
model_reasoning_effort = "low"
model_reasoning_summary = "concise"

# 不要なツールは切る (使うときだけ /tools で有効化)
[tools]
web_search = false

# プロジェクトのルートを跨いだ書込みを禁止 = 安全 + 余計な探索を抑える
[sandbox_workspace_write]
network_access = false
```

`web_search` をデフォルト OFF にすると、Codex がツール呼び出しで Web を漁って大量のページを読み込む事故を防げる。本当に必要なときだけ session 内で `/tools enable web_search` (または相当) で有効化する。

## ファイルを「読ませる」のではなく「貼る」

Codex に「○○ ファイルを読んで」と頼むと、Codex は read_file ツールを使ってファイル全体を context に入れる。**狙った行範囲だけ自分で先に切り出して渡した方が圧倒的に安い**。

```
NG (codex に読ませる):
  「predictor/rules.py を読んで _score_one を改善して」
  → Codex が rules.py 全 700 行を context に入れる

OK (必要箇所だけ渡す):
  $ sed -n '52,250p' predictor/rules.py | clip
  codex> [貼り付け] この関数で同距離適性の重みを 4 → 6 にして
```

特に重い: `predictor/rules.py` (700 行)、`gui/app.py` (1200 行)、`web/generator.py`、`predictor/features.py` (800 行)。これらを「読んで」と頼むと毎回大量のトークンを消費する。**該当関数だけを切り出すか、関数名で行範囲を指定**する。

## Codex に頼まずに済むタスクは頼まない

Codex (gpt-5-codex high) は 1 ターンで簡単に数千〜数万トークン使う。次は Codex を使わない:

| タスク | やり方 |
|---|---|
| 文字列置換、ファイル名変更 | エディタ or `sed` |
| 大量ファイルの grep | `grep -rn` |
| 既知のコマンドの実行 | 自分で打つ (codex に「○○して」と頼まない) |
| ライブラリのドキュメント参照 | `pydoc` / 公式 web を直接見る |
| 軽い質問 (「この関数の戻り値は?」) | エディタの hover or Read で十分 |

「Codex を起動するコスト > 自分で 30 秒考えるコスト」なら、自分でやる方が安い。

## 出力を切り上げさせる

Codex は丁寧に長文で説明しがち。指示で短くさせる:

```
codex> 修正だけして、説明文は最小限で。差分は出さないで実ファイルに書いて。
```

「説明より差分」「差分より実適用」「結果と次手順だけ」を明示する。

## チェックリスト: codex を起動する前に

1. [ ] このタスク、Codex 必要? (簡単な置換は自分で)
2. [ ] 起動するフォルダは絞れている? (ルートじゃなくサブフォルダ)
3. [ ] `model_reasoning_effort` は low or minimal?
4. [ ] 前のセッションを引きずってない? (新規 session or `/compact`)
5. [ ] 渡すファイルは行範囲で絞れる? (全文を読ませない)
6. [ ] 巨大バイナリ・PDF・DB を「読んで」と頼んでない?
7. [ ] 出力に「説明は最小限で」を添えた?
8. [ ] 終わったら Ctrl-D で session を閉じている?

## チェックリスト: 長い session の途中で

1. [ ] `/compact` を最後にしたのは何ターン前? (5-10 ターンが目安)
2. [ ] reasoning_effort を下げる余地は? (探索が終わったらもう low で十分)
3. [ ] このタスクは別 session に分けた方がいい? (テーマが変わってきたら)
4. [ ] context 表示 (`/context` 等) でトークン残量を確認した?
