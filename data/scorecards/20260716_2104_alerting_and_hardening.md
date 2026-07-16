# 採点 2026-07-16 21:04 (正規版)

**改修内容**: 監視アラート再設計 + 人間到達 + アーカイブ堅牢化 (第 3 サイクル) — '00' カナリアを violation 述語へ再設計 (偽陽性ウィンドウ解消 + early-return 廃止) / bat 日付別ログ固定 + Discord best-effort notifier / gap 警告日付付与 / 監視系 read-only 化 / アーカイブ原子書込 + sha 記録 + 自動 commit / manifest warnings schema:2
**対象 commit**: `d3763bc` (Codex 実装、指示書 `docs/codex_fix_20260716_alerting_and_hardening.md`) + `bea5d9f` (Claude テスト是正)、branch `codex/alerting-and-hardening`。Codex の scorecard 自作は今回もゼロ

> **実環境イベント (本レビューの特異点)**: Codex 報告直後の 7/16 朝 9:00 定期 fetch が 7/18-19 の
> 枠順確定前出馬表 72 行 ('00') を取り込み、第 2 サイクル製 live-DB invariant テスト (raw count==0)
> が**実際に FAIL** — カナリア再設計が対処した偽陽性ウィンドウの実在が本番で証明された。
> Claude が violation 述語 (`db.count_horse_num_violations`) へ是正 (`bea5d9f`)。
> 過渡 72 行が実在する本番 DB で `scripts.monitor` が violation 0 / Brier +1.06% 完走 / exit 0 を
> ライブ実証 (validation-process-auditor が独立再実行で再現)。
> 前回の正規基準は `20260716_0050_monitoring_and_archive.md`。

## 総合スコア (項目平均) の推移

| 専門家 | 今回 | 前回 (0050) | 差分 | 判定 |
|---|---:|---:|---:|---|
| GUI / UX 監査人 | 4.0 | 3.6 | +0.4 | PASS |
| モバイル HTML レビュアー | 4.6 | 4.5 | +0.1 | PASS |
| 予想ロジック分析官 | 4.6 | 4.5 | +0.1 | PASS |
| 収益性ジャッジ | 4.2 | 4.1 | +0.1 | PASS |
| データ基盤エンジニア | 4.3 | 4.2 | +0.1 | PASS |
| コード品質レビュアー | 4.2 | 4.0 | +0.2 | PASS |
| 検証プロセス監査人 | 4.4 | 4.2 | +0.2 | PASS |
| **平均** | **4.33** | **4.16** | **+0.17** | **7 PASS** |

- **全 7 名がスコア改善、後退ゼロ** (プロジェクト初)。前回 (0050) の 7 名の改善提案は執行率 100%。
- 5 層防御は「完成」と再判定 (予想ロジック分析官)。bea5d9f のテスト述語是正は「post-hoc weakening に
  該当しない」と検証プロセス監査人が明示判定 (述語変更は FAIL 発生前にコミット済み + 検知対象クラス不変)。
- テスト 353 passed / 4 skipped を複数名が独立再実行。

## 各専門家の所見 (要点)

### GUI / UX 監査人 (4.0 / PASS、+0.4)

- 前回の核心的弱点「アラームは鳴るが誰も居ない部屋」が Discord 連携 + 日付別永続ログで構造的に解消。障害→通知→ログ→復旧手順の導線が一本化。提案消化率 3/3。
- register ps1 の chain 記述と bat 実体の exit bits が完全一致することを突合確認。
- 留保: weekly Discord は exit code 生値のみで bit 復号がない / ACTION 1-3 (Brier 復旧手順) が原因無関係に echo される誤処方リスク / webhook 自体の故障は監視されない (best-effort の意図的トレードオフ)。

### モバイル HTML レビュアー (4.6 / PASS、+0.1)

- 原子書込は満点: 同一 dir tmp → sha256 照合 → os.replace で「部分ファイルが destination に現れる経路が存在しない」構造保証。前回繰越 3 件 (非原子・sha 偽不一致・git add 未追跡) すべてテスト付きで解消。
- fail-safe は StalePublishRefused (try の前で raise) を巻き込まないことをコードで確認。
- 留保: `repository_archive: null` を読む監視 consumer がゼロ (失敗が log にしか出ない)、dist 1.58MB は既存課題 (本改修外)。

### 予想ロジック分析官 (4.6 / PASS、+0.1)

- **5 層防御 L1-L5 すべて実装 + テスト証明済みで完成と再判定**。新述語は「ingest が実際に保証する不変量 (L2 の同 txn DELETE)」そのものを監視する正しい設計。前回仮説だった偽陽性シナリオが本番で実発生し、是正の必要性が事後実証された。
- 偽陰性の反証: 正規行が来ないまま '00' 単独残置のケースのみカナリア沈黙 (別経路の欠落検知で部分補完)。
- 指摘: **復旧導線の dead-end** — 警告が案内する cleanup は '00' しか走査しないため、空文字共存で発火した場合「0 件 / クリーン」と報告し恒久アラート化する (低優先、cleanup の走査述語を `sql_invalid_horse_num` へ)。

### 収益性ジャッジ (4.2 / PASS、+0.1)

- 提案 3/3 充足 (自動 commit / unclassified 分離 / 非短絡化)。warnings 3 分割 + schema:2 で era 差の機械判別が可能に。収益主張ゼロの規律維持 (段階は観察用のまま)。
- **新規リスク発見: starter_count 連動ゲートの取消偽陽性** — starter_count は取消後の出走頭数のため、朝オッズ取得後に競走除外が出ると「人気順位 > 頭数」で当日台帳全体が rc=1 / CSV 不生成 (答え合わせの欠測日 = 封印ホールドアウトの穴)。実データ 2 日で発火 0 件だが取消は正常イベント。`max(starter_count, registered_count)` への変更を最優先提案。
- 他: archive 失敗が Discord に届かない / GUI 手動 publish 分は staging 対象外。

### データ基盤エンジニア (4.3 / PASS、+0.1)

- bat の errorlevel 伝播は満点 (call :run リダイレクト → exit /b 連鎖を精読、bit 合成も遅延展開問題なし)。0-run FN フォールバックは JSONL 完全欠損でも races 由来 open_dates + 仮想窓端で exit 1 に到達する経路を確認。
- **カナリア述語の FN トレードオフを明確化**: 新述語は「過去日なのに全行 '00' のまま放置」(取込欠落) を検知しない。過渡状態は未来日にしか存在し得ないので、「race_date < today の不正行は共存条件なしでカウント」する第 2 述語で **FP ゼロのまま旧検査の FN を補完可能**。
- 他の残穴: monitor の Brier/mining 計測 2 経路 (`monitor.py:91,136`) が `open_db` のまま (週次 run が migration 書込 Tx を発行) / `notify_discord` の except 網に `http.client.HTTPException` の漏れ (push 成功後の通知で propagate すると偽の bit-2 化)。

### コード品質レビュアー (4.2 / PASS、+0.2)

- 前回指摘 5 件すべて構造的に充足。テスト容易性 5/5: 全 9 系統の修正に同型回帰テスト同梱 + 純粋関数抽出が一貫。
- 変更失敗モード 2 件: (1) **アーカイブ日付規約の 2 ファイル分散** — generator の保存先と auto_predict の glob が平行記述で、fallback 経路や規約変更時に「アーカイブは生成されるが git add が空振りし、警告なしで改ざん耐性が不成立」。`_sync_status.json` の実測パス駆動へ。(2) **アラート→是正ループの非収束** — NULL/'' violation で cleanup が「0 件」と健全に見える no-op を返す (予想ロジック分析官と同根)。
- bea5d9f は妥当と判定 (単一出典への合流 + 過渡状態の根拠コメント)。留保: 同テストの接続が書込可能 (mode=ro URI が望ましい、軽微)。cleanup の `--dry-run` が未参照の no-op 引数。

### 検証プロセス監査人 (4.4 / PASS、+0.2)

- 前回提案 3 件執行率 100%。**bea5d9f の反証を 3 系統実施し「検証の弱体化ではない」と判定**: 失った検知力は「正当な過渡状態の誤検知」のみで、本来の異常クラス (冪等削除の失敗 = 共存) の検知力は不変。monitor 側の述語移行が FAIL 発生前にコミット済みであることを根拠に post-hoc weakening を否定。
- 実測を独立再導出: 353 tests / violation 0 / drift +1.06% / gap 日付付き exit 1。
- **7/18-19 初実戦の検収 4 項目を合否基準付きで固定**: ①gap 誤警報 0、②新 manifest に schema:2、③アーカイブ自動 commit + sha 非 null、④Discord 実着弾 ≥1 (未着弾でも predict exit 0 なら設計どおり、着弾のみ再調査)。
- 繰越管理の注意: テンプレート data-odds 属性化が **3 サイクル連続繰越** — 次サイクルで実施 or 明示クローズを。

## 横断的に見た優先課題

1. **カナリアの仕上げ: cleanup 述語一元化 + 過去日第 2 述語** (指摘 4 名)
   - (a) `cleanup_placeholder_horse_rows` の走査述語 (`inspect_placeholders`) を `db.sql_invalid_horse_num` ベースへ拡張 (DELETE は '00' 限定維持) — NULL/'' violation 発火時に復旧ツールが「0 件」を返して警告が永久収束しないループの解消。
   - (b) `count_horse_num_violations` に「race_date < today の不正行は共存条件なしでカウント」の第 2 述語 — 過渡状態は未来日にしか存在しないため、FP ゼロのまま「過去日の全行 '00' 残置」FN を補完。
2. **品質ゲートの取消偽陽性の是正** (収益性ジャッジ最優先)
   - 人気上限を `max(starter_count, registered_count)` に変更 + 取消シナリオのテスト。現状は競走除外の出た日に当日台帳全体が生成不能となり、答え合わせの欠測日を作る。
3. **堅牢化の残渣 3 点** (小粒・各 1-数行)
   - `notify_discord` の except を `Exception` へ拡大 / monitor の Brier・mining 計測 2 経路を read-only 化 / `_stage_publish_artifacts` を `_sync_status.json` の実測パス駆動に + archive 失敗の Discord 通知。

## 検収計画 (7/18-19 初実戦、合否基準固定済み)

①gap 検知の誤警報 0 (開催 2 日) / ②`data/results/2026-07-18/` の manifest に `schema: 2` + `post_start_unclassified_rows` / ③`predictions_source_*.html` の自動 commit + `repository_archive_sha256` 非 null / ④Discord 実着弾 ≥1 件 (best-effort につき未着弾でも predict exit 0 なら可、着弾のみ再調査)

## 残課題 (繰越)

- テンプレート data-odds/data-popularity 属性化 — **3 サイクル連続繰越、次サイクルで実施 or 明示クローズ**
- weekly Discord の exit bit 復号 / ACTION 1-3 の原因連動 / gap 詳細の通知文埋め込み (GUI 提案)
- 累計 P/L 台帳 (F3 設計相談が先) / dist 1.58MB (既存、type-D 改修時)
