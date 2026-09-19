# 予想ロジック分析官 採点 — 通知重複抑止 (commit `b437db3`, branch `notify-dedup-20260919`)

## 判定: PASS

**改修タイプ**: type-B 相当 (運用/通知層)。`git show HEAD --stat` の変更は `scripts/notify_dedup.py` (新規) / `scripts/auto_predict.py` / `tests/conftest.py` / `tests/test_notify_dedup.py` / `docs/OPERATION.md` の 5 件のみ。`predictor/` `web/` `config.py` `db.py` `scripts/backtest.py` への差分は **0 行** (`git diff HEAD~1 HEAD --stat -- predictor web config.py db.py scripts/backtest.py` が空)。P25 固有ゲート (A/B/C 層 factorial / bonus_subset_metrics / calibrator refit / market_snapshot) は **N/A (対象外)**。

**理由**: 予測側不変を依頼者の主張とは独立に 5 経路で確認し、すべて成立。通知抑止は「生成・中止の判定 → 終了コード」の**後段**にだけ挿入されており、`decide` / `record` / `_notify` はいずれも例外を投げない設計 (`scripts/notify_dedup.py:160-183, 196-208`, `scripts/notify_discord.py:31-39`) なので、exit 0/1/2/3 の分岐条件は改修前と同一。封印窓のレース数カウントに通知層を参照する経路は存在しない。

**根拠ファイル**: `scripts/auto_predict.py:116-153, 230-273, 314-318`、`scripts/notify_dedup.py:58-70, 150-208`、`tests/conftest.py:14-26`、`config.py:250-298`

**次アクション**: 自然スケジュール実行 (次開催日 08:00/09:00/10:00 の 3 起動) で `notify suppressed (generation_complete:YYYYMMDD): duplicate` がログに 2 回出ることを 1 度観測する。予測側の追加検証は不要。

## 総合: 4.7 / 5 (参考スコア)

## 予測不変の独立検証 (依頼者の 4 主張を鵜呑みにせず再導出)

| # | 検証 | 方法 (本セッションで実行) | 結果 |
|---|---|---|---|
| 1 | 封印 6 成果物のハッシュ不変 | `config.artifact_drift()` は `SEALED_FROM=None` のため **無条件で `[]` を返す短絡** (`config.py:286-287`) があり、依頼者が使った経路では一致の証拠にならない。`SEALED_ARTIFACTS` の 6 件を sha256 で**直接**再計算 | **6/6 一致、mismatch 0** |
| 2 | generator/predictor が通知層を import しない | `import web.generator, predictor.rules, predictor.features` 後の `sys.modules` を走査 | `notify` / `auto_predict` を含むモジュール **0 件** |
| 3 | 通知層が予測側を import しない (逆方向) | `scripts.notify_dedup` の import 閉包を差分計測 | プロジェクト内は `config`, `scripts`, `scripts.notify_dedup` のみ。`predictor`/`web`/`db` 無し |
| 4 | prediction_log 不変 | 全行を主キー順で sha256 | **18,893 行、`799d0697942870f2`** (依頼者の行数と一致。before ハッシュは私の手元に無いので「行数一致 + 差分に DB 書込コードが無い」までが事実) |
| 5 | 既存テストへの副作用 | 新 autouse fixture 下で predictor/calibrator/filter/sealed/guard 系 97 件 + 通知/auto_predict/sealed 53 件を実行 | **150 passed, 6 skipped、失敗 0**。実行後も `data/runtime/notification_state.json` は**生成されず** (本番 state 汚染なし) |

HTML の連続再生成 (変更後→変更前→変更後) は本セッションでは**未実施** (live odds が動くため再現は依頼者の連続 3 本より弱い証拠になる)。代替として上表 2・3 の import 閉包 + 終了コード経路の静的同一性で閉じた。

## 依頼 3 点への回答

**(a) artifact_drift 中止通知の抑止でモデル差し替え検知が遅れる経路** → **無い**。
- 現状 `SEALED_FROM=None` なので `artifact_drift()` は封印開始前は**常に空** = 検知そのものが未稼働。今回の抑止は稼働後の挙動にのみ関係する。
- 稼働後: キーは `artifact_drift_abort:<day>` で **日付が subject に入る** (`scripts/auto_predict.py:257`)。初回起動は必ず `first_time` で送信、同日 2・3 回目は `sorted(drift)` が同一なら抑止、drift 集合が変わればキー付き差分で再送 (`notify_dedup.py:167-177`)。翌日は別キーで再送。→ **検知遅延は 0 (当日初回で必ず届く)**、抑止されるのは同日同内容の 2 通だけ。
- 送信失敗時は記録しない (`auto_predict.py:135-141`) ので、webhook 不通で握り潰される経路は改修前より**改善**。
- 封印窓の判定 (`guard_analysis_window` / `sealed_window_active`) は通知状態を一切読まない (`config.py:260-346`、grep `notification|notify|auto_predict` が `config.py` `predictor/**` `scripts/f3_*.py` で 0 件)。

**(b) conftest autouse fixture の副作用** → **無い**。
- 効果は環境変数 `NOTIFY_STATE_PATH` を per-test tmp に向けるだけ。`predictor/` `web/` はこの変数を読まない (grep 0 件)。
- teardown の `os.environ.pop` (`conftest.py:26`) は monkeypatch の undo と重複 (依存関係上 pop → monkeypatch 復元の順で走るので外部設定値も最終的に復元される)。**冗長だが無害** = dead code 1 行。
- 副次コスト: 全 646 テストで `tmp_path` ディレクトリが 1 つずつ作られる。実測 97 件 1.9s で無視できる。

**(c) 通知抑止で「生成されなかった日」が見逃され封印窓レース数がずれる経路** → **無い**。
- 生成有無は `main()` の exit 2/3 分岐 (`auto_predict.py:230-260`) で決まり、通知はその**後**に呼ばれる。`_notify_once` は例外を投げず、戻り値は捨てられているので分岐に逆流しない。
- coverage_abort は payload に `with_entries/total` を含む (`auto_predict.py:239-240`) ので、取込が進んで数値が動けば「変更あり」で再送され、3 回同じなら 1 通に畳まれる。中止の**事実**は毎日初回で必ず届く。
- 封印窓のレース数は DB (`races` / `prediction_log`) から数える設計で、通知状態ファイルを読む消費者はリポジトリ内に **0 件** (`notification_state` の参照は `notify_dedup.py` / tests / docs のみ)。

## 項目別

- **シグナル網羅性と市場残差性: 5/5** — 予測シグナルの追加・削除なし。差分 0 行を `git diff --stat` で確認 (上記)。
- **重み妥当性 / 過適合リスク: 5/5** — `weights.json` `calibrator.json` `lgbm_*` `second_blend.json` の 6 件 sha256 が `SEALED_ARTIFACTS` と一致 (独立再計算)。paired ablation は N/A。
- **信頼度判定 / 確率推定の構造: 5/5** — raw→blend→calibrate→normalize 経路に差分なし。`web.generator` の import 閉包に通知層が入らないことを実測。
- **デッドコード / 設計の整合性: 4/5** — 留保 3 件: (i) `conftest.py:26` の `os.environ.pop` は monkeypatch と重複する dead code。(ii) `_notify_once` は抑止時に `True` を返す (`auto_predict.py:131`) = 「送った」と「送らなくてよかった」が同値。現状は戻り値未使用なので実害なし、将来 `push_ok` 同様に payload へ載せると誤情報になる。(iii) subject の `day` は `date.today()` (ローカル) で、dedup の `date_jst` は JST 固定 — 同一マシン (JST) では一致するが 2 つの時計を混在させている (`auto_predict.py:199`, `notify_dedup.py:73-75`)。
- **本番運用との乖離リスク (train-serve skew): 4.5/5** — 予測経路の入力・コードパスに変化なし。開発中に本番 state へ書かれた架空 `total: 2` は**既に存在しない**ことを確認 (`data/runtime/notification_state.json` 不在)。留保: `artifact_drift()` が封印開始前は短絡で空を返すため、「封印ハッシュ不変」の運用確認は `artifact_drift()` ではなく直接ハッシュで行う必要がある (docs/OPERATION.md の記述はこの区別をしていない)。

## 停止条件チェック

- [x] 改修タイプを type-B (通知層) と分類し、predictor/web/config 差分 0 行を確認
- [x] 封印成果物 6 件のハッシュを独立再計算して一致
- [x] import 閉包を双方向で実測 (generator→通知層 0 件、通知層→predictor 0 件)
- [x] 新 fixture 下で predictor 系 97 件 + 通知系 53 件 pass、本番 state 未生成
- [x] 終了コード分岐 (0/1/2/3) が通知結果に依存しないことをコードで確認
- P25 再現性メタ / paired baseline / market_snapshot / payout 欠損 / calibrator refit: **N/A (type-A でない)**

## 反証の試み

1. 「封印モデル 6 点のハッシュ不変」に対し、依頼者の確認手段と同じ `artifact_drift()` は **`SEALED_FROM=None` で常に空を返す**ため証拠能力が無いと疑い、直接 sha256 で再計算 → 6/6 一致で**主張は成立**(手段だけが弱かった)。
2. 「抑止で中止通知が消える」に対し、`_load` が壊れた JSON / 非 dict を返す・`_prune` が非 dict 値で AttributeError を起こすシナリオを追った → いずれも `decide` の外側 try で `fail_open:*` として**送信側に倒れる** (`notify_dedup.py:180-183`)。不成立。
3. 「テストが本番 state を汚す」に対し、通知・auto_predict・sealed テスト 53 件を実行後に `data/runtime/notification_state.json` の存在を確認 → 不在。不成立。

## 主な改善提案

1. **`_notify_once` の戻り値を 3 値化 or 抑止時 `None`** (`scripts/auto_predict.py:131`) — 「送信成功」「抑止」「送信失敗」を区別し、将来 payload や監査ログに載せても誤読しない契約にする。
2. **`conftest.py:26` の `os.environ.pop` を削除** — monkeypatch が復元する。二重管理は「片方だけ変えると壊れる」欠陥クラス (本改修が `_key()` で潰したのと同型)。
3. **`docs/OPERATION.md` の「封印モデル成果物 6 点のハッシュ不変」の確認手順を明記** — `artifact_drift()` ではなく `SEALED_ARTIFACTS` の直接 sha256 比較を書く。封印開始前は前者が常に空で、確認したつもりになる罠。

## 前回からの差分

- 前回 (`20260919_1100_phase05_4b_foundation`): HOLD 3.6 — 対象が予測モデル (type-B 分析基盤) で本改修と領域が異なるため直接比較不可。同種の運用層改修 `20260808_0940_auto_predict_watchdog`: PASS 4.8。
- 項目別 (watchdog 比): 網羅性 5 → 5 / 重み 5 → 5 / 確率構造 5 → 5 / 設計整合性 4.5 → 4 (−0.5: 戻り値契約・冗長 pop・時計混在の 3 留保) / skew 4.5 → 4.5。総合 4.8 → 4.7。1 点を超える変動なし。
- 判定 PASS。Phase 0.5-4B の HOLD 事由 (h_history_truncated の時間代理性) は本改修の対象外で未解消のまま (越権採点しない)。
