# Codex 作業指示: 2026-07-12 生成結果監査で確定した 3 バグの修正 + 汚染調査

前提: `data/results/2026-07-12/audit_findings.md` の監査で問題 1/2/4 が確定済み
(問題 3 は修正対象外。根因の裏取りは Claude Code 側で完了しており、以下の記述が正)。

起動前の推奨設定:

```
cd C:\Users\kizun\dev\keiba-yosou
codex            # 新規セッションで開始
codex> /model    # reasoning effort = medium
```

---

## ここから Codex へのプロンプト本文

競馬予想パイプラインの生成スクリプトに確定済みバグが 3 件あります。修正・テスト追加・
再生成・検証まで行ってください。説明文は最小限、差分ではなく実ファイルに書くこと。

### 対象ファイル (これ以外は編集しない)

- `scripts/build_daily_results.py` (602 行) — 修正対象本体
- `tests/test_build_daily_results.py` — 新規作成 (テスト)
- `data/results/2026-07-12/*.csv` — 再生成で更新される
- 調査タスク D のみ `predictor/features.py` を **読み取り専用** で参照可

### 禁止事項

- `data/keiba.db` (288MB) を read しない。確認は `sqlite3` CLI の結果だけ使う
- `data/results/2026-07-12/predictions_source_*.html` (370KB) を全文 read しない。
  検証は grep / python ワンライナーで該当箇所のみ抽出
- `predictor/` 配下のコードを **編集しない** (調査タスク D は報告のみ)
- `data/results/2026-07-12/audit_findings.md` は監査記録なので変更しない

### タスク A: オッズ・人気の連結破損を修正 (audit 問題 1)

**現象**: `predictions.csv` の `morning_odds` / `morning_popularity` が非空 169 行すべてで破損。
HTML の td 内容 `22.9<br><span class='pick-reason'>6人気</span>` が区切りなしで
`22.96人気` に連結され、`^\s*([\d.]+)` が `22.96` を、`(\d+)人気` が `310` (`77.310人気` から)
を拾う。

**該当コード**: `scripts/build_daily_results.py`
- L173 付近: `"".join(self._td_buf)`
- L190-198: オッズ列の正規表現処理 (「span end で吸収済」コメントは誤りなので削除)
- L266 付近: `self._td_buf.append(data)` (handle_data)

**修正方針**: span 内テキスト (`pick-reason`) を `_td_buf` と別バッファに分けるか、
handle_data で区切り文字を挟む。修正後、`20260712-02-01` の 11 番が
`odds=22.9 / popularity=6`、1 番が `77.3 / 10` になること。

### タスク B: horse_num='00' プレースホルダ行の除外 (audit 問題 2)

**現象**: `final_odds.csv` / `race_results.csv` に全 36 レース分の幽霊行が混入
(506 行 = 470 正規 + 36 幽霊)。

**根因 (確定済み、監査所見の推定とは異なる)**: DB の `horse_races` に
`horse_num='00'` のプレースホルダ残骸行が 2026-05-10 以降の全開催日に存在する
(枠順確定前データの PK 衝突残骸、DB 全体で 406 行)。`scripts/backtest.py:587` は
既に `AND horse_num != '00'` で除外しているが、`build_daily_results.py` の
SQL (L351-358 と L360 付近の 2 クエリ) にはフィルタがない。

**修正方針**: 両クエリの WHERE 句に `AND horse_num != '00'` を追加
(backtest.py:573-588 の書き方に合わせる)。DB 側の 406 行は**消さない** (別タスク)。

### タスク C: race_num のゼロ埋め統一 (audit 問題 4)

**現象**: `predictions.csv` / `evaluation_summary.csv` は `1`〜`12`、
他 3 CSV は `01`〜`12`。

**該当コード**: L403 (predictions 側の整数 `rn` 出力)、L433 / L453 / L471 (DB 側)、
L383-385 (`race_id_of` は既に 2 桁化済み)。

**修正方針**: 全 CSV を 2 桁ゼロ埋め文字列 (`01`〜`12`) に統一。

### タスク D: features.py の '00' 行汚染調査 (読み取り専用・報告のみ)

`predictor/features.py` には `FROM horse_races` を参照するクエリが十数箇所ある
(L132, L190, L200, L257, L297, L330, L355, L377, L420, L476 ほか)。
`horse_num='00'` の残骸行 (win_odds=0, win_popularity=0, confirmed_order=0,
odds_fetched_at=NULL) がこれらのクエリ結果に混入し、**近走成績・着順系の特徴量を
汚染しうるか**を各クエリについて判定せよ。

判定観点: そのクエリは (1) horse_num で絞るか、(2) confirmed_order 等の条件で
'00' 行が自然に落ちるか、(3) 落ちない場合どの特徴量にどう影響するか
(例: 同一馬の同一レースが 2 行になり出走数が水増しされる、着順 0 が集計に入る)。

**コードは修正しない**。結果は `data/results/2026-07-12/features_00_contamination.md` に
クエリごとの判定表 (行番号 / 汚染あり・なし / 理由 / 影響する特徴量名) として書き出す。

### テスト (タスク A/B/C に対して)

`tests/test_build_daily_results.py` を新規作成:
1. タスク A: `22.9<br><span class="pick-reason">6人気</span>` を含む最小 HTML 断片を
   `IndexHtmlParser` に食わせ、odds=22.9 / popularity=6 になること
2. タスク B: in-memory SQLite に horse_num '00' と '01' の 2 行を入れ、
   出力に '00' 行が含まれないこと
3. タスク C: 出力 CSV の race_num が全 CSV で 2 桁ゼロ埋めであること

実行: `.venv64/Scripts/python.exe -m pytest tests/test_build_daily_results.py -q`
既存テストのグローバル破壊がないことも確認: `.venv64/Scripts/python.exe -m pytest tests/ -q`

### 再生成と検証

```
.venv64/Scripts/python.exe -m scripts.build_daily_results --date 20260712 ^
  --html data/results/2026-07-12/predictions_source_20260712_git2642e8c.html
```

再生成後、python ワンライナーで以下を確認して数値を報告:
1. final_odds.csv / race_results.csv が 470 行 (ヘッダ除く) になった
2. predictions.csv の morning_popularity は全行 1〜18
3. `20260712-02-01` の 11 番: odds=22.9 / popularity=6、1 番: 77.3 / 10
4. 全 5 CSV の race_num が 2 桁ゼロ埋め
5. evaluation_summary.csv の profit_loss_yen_100unit 再計算が引き続き全行一致
6. manifest.json の counts が新 CSV と一致 (counts の期待値も 470 に変わる)

### 成果物

- 修正済み `scripts/build_daily_results.py` + 新規テスト
- 再生成された CSV 一式 + 更新された manifest.json
- `data/results/2026-07-12/features_00_contamination.md` (タスク D)
- 最後に「変更ファイル一覧 + 検証 6 項目の結果 + タスク D の汚染あり件数」を
  10 行以内で報告して終了。git commit はしない (レビュー後に人間側で行う)

---

## (Claude Code 側メモ — Codex には渡さない)

- Codex 完了後、`scripts/` 編集につき **expert-review (D1) 必須**。その前に worktree/
  親リポ同期状態を確認 (CLAUDE.md ルール 1-bis)
- タスク D の結果次第で、ingest 側の '00' 行防止 + DB 掃除 (406 行) を別改修として起案
- 問題 3 (odds_fetched_at NULL 11 レース) は fresh odds カバレッジ監視の話として
  monitor 側で扱う
