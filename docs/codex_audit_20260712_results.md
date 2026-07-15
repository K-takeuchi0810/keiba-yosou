# Codex 作業指示: 2026-07-12 予想生成結果の問題洗い出し監査

以下を Codex CLI に貼り付けて使う。起動前の推奨設定:

```
cd C:\Users\kizun\dev\keiba-yosou
codex            # 新規セッションで開始 (前セッションを引きずらない)
codex> /model    # reasoning effort = medium (バグ調査のため。high は不要)
```

---

## ここから Codex へのプロンプト本文

あなたは競馬予想生成パイプラインの出力を監査する QA エンジニアです。
2026-07-12 開催分の生成結果一式に含まれる問題点を洗い出してください。
**修正はしない**。問題の列挙・証拠・推定原因の特定までが仕事です。説明文は最小限で。

### 対象ファイル (これ以外は読まない)

- `data/results/2026-07-12/predictions.csv` (471 行) — 予想出力。列: race_id, track_code, race_num, horse_num, horse_name, mark, model_rank_by_mark, morning_odds, morning_popularity, rationale, win_probability, expected_value, confidence, bet_candidate
- `data/results/2026-07-12/final_odds.csv` (507 行) — 確定オッズ
- `data/results/2026-07-12/race_results.csv` (507 行) — 確定着順
- `data/results/2026-07-12/payouts.csv` (37 行) — 単勝・複勝払戻
- `data/results/2026-07-12/evaluation_summary.csv` (471 行) — 上記の結合評価
- `data/results/2026-07-12/manifest.json` — 生成メタ (counts, sha256, version_meta)
- `scripts/build_daily_results.py` (602 行) — これらを生成するコード。原因特定時のみ該当関数を読む

### 禁止事項 (トークン節約 + 事故防止)

- `data/results/2026-07-12/predictions_source_*.html` (370KB) を **全文 read しない**。検証が必要な場合は `grep` / `python -c` で該当レースだけ抽出する
- `data/keiba.db` (288MB) を read しない。必要なら `sqlite3` の結果だけ使う
- `data/raw/`, `docs/*.pdf`, `predictor/` 配下には立ち入らない
- CSV も全文 read せず、pandas ワンライナーで集計して結論だけ context に入れる

### 監査タスク

**A. 件数・スキーマ整合**
1. manifest.json の counts と各 CSV の実行数 (ヘッダ除く) の一致
2. predictions=470 行に対し final_odds / race_results=506 行で **36 行差** (= レース数と同じ)。差分行を特定せよ。ヒント: `race_results.csv` 先頭に `horse_num` が空・`confirmed_order=0` の「ホウオウワイズ」行がある。全 36 レースに同様の幽霊行が 1 行ずつ混入していないか、混入源はパーサか SQL か

**B. 値域チェック**
1. `morning_popularity` に **310 や 68 など人気順として不正な値** がある (人気は 1〜18 のはず)。全行の分布を出し、列ズレ・単位違い (支持率×10? オッズ×?) のどれかを推定せよ
2. `final_popularity=0`、`final_odds` 空、`odds_fetched_at` 空の行の件数と条件 (取消馬か幽霊行か)
3. `win_probability`, `expected_value`, `confidence` が空の行の割合。mark 付き 180 頭のみ埋まる設計か、それとも欠損か
4. race_num の型不整合: predictions.csv は `1`、final_odds/race_results/payouts は `01`。join キーとして事故らないか

**C. レース単位の妥当性**
1. 各レースで `mark`=◎ がちょうど 1 頭か。○▲△の重複・欠落
2. `market_probability` のレース内合計 (単勝控除率 20% なら ≈1.25 の逆数で 0.8 前後になるはず)。大きく外れるレースを列挙
3. `win_probability` のレース内合計が ≈1.0 か (mark 付きのみなら部分和として妥当か)
4. `expected_value ≈ win_probability × morning_odds` が成立するか。数レースをサンプル再計算

**D. 結果突合**
1. payouts.csv の `tan_horse_num1` が race_results.csv で `confirmed_order=1` の馬と全レース一致するか
2. 複勝払戻対象馬 (fuku_horse_num1-3) が着順 1-3 位 (7 頭立て以下は 1-2 位) と整合するか
3. evaluation_summary.csv の `profit_loss_yen_100unit` を `bet_candidate`, `win_payout`, `place_payout` から再計算して全行一致するか

**E. 予想内容の質 (predictions.csv)**
1. `rationale` の文字化け・空・同一文言の異常な重複 (例: 全馬「マイニングN位」だけ等)
2. `model_rank_by_mark` と mark の序列が矛盾する行
3. `bet_candidate=True` の行数と、その行に必要な数値 (win_probability, expected_value) が揃っているか

**F. HTML→CSV パース検証 (grep のみで)**
1. 任意の 2 レースについて HTML から出走頭数を grep で数え、predictions.csv の頭数と一致するか
2. 幽霊行 (A-2) の馬名が HTML 上でどの要素に現れるか特定 (レース名? 前走情報?)

### 成果物

`data/results/2026-07-12/audit_findings.md` に以下の形式で書き出す:

```
## 問題 N: <一行要約>
- 深刻度: 高 / 中 / 低
- 証拠: <race_id や件数、再現ワンライナー>
- 推定原因: <build_daily_results.py の関数名・行番号 or データ源>
```

深刻度の基準: 高 = 数値の意味が誤っている / join が壊れる、中 = 欠損・型不整合だが集計に影響限定、低 = 表示・体裁。

全タスク完了後、問題数と深刻度別サマリを 5 行以内で報告して終了。追加の探索や修正提案の長文は不要。
