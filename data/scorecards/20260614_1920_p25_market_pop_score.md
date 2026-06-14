# 採点 2026-06-14 19:20 — P25: 市場人気1-3番スコア補正 + freshness guard

**改修内容**: P24 診断と favorite-longshot bias 知見を受け、発走30分以内の市場人気1-3番だけを◎決定前スコアへ反映する補正を追加。
**対象ファイル**: `predictor/rules.py`, `predictor/features.py`, `predictor/weights.json`, `tests/test_market_popularity_scoring.py`, `data/backtest/20260614_190926_tan_p25-market-pop-score-fresh-smoke-filtered.json`

## 総合スコア

| 専門家 | 今回 | 前回 | 差分 |
|---|--:|--:|---:|
| GUI / UX 監査人 | 3.8 | 3.9 | -0.1 |
| モバイル HTML レビュアー | 4.2 | 4.3 | -0.1 |
| 予想ロジック分析官 | 3.5 | 3.4 | +0.1 |
| 収益性 / 投資判断 | 2.0 | 3.0 | **-1.0 後退** |
| データパイプライン技術者 | 3.6 | 3.6 | +0.0 |
| コード品質 / 保守性 | 4.0 | 4.1 | -0.1 |
| 検証プロセス監査人 | 3.3 | 3.8 | **-0.5 後退** |
| **平均** | **3.49** | **3.73** | **-0.24** |

## 後退警告

- **収益性 -1.0**: 48戦 smoke では all 73.1%、buy_only 15点 46.7%。実弾投入不可、観察・シャドー運用まで。
- **検証プロセス -0.5**: 48戦 / buy_only 15点のみでは採用判断不能。長期 paired A/B、p25 calibrator refit、fold 検証が必要。
- data-pipeline 指摘で、レビュー中に **freshness guard** を即時追加。古い `odds_fetched_at` の人気では市場人気補正を効かせないよう修正済み。

## 実装内容

- `predictor/weights.json`
  - `popularity.first/second/third = 7/4/2`
  - `popularity.max_snapshot_age_min = 30`
- `predictor/features.py`
  - `current_race_date`, `current_start_time` を特徴量へ追加。
- `predictor/rules.py`
  - `RULES_VERSION = "p25-market-pop-score-2026-06-14"` に bump。
  - `odds_fetched_at` と発走時刻から snapshot age を計算し、30分以内だけ市場人気補正を有効化。
  - 3番人気にも `市場3人気` rationale を出す。
- `tests/test_market_popularity_scoring.py`
  - 1/2/3番人気の加点、少頭数無効、stale/missing snapshot 無効、`predict_race` 経由で◎順序が変わる contract を固定。

## 検証結果

- `pytest`: どの Python 環境にも未導入のため実行不可。
- 代替 direct assertions:
  - syntax/json ok
  - market popularity tests ok
  - filter contract ok
- calibrator mismatch warning:
  - `calibrator=p21-2026-06-13`
  - `current=p25-market-pop-score-2026-06-14`
  - 意図どおり警告。正式評価前に p25 用 refit が必要。
- 実DB smoke:
  - 20260607 場05 1R は `odds_fetched_at=04:57:48` で発走30分超過のため、市場人気 reason は出ないことを確認。
- 短期 backtest:
  - 保存先: `data/backtest/20260614_190926_tan_p25-market-pop-score-fresh-smoke-filtered.json`
  - 期間: 20260601-20260607
  - all: 48戦 / 的中 12 / 回収 73.1%
  - buy_only: 15点 / 的中 2 / 回収 46.7%
  - Brier: 0.061493

## 各専門家の所見

### GUI / UX 監査人

スコア **3.8 / 5**、前回 3.9、差分 -0.1。GUI 変更はなく、JS パースは PASS。新規ブロッカーなし。継続課題として、P25 により「Ⅱ最新オッズ取得 → Ⅲ予想生成で市場人気を使う」依存が強まったため、GUI 内の説明不足、`inFlight` フラグ不足、title/aria 不足を指摘。

### モバイル HTML レビュアー

スコア **4.2 / 5**、前回 4.3、差分 -0.1。HTML レイアウト崩壊なし。render は成功。ただし iPhone では `title` 属性の rationale が読めないため、市場人気根拠が可視テキストに出ない問題を継続指摘。枠番色 `.waku-6`〜`.waku-8` のコントラスト、日付ナビ高さも follow-up。

### 予想ロジック分析官

スコア **3.5 / 5**、前回 3.4、差分 +0.1。7/4/2 は既存シグナル比で過大ではなく、P24 の「市場逆張りに寄りすぎる」問題とは整合。ただし手置き重みであり、`0/0/0`, `4/2/1`, `7/4/2`, `10/6/3` の walk-forward 比較が必要。calibrator mismatch は本番投入前に解消必須。

### 収益性 / 投資判断

スコア **2.0 / 5**、前回 3.0、差分 -1.0。実弾投入不可。48戦 smoke では all 73.1%、buy_only 46.7% で控除率目安にも届かない。P25 は収益改善ではなく、fresh odds がある場合のランキング補助として観察対象に留めるべき。

### データパイプライン技術者

スコア **3.6 / 5**、前回 3.6、差分 0.0。JV-Link / ingest / schema 直接変更なし。ただし `win_popularity` を◎決定前に使うことで鮮度リスクの影響範囲が拡大。レビュー後に、発走30分超過または欠損 snapshot では市場人気補正しない guard を追加済み。

### コード品質 / 保守性

スコア **4.0 / 5**、前回 4.1、差分 -0.1。小さく健全な改修だが、当初は fallback 6/3/1 と weights 7/4/2 が不一致、2番人気と `predict_race` contract テスト不足を指摘。レビュー後に fallback を 7/4/2 へ揃え、2番人気・freshness・`predict_race` 経由テストを追加済み。pytest 不在は継続課題。

### 検証プロセス監査人

スコア **3.3 / 5**、前回 3.8、差分 -0.5。smoke としては有効だが、48戦 / buy_only 15点は採用判断に使えない。before JSON が保存されていないこと、dirty worktree の `git_sha` だけでは再現性が弱いこと、p25 calibrator refit 未実施を指摘。レビュー後に freshness guard を追加し、stale market popularity を使う疑似 pre-race 問題は軽減。

## 横断的に見た優先課題

1. **p25 用の正式 A/B と calibrator refit**
   - `popularity weights=0/0/0`, `4/2/1`, `7/4/2`, `10/6/3` を同一期間・同一コード経路で比較。
   - p25 raw_blended 分布で calibrator を refit し、2025 fit / 2026 holdout の Brier, logloss, reliability を確認。

2. **市場 snapshot の観測性を backtest JSON に追加**
   - `market_snapshot_age_min` 分布、fresh/stale/unknown counts、人気補正を使えた頭数を保存。
   - 今回は freshness guard で stale 使用は防いだが、検証ログから理由を追える状態ではない。

3. **GUI/HTML で市場人気依存を可視化**
   - 「最新オッズ取得後に市場人気補正が効く」ことを GUI help に出す。
   - mobile では title だけでなく、印付き馬の可視 rationale に市場人気根拠を出す。
