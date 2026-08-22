---
name: project-state
description: keiba-yosou プロジェクトの **現状スナップショット**。新セッション開始時に最初に読み、過去 7 改修で何が成された / 何が未着手 / 数値で「実際どこまで進んだか」を一発で把握するためのもの。「現状を教えて」「どこまで進んだ」「次は何やる」のような質問にも対応。具体的な数値 (回収率 89%, baseline 比 +1.03 等) と最新 scorecard へのリンクを持つので、それを起点に新セッションの改修計画を立てられる。
---

# keiba-yosou プロジェクト 現状スナップショット

## ★ 2026-08-22 確定方針 (この節が最上位。以降の節は歴史的記録)

**憲法 = `docs/REFORM_2026H2_MARKET_RESIDUAL.md`** (市場残差アーキテクチャへの転換)。
矛盾する場合は F3 設計 (`docs/F3_MARKET_RESIDUAL_DESIGN.md`) と 4 制約が優先。

### 基本方針 3 箇条 (変更にはユーザ合意が必要)

1. **唯一の幹 = F3 市場残差**。「勝ち馬を当てる」努力 (静的特徴の追加・重み調整・
   sweep 漁り) は幹に従属する場合のみ許可。根拠: 1 番人気ベタ買い 79.0% vs
   ◎ベタ 66.2% (修復後正本 1,932 戦) = 市場と意見を違えると平均で市場が正しい。
2. **実弾判断は 12 月の封印判定 1 回のみ** (CI 下限 > 100% が唯一の昇格条件)。
   それまで全出力は観察専用。買い候補フィルタは suspended=True を維持。
   2026-08-22 の鮮度ゲート付き recent-3fold で形式基準を満たす 2 件
   (`only_t07_pop_1_3` 88.1%/`only_t07_pop_1_2` 83.3%) が出たが、
   **サスペンド維持を決定** (docs/DECISION_20260822_RESELECTION.md)。
   理由: 点推定すら 100% 未達 / 3 fold の 2 つが calibration in-sample /
   clean OOS fold では 68 件中 100% 超え 0 件 / P12 型の単一場 whitelist 形状。
   `only_t07_pop_1_3` は **事前登録仮説 H-t07** として封印判定で 1 回だけ検定する。
3. **棄却済み経路の再訪禁止**: クロスプール直接裁定 / WIN5 / FLB 素朴判別 /
   naive Benter reblend / min_kelly / 通年 sweep 一発採用 / 静的特徴深掘り。
   全て事前宣言基準の artifact 付きで棄却済み (scripts/analyze_cross_pool.py、
   scripts/analyze_simple_edges.py、data/backtest/20260822_*)。

### スケジュール (確定日付)

| Phase | 期間 | 内容 |
|---|---|---|
| R1 | 〜2026-09-30 (dev 窓) | 下記優先タスク 1-6 |
| R2 | 10/1〜 (封印開始、D2 確定済) | 残差モデル凍結・紙運用のみ・封印窓に一切触れない |
| R3 | 12 月頃 (封印窓 ≥800 レース) | 封印判定 1 回。合格→fractional Kelly + 大量多点型の実弾設計 / 不合格→ (a) 観察プロダクト化 or (b) 私有情報投資 の二択をユーザ判断 |

### R1 優先タスク (順位固定)

1. **T−10 再生成パイプライン** (改革の心臓)。predictor/pit_gate.py (実装済) を
   生成側に配線し、開催日の各レースを T−10 時点で再計算・再出力する経路。
   朝 HTML は「プレビュー」明記。backtest 印 (T 直前情報込み) と朝 HTML 印
   (市場盲目) の乖離をこれで解消する
2. **印 = P ランカー統一** (◎≠最高 P 39.2% の分裂解消)。paired backtest で
   非劣化を確認してから切替
3. **calibrator compat 確認 + sweep fold 定義の是正** (fresh 比率が設計前提
   0.4%→23.9% に激変。加えて `--recent-3fold` の fold 2/3 が calibrator 学習期間
   (2025 通年) と重複 = in-sample。選定 fold を calibrator と disjoint にする
   3 案は docs/DECISION_20260822_RESELECTION.md §4)。持ち越し課題の筆頭
4. **残差特徴 v1** (dev 窓 walk-forward のみ): オッズドリフト系 + クロスプール
   整合性特徴 (直接裁定は死んだが説明変数としては未検証) + オッズ分布
   microstructure (エントロピー/集中度)。外部調査 (docs/RESEARCH_AI_PREDICTORS_2026.md)
   の取り込み
5. **調教 (training_times)・コーナー/ラップ dormant 特徴の ablation** (残差
   モデルの説明変数として。市場が扱いに困っている領域)
6. **収集系 SLO 監視の継続** (fresh odds は F3 の生命線。欠損日は dev から除外)

### 運用継続事項 (自動)

- weekly_monitor (baseline=0.062605、2026-08-22 修復後凍結) / 答え合わせ CSV
  (would_be_candidate 列で仮想紙運用も記録) / expert-review D1 / 四半期再選定
- 正本 backtest は clean tree で実行する (git_dirty=True の run を config に焼かない)

### 2026-08-22 の到達点 (詳細は data/scorecards/20260822_* と REFORM doc)

- fresh odds 6 日間停止を復旧 (watchdog + 日付別ログ + Discord 通知)
- 発走後刻印 7,444 行を修復 (post-start 0 収束、適格レース 1,460→1,932)
- 買い候補フィルタ suspended=True (52.6% CI[33.2,73.2] < ◎ベタ 66.2%)
- 打開 3 経路を事前宣言基準で棄却、F3 に集中と確定
- expert-review 2 ラウンド: 平均 3.79 → 3.96 (PASS 5 / HOLD 2、指摘は全件是正済)

## ⚠ 2026-07-05 更新 (歴史的記録)

**下記の旧サマリ (P12 184%) は崩壊済み** — P12 は PRODUCTION 2026 で 45% に暴落
(CLAUDE.md 必須ルール 4 の教訓)。さらに 2026-06-14 の答え合わせ診断でモデルの
EV/Kelly 信号は **anti-predictive** と確証され、`BUY_FILTER_DEFAULT` の min_kelly は
撤廃済み (現 config.py 参照。利益エッジは現在主張していない)。

### 2026-06-29〜07-05 セッションの成果 (branch: claude/feature-bias-validation-yl5key)

1. **`scripts/bias_scan.py`** — 層別特徴量バイアス検証 (場/馬場/天候/開催進行/kaiji 等 ×
   calibration gap、Wilson CI + min_n + 多重比較開示、subject=all はレース内相関補正済)。
   重み変更の前提 3 条件 (多重補正・2024/2025 再現・holdout) を docstring に明記。
2. **rubric v4** (`.claude/agents/_rubric.md`) — 改修タイプ別ゲート (type-A〜E)。P25 固有
   ゲートは type-A のみ適用、非該当は N/A (NOT_EVALUABLE 乱発の誤発火を是正)。
3. **`webapp/`** — SmartRC 踏襲の独自出馬表 (stdlib http.server + jinja2、127.0.0.1)。
   出馬表(系統色分け+補助指標サブ行)/傾向集計(回収率 bootstrap CI 付)/当日速報。
   **予想生成に非干渉**: `db.open_db_readonly` (mode=ro+query_only、migration 非実行)。
4. **コーナー順位 + RA ラップ ingest** — SE corner_order_1..4 (352/354/356/358。旧 394 は
   1着馬血統番号誤読の実バグを修正)、races に front3f_time 等 + lap_times。
   `predictor.features.recent_corner_stats` (先行力/差し脚) は **scoring 未配線の dormant**。
5. **★hard gate (未消化・次セッション最優先)**: 実 .jvd で
   `python -m scripts.probe_corner_offsets <SE.jvd> --expect race_id:馬番:c1:c2:c3:c4` と
   `... <RA.jvd> --ra` を**緑化するまで corner/lap の backfill・利用は禁止**。
   緑化後: `ingest_all(force=True)` で backfill → webapp 出馬表の 4角avg 表示が自動有効化。

### 次の優先課題 (2026-07-05 時点)

1. probe 2 種の緑化 → backfill (上記 hard gate)
2. bias_scan を実 DB で実行し、layered gap の実測 (subject=pick/all 両方、--save)
3. 先行力指標の scoring 配線前の**単独 ablation backtest** (配線 PR の受入条件)
4. Fable 5 復旧時に expert-review を fable で再採点 (現行 scorecard は Opus 代替)

最新 scorecard: `20260705_0140_webapp_parity.md` (7 名全員 PASS)。直近の全 scorecard は
20260629_2344 以降を参照。**以下の旧節の数値 (184%/min_odds 8-20 等) は現状と異なる。**

## 1 行サマリ (歴史的記録: 2026-05-15 時点 — ⚠上記更新で上書き済み)

JRA-VAN JV-Link を使うローカル競馬予想 GUI。**2026-05-15 P12 wl5_pop_1_2 採用** で TEST 2024-25 buy_only 回収率 **184.0%** / **Bootstrap CI [116.4%, 266.5%]** / 収支 **+55,360 円** を達成。CI 下限ですら +100% 超え = 統計的に勝ち戦略確立。LGBM v4 (84 features 含 Tier 1 場別相性) + 3-fold walk-forward sweep (69 filters) で `wl5_pop_1_2` (5 場 × 1-2 人気) を最強と検出。年間 ~330 戦。

## データ期間の正規分割 (`config.DATA_PERIODS`)

| ラベル | 期間 | 用途 | 注意 |
|---|---|---|---|
| **train** | 2021-01-01 〜 2023-12-31 (3 年) | calibrator fit + weights チューニング素材 | TEST と必ず disjoint |
| **test** | 2024-01-01 〜 2025-12-31 (2 年) | filter sweep + A/B 採用判断 | win_odds は ~50% カバー |
| **production** | 2026-01-01 〜 2026-12-31 (本番) | 当日まで遡って予測。HOLDOUT 兼用 | 採用 *決定後* に 1 回検証 |

JRA 中央場 (track_code 01-10) の各年カバレッジ (ingest 後):
- 2021-2025: 各 ~3,460 戦 / ~47,000 horse_races / ~24,500 with win_odds
- 2026 (5/10 まで): 1,308 戦 / 18,588 horse_races / 12,328 with win_odds

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
    "whitelist_tracks": ["07", "09"],           # 中京 / 阪神 (2026-05-13 修正: 中山/京都 と誤記していた)
}
```

**現実の数値** (`data/backtest/20260512_205837_tan_p05-wl-odds-8-20-filtered.json`、旧 EVAL = 現 TEST 部分の 2026 Q1):
- 旧 EVAL (2026/01-04): buy_only **41 戦 / 9.8% / 116.1%** / 収支 **+660 円** 🏆
- 旧 DESIGN (2025/06-12): sweep 値 74 戦 / 103.5% (再現性確認済)
- ⚠ 戦数少なくサンプル分散大。Wilson 95% CI: hit_rate [3.9%, 22.6%] / return_rate [8.0%, 224.2%]
- 旧 `wl_ex_unsure_pop_1_4` (EVAL 105 戦/89.0%/-1,150 円) からの切替で初の +収支
- 5 年分割再評価 (TRAIN 2021-23 calibrator + TEST 2024-25 sweep) は 2026-05-12 進行中。
  完了後 `20260512_2300_p07_5year_split_*.md` に新スコアを保存予定。

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
