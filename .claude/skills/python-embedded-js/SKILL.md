---
name: python-embedded-js
description: Python の triple-quoted 文字列 (`"""..."""`) に JS / HTML / CSS を埋め込んでいるコード (`gui/app.py` の `CONTROL_HTML` / `PREVIEW_HTML` など) を編集するときに必ず使う。「ボタンが動作しない」「イベントが発火しない」「予想生成ボタンを押しても何も起こらない」「クリックが反応しない」「`run is not defined`」のような症状はこのスキルが対象とするバグ (JS シンタックスエラーで全関数が未定義) の典型。改修後の検証コマンド (Python が解釈した後の JS を取り出して `node --check` する手順) を持っているので、コミット前に必ず通せば再発を防げる。
---

# Python に埋め込んだ JS/HTML を壊さないためのスキル

## 何のためのスキル？

このプロジェクトの GUI は `gui/app.py` の中で **Python の三重引用符文字列に JS と HTML を丸ごと書く** 方式を採っている (`CONTROL_HTML`, `PREVIEW_HTML`)。この構造は便利だが、**Python のエスケープ解釈と JS のエスケープ解釈が衝突する** 致命的な落とし穴がある。

過去 4 回以上「ボタンを押しても何も起きない」症状で同じバグに当たっているので、**編集 → 検証 → コミットの 3 ステップを自動化する**ためのスキルにした。

## 典型バグ: 「予想生成ボタンが動作しなくなった」

### 症状

- GUI のボタンを押しても何も起こらない
- `onclick` が発火していないように見える
- ブラウザコンソール (pywebview) を開ければ `Uncaught SyntaxError: Invalid or unexpected token` か `ReferenceError: run is not defined` が見える (が pywebview だと普通は見えない)
- 直前に `gui/app.py` を編集している (codex / Claude / 手動問わず)

### 真因

```python
CONTROL_HTML = """<!doctype html>
...
<script>
  var s = 'foo'.split('\n');     # ← この \n が罠!
</script>
...
"""
```

Python の **通常の** 三重引用符文字列 (`"""..."""`) は `\n` を **本物の改行** に展開する。つまりランタイムの `CONTROL_HTML` の中身は:

```
  var s = 'foo'.split('
');
```

JS シングルクォート文字列の中に**生改行** が混入 → `SyntaxError: Invalid or unexpected token` でスクリプト全体がパースされない → `run` などすべての関数が未定義 → `<button onclick="run(...)">` が発火せず黙って沈黙、というオチ。

### 同じ罠を踏むエスケープシーケンス

Python が triple-quoted 文字列内で勝手に解釈するもの (順に踏みやすさ):

| 書き方 | Python の解釈 | JS 側に届くもの | 期待 |
|---|---|---|---|
| `'\n'` | LF (`0x0A`) | 生改行 | JS の `\n` (改行エスケープ) |
| `'\t'` | TAB (`0x09`) | 生 TAB | JS の `\t` |
| `'\\'` | `\` (1 文字) | `\` (正常) | これは OK |
| `'\''` | `'` (1 文字) | `'` (正常) | これは OK |
| `'\"'` | `"` | `"` | OK だが冗長 |
| `'\b' '\f' '\r' '\v' '\a'` | 制御文字 | 生制御文字 | JS のエスケープ |
| `'\xNN' '\uNNNN'` | バイト/Unicode | 解釈済み文字 | (ケースバイケース) |

## 修正パターン

### パターン A (推奨): JS で必要な escape は `\\` でエスケープ

```python
# BAD
js = """
  var summary = parts.join('\n');
  setDetails(text + '\n\n' + json, true);
"""

# GOOD
js = """
  var summary = parts.join('\\n');
  setDetails(text + '\\n\\n' + json, true);
"""
```

Python が `\\n` を `\n` に変換し、JS には `\n` (改行エスケープ) が届く。

### パターン B: テンプレ全体を raw string にする

```python
# CONTROL_HTML 全体を r"""..."""  に
CONTROL_HTML = r"""<!doctype html>
...
<script>
  var s = 'foo'.split('\n');   ← そのまま JS 側で \n エスケープになる
</script>
"""
```

ただし **Python 側で format / `.replace("__X__", val)` を使う場合、引数の中身に意図せぬ `\` が混じると混乱する** ので、現行コードのように **default の triple-quoted + 個別エスケープ** のほうが安全。

### パターン C: テンプレ外部化 (大幅リファクタ)

`gui/templates/control.html` のような独立ファイルにして `read_text()` する。Python のエスケープ解釈を完全に回避できるが、変更範囲が大きい。

## 編集後の必須検証コマンド (これだけは絶対やる)

### ワンライナー: モジュールをインポート → CONTROL_HTML から script を抽出 → node でパース

```bash
.venv32/Scripts/python.exe -c "
import sys, os, tempfile, re, importlib
sys.path.insert(0, '.')
import gui.app
importlib.reload(gui.app)
m = re.search(r'<script>(.*?)</script>', gui.app.CONTROL_HTML, re.DOTALL)
js = m.group(1)
p = os.path.join(tempfile.gettempdir(), 'check.js')
open(p, 'w', encoding='utf-8').write(js)
print('JS bytes:', len(js))
" && node --check "C:\Users\kizun\AppData\Local\Temp\check.js" && echo "JS OK"
```

ポイント:
- **`open().read()` でなく `import gui.app`** で「Python が解釈した後の」CONTROL_HTML を見るのが重要。`re` で regex マッチすると Python のエスケープ解釈前の内容を見ることになり、バグを見逃す
- `node --check` で構文だけ判定 (実行はしない)
- 通れば `JS OK` が出る。通らなければ行番号付きで `SyntaxError` が出る

### `PREVIEW_HTML` も含めて全部チェック

> 注: 2026-06-12 のタブ化改修で `PREVIEW_HTML` は削除済み (プレビューは
> CONTROL_HTML 内 iframe に統合)。下のループは `getattr(..., '')` なので
> 欠落していてもそのまま動く。現存するのは `CONTROL_HTML` のみ。

```bash
.venv32/Scripts/python.exe -c "
import sys, os, tempfile, re, importlib
sys.path.insert(0, '.')
import gui.app
importlib.reload(gui.app)
all_ok = True
for name in ('CONTROL_HTML', 'PREVIEW_HTML'):
    html = getattr(gui.app, name, '')
    for i, m in enumerate(re.finditer(r'<script>(.*?)</script>', html, re.DOTALL)):
        js = m.group(1)
        p = os.path.join(tempfile.gettempdir(), f'check_{name}_{i}.js')
        open(p, 'w', encoding='utf-8').write(js)
        print(name, i, 'bytes:', len(js))
"
# その後それぞれを node --check
for f in /tmp/check_*.js; do node --check "$f" || echo "FAIL: $f"; done
```

## 編集ワークフロー (このスキルが提唱する手順)

1. **編集前**: 既存の CONTROL_HTML / PREVIEW_HTML が壊れていないか上記コマンドで確認 (壊れた状態を出発点にしないため)
2. **編集**: JS / HTML / CSS を変更
3. **編集後 必須**: 上記検証コマンドを実行。`JS OK` を確認
4. **新規 escape を追加した場合**: その escape が `\\n` のように **ダブルバックスラッシュ** になっているか目視確認
5. **コミット**: 検証通過後のみ

`Edit` ツールで `\n` を `\\n` に直しても、`Read` した内容を貼り付けるときに ツール側でまた解釈され直す事故もあるので、**必ず最後に `node --check` まで行う**。

## このプロジェクトでの実例 (2026-05-09 時点で 4 回目の被弾)

過去のバグ事例:

```python
# 例 1: setDetails (今回の被弾)
var summary = parts.join('\n');                ← BAD
var summary = parts.join('\\n');               ← GOOD

# 例 2: HTML の onclick attribute 内の JS escape
'onclick="setBacktestRange(\'' + v + '\')"'      ← Python で \' = ' なので JS では setBacktestRange('3') にしかならない
'onclick="setBacktestRange(\\'' + v + '\\')"'    ← Python で \\' = \' なので JS でも \' (= 文字列内のシングル)
```

## トラブルシュート

### `node --check` が `Cannot find module '...check.js'`
- Windows + WSL/Git Bash で `/tmp/` パスが解釈されない。`tempfile.gettempdir()` を使うか `C:\Users\...\AppData\Local\Temp\check.js` で直接指定

### 検証が通っているのに動かない
- `CONTROL_HTML` 以外の何かが破綻している (Python 例外で `Api.get_status` が raise しているなど)。`gui.app` を import してインスタンス化までできるか確認:
  ```python
  python -c "import sys; sys.path.insert(0, '.'); import gui.app; api = gui.app.Api(); print(dir(api))"
  ```

### `<button onclick>` の `data-action` が disabled でない
- run() の `inFlight` フラグが永続 true になっている可能性。`Api._status` の `running` フラグもチェック。一度アプリを再起動してリセット。

## 関連スキル

- 編集後に **動作確認まで自動化する** には外部 process で run.bat を起動すれば良いが、JV-Link COM が絡むため通常は手動確認。せめて構文チェックだけは絶対に通す
