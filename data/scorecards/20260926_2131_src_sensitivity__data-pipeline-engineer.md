# データパイプライン技術者 採点 — 3fea521 「Phase 0.5-4B T−10 市場の取得元に対する感度分析」

**subagent CWD 限定運用での評価 (worktree 絶対パス指定)**: 対象 SHA `3fea5218f34b65c833d2d6b824d78f35fd00c9cd` (branch `t10-source-sensitivity-20260926`、base main `491d2e6`)、worktree `C:\Users\kizun\dev\keiba-yosou\.claude\worktrees\src-sens`。git はすべて `git -C <worktree>`。開始時・終了時ともに `rev-parse HEAD` = 3fea521、`status --porcelain` 空。本番 `keiba.db` は `mode=ro` URI でのみ開いた (data_version `44292:3527feed56`、成果物 manifest と同一)。raw は読み取りのみ。再実行は `--out-dir` を scratchpad (`...\scratchpad\review_dpe\out`) に向けて 1 回 (約 6 分、exit 0)。独自の検証スクリプト 3 本 (verify.py / verify2.py / verify3.py) は scratchpad 内のみで、対象スクリプトの関数は使わず自前で raw を読み直した (author の実装に依存しない再計算)。main checkout / worktree / ai-builder / Task Scheduler / プロセスには触れていない。

## 判定: PASS

**理由**: 感度分析の**データ層の前提 (raw から組み直した T−10 市場が、PIT 規則を守り、DB 経路と同じ意味の値を持つ) は独立再計算で全項目成立**。(1) original_mixed は 4B 成果物と集合・β₂・LogLoss が完全一致。(2) raw 系列の `received <= cutoff` は `_pick` と `build_market` の二重で強制され、出力 CSV の `lead_min` 最小は 10.05 分 (= cutoff 以後の raw は 1 行も出ていない)。(3) 同じ秒の両取得元 = 28 レースを自前で再現、宣言規則 (票数合計の多い方 → 0B31) と一致、manifest に件数あり。(4) 共通 626 レースで raw_mixed と DB の T−10 オッズは 626/626 で完全一致 (自前再計算: オッズ 626 一致、受信秒まで一致 622 / 1 秒差 4 — 後述の mtime 由来)。分類 858/281/3/0/34 も自前再計算と一致。(6) 結論は判定可能 3 系列のみに基づき、raw_0B30 / matched_same_state は「否定にも肯定にも使わない」と明記。成果物は**再実行でバイト一致** (series_summary / common_fresh_set / samples CSV / selection_classes の sha256 同一、bootstrap CI 込み)。

PASS の留保 (FAIL/HOLD にはしない理由つき):
- **(5) 50% 閾値の事前固定は git からは証明できない** (script + 結果が同一 commit、reflog は 1 件、main の docs にも閾値の事前宣言なし)。成立側の証拠は manifest の `script_sha256` が commit 版と一致 (= 走ったコードは commit されたもの) と docstring の宣言のみ。**raw_0B30 は 300 レースで閾値 313 の 13 レース下**、しかも唯一 `rejected_by` が非空 (棄却条件 2) なので、閾値が 47.9% 以下なら「結論が同じ」判定は False になる。文書は棄却該当を開示しているので隠匿ではないが、閾値感度は次アクションで補う。
- 受信時刻の由来は「ファイル名 epoch」で統一されているが、**DB の live 行 (0B31 7/18 以降、ai-builder 0B30) の fetched_at は file mtime**。両者は 96 本 (0B30 78 / 0B31 18) で ±1 秒ずれる。実害は自前で測って **ゼロ** (整数秒 mtime を受信時刻にしても 3 raw 系列の選択はファイル・票数・オッズとも 1 件も変わらない、verify3)。ただし文書の「backfill_odds_snapshots と同じ由来」は backfill 行にしか当たらないので、表現を正確にする (下記)。

## 対象・改修タイプ

- diff `491d2e6..3fea521`: `scripts/t10_source_sensitivity.py` (+384)、`docs/PHASE05_4B_SOURCE_SENSITIVITY.md` (+92)、`data/backtest/src_sensitivity_20260926/*` (10 files)。取得・ingest・schema・predictor は不変。
- 改修タイプ: **type-B (診断/分析ツール)**。P25 固有ゲート (fresh odds スケジューラ / coverage JSONL / market_snapshot counts / bonus_candidate) は **N/A (対象外)**、fresh odds を総合判定のゲートにしない。適用したのは汎用ゲート: DB 読み取りの副作用なし / raw 再構築の正しさ / PIT 規律 / 成果物の再現性・命名 / 判定不能系列の扱い。

## 総合: 4.6 / 5

## 項目別

- **DB 読み取りの副作用なし / 成果物の隔離: 5/5** — `market_offset_eval` は `mode=ro` URI (`:123,:205`)、本スクリプトは DB を開かない。出力は `--out-dir` 必須で **空でない出力先は拒否** (`:244-245`、4A/4B の JSON を上書きしない設計)。再実行後も worktree・親リポとも modified 0。
- **raw 再構築の正しさ (分割 / O1 限定 / 票数 offset / odds>0 / 馬番 / race key): 5/5** — `_split_records` + `rec[:2]==b"O1"` は backfill と同じ経路。window 内 raw 10,521 レコードはすべて長さ 960 (`\r\n` 除去後、`parse_o1` が 962 に pad) で、票数 `rec[927:938]` (仕様 pos 928 / 11 byte、1 始まり → 0 始まり 927) は **非数字 0 件、同一レース・同一取得元で連続 8,227 組すべて非減少** (累計票数の性質と整合 = offset が正しい構造的証拠。PDF の文字抽出は環境に poppler/pypdf が無く未実施、3-bis の記述と構造検査で代替)。odds>0 は `parse_o1` (`:481`) が両経路の共通上流なので DB の `win_odds > 0` と同値。馬番は `_ascii` で strip 済 + `h.strip()`。ファイル名 16 桁キーと O1 レコード内キーの不一致 0、race_id 形式は `RACE_KEYS` と同じ `-` 結合で eval 側と一致 (黙って落ちるレース無し: raw_mixed の no_t10 107 = raw 無し 16 + 全 raw が cutoff 後 91、自前再計算で分解できた)。
- **PIT 規律と時刻の由来: 4.5/5** — `received <= cutoff` を選択と監査の 2 箇所で強制、`decision_time` (発走時刻変更の既知性込み) は DB 経路と同じ関数。全 raw 系列の CSV で `lead_min >= 10.05`。選ばれた state の `data_div` は全系列 **'1' のみ** (raw には 0B31 '4' 856 / '3' 16 / '2' 2、0B30 '3' 21 / '4' 1 が存在するが、いずれも cutoff 後で選択されない — 確認済)。減点: epoch vs DB mtime の 1 秒差 (上記) と、その結果 DB 側で `announced_at` が NULL の 4 レース (`2026-0718-03-02-07-12` 等) では DB 経路の発表時刻監査が空振りし raw 経路だけが検査している、という非対称が文書化されていない。実害ゼロは実測したが、由来の記述は「backfill 行は epoch、live 行は mtime、差は ±1 秒 96 本、選択への影響 0」まで書くべき。
- **0B30/0B31 の分離・分類・同秒規則・共通集合: 5/5** — 分類は自前実装で 858/281/3/0/34 を再現。28 の同秒組は **27 が同一市場状態**、1 件 (`2026-0823-01-02-02-09`: 0B30 186,698 票 vs 0B31 202,384 票、同じ 14:20:02 受信) だけ状態が違い、規則どおり票数の多い 0B31 が選ばれ、DB (REPLACE の勝者) も偶然同じ 0B31 の値だった → 「同じ秒の上書きは 626 レースの T−10 を 1 レースも変えていない」は成立。matched_same_state 34 は 3 例とも受信 epoch まで同一 = 実質「同じ秒に両方が取りに行った」集合で、0B31 の取得間隔 (レースあたり約 2 本) と 0B30 (約 17 本) の粒度差から必然的に小さい。文書は「8 月 1 か月分」を理由にしているが、**取得間隔の差が根本原因**なので追記推奨。
- **事前固定・判定不能系列の扱い・再現性メタ: 4/5** — manifest に script/prod git_sha・script sha256・model 4 本の sha256・DB data_version・時刻由来・同秒規則・読み方の規則・選択監査件数・4B 再現を記録。**再実行で全成果物がバイト一致**。減点: 閾値の事前固定が外部証拠で確認できない + raw_0B30 が閾値の直下で唯一 `rejected_by` 非空 (上記)。samples CSV に系列ごとの「選ばれた取得元 / 受信時刻 / 票数」列が無く、レース単位の出自は成果物から復元できない (集計 `selection_audit_counts` と各 3 例のみ)。
- **7 月欠落・異常ファイルの取り扱い: 4.5/5** — 7/04・05・11・12 の 0B31 raw = 80+116+116+56 = **368 本を実測**、DB `odds_snapshots` はこの 4 日 **0 行**、backfill は 6/28 が最終日、live 0B31 は 7/18 開始 — 3-ter の主張どおり。8 月 0B31 raw 978 / DB 697 も一致。名前が二重の `*.jvd_*.jvd` 1,980 本は **全て 0 バイト** (find -size +0 → 0)、通常名で 0 バイトのものは 0 本、manifest では `0B31_name_not_matched: 1980` として件数だけ記録 (「0 バイト」であることは文書側に記述、manifest には無い)。mtime≠epoch 96 本は件数を記録し差は ±1 秒。減点: 二重名 0 バイト raw は data/raw の衛生問題として別 ticket 化されていない。

## 必須確認 6 点

| # | 確認 | 判定 | 根拠 |
|---|---|---|---|
| 1 | original_mixed が 4B を再現 | **成立** | manifest `reproduction_of_4B.sets_equal=true`、β₂ 0.4996637467589598 / LogLoss 0.21348138623836102 が ref と同値。再実行でも同じ |
| 2 | raw 系列が未来の raw を使わない / 時刻の由来が manifest にある | **成立** | `_pick` `s["received"] <= cutoff`、`build_market` violation → `not m10.ok` で除外 (eval `:142`)。CSV `lead_min` 最小 10.05。manifest `raw_received_at_origin` / `pit_rule` |
| 3 | 同秒規則が宣言と一致、件数 28 | **成立** | `_pick` sort key `(votes, source=="0B31")` reverse。自前再計算 28 (すべて 626 集合内)、manifest `same_second_both_sources: 28` |
| 4 | 626 の値差と集合差の分離 / spot check | **成立** | 626/626 オッズ一致 (自前)。spot: `2026-0509-08-03-05-01` raw 0B31 epoch 09:40:40 ann 05090940 odds 1064/483/158 ↔ DB 09:40:40 / 09:40 / 106.4/48.3/15.8; `2026-0808-01-01-05-08` 0B31 13:40:02 一致; 7/04 `2026-0704-02-01-07-01` raw 0B31 09:30:04 (26.2/1.8/3.0) が raw_mixed CSV と一致し DB は None (欠落の実証) |
| 5 | 50% 閾値の事後変更なし | **検証不能 (不成立の証拠も無し)** | 単一 commit・reflog 1 件・外部宣言なし。script sha256 = manifest。raw_0B30 300 vs 閾値 313 |
| 6 | 判定不能系列を結論に使っていない | **成立** | 文書「結論」は 3 系列のみ、raw_0B30 の棄却該当は「判定不能なので結論に使わない」と明記 |

## データ層の所見 (本改修の欠陥ではないが、本レビューで初めて機構を特定したもの)

1. **`scripts/backfill_announced_at.py` が同じ秒の衝突で `announced_at` を別取得元の値で上書きする** — 紐付けキーはファイル名 epoch、走査順は `RAW_DIRS = ("0B31","0B30",...)` なので **最後に当たる 0B30 の発表時刻が勝つ**。実例 `2026-0823-01-02-02-09` 14:20:02: DB 行は `source=0B31`・オッズは 0B31 の値だが `announced_at=08231418` (0B30 レコードの値、0B31 raw は 08231419)。また mtime≠epoch の live 行は epoch で照合できず `announced_at=NULL` のまま (626 集合中 4 レース)。3-bis の「同じ出自・同じ取得秒で発表時刻だけ 1 分違う 462 (原因未確定)」はこの機構で説明できる可能性が高い。DATA_PROVENANCE_DEFECT の台帳に追記推奨 (修正は JST 凍結明け、schema に `source` を主キーへ足す議論と同時)。
2. **「cutoff 以前で最新受信」は「最新の市場状態」と一致しない** — `different_state` 3 件のうち `2026-0808-04-02-05-03` は 0B30 (10:29:56 受信、161,532 票) が 0B31 (10:29:26 受信、162,165 票) より後に受信されたのに票数は少ない = 0B30 は配信が遅れる。T−10 規則 (pit_t10) が受信時刻のみで選ぶ限り、mixed-source 環境では稀に古い状態を選ぶ。本分析の結論には影響しないが、PIT データセット凍結前の規則設計で「票数合計を保存して後方比較できるようにする」ことを検討課題に。
3. `data/raw/0B31/` に二重名 0 バイト raw 1,980 本が残置 (live ingest の副産物と推定)。次回 ingest には無害 (O1 0 件) だが、ディレクトリ走査コストと監査の誤読を招く。

## 根拠ファイル

`.claude/worktrees/src-sens/scripts/t10_source_sensitivity.py:59,67-98,101-115,126-137,171-184,244-245,302-308,347-350`、`docs/PHASE05_4B_SOURCE_SENSITIVITY.md:22-29,41-45,59-63,77-85`、`data/backtest/src_sensitivity_20260926/{manifest,series_summary,common_fresh_set,selection_classes}.json`、`predictor/pit_t10.py:194-213`、`jvlink_client/parser.py:43-52,469-498`、`jvlink_client/ingest.py:106-124,139,169-184`、`db.py:969-994`、`data/schema.sql:645-664`、`scripts/backfill_odds_snapshots.py:23-40`、`scripts/backfill_announced_at.py:43-59,105-111`、`scripts/market_offset_eval.py:123,140-157`、3-ter: `git -C <worktree> show 56eeda9:docs/LIVE_INGEST_DATA_INTEGRITY_AUDIT.md` :183-198。本番 DB (ro) `odds_snapshots` 日別・source 別集計、`data/raw/0B30` 6,489 本・`0B31` 4,032 本 (window 内)。

## 次アクション

1. **閾値感度の追記 (小、文書のみ)**: 判定可能閾値を 40/45/50/55% で動かしたときの各系列の判定可否と「結論が同じ」の表を `PHASE05_4B_SOURCE_SENSITIVITY.md` に足す。raw_0B30 が 47.9% 以下で判定可能になり棄却条件 2 で「結論が違う」に転ぶ事実を明示する (隠れた分岐点をユーザに見せる)。
2. **時刻由来の記述を正確に**: 「raw は epoch、DB の backfill 行は epoch、live 行は mtime、差 ±1 秒 96 本、整数秒で選択への影響 0 (実測)」を manifest の `raw_received_at_origin` と文書に反映。
3. **samples CSV に出自列を追加** (`t10_source` / `t10_received_at` / `t10_votes` / `t10_announced`) — 次回以降、レース単位の追跡を成果物だけで可能にする。
4. **所見 1 を `LIVE_INGEST_DATA_INTEGRITY_AUDIT.md` に 3-quater として記録** (backfill_announced_at の上書き機構、実例 8/23 札幌 9R、NULL 4 例)。修正は凍結明けに `source` 主キー化と同時に設計。
5. 0 バイト二重名 raw 1,980 本の由来 (どの ingest 経路が作るか) を特定し、削除 or 生成停止の ticket 化 (type-C の別改修)。
