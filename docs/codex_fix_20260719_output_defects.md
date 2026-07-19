# Codex 作業指示: 予想出力 HTML の 3 欠陥是正 (完走型・全 4 ステージ)

前提: 2026-07-19 に公開中の予想 HTML (`web/dist/index.html`, Pages `552e949`) を 4 専門家が
精査し、全員 HOLD。監査記録は `data/scorecards/` ではなくメモリ + 本指示書に集約。
3 欠陥 (①観察専用開示が本文に無い ②印と勝率 P が別ランカーで 42% 矛盾 ③土曜生成<日曜 ingest で
毎週日曜が空) を **1 セッションで是正**する。**①は利用者の金銭的損失に直結する安全欠陥のため最優先**。

起動前:
```
cd C:\Users\kizun\dev\keiba-yosou
codex            # 新規セッション
codex> /model    # reasoning effort = medium
# ステージ間で /compact
```

---

## ここから Codex へのプロンプト本文

競馬予想の公開 HTML に、利用者を誤らせる 3 つの表示欠陥があります。**途中で人間に確認を
求めず、ステージ 1→4 を順に完走**してください。受入ゲート未達は自力で最大 3 回再試行、
それでも駄目ならスキップ理由を最終報告に記し残ステージを続行。説明は最小限、実ファイルに書く。

### 全体ルール

- 最初に `git status --short` を確認。tracked に未コミット変更があれば**着手せず報告して終了**
  (別ストリーム保護)。`git checkout -b codex/output-defects main` で新ブランチ。push しない
- コミットは最終ステージのみ `git add <個別パス>` 明示 (git add -A/-u 禁止)
- **触ってはいけない**: `data/backtest/20260703_*.json`, `predictor/_v5_backup/` は存在しないはず
  だが untracked があっても触らない。**`predictor/rules.py` の印割当ロジック・BUY_FILTER・
  weights.json・calibrator.json は変更しない** (監視下の戦略。本作業は表示層のみ)
- 専門家レビュー / scorecard の作成禁止。Discord 実送信禁止 (テストは mock)
- `data/keiba.db` (19GB) 直 read 禁止 (sqlite3 CLI 可)、DB の中身は変更しない
- `web/templates/index.html.j2` を編集したら **dist を再生成して目視/grep 検証**
  (`python-embedded-js` の対象は gui/app.py であり j2 は別。ただし j2 内に `<script>` があれば
  `node --check` 相当で構文確認)。ps1 は ASCII のみ

### ステージ 1 (欠陥①・最優先): 観察専用開示の常時表示 + バナー論理是正

対象: `web/templates/index.html.j2` / `web/generator.py` / tests

背景: 「観察専用・利益エッジ無し (OOS 回収率 CI 上限<100%)・EV は検証で anti-predictive と
確定・実弾購入不可」という前提が、レンダリングされる本文に **1 文字も無い** (CSS コメントと
`verification-banner` にしか存在せず、通常公開版では消える)。その状態で EV>1 の馬 (▲1.21/
☆1.16) を印付き表示 → 利用者が「EV+なら買える」と誤読し控除率超で資金を失う経路がある。

1-1. **観察専用バナーを body に常時出力**: `index.html.j2:539-556` 付近、`meta`/`filter-summary`
   の直後に、`ignore_odds_freshness` に依存しない**無条件**の常設バナーを追加する
   (既存 `verification-banner` は検証モード専用なので別 class、例 `observation-notice`)。
   文言 (簡潔・WCAG AA コントラスト、role="note"):
   「⚠ 本ページは観察専用です。OOS 検証で利益エッジは確認されていません (回収率 CI 上限
   <100%)。表示中の EV・印は購入推奨ではなく、実際の馬券購入には使用できません。」
   sticky header の高さ計算 (`:133` 付近のコメント) に影響するなら、その分の
   `scroll-margin-top` / padding を調整。
1-2. **見送りバナーの論理反転を是正**: `index.html.j2:640` の
   「EV/信頼度条件を**満たす**レースは見送り判定です」→ 実際の除外理由に合わせて是正。
   正しくは「買い条件 (1-3 番人気 かつ 予測勝率≤40%) を満たす馬がいないため全レース見送り。
   下の EV・印は観察用で購入推奨ではありません」。フィルタ表示 (`filter_summary`) の語彙と一致させる。
1-3. **EV 表示に anti-predictive 注記**: EV 列/値の近傍 (凡例 or 各 EV のツールチップではなく
   可視の 1 行) に「EV は検証で的中回収と結びつかないと確認済 (2026-06)」の注記を出す。
   EV 値自体の削除まではしない (数値は内部整合しているため)。凡例に 1 行が最小コスト。
1-4. **テスト**: 通常モード (`ignore_odds_freshness=False`) で render した HTML に
   `observation-notice` (常設バナー) が含まれること、見送り文言が新版であること、
   検証モードでは従来の `verification-banner` も併存することを assert
   (`tests/test_template_render.py` or 新規)。

**受入ゲート 1**: 通常モード dist に観察専用バナーが出力される (grep で本文に文言 1 件以上)、
見送り文言が是正済み、テスト green。

### ステージ 2 (欠陥②): 印と勝率 P の表示整合 (表示層のみ・戦略不変)

対象: `web/templates/index.html.j2` / `web/generator.py` / tests

背景: 印 (◎○▲△☆) は手作りルールスコア順 (`rules.py:1379`、LGBM 非含有)、表示 P は LGBM v6
ブレンド (`investment_probability`) で、**別ランカー**。7/18 の 38 レース中 16 (42%) で
◎ が最高 P 馬でない。利用者には「本命なのに自社モデルの勝率が 2 番手以下」= 内部矛盾に見える。
**印割当ロジック自体は監視下の戦略なので変更しない。表示で整合させる。**

2-1. **凡例に印と P の関係を明記**: 「◎○▲△☆ = 総合本命度 (ルール+人気の合成順)。P = 校正済み
   勝率 (LGBM v6 ブレンド、別指標)。両者は一致しないことがあります」を凡例/ヘルプに 1 ブロック追加。
2-2. **最高 P 馬の視覚マーカー**: レース内で `investment_probability` が最大の馬が ◎ と異なる場合、
   その馬の行に小さなバッジ (例 `<span class="top-p">最高勝率</span>`) を表示。generator 側で
   レースごとに argmax(P) を計算して view model に `is_top_p` 相当のフラグを渡す
   (`web/generator.py` の各馬 dict 構築箇所)。**印の値・順序は変えない**。
2-3. **P ラベルの頁内不統一を注記**: オッズ有レースの P は市場ブレンド済み、オッズ無レースの P は
   純モデル確率。同じ「P」表記なので、凡例に「オッズ確定前の P はモデル単独値」と 1 行注記
   (または view model に blend 有無フラグを持たせ、無い馬の P に `*` を付す — 簡潔な方)。
2-4. **◎ 根拠の可視化確認**: ◎ の rationale がプレビュー行に可視表示されているか確認し、
   `title` 属性のみ (iOS で不可視) の箇所があれば可視要素へ移す。
2-5. **テスト**: argmax(P) ≠ ◎ の合成データで `is_top_p` バッジが最高 P 馬に付くこと、
   凡例文言の存在。

**受入ゲート 2**: 実 dist 再生成で「最高勝率」バッジが ◎≠最高 P のレースに出る + 凡例追記を確認、
テスト green。**印の割当 (rules.py) は無変更を diff で確認**。

**（Codex はここで判断しない・報告のみ）**: 「印を investment_probability 順に一本化する」根本策は
監視下戦略の変更でありバックテストが要る。本作業では**やらない**。表示整合のみ。

### ステージ 3 (欠陥③): 生成スケジュールの是正 + 公開完全性ゲート

対象: `scripts/register_auto_predict_task.ps1` / `web/generator.py` / `scripts/auto_predict.py` / tests

背景: 生成タスクは毎日 09:30 単発 (`register_auto_predict_task.ps1:8,27`)。日曜の出馬表 (SE) は
土曜 11:00 の日次バッチで届くため、**土曜朝生成では日曜平場が毎週必ず空** (再現性100%)。
DB は 11:00 に日曜全 36R 揃うのに再生成トリガが無く、22.5h 欠損ページを公開し続けた。
publish 面に出走馬充足の完全性ゲートが無い。

3-1. **土曜午後の再生成トリガ追加**: `register_auto_predict_task.ps1` に 2nd trigger (例 11:30) を
   追加 (ASCII のみ)。`New-ScheduledTaskTrigger` を配列で 2 本 (09:30 と 11:30) 登録するか、
   別タスクとして登録。`auto_predict.py` は再実行冪等 (同日再生成で上書き) なので本体変更は不要な
   はずだが、要確認。コメントに「日曜出馬表は土曜 11:00 バッチ着 → 11:30 で翌日分を反映」と明記。
3-2. **公開完全性ゲート**: `web/generator.py` の render 結果から
   `empty_races` (出走馬未取得) / `total_races` を集計し、view model に渡す。対象日が
   「本日または翌日の開催日」で空率 > 20% のとき:
   - header に警告バナー「一部レースは出走馬未確定 (翌日分は当日朝に反映)」を出す
   - `publish_safety.py` と同型の純関数で判定し、`_sync_status.json` に `empty_race_ratio` を記録
   - (Discord 通知は best-effort、既存 `notify_discord` を import。送信内容はテストで mock)
3-3. **メタ行の是正 (欠陥①③ 共通)**: `index.html.j2:543` の「全 {{ race_count }} レース」を
   「予想 {{ predicted_count }} レース / 出走馬未確定 {{ empty_count }}」に分解
   (generator で predicted/empty を数えて渡す)。「全 72」という誇大表示を解消。
3-4. **オッズ鮮度の可視化 (mobile 副次)**: `col-odds` セルに `title="取得 HH:MM"`
   (`odds_snapshots.fetched_at` 由来) を出力、または各レース見出しにオッズ取得時刻を 1 行。
   利用者に「表示オッズがいつの値か」を伝える。空セルには「—」を入れる。
3-5. **テスト**: 空率集計 (合成 view model)、完全性ゲートの閾値判定、メタ行の predicted/empty 分解。

**受入ゲート 3**: ps1 が ASCII で 2 trigger を登録する形になっている、空率ゲートのテスト green、
メタ行が分解表示。実 dist 再生成でメタ行・鮮度 title を目視確認。

### ステージ 4: 再生成 + 検証 + コミット

4-1. `pytest tests/ -q` 全 green。
4-2. **本番相当の単日 render で実 dist を再生成** (`.venv64/Scripts/python.exe -m web.generator
   --from <直近開催日> --to <同> --no-publish`) し、以下を grep/python で確認して報告:
   - 観察専用バナーの文言が本文に出る / 見送り文言が新版 / EV 注記あり
   - ◎≠最高 P のレースに「最高勝率」バッジ / 凡例追記
   - メタ行が「予想 N / 未確定 M」/ オッズ鮮度 title / 空セルは「—」
   - dist サイズが単日 +50KB 以内 (バナー・バッジ分の増加は許容範囲内か報告)
4-3. **コミット (1 回)**: 変更した j2/py/ps1/tests + `docs/codex_fix_20260719_output_defects.md`
   を明示 add。英語 1 行 + 本文数行。
4-4. `git status --porcelain --untracked-files=no` が空、rules.py 無変更、push なし、DB 不変を確認。

**受入ゲート 4**: 1 コミット、全テスト green、rules.py/weights/calibrator 無変更。

### 最終報告 (15 行以内)

1. ステージごとの完了/スキップ
2. 観察専用バナー・見送り文言の是正後テキスト (実際の出力文字列)
3. 「最高勝率」バッジが出た ◎≠最高 P レース数 (再生成 dist 実測)
4. ps1 の trigger 構成 (09:30 + 11:30)、空率ゲートの閾値と発火確認
5. メタ行・鮮度表示の before/after
6. コミット sha / rules.py 無変更 / push なし / DB 不変

---

## (Claude Code 側メモ — Codex には渡さない)

- Codex 完了後、**正規 expert-review (D1) を実行** — j2/generator は `mobile-html-reviewer` +
  `profitability-judge` (①の開示が十分か) + `prediction-logic-analyst` (②の表示整合が誤解を
  生まないか) が重点。**再生成した dist を成果物として精査させる** (今回の監査と同じ土俵)
- ①の是正が本命なので、レビューは「観察専用開示が本文に常時出るか」を最重要ゲートに
- ②の「印を investment_probability 順に一本化」は別サイクル (戦略変更 → backtest 必須、
  F3/封印ホールドアウトの規律に注意)。ユーザに要相談
- 現在 Pages 公開中の版 (`552e949`) は日曜 09:30 再生成で③の空レースは埋まるが①②は残る。
  マージ後に再 publish して初めて①②が解消する
- 残課題: dist 1.76MB (デフォルト窓、GUI 手動 publish 経路) の予算恒久解 / 述語基盤の db.py 集約
