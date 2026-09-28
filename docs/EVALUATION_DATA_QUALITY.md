# 評価成果物の品質台帳 (2026-09-25〜)

`data/results/<date>/` の評価成果物 (`evaluation_summary.csv` ほか CSV 5 本 + `manifest.json`)
のうち、**成績の主張に使ってはいけない**ものを記録する。

## 運用ルール

- `status=INVALID` の日を含む評価 CSV を使って、新しい成績の主張をしない。
  対象は `scripts/analyze_misses.py`、累積的中率、回収率集計、期間比較、モデル評価のすべて。
- 「CSV があるから読んでよい」ではない。**修復が完了するまでは既知の不正データとして使用禁止**。
- 分析コードに除外ロジックはまだ入れていない (JST 統一を遅らせないため)。守るのは人間側の運用。
- 修復は再生成で行い、旧成果物との差分と理由を修復記録に残す (履歴を消さず、誤評価だったことを追えるようにする)。
- **2026-09-28 の修復後** (下の「修復記録」):
  - `REPAIRED` / `GENERATED_REPAIRED` の 7 日は、修復した builder (`9cff875`) の成果物として通常どおり使ってよい
  - **`REPAIRED_NO_TARGET_DATE` の 3 日 (6/12・6/17・7/03) は、成績の集計に絶対に含めない**。
    「正常な評価日になった」という意味ではなく、**誤った評価を正しく「評価しない」状態に修復した**という意味
  - 下の「関連する既知の互換性問題」(旧スキーマの 21 日) は別件で、まだ残っている

## INVALID 一覧 (2026-09-25 の検出時点の記録。状態の変化は下の「修復記録」)

| date | status | reason | affected_artifact | detected_at | repair_pending | 内容 |
|---|---|---|---|---|---|---|
| 2026-07-18 | INVALID | cross_date_prediction_contamination | evaluation_summary.csv / predictions.csv / final_odds.csv / race_results.csv (旧 builder `4ff5c0f`) | 2026-09-25 | true | 土曜 HTML に入っていた翌日 (日曜) の 2 レースが、土曜の同じ場・同じ R として土曜の着順で採点されている (31 行、◎ 2) |
| 2026-08-08 | INVALID | cross_date_prediction_contamination | 同上 | 2026-09-25 | true | 同上 (30 行、◎ 2) |
| 2026-08-15 | INVALID | cross_date_prediction_contamination | 同上 | 2026-09-25 | true | 同上 (32 行、◎ 2) |
| 2026-06-12 | INVALID | cross_date_prediction_contamination | 同上 | 2026-09-25 | true | ★ **開催の無い日付 (金)** に週末分の予想 1,416 行がその日付として保存されている。一部混入ではなく**全面的に使用禁止** |
| 2026-06-17 | INVALID | cross_date_prediction_contamination | 同上 | 2026-09-25 | true | ★ **開催の無い日付 (水)** に別日の予想 485 行。全面的に使用禁止 |
| 2026-07-03 | INVALID | cross_date_prediction_contamination | 同上 | 2026-09-25 | true | ★ **開催の無い日付 (金)** に別日の予想 479 行。全面的に使用禁止 |

## 未生成 (2026-09-25 の記録。混入が分かっていたので評価成果物を作っていなかった)

| date | status | reason | repair_pending | 備考 |
|---|---|---|---|---|
| 2026-08-22 | NOT_GENERATED | cross_date_prediction_contamination | true | 新 evaluator `8a91d73` で生成したが混入 (26 行、◎ 2 頭が並ぶレース 2) を確認して破棄。予想 HTML は保存済み |
| 2026-08-29 | NOT_GENERATED | cross_date_prediction_contamination | true | 同上 (20 行) |
| 2026-09-05 | NOT_GENERATED | cross_date_prediction_contamination | true | 同上 (27 行) |
| 2026-09-12 | NOT_GENERATED | cross_date_prediction_contamination | true | 同上 (28 行) |

## 原因

`scripts/build_daily_results.py` の HTML 解析は、レース ID (`race-20260823-01-11` など) の
**末尾の「場-R番号」だけ**を使い、日付を捨てている。日次分割 (2026-09-13) より前の土曜 HTML には、
先に出馬表が出た日曜のレースが入っているので、それが土曜の同じ場・同じ R に結合される。
金額への影響は 0 (該当期間の買い候補は 0 件) だが、**評価 N と的中率の母集団を別日の予想で
汚染している**。140% 検証では金額が発生する前に止めるべき種類の欠陥なので、重大度は下げない。

> **訂正 (2026-09-28、再生成で判明)**: 「買い候補は 0 件、金額への影響は 0」は正確でなかった。
> - 開催日 3 日の旧成果物は、8/08 に買い候補 3 件 (−300 円)、8/15 に 6 件 (−600 円) があった。
>   ただし修復の前後で金額は同じ (混入した翌日分に買い候補が無かった) なので、金額の差は 0
> - **開催の無い 2 日の旧成果物には、架空の金額があった**: 6/12 は買い候補 27 件・−2,700 円、
>   6/17 は 9 件・−900 円 (7/03 は 0 件)。別の日の予想を、その日のレースとして (着順が無いまま) 外れに数えていた。
>   旧 builder は race ID の日付を評価の対象日に書き換えていた (旧 CSV の race_id はすべて対象日の日付)。
>   修復後は 3 日とも 0 円

## 修復の予定 (JST 統一の後)

1. 解析を直す: レース ID から `prediction_date` / `venue` / `race_no` を取り出し、
   `prediction_date == 評価対象日` を必須にする。対象日と違う予想は**評価しないが黙って捨てない**
   (manifest に `foreign_date_predictions_dropped` / `foreign_date_race_ids` を記録)。
2. 不変量「1 レースにつき ◎ は最大 1 頭」を追加。2 頭出たら評価を続けずエラーにする。
3. 変異テストに最低限これらを入れる: レース ID の日付を無視する / 日付比較を常に true にする /
   manifest の drop 件数を 0 にする / 他日付の行を同じ場・同じ R へ結合する / 同一レースに ◎ 2 頭を許す。
4. 再生成: 未生成の 4 土曜 + INVALID の 6 日。旧成果物との差分と理由を修復記録に残す。
5. 以上が終わったら、この台帳の `repair_pending` を false にし、使用禁止を解除する。

→ **1〜5 は 2026-09-28 に実施した** (上の「修復記録」)。上の INVALID / 未生成の表は検出時点の記録として
そのまま残し、状態の変化は修復記録の表で追う。

## 修復記録 (2026-09-28)

| 項目 | 値 |
|---|---|
| defect | `cross_date_prediction_contamination` (上の「原因」) |
| original artifact commit | `3b53b4b` (2026-08-22、旧 builder `4ff5c0f` で生成。INVALID の 6 日) |
| repaired builder SHA | `9cff875` (branch `cross-date-fix-20260926`。`ead43ce` 修正 + `c3be0e9` / `9cff875` テスト。3 名レビュー PASS) |
| regeneration date | 2026-09-28 09:16 (scratch) → 09:19 (tracked)、非開催日・ai-builder Disabled |
| DB | 本番 `data/keiba.db` を `--db` で渡した (builder は SELECT のみ。読み取り専用への切り替えはバックログ `BUILD_DAILY_RESULTS_READONLY_DB`)。開始前・各日の後・終了後の size / mtime と WAL の size が不変 |
| 証拠 | `data/backtest/cross_date_repair_20260928/` (再生成・独立チェックのスクリプトと結果。1 回目は WAL が消えたのを変化と誤判定して止めた記録も残す) |

### 状態の変化と manifest

旧 manifest の sha256 は 2 通り書く: 作業ツリーのバイト (Windows、`core.autocrlf=true` で CRLF。
builder が新 manifest の `supersedes_manifest_sha256` に刻んだ値と一致) と、git の blob (LF)。

| date | 状態の履歴 | source_html | 旧 manifest sha256 (作業ツリーのバイト = 新 manifest の supersedes_manifest_sha256) | 旧 manifest sha256 (git blob, LF) | 新 manifest sha256 |
|---|---|---|---|---|---|
| 2026-07-18 | INVALID → **REPAIRED** | `predictions_source_20260718_093147_git552e949.html` | `223dd7a9e3de5e319407344315fff1d3a020cacac7668fb4432885e2b023a60c` | `e4e5c446caf6f32353bf405aa838a65011c526a33b6cbcf7f6f8904c6b9df052` | `e3a7f16d77d4e6d580e3e632ec527fde05e5fbc10c487bdd9d725bffea33365d` |
| 2026-08-08 | INVALID → **REPAIRED** | `predictions_source_20260808_105630_git0f90945.html` | `cd58c881e10a44ee90e306fb328ad697b9743f244e6e265685000288e435e525` | `07694b825b3cf43e27ab2bcade298bb1821be252d9a1daa09ac1860cee00ac6d` | `bd223b45c44abb52dd655ee4462855554ab2f99301c4d5eed36b7ec440e96946` |
| 2026-08-15 | INVALID → **REPAIRED** | `predictions_source_20260815_090147_gitc7cfdda.html` | `637ee37e8fd1af4ae795cdb047871c6a455072548c6c88bcf857d2278a30c01f` | `87ad3a541585a3046a8553a7f16a8f0b241131365e62d647dbb5beca96ca6d4d` | `c2924667504475937bfe58991e04d7731091ca7ecf7a007c2bf5dc8ab0c3d9c3` |
| 2026-08-22 | NOT_GENERATED → **GENERATED_REPAIRED** | `predictions_source_20260822_090157_gitaff08ca.html` | — (旧成果物なし) | — | `fc1ae263f30694abb53d898a5a7f13127fed86035afbcd3ca8aa8aca0f63b445` |
| 2026-08-29 | NOT_GENERATED → **GENERATED_REPAIRED** | `predictions_source_20260829_110148_git82431ed.html` | — (旧成果物なし) | — | `e2cb857bab4458f4abc445ebdffe73f436825252b7137141e95548797d0f7201` |
| 2026-09-05 | NOT_GENERATED → **GENERATED_REPAIRED** | `predictions_source_20260905_110142_git6bab015.html` | — (旧成果物なし) | — | `6994ca9b685d4f449c2b8f028eee75c9e7fd8ade1d3803950edf61f34cc9bedd` |
| 2026-09-12 | NOT_GENERATED → **GENERATED_REPAIRED** | `predictions_source_20260912_110134_gite554694.html` | — (旧成果物なし) | — | `e777d5421a67a93da08a5f22184c6f4e4edf9eee75033ee62d573541feebbffb` |
| 2026-06-12 | INVALID → **REPAIRED_NO_TARGET_DATE** | `index_20260612_013732_175436.html` | `ca59452110a1139553803392bd9dde0a96ba751c371b323dbb7eaaf824477b48` | `0ef745fac788df1ae868b68fcc485df0f68d207cce00daa48ef5f0aab944ba3c` | `9dcb1074da170f43da6d0cf066d64be2def2ca1e9a9ad1e1c9917b00d69c58fd` |
| 2026-06-17 | INVALID → **REPAIRED_NO_TARGET_DATE** | `index_20260617_082325_554073.html` | `416e49a501faf6103f369428e1140bd024dec8bea2499f04f77d8937dd5f555f` | `22f13c6b2ae175de53a0dca86180520a17809e0dca8b04de1dbe9110ebaabf17` | `5e8019be5ff592a6a9d5e8b68dc8e3d1030dd7330cd721f9bd6e1b4982037cb3` |
| 2026-07-03 | INVALID → **REPAIRED_NO_TARGET_DATE** | `index_20260703_230334_330683.html` | `5cb460855fee061a5054af3c74c3017a319884b2685c8107e7748bb67c96bd09` | `607377055afdcc15b3bac38d65bf51b7a46d4707443c9aa26ba9b0cdd2a862be` | `1de3e2e7bb8374e721e480f32e58524022378f1424d4252746716d0f7d61824a` |

- source_html: 旧成果物がある 6 日は **旧 manifest と同じ HTML** (sha256 も旧 manifest の記録と一致)。
  6/17 は archive に 2 本あるが、旧と同じ `082325` を使った。旧成果物が無い 4 日は、builder の既定の規則
  (`predictions_source_*.html` を名前で並べた最後) と同じものを明示して渡した

### 修復後の件数 (builder を使わない独立チェックで確認)

| date | HTML レース (対象日 / 別の日) | 外した頭数 | 評価行 (evaluable / total) | ◎ 評価可 N / 的中 | 賭け金 / 損益 (円) | 返還 | DB 当日 JRA レース |
|---|---|---|---|---|---|---|---|
| 2026-07-18 | 36 / 36 | 31 | 468 / 468 | 36 / 6 | 0 / +0 | 2 | 36 |
| 2026-08-08 | 36 / 36 | 30 | 462 / 462 | 36 / 12 | 300 / -300 | 2 | 36 |
| 2026-08-15 | 36 / 36 | 32 | 487 / 487 | 36 / 11 | 600 / -600 | 2 | 36 |
| 2026-08-22 | 36 / 36 | 26 | 477 / 477 | 36 / 12 | 800 / +160 | 6 | 36 |
| 2026-08-29 | 36 / 36 | 20 | 494 / 494 | 36 / 8 | 0 / +0 | 4 | 36 |
| 2026-09-05 | 36 / 36 | 27 | 455 / 455 | 36 / 11 | 0 / +0 | 3 | 36 |
| 2026-09-12 | 24 / 24 | 28 | 316 / 316 | 24 / 3 | 0 / +0 | 1 | 24 |
| 2026-06-12 | 0 / 168 | 1416 | 0 / 0 | 0 / 0 | 0 / +0 | 0 | 0 |
| 2026-06-17 | 0 / 36 | 485 | 0 / 0 | 0 / 0 | 0 / +0 | 0 | 0 |
| 2026-07-03 | 0 / 72 | 479 | 0 / 0 | 0 / 0 | 0 / +0 | 0 | 0 |

独立チェック (`data/backtest/cross_date_repair_20260928/verify.py`) で 10 日とも成立したこと:
HTML の race ID から日付を分類した件数と manifest の件数 (`html_races_parsed` / `foreign_date_races_dropped` /
`foreign_date_predictions_dropped` / `foreign_date_race_ids` / `predictions`) が一致 / **出力 CSV 5 本に
race_date ≠ 対象日の行が 0** / ◎ が 2 頭以上のレース 0 / HTML の対象日レース集合 ⊆ DB の当日 JRA レース集合
(開催日 7 日は一致) / HTML の対象日レース数 = 扱ったレース数 + 馬の行が無いレース数 / evaluable + excluded = total /
評価外・返還の行は settled と profit が 0、settled ≤ planned、買い候補でない行は planned 0。
git 管理下に書いた CSV は、独立チェックを通した scratch の CSV とバイト単位で一致 (manifest の差は
`generated_at` と `supersedes_manifest_sha256` だけ)。

### 旧 → 新の差分 (旧成果物がある開催日)

旧 builder には `evaluable` 列が無いので、旧の「◎ 評価可 N」は **◎ で着順が付いた行** と定義した。

| date | 行数 旧 → 新 | ◎ 評価可 N 旧 → 新 | ◎ 的中 旧 → 新 (的中率) | 外したレース / 頭数 | 賭け金 / 損益 旧 → 新 | 返還の行 旧 → 新 |
|---|---|---|---|---|---|---|
| 2026-07-18 | 499 → 468 | 37 → 36 | 6 → 6 (16.2% → 16.7%) | 36 / 31 | 0 / 0 → 0 / 0 | 列なし → 2 |
| 2026-08-08 | 492 → 462 | 37 → 36 | 13 → 12 (35.1% → 33.3%) | 36 / 30 | 300 / −300 → 300 / −300 | 列なし → 2 |
| 2026-08-15 | 519 → 487 | 38 → 36 | 12 → 11 (31.6% → 30.6%) | 36 / 32 | 600 / −600 → 600 / −600 | 列なし → 2 |

- **金額の差は 0 でも、N と的中率は変わった** (混入した翌日の ◎ が 1〜2 頭、N と的中に入っていた)
- 旧成果物の「◎ が 2 頭並ぶレース」は各日 2 → 修復後 0

### 開催の無い 3 日 (REPAIRED_NO_TARGET_DATE)

builder は変えていない (manifest に明示の `evaluation_status` を足すのは次のサイクルで、要合意)。
次の条件をすべて満たすことを独立チェックで確かめ、この台帳で `REPAIRED_NO_TARGET_DATE` と判定した。

| 条件 | 6/12 | 6/17 | 7/03 |
|---|---|---|---|
| predictions = 0 | 0 | 0 | 0 |
| html_races_parsed > 0 | 168 | 36 | 72 |
| foreign_date_races_dropped = html_races_parsed | 168 = 168 | 36 = 36 | 72 = 72 |
| 対象日の HTML レース (独立チェック) = 0 | 0 | 0 | 0 |
| 評価可 N = 0 / 的中率 | 0 / N/A | 0 / N/A | 0 / N/A |
| settled stake = 0 / profit = 0 | 0 / 0 | 0 / 0 | 0 / 0 |
| 旧成果物の金額 (架空) | 27 件・−2,700 円 | 9 件・−900 円 | 0 |

- **6/17**: DB-derived result artifacts contain 75 rows (`final_odds.csv` / `race_results.csv`、地方交流の
  7 レース、track 30 / 45 / 48 / 50。旧成果物では 32 行で、DB 側に後から結果が入った), but target-date
  predictions are 0; these rows do not constitute an evaluated prediction set.
  判定に使うのは「DB に当日の結果行があるか」ではなく「その日の HTML に評価対象の予想があったか」
- 3 日とも、通常の成績集計に **絶対に含めない**

### 修復で残したバックログ

- `BUILD_DAILY_RESULTS_READONLY_DB`: `main()` の `sqlite3.connect(args.db)` を読み取り専用 (`db.open_db_readonly` / `mode=ro`) に。次に builder 本体を触るサイクルで、挙動テスト付きで
- manifest に `evaluation_status` (例: `NO_TARGET_DATE_PREDICTIONS`) を明示する (要合意)
- 入力の不変量違反 (◎ 2 頭など) の終了コードが、`--date` 不正・HTML 不在と同じ 2。別の値にするか runbook に stderr での見分け方を書く
- 変異の結果ファイルに、コピーの元 SHA・spec の hash・日時を付ける (2 回目の実行から実施)

## 関連する既知の互換性問題

- 2026-06-07〜08-16 の管理済み 21 日分は旧スキーマで、`horse_refunded` 列が無い。
  過去の返還 ◎ が不的中に数えられる (実害が確認できたのは 2026-07-11 の 1 レース、金額 0)。
  成績の主張に使う前に再生成が要る。上の INVALID と同じく、修復まで成績の主張には使わない。
- 2026-09-28 に再生成した日 (6/12・6/17・7/03・7/18・8/08・8/15) は新しいスキーマ (`horse_refunded` 列あり) になった。
  それ以外の旧スキーマの日はまだ残っている

## 有効な評価成果物 (新 evaluator `8a91d73` で初回生成、2026-09-25)

混入 0・◎ が 2 頭並ぶレース 0・manifest と CSV のハッシュ一致・除外行の金額 0 を確認済み。

| date | rows | evaluable | excluded (理由) | 返還馬 | ◎ 評価可 / 的中 | 買い候補 |
|---|---|---|---|---|---|---|
| 2026-08-23 | 466 | 466 | 0 | 1 | 36 / 9 | 0 |
| 2026-08-30 | 479 | 479 | 0 | 2 | 36 / 8 | 0 |
| 2026-09-06 | 491 | 491 | 0 | 0 | 36 / 7 | 0 |
| 2026-09-13 | 314 | 314 | 0 | 1 | 24 / 5 | 0 |
| 2026-09-19 | 287 | 287 | 0 | 1 | 24 / 7 | 0 |
| 2026-09-20 | 334 | 334 | 0 | 0 | 24 / 5 | 0 |
| 2026-09-21 | 320 | 159 | 161 (cancelled) | 1 | 12 / 3 | 0 |
| 2026-09-22 | 161 | 161 | 0 | 0 | 12 / 2 | 0 |

- `builder_git_dirty=true` は main checkout に untracked の成果物 (scorecards / backtest json など)
  があったため。tracked の差分は 0 で、builder のコードは SHA `8a91d73` と一致する。
  manifest は手で書き換えていない。将来 provenance を `tracked_dirty` / `untracked_present` に
  分ける案はコード品質のバックログ (JST 統一の後)。
- ◎ の数字は小標本で、予測能力の評価ではない。評価の会計が正しく動いたことの確認として扱う。
