# 2026-07-12 予想生成結果 監査所見

- 検出: 4件（高 2 / 中 2 / 低 0）
- 対象件数: 36レース、予想470頭

## 問題 1: 朝オッズと人気が連結され、非空169行の数値が破損
- 深刻度: 高
- 証拠: `morning_odds` / `morning_popularity` が入る169行のうち、人気が18超なのは139行。残る30行も、例として `20260712-02-01` 11番ホウオウワイズはHTMLの `22.9倍 / 6人気` がCSVでは `22.96 / 96`、1番ニシノギャルズは `77.3倍 / 10人気` が `77.31 / 310` になっている。再現: `python -c "import csv; r=list(csv.DictReader(open(r'data/results/2026-07-12/predictions.csv',encoding='utf-8'))); print(len([x for x in r if x['morning_popularity']]),len([x for x in r if x['morning_popularity'] and int(x['morning_popularity'])>18]))"` → `169 139`。
- 推定原因: `IndexHtmlParser` が同じ`td`内の `22.9` と `6人気` を区切りなしの `"".join(self._td_buf)` で `22.96人気` にし、貪欲な数値正規表現を適用している（`scripts/build_daily_results.py:173`, `190-198`, `266`）。

## 問題 2: 全36レースに空馬番の幽霊行が1行ずつ混入
- 深刻度: 高
- 証拠: predictions/evaluationは各470行、final_odds/race_resultsは各506行。差分36行はすべて `horse_num=''` で、final_odds側は `final_odds='' / final_popularity=0 / odds_fetched_at=''`、race_results側は `confirmed_order=0`。36件すべての馬名が同一レースの正規出走馬にも存在する（例: `20260712-02-01` ホウオウワイズは正規11番、`20260712-10-12` セレブトーチは正規3番）。
- 推定原因: DBの`horse_races`にある空馬番行を、日付だけのSQLで取得し無条件に両CSVへ出力している（`scripts/build_daily_results.py:351-358`, `425-456`）。HTMLパーサ由来ではない。SQLに馬番の妥当性条件がなく、上流DBの重複不正行もそのまま通過する。

## 問題 3: 正規137頭で最終オッズ取得時刻が欠損
- 深刻度: 中
- 証拠: `odds_fetched_at`空は計173行。その内訳は問題2の幽霊36行と、馬番・最終オッズ・最終人気が揃う正規137行。正規欠損は11レース全頭（02-06〜08、03-05〜08、10-05〜08）に集中する。
- 推定原因: `horse_races.odds_fetched_at` の欠損をそのまま出力している（`scripts/build_daily_results.py:351-355`, `438`）。レース全頭単位の欠損なので、生成時の結合ではなく上流のオッズ取得・保存経路で時刻が記録されなかった可能性が高い。

## 問題 4: race_numの表現がCSV間で不統一
- 深刻度: 中
- 証拠: predictions/evaluationは `1`〜`12`、final_odds/race_results/payoutsは `01`〜`12`。現在の内部結合は正規化済み`race_id + horse_num`を使うため一致しているが、CSV利用者が `track_code + race_num + horse_num` で結合すると1〜9Rが不一致になる。
- 推定原因: predictions側はHTML由来の整数`rn`を出力する一方、DB由来3 CSVはゼロ埋め文字列をそのまま出力している（`scripts/build_daily_results.py:403`, `433`, `453`, `471`）。`race_id_of`だけは整数化・2桁化している（`383-385`）。

## 検証済み（問題なし）

- manifestの5件のcountsは各CSV実行数と一致。HTML 36レース / 470頭 / top picks 180頭とも一致。
- 全36レースで印は ◎○▲△☆ が各1頭。`model_rank_by_mark`との矛盾は0件。
- `win_probability` / `confidence` は印付き180頭だけにあり、空290/470（61.7%）は設計どおり。`expected_value`は朝オッズのある印付き60頭だけにあり、空410/470（87.2%）。`bet_candidate=True`は1頭で必要数値の欠損なし。
- `market_probability=1/final_odds` のレース内和は1.2551〜1.2939。未正規化の単勝インプライド確率なので約1.25が妥当。`win_probability`は上位5頭だけの部分和で0.518〜0.834。
- `expected_value ≈ win_probability × morning_odds` は60件で概ね成立（最大絶対差0.044824）。例: 20260712-02-01 4番は `0.210×4.62=0.9702`、CSVは`0.97`。
- 単勝勝馬と1着馬、複勝対象と1〜3着馬は全36レース一致（全レース8頭以上）。`profit_loss_yen_100unit`の再計算は470行すべて一致。
- rationaleは空0、文字化け0、452種類。マイニング順位だけの文言は13/470で、全馬一律ではない。
- HTMLの出走馬行は20260712-02-01が12頭、20260712-10-12が17頭でpredictionsと一致。幽霊名はHTML上では通常の`td.horse-name`（ホウオウワイズ: 795行、セレブトーチ: 8399行）に正規馬番付きで現れる。
