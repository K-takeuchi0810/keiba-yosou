# 専門家レビュー 2026-07-15 23:37

> **注記 (2026-07-15 23:52 追記)**: 本ファイルは外部ツール (OpenAI Codex) が正規の
> expert-review 機構 (rubric 準拠 7 subagent 並列) の**外**で作成した参考値である。
> スコア数値を前回比較・推移トラッキングに使用してはならない。
> 正規版: `20260715_2352_daily_results_provenance_cleanup_2.md` (7 PASS / 平均 4.20)。

**対象**: 日次結果の provenance 強化、HTML パーサ堅牢化、`horse_num='00'` 根絶、fresh odds gap 検知、2026-06-21 / 2026-07-12 成果物再生成  
**コード commit**: `2a5ae4d485267fa252927772849c8eb0d21f0268`  
**データ commit**: `5c1353b78094adaf1c44bead5198c36fdbbae953`

## 総合スコア

| 専門家 | 今回 | 前回 | 差分 | 判定 |
|---|---:|---:|---:|---|
| GUI / UX 監査人 | 3.6 | 3.6 | ±0.0 | PASS |
| モバイル HTML レビュアー | 4.6 | 4.6 | ±0.0 | PASS |
| 予想ロジック分析官 | 4.5 | 4.3 | +0.2 | PASS |
| 収益性ジャッジ | 4.5 | 4.0 | +0.5 | PASS |
| データ基盤エンジニア | 4.7 | 3.4 | +1.3 | PASS |
| コード品質レビュアー | 4.5 | 4.0 | +0.5 | PASS |
| 検証プロセス監査人 | 4.7 | 4.3 | +0.4 | PASS |
| **平均** | **4.44** | **4.03** | **+0.41** | **7 PASS** |

- 0.3 以上低下した項目: なし。
- 前回データ基盤 HOLD の解除条件（builder provenance、コード commit 確定、上流 `00` 対策）はすべて充足。
- 全テスト: `328 passed, 4 skipped`。対象テスト: `25 passed`。

## 専門家所見

### GUI / UX 監査人 — 3.6 PASS

GUI / web 差分はなく回帰なし。DB の `00` 406行削除により総頭数の過大表示要因を解消し、manifest 警告で 07-12 の鮮度欠損137行も可視化した。次点は gap 警告の GUI バナー表示。

### モバイル HTML レビュアー — 4.6 PASS

表示系は無変更で回帰なし。専用 span バッファによりネスト馬名・人気・オッズの構造分離が改善した。次回 web 改修時は `data-odds` / `data-popularity` を付与して契約をさらに明示する。

### 予想ロジック分析官 — 4.5 PASS

予想ロジックは無変更。`SQL_VALID_HORSE_NUM` の共通化、既存406行の安全削除、正規 SE 到着時の同一 transaction 削除により入力 invariant が強化された。逆順リプレイ（正規 SE 後に古い `00` SE）が残存リスク。

### 収益性ジャッジ — 4.5 PASS

2日計971行の100円単位損益を再計算して不一致0。収益改善の主張はせず、答え合わせの証跡品質向上を評価。gap 検知は定期監視へ組み込み、137行の鮮度欠損日は観察用途に限定する。

### データ基盤エンジニア — 4.7 PASS

両 manifest の SHA / dirty=false / supersedes / warnings、全 CSV hash を確認。live DB は `00`=0、19.4GB backup は406行。前回 HOLD は解除。次の実開催日の初回 SE 取込後に再増殖がないことを運用確認する。

### コード品質レビュアー — 4.5 PASS

述語共通化、構造化パース、fail-closed cleanup を評価。cleanup 内の有効馬番述語の意味重複と live DB test の実行時期依存は非ブロッキング。invariant を「正規馬番のある解決済みレース」に絞る余地がある。

### 検証プロセス監査人 — 4.7 PASS

コード commit → 再生成 → データ commit の順序、両日の provenance / hash / counts、gap exit 1、DB backup を独立確認。`supersedes_manifest_sha256` が指す旧 manifest の immutable 保存がないため、次回は旧 artifact または前 blob SHA も保持する。

## 横断優先課題

1. `fresh_odds_coverage --check-gaps` を定期監視と GUI 状態表示へ接続する。
2. SE の逆順リプレイでも、解決済みレースに `horse_num='00'` が再挿入されない invariant を追加する。
3. supersedes 先の旧 manifest / blob を immutable に保存し、provenance chain を自動検証する。
