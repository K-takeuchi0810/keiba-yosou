# 採点 2026-07-16 00:50 (正規版)

**改修内容**: 監視完全化 + '00' 完全封鎖 + 予想 HTML 恒久蓄積 — upsert 拒否ガード / generator 述語適用 / monitor '00' カナリア / ギャップ検知の窓端仮想区間 + bat 配線 / manifest warnings 意味論補強 / publish 自動アーカイブ + iCloud snapshots 15 件退避
**対象 commit**: `60331b0` (コード) / `34ef218` (データ)、branch `codex/monitoring-and-archive`。実装は OpenAI Codex (指示書: `docs/codex_fix_20260716_monitoring_and_archive.md`)。**今回 Codex の scorecard 自作はゼロ** (指示書明文化による封鎖を確認)
**レビュー中の追加修正**: mobile-html-reviewer が HOLD 主因として特定した日付抽出 regex の dead code (欠陥 1) を Claude Code がレビュー中に修正 → 再評価で PASS 転換。修正はユーザの並行マージ処理により `19e3f06` (sire_lines コンフリクト解消 commit) に混載でコミットされた

> 注: 前回の正規基準は `20260715_2352_daily_results_provenance_cleanup_2.md`。
> レビュー期間中に並行作業 (sire_lines 系統追加) が本ブランチへマージされたため、
> branch には監視改修と血統改修が混在している (テストは混在状態で 339 passed / 4 skipped を確認済み)。

## 総合スコア (項目平均) の推移

| 専門家 | 今回 | 前回 (2352) | 差分 | 判定 |
|---|---:|---:|---:|---|
| GUI / UX 監査人 | 3.6 | 3.6 | ±0 (GUI 無変更) | PASS |
| モバイル HTML レビュアー | 4.5 | 4.6 | -0.1 (初回 4.3 HOLD → regex 修正 → 再評価 PASS) | PASS |
| 予想ロジック分析官 | 4.5 | 4.4 | +0.1 | PASS |
| 収益性ジャッジ | 4.1 | 4.1 | ±0 | PASS |
| データ基盤エンジニア | 4.2 | 4.1 | +0.1 | PASS |
| コード品質レビュアー | 4.0 | 4.2 | -0.2 | PASS |
| 検証プロセス監査人 | 4.2 | 4.4 | -0.2 (評価対象の性質差、後退ではないと明記) | PASS |
| **平均** | **4.16** | **4.20** | -0.04 | **7 PASS** |

- 0.3 以上の後退なし (mobile の初回 -0.3 は HOLD 主因の regex バグ修正 + 再評価で -0.1 に解消)。
- 前回 (2352) の改善提案・宣言済み宿題は**執行率 100%** (validation 実測)。
- ギャップ検知は実 JSONL 1,178 行 / 直近 14 日 623 起動で「既知の 07-12 ギャップのみ検知・FP ゼロ」を
  2 名が独立実測。アーカイブ 15 件は sha256 全数一致 + 冪等性を実 dry-run で確認。

## 各専門家の所見 (要点)

### GUI / UX 監査人 (3.6 維持 / PASS)

- 前回提案② (--check-gaps 定期接続) の実装執行を確認。日次 bat の「検知→auto_predict 前」順序と当日窓クランプは FP を構造的に防ぐ正しい設計。
- **核心的弱点: 警告が人間に届かない** — Task Scheduler 実行は stdout をリダイレクトせず破棄、Discord (`auto_predict.py:_notify`) にも非配線。残る信号は exit code のみ。「アラームは鳴るが誰も居ない部屋」。
- monitor '00' カナリアが早期 return で Brier / mining 検査をマスクする (1 障害が他障害を隠す)。
- weekly bat の警告文から旧版の具体的復旧 3 手順が消え、復旧支援が後退。
- 提案: ①ギャップ警告の Discord 到達 (bat から auto_predict へ GAPCODE 連携 or ログファイル固定)、②カナリア非マスキング化、③register ps1 の chain 説明更新。

### モバイル HTML レビュアー (初回 4.3 HOLD → 修正後 4.5 PASS)

- **HOLD 主因 (欠陥 1)**: `_prediction_date_from_html` の regex `race-(\d{4})-(\d{2})-(\d{2})-` が実テンプレートの id 形式 `race-20260712-02-1` と一切マッチしない dead code で、テストは存在しない形式を固定化。GUI 経路の publish では常に公開日 fallback → 前夜 publish で日付パーティションが誤る。実 dist への適用で None 返却を実測。
- → Claude Code が regex + fixture を修正、実公開 HTML で `2026-07-12` 抽出を双方実測し **PASS 転換 (4.5)**。複数開催日窓では先頭日採用という仕様留保のみ。
- '00' 封鎖は SQL + Python の 2 層で完遂、再生成 dist に `>00<` 出力 0 件を実測。archive は prune より前に実行される正しい順序で「retention 20 で publish が失われる穴」を封鎖。
- 欠陥 2 (archive 例外時に `_sync_status.json` が旧状態のまま → sha 照合の偽不一致): 繰越提案で可 (優先度中)。
- サイズ実測: 本番公開物 377-419KB (予算内)。既定 ±14 日窓の dist は 1.61MB (既存問題、参考所見)。

### 予想ロジック分析官 (4.5 / PASS、+0.1)

- **upsert ガードは正常経路を壊さない**: 初回 '00' 取込は既存テストが guard 後も green、'00'→'00' 更新も素通り (コード検証)。EXISTS は '00' 行のみ対象で PK prefix seek — 性能影響実質ゼロ (「全 SE upsert に走る」という事前懸念を訂正)。
- 5 層防御 (入口ガード / 同 txn DELETE / SQL 述語 / Python 述語 / カナリア) の論理検証で穴は L5 のみ:
  **カナリアの偽陽性ウィンドウ** — '00' は枠順確定前の正当な過渡状態であり「count=0 が常時不変量」という仮定が誤り。木金に翌週出馬表を取込むと日曜の週次監視が誤警報 + early-return で Brier 監視をマスク。violation 定義 (正規行と共存する '00' のみ) への統一と warn+続行+exit bit 合成を提案。
- 書込単一経路 (`INSERT INTO horse_races` は db.py のみ、grep 確認) への入口ガード = DB レベル不変量として train-serve skew を狭める本改修最大の価値。

### 収益性ジャッジ (4.1 維持 / PASS)

- 前回提案①② (morning_popularity 可視化 / dirty 判定精緻化) 実装確認。post_start_stamped_rows は producer 全部が naive JST であることを grep 実測し判定正しさを確認 ("Z" suffix 混入時の 9h 誤分類は潜在パス)。
- **アーカイブの改ざん耐性は「push された時点」で成立** — `auto_predict.py` の git add は `docs/index.html` のみで、publish 時の自動アーカイブは untracked のまま。自動 commit への追加を最優先提案。
- 旧 manifest 非再生成は条件付き妥当 — ただし post_start_stamped_rows を最も必要とする 06-21 にこそ無い皮肉。schema_version 明記を提案。
- 段階判定: **観察用のまま** (収益性証拠は何も生成されていない改修であり、それ自体正しい)。

### データ基盤エンジニア (4.2 / PASS、+0.1)

- 実測検証: 実 JSONL で 07-12 ギャップ再現 (exit 1) + 直近 14 日 FP ゼロ、アーカイブ dry-run 全 17 件 SKIP (完全冪等)、schtasks の実配置 (9:00 fetch / 9:30 predict / 日曜 10:00 weekly) 確認。bat の errorlevel 処理はパーレン罠を回避した正しい実装。
- upsert ガードは read-only SELECT のみで partial state リスクなし、open_db の commit/rollback 一元管理下。
- 残穴 3 点: (a) **監視系が書込接続 `open_db` を使用** (db.py 自身の docstring に反する。日曜 10:00 / 毎朝 9:30 に ingest との write-lock 競合窓)、(b) gap 警告に日付が無い (複数日窓で特定不能)、(c) fetch_full が朝失敗すると当日が開催日と認識されず 0-run 警告が沈黙する FN。
- 提案: ①open_db_readonly 化、②gap 警告への日付付与、③カナリア非短絡化。

### コード品質レビュアー (4.0 / PASS、-0.2)

- 前回提案 3 点 (述語一元化 / 窓端 FN 封鎖 / テスト実 DB 化) すべて構造的に充足。cleanup subquery の alias 束縛も micro-test で実証。
- 変更失敗モード: **M1** アーカイブが `shutil.copy2` 直書きで非原子 — 破損 HTML が残ると sha 未記録のため永続かつ観測不能 (tmp 書き→os.replace + sha 照合を提案)、**M2** `_load_open_dates` が open_db (migration 書込) を使用、**M3** カナリアの Brier 遮蔽。
- 逆述語の非対称: カナリアは `='00'` のみ数え、NULL/'' は沈黙 — `NOT (SQL_VALID_HORSE_NUM)` に統一すべき。
- bat から運用知識 (Brier 警告時の復旧 3 手順) が削除された点は「dead code ではなく運用知識の削除」。
- レビュー時点の working tree に sire_lines 未解決コンフリクトを検出しマージ前解消を要求 (→ ユーザの並行作業側で解消済み)。

### 検証プロセス監査人 (4.2 / PASS)

- 宣言済み宿題の執行率 100% を diff で実測。ギャップ検知は「証拠の不在が警報を出す (dead-man switch)」のベストプラクティスを満たすと評価 (5/5)。
- 退避 15 件の sha256 を iCloud 原本と全数照合し一致。コミット以前の chain-of-custody は iCloud のファイル名時刻への信頼に依存 (移行 1 回性の内在的限界として許容、前向き機構が恒久的に閉じる)。
- **Codex 運用の構造的改善を確認**: scorecard 自作禁止の指示書明文化 → 今回自作ゼロ。
- クリーン worktree でテスト再実行 fail 0 (337/6、総数 343 一致 — skip 数は環境差)。
- 提案: ①カナリア early-return 廃止、②warnings に明示 schema version、③(当時) sire_lines コンフリクト解消 — 解消済み。

## 横断的に見た優先課題

1. **monitor '00' カナリアの再設計** (指摘 6 名 — 本レビュー最多の一致)
   - 3 欠陥の複合: (a) early-return が Brier / mining 監視をマスク (単一障害点)、(b) '00' は枠順確定前の
     正当な過渡状態なので raw count=0 は不変量でなく**偽陽性ウィンドウ**がある (木金取込→日曜誤警報)、
     (c) 述語が `='00'` のみで NULL/'' を数えない非対称。
   - 修正: 検査述語を `cleanup_placeholder_horse_rows` の violation 定義 (正規行と共存する '00' のみ) +
     `NOT (SQL_VALID_HORSE_NUM)` に統一し、warn + 続行 + exit bit 合成へ。
2. **警告の人間到達 + 監視系の read-only 化** (gui + pipeline + code-quality)
   - ギャップ警告は現状 exit code しか人間に届かない — Discord 通知への連携 or ログファイル固定。
     gap 警告に開催日を付与。`_load_open_dates` / カナリアの DB 接続を `open_db_readonly` へ
     (ingest との write-lock 競合窓の排除)。
3. **アーカイブの堅牢化** (profitability + code-quality + mobile)
   - 自動アーカイブを `auto_predict.py` の git add 対象に追加 (push されて初めて改ざん耐性が成立)、
     tmp 書き → `os.replace` の原子化 + sha256 記録、archive 例外時の fail-safe
     (`repository_archive: null`)、fetch_full 朝失敗時の 0-run 警告沈黙 FN。

## 残課題 (繰越)

- テンプレート data-odds/data-popularity 属性化 (type-D、次回 web 改修同乗 — 2 サイクル繰越)
- manifest warnings への `schema: 2` 明記 / `post_start_unclassified_rows` 追加
- 累計 P/L 台帳 (n + Wilson CI) — 集約器なしで日次 return を暗算し始めたら必須化 (profitability 条件)
- 品質ゲート上限の starter_count 連動 / register ps1 の chain 説明更新
- **ブランチ混在**: 並行マージにより本ブランチに sire_lines 改修 (433 行) が混在。PR の切り方はユーザ判断
