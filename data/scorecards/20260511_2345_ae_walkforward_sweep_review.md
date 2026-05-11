# 採点 2026-05-11 23:45 — a (walk-forward 検証) + e (sweep + filter 更新)

**改修内容**: 「84.9% は自己参照リスクの幻」と確証 → sweep で両期間で再現する filter を発見 → config 更新

## 総合スコア (項目平均) の推移

| # | 専門家 | 今回 | 前回 | baseline | 差分 |
|---|---|---|---|---|---|
| 1 | GUI / UX 監査人 | 3.6 | 3.6 | 3.2 | ±0 |
| 2 | モバイル HTML レビュアー | 4.4 | 4.4 | 3.4 | ±0 |
| 3 | 予想ロジック分析官 | 4.2 | 4.2 | 3.4 | ±0 |
| 4 | **収益性 / 投資判断専門家** | **3.4** | 3.0 | 1.8 | **+0.4** |
| 5 | データパイプライン技術者 | 4.0 | 4.0 | 3.8 | ±0 (7 連続持ち越し) |
| 6 | **コード品質 / 保守性** | 4.2 | 4.1 | 2.6 | +0.1 |
| 7 | **検証プロセス監査人** | **4.8** | 4.6 | 3.2 | **+0.2** |

**全体平均: 3.06 (baseline) → ... → 3.99 → 4.09 (a+e)** = baseline 比 **+1.03** 🎉

7 改修で **全体 +1 点超え**。専門家 3 名が 4.0 超え (収益性以外)。

## 達成した重要マイルストーン

### 🟢 収益性 +0.4: 「買い目フィルタ実用化」が完成
- 買い目フィルタ 3 → 4 (+1)
- buy_only **0 戦 → 105 戦** (詰みフィルタ解消)
- 回収率 89.0% (control 60.8% に対して +28.2pt、控除率 80% に対して +9pt)
- 収支 -1,150 円 (control -45,590 円から大幅改善)、+100% 未達

### 🟢 検証プロセス +0.2: 「過適合監視」5 連続警告解消
- 過適合監視 3 → 5 (+2) 🎉
- 時系列リーク防止 4 → 5 (+1) — design/eval ギャップが境界漏れない実証
- ただし calibration 計測 5 → 4 (-1) — backtest 出力に brier_score 等が欠落 (回帰指摘、要修正)

### 🟢 コード品質 +0.1: config 一元化が広がった
- min_popularity / max_popularity / exclude_confidence が config 経由に
- 3 経路 (`_is_buy_candidate` / `_matches_buy_filter` / `bet_candidate`) で同語彙
- ⚠ DRY 微回帰: `filter_sweep.py` で WHITELIST_GRADES/TRACKS を再定義 (config と二重)

## 横断的な次の優先課題

### 🟠 即対処すべき軽微回帰
1. **`filter_sweep.py` の WHITELIST_*  を config 参照に統合** (DRY 4.0 → 4.5)
2. **backtest 出力に calibration メタを復元** (Brier / LogLoss / reliability_bins)

### 🟠 継続課題
- **データパイプライン 3 件** (7 連続持ち越し): mtime / JVStatus timeout / DB PRAGMA
- **`_score_one` 関数分割** (予想ロジック継続)
- **GUI dashboard で新 filter キー (人気帯) を弄れるように**
- **walk-forward 結果を scorecard に常時添付** (= 84.9% 幻の事故再発防止)
- **`wl_odds_8_20` 路線で +100% 超え探索** (現状 89%, ターゲット 100%+)
- **Kelly fraction を実ベット額に接続** (現状表示のみ)

## 個別 scorecards

- `20260511_2345_ae__gui-ux-auditor.md`
- `20260511_2345_ae__mobile-html-reviewer.md`
- `20260511_2345_ae__prediction-logic-analyst.md`
- `20260511_2345_ae__profitability-judge.md`
- `20260511_2345_ae__data-pipeline-engineer.md`
- `20260511_2345_ae__code-quality-reviewer.md`
- `20260511_2345_ae__validation-process-auditor.md`
