# 採点 2026-07-04 18:19 (Opus 代替 / rubric v4)

> **モデル注記**: 専門家 7 名の agent 定義は `model: fable` だが、Fable 5 が利用不可のため
> **`model: opus` 代替**で採点。rubric v4「改修タイプ別ゲート適用」に従い分類して採点した。

**改修内容**: SmartRC (亀谷スマート出馬表) 踏襲の独自出馬表 webapp を新規実装 (Phase 1-4)。
系統分類・傾向集計・FastAPI でなく stdlib http.server の webapp・コーナー通過順位 ingest + 先行力指標。
**対象ファイル**: webapp/{aggregate,views,server}.py + templates/*.j2, predictor/sire_lines.py,
predictor/features.py (recent_corner_stats), jvlink_client/parser.py + schema.sql + db.py (corner ingest),
scripts/probe_corner_offsets.py

## 総合スコア (Opus / v4)

| 専門家 | 初回 | 判定 | 主な指摘 (→ 本セッションで対処) |
|---|---|---|---|
| データパイプライン技術者 | **4.4** | PASS | migration/asdict/冪等性を実測。corner の >0 上書きガード → 対処 |
| コード品質レビュアー | **4.0** | PASS | predict_race 握り潰しにログ / JRA コード判定の重複 → 対処 |
| 検証プロセス監査人 | **4.0** | PASS | 回収率の払戻欠損下方バイアス / probe docstring 過大表示 → 対処 |
| 予想ロジック分析官 | **3.9** | PASS | dormant corner SQL のホットループ発行 → 対処 |
| GUI / UX 監査人 | **3.8** | PASS | 500 traceback 直出し / 回収率閾値と注記の齟齬 / muted コントラスト → 対処 |
| モバイル HTML レビュアー | **3.6** | HOLD→対処 | 全タップ 44pt 未満 / 出馬表 375px 横スクロール → 対処 |
| 収益性 / 投資判断 | **3.5** | HOLD→対処 | 回収率が CI 無しの点推定で緑表示 (非対称) → 対処 |

**全体平均: 3.89**（全員 PASS 5 / HOLD 2、いずれも UI・統計表示の具体的欠陥）。

## 2 件の HOLD と対処 (PASS 相当へ)

### 収益性 HOLD (3.5) — 回収率の非対称な不確実性開示
複勝率に Wilson CI を出すのに、より分散の大きい単勝回収率を CI 無しの点推定で緑 (>=100%) 表示し、
winner's curse を誘発。対処:
- `aggregate.py`: `bootstrap_return_rate` で各セルの単勝払戻系列から **return_ci_lo/hi** を算出。
- `trends.html.j2`: 単回収の緑は **CI 下限 > 100% のときのみ**、CI 列を併記。「観察用の記述統計・買い推奨でない」を明記。
- 勝ち馬の払戻 join 欠損 (`payout_missing`) をセルに開示 (回収率の下方バイアス可視化)。validation 指摘も同時解消。

### モバイル HTML HOLD (3.6) — タップ領域と出馬表の横スクロール
- 全インタラクティブ要素を **HIG 44pt** へ: header リンク / レースチップ / select・button に min-height:44px。
- 出馬表 (10 列) が 375px で ◎/人気/オッズを右端へ押し出す → `@media(max-width:480px)` で補助列 (父/母父) を
  `.opt-col` 畳み。系統 (色+ラベル) が父系を要約するため核心情報を横スクロールなしで同時視認可能に。
- 系統色ドットに outline (light での淡色 3:1 未満対策)、`--muted` を #5b6670 へ (AA 余裕)、theme-color メタ追加。

## その他の対処 (PASS 陣営の指摘)
- code-quality: `views.py` の predict_race 例外に `logger.warning` 追加 (silent break 解消)。
  JRA 中央場判定 (1-10) を `aggregate.jra_track_clause()` に一元化し 4 箇所の平行記述を解消。
- gui-ux: 500 エラーを traceback 直出し → 日本語 1 行 + 「開催へ戻る」リンク (LAN 情報露出も防止)。
- data-pipeline: `corner_order_1..4` を upsert の `>0` 上書きガード集合に追加 (発走前 SE 再取込で確定 corner=0 潰れ防止)。
- prediction-logic: dormant な recent_corner_stats を「corner データ存在」を run 単位 1 回判定して不在ならスキップ (ホットループの無償 SQL 回避)。
- validation: probe_corner_offsets の docstring を実装 (_verdict の自動判定) に一致させ、「先行馬傾向」は目視補助と明記。

## 設計上の重要判断 (reviewer 追認済)
- **FastAPI でなく stdlib http.server + jinja2**: 自己利用・4 経路のみ・既存依存 jinja2 で完結。重依存追加回避を code-quality が加点評価。
- **corner byte offset (394-401) は best-known + probe 必須ゲート**: PDF/実データが本環境に無く offset を決定的検証できないため、dataclass/commit/probe の三重明示 + 「緑まで backfill 禁止」で「誤 offset の静かな破壊」を運用ゲート化。data-pipeline が三重封じを確認。**RA ラップ配列は offset 検証不能として見送り** (次段で PDF p.11 突合 + probe 後に追加)。
- **先行力指標は dormant (scoring 未配線)**: weights/calibrator 分布を一切動かさず train-serve skew を回避。投入は probe 緑化 + 単独 ablation でエッジ実証後 (prediction-logic の持ち越し)。

## 次フェーズ持ち越し (今回スコープ外)
- probe を heuristic → spec byte-diff / golden fixture 化 (data-pipeline/validation)。
- 先行力指標の scoring 配線前の単独 ablation backtest (prediction-logic)。
- RA ラップ ingest (PDF offset 確定後)。
- 傾向集計の多重比較 FDR 補正 (現状は文言警告 + min_n ゲート)。

検証: 全体テスト 219 passed / 3 skipped、webapp 新規テスト 29、実サーバ (stdlib http) で 4 ページの実描画・
更新後テンプレート (回収率 CI 列・観察用文言・44pt・opt-col 畳み) を live 確認。
