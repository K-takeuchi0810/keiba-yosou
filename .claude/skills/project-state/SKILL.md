---
name: project-state
description: keiba-yosou プロジェクトの **現状スナップショット**。新セッション開始時に最初に読み、過去 7 改修で何が成された / 何が未着手 / 数値で「実際どこまで進んだか」を一発で把握するためのもの。「現状を教えて」「どこまで進んだ」「次は何やる」のような質問にも対応。具体的な数値 (回収率 89%, baseline 比 +1.03 等) と最新 scorecard へのリンクを持つので、それを起点に新セッションの改修計画を立てられる。
---

# keiba-yosou プロジェクト 現状スナップショット

## 1 行サマリ

JRA-VAN JV-Link を使うローカル競馬予想 GUI。直近 walk-forward 検証で **「重賞+中山+京都+1-4 人気+信頼度判定」フィルタが 4 ヶ月 105 戦 / 回収率 89%** (控除率 80% を +9pt 超え、ただし +100% 未達) を達成。実弾投入の現実線が見えている段階。

## スコア推移 (7 改修分、`data/scorecards/` 詳細あり)

| | baseline | P0-1 | P0-2 | P1-3 | P0-3 | P1-1 | P2-1 | **a+e** |
|---|---|---|---|---|---|---|---|---|
| **全体平均** | 3.06 | 3.14 | 3.30 | 3.41 | 3.59 | 3.77 | 3.99 | **4.09** |
| GUI / UX 監査 | 3.2 | 3.2 | 3.3 | 3.3 | 3.2 | 3.2 | 3.6 | 3.6 |
| モバイル HTML | 3.4 | 3.4 | 3.4 | 3.4 | 3.4 | 3.4 | 4.4 | 4.4 |
| 予想ロジック | 3.4 | 3.4 | 3.6 | 3.6 | 3.6 | 4.2 | 4.2 | 4.2 |
| **収益性** | 1.8 | 2.0 | 2.4 | 2.0 | 3.0 | 3.0 | 3.0 | **3.4** |
| データパイプライン | 3.8 | 3.8 | 3.8 | 4.0 | 4.0 | 4.0 | 4.0 | 4.0 |
| コード品質 | 2.6 | 2.8 | 3.0 | 3.4 | 3.5 | 4.0 | 4.1 | 4.2 |
| **検証プロセス** | 3.2 | 3.4 | 3.6 | 4.2 | 4.4 | 4.6 | 4.6 | **4.8** |

baseline 比 **+1.03**。3 名 (収益性除く) が 4.0 超え。

## 完了した改修 (時系列)

| 改修 | 内容 | scorecard |
|---|---|---|
| P0-1 | buy_filter を `config.BUY_FILTER_DEFAULT` に一元化 | `20260510_2300_p01_buy_filter_unified.md` |
| P0-2 | calibrator の少数 bin 恒等寄せ (min_count 20→50) | `20260510_2310_p02_calibrator_minbin.md` |
| P1-3 | `except: pass` 9 箇所を logger.warning に + print→logger | `20260510_2330_p13_logging.md` |
| P0-3 | 重賞ホワイトリストモード (`whitelist_grades / tracks`) | `20260510_2355_p03_whitelist.md` |
| P1-1 | dead feature 5 削除 + 直書き 60→1 + weights.json 12 namespace | `20260511_0030_p11_refactor.md` |
| P2-1 | モバイル CSS 変数化 + `<details>` インジケータ + theme-color | `20260511_0100_p21_mobile.md` |
| a+e | walk-forward 検証 + sweep + filter 更新 | `20260511_2345_ae_walkforward_sweep_review.md` |

## 現在の運用フィルタ (= `config.BUY_FILTER_DEFAULT`)

```python
BUY_FILTER_DEFAULT = {
    "min_ev": None,          # 制約なし (calibrator 不安定のため EV 依存解除)
    "min_value": None,
    "min_odds": 1.0,         # 実質無効化
    "max_odds": 100.0,       # 実質無効化
    "min_popularity": 1,     # ★主絞り条件: 1-4 人気
    "max_popularity": 4,
    "exclude_confidence": ["暫定", "混戦", "接戦"],
    "max_odds_age_min": 30,
    "whitelist_mode": True,
    "whitelist_grades": ["A", "B", "C", "F"],  # G1/G2/G3/重賞
    "whitelist_tracks": ["07", "09"],           # 中山 / 京都
}
```

**現実の数値** (`data/backtest/20260511_234351_tan_p04-final-eval-v3-filtered.json`):
- EVAL (2026/01-04): buy_only **105 戦 / 34.3% / 89.0%** / 収支 -1,150 円
- DESIGN (2025/06-12): sweep 値 166 戦 / 86.3% (再現性確認済)

## 直近の重要な指摘 (= 次の改修候補、優先順)

### 🔴 即対処すべき軽微回帰
1. ~~**backtest 出力に calibration メタを復元**~~ ✅ **解決済み (2026-05-12 確認)**
   - 全 p04 backtest で `count=16550 / brier=0.057508 / bins=20` 確認済。`scripts/backtest.py:351` で `calibration_report()` を正常に出力中。リスト上の指摘は古い。
2. ~~**filter_sweep.py の WHITELIST_GRADES/TRACKS を config 参照に**~~ ✅ **解決済み (2026-05-12)**
   - `scripts/filter_sweep.py:18-22` で `from config import BUY_FILTER_DEFAULT` → `frozenset(BUY_FILTER_DEFAULT["whitelist_grades"|"whitelist_tracks"])` 経由に変更済。

### 🟠 高インパクト未着手
3. **`wl_odds_8_20` 路線で +100% 超え探索** (収益性)
   - sweep で両期間 100%+ (74戦/103%, 41戦/116%) と既に検出済
   - 戦数少なめなのでハイブリッド (wl + 信頼度除外 + odds 8-20) も検討
4. **データパイプライン 3 件** (7 連続持ち越し!): mtime / JVStatus timeout / DB PRAGMA
5. **`_score_one` 関数分割** (予想ロジック)
   - 508 行肥大、namespace 化済なので機械的分割可
   - 項目「デッドコード / 整合性」が 4.5 → 5 で総合 4.4-4.5 射程

### 🟡 GUI / UX 改善
6. **GUI dashboard で人気帯 input を露出**
   - 現在 min_popularity / max_popularity / exclude_confidence は config のみ、JS dashboard で弄れない
7. **「ホワイトリスト除外で買い候補無し」を画面に説明**
   - エラー人間化軸の継続課題
8. **サイドバー overflow + helpBox** (5 連続持ち残し)

## 重要ファイル / ディレクトリ早見

```
config.py                    # BUY_FILTER_DEFAULT / is_whitelisted_race
predictor/
  rules.py                   # _score_one (508 行)、calibrator、確率計算
  features.py                # 49 特徴量を SQLite から計算
  weights.json               # 25 namespace、137 leaf
  calibrator.json            # bin shrinkage (min_count=50, alpha=30)
jvlink_client/
  client.py                  # JV-Link COM ラッパ (logger 統一済)
  ingest.py                  # raw → SQLite, only_files/modified_since 対応
gui/app.py                   # 1900+ 行、CONTROL_HTML/PREVIEW_HTML
web/
  generator.py               # build_view_model / render / publish_to_icloud
  templates/index.html.j2    # ダークモード対応済 (P2-1)
scripts/
  backtest.py                # 全体/buy_only/whitelist_only の 3 系統
  filter_sweep.py            # --walk-forward フラグで両期間並列
  sweep_weights.py           # weights.json の grid search 用
data/
  backtest/*.json            # rule_version 付き履歴
  scorecards/*.md            # 改修ごとの専門家採点 (個別 + 集約)
.claude/agents/_rubric.md    # 5 段階ルーブリック (全専門家共通)
.claude/agents/<role>.md     # 専門家 7 名の subagent 定義
```

## 必須運用ルール (重要、CLAUDE.md と重複だが明示)

1. **改修ごとに `expert-review` を D1 自動実行** — タスク完了宣言の直前に必ず通す
2. **`gui/app.py` の `CONTROL_HTML` / `PREVIEW_HTML` を触ったら必ず `python-embedded-js` 検証** — `node --check` まで通すこと (過去 4 回ボタンが死んだ罠)
3. **32bit Python (`.venv32/Scripts/python.exe`) を使う** — JV-Link COM のため
4. **backtest を取ったら `--rule-version <topic>` で必ず保存** — 検証プロセス監査人の自己参照リスク監視に必要

## 新セッション開始時のチェックリスト

> **⚠ 鉄則**: ステップ 1 (`git status`) は省略しない。
> 未コミットの変更や未追跡ファイルが残っていれば、**新規改修に着手する前にコミット or 退避**。
> 過去、`master` 側に `config.py` `CLAUDE.md` `scripts/filter_sweep.py` 等の主要ファイルが untracked のまま長期間放置され、worktree 側のファイル一覧 (スパース) と乖離して優先課題リストが噛み合わない事故が起きた (2026-05-12)。
> スパースな worktree に居ても、迷ったら親リポ (`C:\Users\kizun\dev\keiba-yosou`) でも `git status` を取ること。

```bash
# 1. 未コミット差分があるか (★最優先★ — 残っていれば先にコミット)
git status
# 親リポでも (worktree に居る場合)
cd C:/Users/kizun/dev/keiba-yosou && git status

# 2. 最新 scorecard を確認 (現状把握)
ls -lt data/scorecards/*.md | head -5

# 3. 直近 backtest を確認 (数値把握)
ls -lt data/backtest/*.json | head -5

# 4. 構文 + JS パースが通っているか (運用準備)
.venv32/Scripts/python.exe -c "
import ast, sys, os, tempfile, re
sys.path.insert(0, '.')
for f in ('config.py','gui/app.py','web/generator.py','scripts/backtest.py','predictor/rules.py'):
    ast.parse(open(f, encoding='utf-8').read())
import gui.app
m = re.search(r'<script>(.*?)</script>', gui.app.CONTROL_HTML, re.DOTALL)
open(os.path.join(tempfile.gettempdir(), 'gui.js'), 'w', encoding='utf-8').write(m.group(1))
print('Python OK')
" && node --check "C:\\Users\\kizun\\AppData\\Local\\Temp\\gui.js" && echo "JS OK"
```

これが通れば、すぐ次の改修 (上のリスト 1-8) に着手できる。

## 関連スキル

- `.claude/skills/expert-review/` — 改修ごとの 7 名採点
- `.claude/skills/python-embedded-js/` — CONTROL_HTML 編集時の JS 罠回避
- `.claude/skills/jvlink-com/` — JV-Link COM プロトコル
- `.claude/skills/jvdata-record/` — レコード解析
- `.claude/skills/keiba-feature/` — 予想シグナル追加
- `.claude/skills/keiba-backtest/` — backtest 設計 / リーク防止
- `.claude/skills/token-economy/` — 大ファイル避け
