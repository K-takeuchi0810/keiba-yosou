# 採点 2026-07-27 00:30 (F3 §4.4 fail-closed) — 正規 D1

**改修**: LGBM 不在・特徴失敗時の **silent rule-only 縮退**を廃し、`prediction_mode`
(full/observation/blocked) + `error_reasons` (E01-E04 の閉じた enum) で構造化。強制は
production 経路 (`is_production_buy_candidate`) のみ、分析系 (backtest / f3_phase0_0_eval) は
raw `is_buy_candidate` のままで**絶縁**。
**対象**: branch `codex/phase0-fail-closed`、`7e598e4` (Codex 実装) + レビュー是正 (Claude)。
指示書 `docs/codex_f3_phase0_fail_closed.md`。**commit 同梱の Codex 自作 scorecard は D1 無効**
(3 回目)。本 scorecard が正本。

## 7 名 (平均 3.90)

| 専門家 | 判定 | 点 | 決定的な指摘 |
|---|---|---:|---|
| prediction-logic | PASS | 4.2 | 親 commit を worktree 展開し asdict 全フィールド **bit 一致**を実証 |
| profitability | PASS | 4.1 | 買い候補抑止に漏れなし (GUI cache / plain-list / meta 欠如 / webapp を反証) |
| mobile-html | HOLD→是正 | 4.1 | **M1 が実出力で顕在化** (full=0 時にバナーが画面実態と矛盾) |
| gui-ux | PASS | 4.0 | publish が mode 非対応 / mixed banner 断定 |
| code-quality | PASS | 3.9 | **backtest の loud→silent 反転** (新規混入) / 配線 pin が GUI のみ |
| data-pipeline | HOLD→是正 | 3.6 | legacy 'full' を**実 DB で反証 (59 行)** / monitor 信号飽和 / 土曜 bit8 恒常発火 |
| validation | CONDITIONAL | 3.4 | **G4 形骸化をコード証拠で確定** (val AUC は predict_race を通らない) |

## ★G4 の再実施 — 形骸化の是正と、そこで判明した 2 件

Codex の G4 は `--skip-oos` で val AUC のみ照合。しかし **val AUC は `Booster.predict` を直接
適用し `predict_race` を一切通らない**ため、この改修の回帰を検出できていなかった (validation 指摘)。
Claude が **OOS 込みの完全 G4 (1578 レース)** を実行し、さらに **base commit を worktree に展開して
同一 DB (hardlink)・同一 cache・同一参照で paired 実行**した。

| | 凍結 (07-20) | **BASE** (現 DB) | **HEAD** (現 DB) |
|---|---:|---:|---:|
| bets / hits | 425 / 65 | **430 / 68** | **430 / 68** |
| 回収率 | 62.09% | **64.98%** | **64.98%** |
| 日block 95%CI | [48.97, 76.28] | **[51.18, 79.84]** | **[51.18, 79.84]** |
| val AUC ×4 | — | — | 4 モデルすべて凍結値と MATCH |

1. **fail-closed は数値中立 (paired で確定)**: BASE == HEAD が bets/hits/return/CI まで完全一致。
   実 artifact・1578 レース規模で、独立 2 名の bit 一致所見を追認。**G4 の intent (回帰検出) は充足**。
2. **★凍結ベースラインが現 DB から再現しない**: frozen ≠ BASE。差分 (425→430) は **fail-closed でなく
   DB ドリフト** (07-20→07-26)。OOS 窓のオッズ刻印は不変 (max 2026-06-14) なので、確定オッズ再取り込み等
   別経路。**rev1.1 §4.0 に記録した baseline (62.09% / CI[48.97,76.28]) は DB 状態依存のスナップショット**
   であり、Phase 1 の比較基準としてはそのままでは使えない。**要 rev1.3 で注記** (エッジ無しの結論
   =CI 上限 <100% は 79.84% で不変)。
   - 診断が難航した理由は validation が挙げた「**paired ledger 未永続化**」。次回 paired 評価の
     必須要件 (rev1.1 §4.0 TODO) を**優先度上げ**。

## 是正 (10 件、Claude 実施・全て検証済み)

| 指摘者 | 是正 |
|---|---|
| mobile M1 | バナーを**常に件数表示** (「予測停止 7 / 観察専用 29 / 通常 0」) + **full=0 の実在ケースのテスト**追加 |
| mobile M2 | no-buy の原因帰属を是正 (fail-closed 時に「フィルタ不合格で見送り」と偽らない) + テスト |
| mobile M3 | 閉状態に「停止」「観察」バッジ (塗り+白文字で AA) |
| data-pipeline / validation | `PREDICTION_MODE_CUTOVER_AT` 定数 + 「DEFAULT 'full' は便宜であり観測事実でない (59 行が反証)」を db.py に明記 |
| data-pipeline | **exit bit 8 を blocked のみに** (observation は本プロジェクトの常態、かつ土曜は必ず発火 → alert fatigue) |
| data-pipeline | monitor の**信号飽和をコードに明記** (observation は構造的飽和、有意なのは blocked のみ、窓が埋まれば ledger 読取りへ) |
| code-quality | **backtest に mode カウンタ** (従来 backtest を即死させていた特徴バグの静かな混入を観測可能化) |
| code-quality | `filter.py` docstring に**二層契約**を明記 (旧記述は新契約と矛盾し raw 誤用を誘導していた) |
| code-quality | **配線 pin テストを双方向** (production→raw 退行 / 分析→wrapper 混入 の両方) |
| Claude | 実出力で M1-M3 を実測確認 (バナー件数 / fail-closed 帰属 / バッジ 7+29 / 340,872 bytes) |

**検証**: pytest **445 passed / 4 skipped**、production artifact 4 点 SHA 不変、G4 paired 一致。

## Claude の独立検証 (4 点すべて PASS)
層分離 (`predict_race` は縮退で raise せず backtest 非破壊) / 強制が production のみ / enum 閉鎖 /
artifact SHA 不変。加えて **部分カバレッジ不可を preflight の構造から証明** (reviewer 3 名と独立一致)。

## 自省 — 検証系での silent failure
Claude 自身が最初の G4 を `... 2>&1 | tail -25` で回し、**パイプの終了コード (tail) が 0 を返すため
python の異常終了を「完了」と誤報**した。本セッションで潰してきた silent failure クラスと同型。
再実行はパイプを外し真の exit code を取得。**教訓: 検証コマンドでパイプを噛ませない**。

## 残課題 (次サイクル)
severity 集約の一元化 (3 実装) / guidance の 3 重複 (Python↔JS) / `_live_odds_errors` の `now` 注入と
直接テスト / `E05_MODEL_ERROR` 分離 (booster 失敗を「特徴不完全」と誤表示) / `use_features=False` の
mode 契約 / exit 8 定数化 / `assert_safe_to_publish` の mode 対応 / `prediction_accuracy.py` の
sentinel 防御 1 行 / **paired ledger 永続化 (優先度上げ)** / **rev1.3 で baseline の DB 依存を注記**。
