---
name: project-state
description: keiba-yosou プロジェクトの **現状スナップショット**。新セッション開始時に最初に読み、過去 7 改修で何が成された / 何が未着手 / 数値で「実際どこまで進んだか」を一発で把握するためのもの。「現状を教えて」「どこまで進んだ」「次は何やる」のような質問にも対応。具体的な数値 (回収率 89%, baseline 比 +1.03 等) と最新 scorecard へのリンクを持つので、それを起点に新セッションの改修計画を立てられる。
---

# keiba-yosou プロジェクト 現状スナップショット

## 1 行サマリ

JRA-VAN JV-Link を使うローカル競馬予想 GUI。**2026-05-12 walk-forward sweep で `wl_odds_8_20` (重賞+中山+京都 で 8-20 倍帯) を採用、EVAL 4 ヶ月 41 戦 / 回収率 116.1% / +660 円で初の +収支到達**。両期間 (DESIGN 103.5% / EVAL 116.1%) +100% 維持。サンプル少 (n=41 / 月 ~10 戦) で分散リスクあり、第三 hold-out (2026/05 以降) 必須。

## スコア推移 (9 改修分、`data/scorecards/` 詳細あり)

| | baseline | P0-1 | P0-2 | P1-3 | P0-3 | P1-1 | P2-1 | a+e | p05 | **p06** |
|---|---|---|---|---|---|---|---|---|---|---|
| **全体平均** | 3.06 | 3.14 | 3.30 | 3.41 | 3.59 | 3.77 | 3.99 | 4.09 | 4.09 | **4.12** |
| GUI / UX 監査 | 3.2 | 3.2 | 3.3 | 3.3 | 3.2 | 3.2 | 3.6 | 3.6 | 3.4 | **3.6** ↑ |
| モバイル HTML | 3.4 | 3.4 | 3.4 | 3.4 | 3.4 | 3.4 | 4.4 | 4.4 | 4.4 | 4.4 |
| 予想ロジック | 3.4 | 3.4 | 3.6 | 3.6 | 3.6 | 4.2 | 4.2 | 4.2 | 4.1 | 4.1 |
| **収益性** | 1.8 | 2.0 | 2.4 | 2.0 | 3.0 | 3.0 | 3.0 | 3.4 | **3.8** 🏆 | 3.8 |
| データパイプライン | 3.8 | 3.8 | 3.8 | 4.0 | 4.0 | 4.0 | 4.0 | 4.0 | 4.0 | 4.0 |
| コード品質 | 2.6 | 2.8 | 3.0 | 3.4 | 3.5 | 4.0 | 4.1 | 4.2 | 4.3 | 4.3 |
| **検証プロセス** | 3.2 | 3.4 | 3.6 | 4.2 | 4.4 | 4.6 | 4.6 | 4.8 | **4.6** | 4.6 |

baseline 比 **+1.06**。p05 で GUI -0.2 だったが、p06 navfix で +0.2 戻し収益性確保のまま安定。

## 完了した改修 (時系列)

| 改修 | 内容 | scorecard |
|---|---|---|
| P0-1 | buy_filter を `config.BUY_FILTER_DEFAULT` に一元化 | `20260510_2300_p01_buy_filter_unified.md` |
| P0-2 | calibrator の少数 bin 恒等寄せ (min_count 20→50) | `20260510_2310_p02_calibrator_minbin.md` |
| P1-3 | `except: pass` 9 箇所を logger.warning に + print→logger | `20260510_2330_p13_logging.md` |
| P0-3 | 重賞ホワイトリストモード (`whitelist_grades / tracks`) | `20260510_2355_p03_whitelist.md` |
| P1-1 | dead feature 5 削除 + 直書き 60→1 + weights.json 12 namespace | `20260511_0030_p11_refactor.md` |
| P2-1 | モバイル CSS 変数化 + `<details>` インジケータ + theme-color | `20260511_0100_p21_mobile.md` |
| a+e | walk-forward 検証 + sweep + filter 更新 (wl_ex_unsure_pop_1_4 採用) | `20260511_2345_ae_walkforward_sweep_review.md` |
| **p05** | **wl_odds_8_20 に切替、初の +収支到達** + filter_sweep dedup + scorecards/code 整理 4 コミット | `20260512_2100_p05_wl_odds_8_20.md` |
| **p06** | pywebview navigate race 修正 (Timer 遅延化で TypeError 連発消滅) | `20260512_2200_p06_pywebview_navfix__gui-ux-auditor.md` |

## 現在の運用フィルタ (= `config.BUY_FILTER_DEFAULT`, 2026-05-12 更新)

```python
BUY_FILTER_DEFAULT = {
    "min_ev": None,
    "min_value": None,
    "min_odds": 8.0,         # ★主絞り条件: 8〜20 倍帯 (中穴)
    "max_odds": 20.0,
    "min_popularity": None,  # 制約解除
    "max_popularity": None,
    "exclude_confidence": [], # 8-20 帯は混戦ラベル不可避なので解除
    "max_odds_age_min": 30,
    "whitelist_mode": True,
    "whitelist_grades": ["A", "B", "C", "F"],  # G1/G2/G3/重賞
    "whitelist_tracks": ["07", "09"],           # 中山 / 京都
}
```

**現実の数値** (`data/backtest/20260512_205837_tan_p05-wl-odds-8-20-filtered.json`):
- EVAL (2026/01-04): buy_only **41 戦 / 9.8% / 116.1%** / 収支 **+660 円** 🏆
- DESIGN (2025/06-12): sweep 値 74 戦 / 103.5% (再現性確認済)
- ⚠ 戦数少なくサンプル分散大。Wilson 95% CI: hit_rate [3.9%, 22.6%] / return_rate [8.0%, 224.2%]
- 旧 `wl_ex_unsure_pop_1_4` (EVAL 105 戦/89.0%/-1,150 円) からの切替で初の +収支

## 直近の重要な指摘 (= 次の改修候補、優先順)

### 🔴 即対処すべき軽微回帰
1. **GUI input デフォルト値を config 参照に統一** (2026-05-12 採点で GUI -0.2 の主因)
   - `gui/app.py:1405-1408, 1477-1480` の `value="10"` `value="1.05"` `value="0"` が新 config (`min_odds=8.0, min_ev=None, min_value=None`) と矛盾
   - F5 直後 UI が config と一致するよう `f"value=\"{BUY_FILTER_DEFAULT['min_odds']}\""` 等動的埋込
   - 工数 30-60 分、GUI -0.2 を取り戻し可
2. **第三 hold-out 期間で本番昇格判断** (検証 -0.2 の主因)
   - 「両期間 +100%」を採用基準にしたことで EVAL 2026/01-04 が in-sample 化
   - 採用決定後の前向きデータ (2026/05 以降) で `--rule-version p05-holdout` 1 回だけ実行
   - `scripts/backtest.py` に `buy_only_hit_rate_ci95` / `buy_only_return_rate_ci95` 出力追加

### 🟠 高インパクト未着手
3. **`_score_one` 関数分割** (予想ロジック / コード品質 — 多セッション持ち越し)
   - 508 行肥大、namespace 化済なので機械的分割可
   - 項目「デッドコード / 整合性」が 4.5 → 5、テスト容易性 2.5 → 3.5 で総合 4.5 射程の最大レバー
4. **データパイプライン 3 件** (**8 連続持ち越し、臨界域**): mtime / JVStatus timeout / DB PRAGMA
   - `wl_odds_8_20` 運用でオッズ鮮度 SQL 自動カット不在のリスク影響度拡大
5. **`wl_odds_8_20_pop_4_8` 併用 A/B** (収益性)
   - sweep で 67戦/101.2% (design) / 37戦/128.6% (eval) 検出、戦数を 41→ 50-60 に増やす候補
   - `BUY_FILTER_DEFAULT` を list-of-dict 化して和集合運用化

### 🟡 GUI / UX 改善
6. **`min_popularity / max_popularity / exclude_confidence` を JS dashboard input に露出**
   - 現状 config のみ、UI から弄れない
7. **「ホワイトリスト除外で買い候補無し」を画面に説明**
   - エラー人間化軸の継続課題
8. **サイドバー overflow + helpBox** (6 連続持ち残し)

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
