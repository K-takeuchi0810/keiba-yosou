# 収益性 / 投資判断専門家 採点

## 総合: 2.0 / 5

P0-1 で生成側 / 検証側のフィルタが `config.BUY_FILTER_DEFAULT` 一点集約された結果、「フィルタが効くのか」を測定可能にしたという点で項目4は大きく改善 (1→3)。一方で回収率・EV 整合・Kelly・校正は数値も実装も未変動 (本改修のスコープ外)。控除率 80% を超えていないため総合は依然 3 未満ルール適用で 2.0 まで。

## 項目別

- **回収率 (本丸): 1/5 (前回 1/5, ±0)** — 直近 5 件 (72 戦) は 50.7 / 52.2 / 62.4 / 62.4 / 62.4% と前回スナップショットから一切動かず。フィルタ通過分は 0〜2 件で `buy_only_return_rate=0.0%` 据え置き。控除率 (約 80%) を 17pt 以上下回り、実弾投入なら毎週マイナス確定の構造は不変。
- **EV 計算の整合性: 2/5 (前回 2/5, ±0)** — `_investment_probability` の三段がけ (calibrator → market blend → odds-band discount) は今回未変更。`PRED_DISABLE_DISCOUNT=1` の比較 backtest も `data/backtest/` に追加なし。P1 で対処予定とのことなので維持で正しい。
- **Kelly fraction / 投資割合: 2/5 (前回 2/5, ±0)** — `_bet_metrics` の `min(kelly, 0.05)` 上限は依然表示のみ。同 race 複数候補の分散投資ガイダンスも未着手。今回スコープ外として維持。
- **買い目フィルタの実用性: 3/5 (前回 1/5, +2)** — 本改修の主役。`config.BUY_FILTER_DEFAULT = {min_ev:1.05, min_value:0, min_odds:10, max_odds:20, max_odds_age_min:30}` を **唯一の出典** とし、`web/generator.py:35-39` が BET_MIN_* を derive、`gui/app.py:217-228 _is_buy_candidate` が同 dict 参照、`scripts/backtest.py:29-36 buy_filter_from_generator()` が generator 経由で同値を取得。GUI 側も `get_buy_filter_default` API (app.py:177-183) を JS が起動時 fetch して input 初期値に反映 (app.py:1642-1644)。生成 / 検証 / GUI 表示の三者一致で「フィルタを掛ければ勝てるか」が原理的に測定可能になった。+2 の根拠はここ。ただし採用件数 1〜2 / 72 戦の死フィルタ状態は不変で、`relaxation` ヒントも未実装のため 4 には届かない (実用性 = 一致 + 件数確保 + 緩和示唆 の 3 条件のうち 1 条件達成)。
- **校正済み確率の信頼性: 2/5 (前回 2/5, ±0)** — `predictor/calibrator.json` は M フラグだが目視差分なし (本タスクで触る対象外)。bin 0.15-0.20 の count=27 で `calibrated=0.3333` の過大評価、0.45 以上 count=0 の空白は P0-2 で対処予定。維持。

## 主な改善提案 (優先 1 件、最大 3 件)

1. **フィルタ採用 0 件問題に直接効く `relaxation` チェーンの実装** — 統一は終わったので、次は「`min_ev=1.05 / odds 10-20` で 1 件しか出ないなら、自動的に `min_ev=1.00 / odds 8-25` で 1 段緩めた候補もペイロードに `relaxation_tier=1` 付きで出す」階段を `web/generator.py` で実装。`config.py` に `BUY_FILTER_RELAXATION = [{"min_ev":1.00,"min_odds":8,"max_odds":25}, ...]` を 2-3 段並べる。期待効果: 72 戦中 2→10〜15 件に増えれば、buy_only_return_rate がノイズから抜けて統計的判断が可能に。
2. **`config.BUY_FILTER_DEFAULT` の `__hash__` を backtest 出力 JSON に埋め込む** — 現状 `data/backtest/*.json` の `buy_filter` フィールドは値を持っているが、`config_version` や hash がないので「どの commit の DEFAULT で取った backtest か」が後追いできない。`scripts/backtest.py:363` 付近で `"config_buy_filter_hash": hashlib.md5(json.dumps(BUY_FILTER_DEFAULT, sort_keys=True).encode()).hexdigest()[:8]` を追加。期待効果: P0-1 後の backtest と P1 完了後の backtest を fair に比較できる土台。
3. **GUI dashboard で「現在 default と異なる input を使っている」可視化** — `app.py:1642-1644` で default を input に流し込んだだけだと、ユーザが手で書き換えても警告が出ない。`config と現在 input が異なれば input を黄色背景` の JS を 5 行追加。期待効果: 「いつの間にか手元 GUI のフィルタだけずれて backtest と乖離していた」事故を防止 (今回直したばかりの問題の再発防止)。

## 前回からの差分 (1.8 → 2.0, +0.2)

- 回収率: 1 → 1 (±0) — backtest 数値変動なし
- EV 計算の整合性: 2 → 2 (±0) — 三段がけは P1 で対処予定、今回スコープ外
- Kelly fraction: 2 → 2 (±0) — 未着手、維持
- 買い目フィルタの実用性: **1 → 3 (+2)** — 生成 / 検証 / GUI の三者で同一定数を参照する構造に変わり、「フィルタの責任所在が確定する」という前回提案 #1 を直接吸収。ただし採用件数の絶対不足と relaxation 未実装で 4 には届かず。
- 校正済み確率: 2 → 2 (±0) — calibrator.json は触っていない、P0-2 で対処予定
