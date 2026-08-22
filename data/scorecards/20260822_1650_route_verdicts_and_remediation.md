# 採点 2026-08-22 16:50 (第 2 ラウンド: 是正確認 + 経路 1-3 検証)

**改修内容**: 前回 (20260822_1210) の HOLD 4 名の指摘是正 + repair --apply 適用 + 経路 1-3 検証 (改革案 rev 1.1/1.2) + 修復後正本 backtest + baseline 再凍結
**対象**: `db.py` 分離 / `scripts/analyze_cross_pool.py` (新規) / repair 適用 / `config.py` 正本差し替え / docs/REFORM_2026H2_MARKET_RESIDUAL.md
**コミット**: `015c118` (経路検証) / `70468f2` (修復後正本) / `efd4894` (baseline) / `9e388fd` (調査報告) / `9fb1f08` (本ラウンド指摘の是正)

## 総合スコア推移

| 専門家 | 今回 | 前回 (1210) | 差分 | 判定 |
|---|---|---|---|---|
| GUI / UX 監査人 | 3.8 | 3.4 | +0.4 | HOLD→**PASS** |
| モバイル HTML | 4.2 | 4.2 | ±0 | PASS 維持 |
| 予想ロジック分析官 | 3.9 | 3.9 | ±0 | PASS 維持 |
| 収益性 / 投資判断 | 4.0 | 4.2 | -0.2 | PASS→HOLD |
| データパイプライン | 4.0 | 3.6 | +0.4 | HOLD→**PASS** |
| コード品質 | 4.0 | 3.8 | +0.2 | HOLD→**PASS** |
| 検証プロセス | 3.8 | 3.4 | +0.4 | HOLD 継続 (別事由) |
| **全体平均** | **3.96** | 3.79 | **+0.17** | PASS 5 / HOLD 2 |

前回の HOLD 事由 (GUI 虚偽表示 / HEAD 非自己完結 / repair 未適用 / backtest 契約矛盾 /
env 未登録 / sweep 鮮度ゲート) は**全員が実測で解消確認**。

## 新規 HOLD 2 名の事由と即日是正 (commit 9fb1f08)

| 指摘 (収益性 + 検証 + 予想ロジックが収束) | 是正 |
|---|---|
| cross_pool JSON に meta.git_sha 無し (type-B 再現性ゲート抵触) | `_repro_meta()` を追加し v2 artifact (20260822_164201) に差し替え。**棄却判定は不変** |
| bootstrap が combo 単位でレース内相関を無視 (CI 過小) | レースクラスタ単位に変更。クラスタ CI でも全 EV≥1 帯上限 <100% |
| 経路 1/3 が script・artifact 無しで厳密再現不能 (n=1,445 vs 1,374) | `scripts/analyze_simple_edges.py` 新規。母数定義を明文化し n=1,374 / 85.5% を厳密再現、WIN5 実質機会 0 回を artifact 化 |
| REFORM の「保証される下限」「Stern は縮める方向にしか働かない」等の over-claim / 技術的誤り | 5 箇所修正 (残差→0 収縮 + 非劣化ゲート前提の近似に弱化 / Stern 論拠を正しい算術に / §1 表を修復後正本に / 事前宣言の自己評価を commit 証明可能な範囲に限定 / 柱 1 に backtest 印 vs 朝 HTML 印の解釈注意) |
| would_be_candidate 未実装 (収益性 3 回目) | build_daily_results に実装 (仮想判定、None 意味論、テスト付き) |
| Harville 数式のテスト無し | tests/test_cross_pool.py 3 本 (top2/top3 総和=1、対称性) |

tests: **448 → 452 passed** (シリーズ全体で当日 436→452)

## 主要な確定事項 (両ラウンド総括)

1. **経路 2 棄却は 3 名の独立検証で頑健** — Harville 実装の数学的正しさ (総和=1)、
   combo/払戻の整合、EV 単調悪化、クラスタ CI でも覆らず
2. **経路 3 棄却も独立再計算で一致** (WIN5 348 回、実質 EV>1 = 0 回)
3. **修復後正本** YTD 1,932 戦 66.2% CI[59.4,73.3] / 買い候補 186 戦 52.6% CI[33.2,73.2]
   は複数名が独立再導出で一致。サスペンド根拠は強化
4. **残る要注意** (次回以降):
   - 正本 backtest が git_dirty=True の tree で走った (JC/CC 並行改修。読み経路
     非干渉は確認済みだが、次の正本は clean tree で)
   - calibrator compat の確認 (fresh 比率が設計前提 0.4% → 23.9% に激変) が持ち越し
   - backtest 印 (T 直前情報込み) と朝 HTML 印 (市場盲目) の乖離は T−10 再生成
     実装まで常在
