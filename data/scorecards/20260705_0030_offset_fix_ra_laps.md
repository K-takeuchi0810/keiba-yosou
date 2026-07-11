# 採点 2026-07-05 00:30 (Opus 代替 / rubric v4)

> **モデル注記**: 専門家定義は `model: fable` だが Fable 5 利用不可のため Opus 代替。

**改修内容**: (1) SE コーナー順位 offset の実バグ修正 (394→352。旧値は 1着馬血統登録番号の誤読) +
RA ラップ/ハロン ingest 追加 (2aa1263)。(2) 前セッション持ち越し課題の一括消化 (fce7232:
bias_scan streaming 化 + warn_n、backtest public 昇格、距離バケット統一、probe --expect、webapp 開示強化)。
**対象ファイル**: jvlink_client/parser.py, db.py, data/schema.sql, scripts/{bias_scan,backtest,analyze_predictions,probe_corner_offsets}.py, webapp/, tests/

## 総合スコア (Opus / v4)

| 専門家 | 今回 | 判定 | 備考 |
|---|---|---|---|
| 予想ロジック分析官 | **4.4** | PASS | 旧 offset の被害が多層防御 (dormant+probe) で止まったと確認 |
| 収益性 / 投資判断 | **4.3** | **HOLD→PASS** | 前回 3 指摘 (CI 無し緑/払戻欠損/観察用明示) の解消を行番号で確認 |
| コード品質レビュアー | **4.0** | PASS | offset 根拠の single-source+pointer 構造を DRY 準拠と評価 |
| GUI / UX 監査人 | **3.9** | PASS | 前回指摘 3 件 (500 人間化/閾値齟齬/コントラスト) 全解消 |
| モバイル HTML レビュアー | **3.9** | **HOLD→PASS** | 実レンダリング+列幅概算で 44pt / 375px 横スクロール解消を実測 |
| データパイプライン技術者 | **3.8** | PASS | offset を全アンカーから独立再検算し完全整合。**実バグ 1 件発見** (下記) |
| 検証プロセス監査人 | **2.8** | **HOLD** | 「検証済み」は過大主張 — 指摘は正当、下記で全対処 |

**平均 3.87、PASS 6 / HOLD 1**。前回 HOLD 2 名 (収益性/モバイル) は解消確認により PASS 回復。

## offset 修正の検証状況 (validation HOLD の核心 — 正確な表現)

- SE corner=352-358 / RA lap=891-981 は、実データ検証済みアンカー 7 点との**端点整合** +
  公開実装のフィールド順で導出した「**暫定確定**」。端点整合は必要条件であって十分条件ではなく、
  ギャップ内の順序 (着差↔角、S3/S4/L3/L4) は公開実装/公知構造体順への依拠 = **2 ラインは独立でなく相補**。
- 旧 394 が誤り (1着馬血統番号の誤読) である点は後方連鎖の再検算で複数 reviewer が独立確認。
- 実 DB は空 (0 byte) で旧 offset の backfill 実績なし = **被害ゼロ確定** (validation が git+DB で確認)。
- **決定的検証は実 .jvd での probe のみ**。本 scorecard と同コミットで hard gate に再昇格 (下記)。

## 本採点を受けて実施した修正 (同コミット)

1. **[実バグ] 発走前 RA によるラップ上書き消失** (data-pipeline が実測で発見) —
   `upsert_race` を INSERT OR REPLACE から ON CONFLICT DO UPDATE に変更し、front/last 3F/4F は
   `>0`、lap_times は `GLOB '*[1-9]*'` (非ゼロラップ含有) のときのみ上書き。順序逆転テストで固定。
2. **probe --expect の hard gate 再昇格** (validation) — parser 注記を「暫定確定」に修正し
   「実 .jvd で緑化するまで backfill/利用禁止」を SE・RA 両方に明記。「2 独立ライン確定」の
   過大表現を「相補的補完」に是正。
3. **--expect の全 4 角対応** (validation) — `race_id:馬番:c1:c2:c3:c4` 形式を追加 (352/354/356 も実データ固定可能に)。
4. **RA 用 probe (--ra) 新設** (data-pipeline) — 「前3F ≒ 先頭3ハロン和 / 後3F ≒ 末尾3ハロン和」の
   サニティで、端点整合では一意化できない S3/S4/L3/L4 並び順を実データ確定できる。
5. **streaming brier の golden test + warn_n テスト** (code-quality) — 手計算値との一致を assert し無音回帰を防止。

検証: 全体 **226 passed / 3 skipped** (+4 テスト)。

## 対応不能 (環境制約) の残項目 — ユーザ Windows 実機での作業
- `probe_corner_offsets.py --expect ...` (SE) と `--ra` (RA) を実 .jvd で緑化 → 緑化まで backfill 禁止 (hard gate)。
- 先行力指標の scoring 配線前の単独 ablation backtest (実 DB 必須。配線 PR の受入条件)。
- コミットの GitHub Verified 化 (署名鍵不在。author/committer email は正しい)。

## 持ち越し (軽微)
- lap_times 消費側での NULL 正規化 (`or ""`) — consumer 追加時 (code-quality)。
- warn_n の警告種別分解 (現状 OR 集約、prediction-logic)。
- 320px 端末の tight / 戻りリンク 44pt 化 / line-dot の box-shadow 化 (mobile 任意改善)。
- today の onchange → change 確定イベント化 (gui-ux, WCAG 3.2.2)。
