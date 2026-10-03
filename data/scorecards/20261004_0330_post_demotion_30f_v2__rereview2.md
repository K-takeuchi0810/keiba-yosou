# post-demotion repaired 30-feature — 限定再レビュー (2f74046、2026-10-04)

- 対象: SHA **2f74046** (前回 da05c51 → 4 名 PASS、must-fix は prediction-logic M1 = docs の因果の付与)
- 担当: prediction-logic (docs の是正) / code-quality (コードの是正)
- 運用: subagent CWD 限定運用。学習・評価は再実行しない。変異は git archive 2f74046 の隔離コピー。レビュー中 worktree 不変

| 担当 | 判定 | 点 | 前回 |
|---|---|---|---|
| prediction-logic-analyst | PASS | 4.3 | 4.0 (M1 あり) |
| code-quality-reviewer | PASS | 4.3 | 4.2 |

## 確認されたこと

- M1 是正: 裾の広がりの原因は判別できない (再学習のばらつきと区別できない、seed sweep 未実施) と書き直し、初稿の撤回を明記。docs の数値 (gain 0.1999% / 0.2972%、発火 0.858%、木 28→36 / 247→220、SD ×1.121、R² 0.295、≥1.75 の馬・購入条件の馬の値、受理 (a) の半幅) を成果物から独立に再計算して全一致
- 窓ガードの fail-closed 化・build_dataset の前への移動: 本番の呼び出しは 2 つの eval だけ。worktree の meta 6 件はすべて train / validation を持ち、壊れる利用は無い。窓キーを改名したときに黙って素通りしていた変更失敗モードが、即停止に変わった
- B30〜B34 を独立に再現して 5/5 KILLED。追加の変異 7 体中 4 体 KILLED、生存 3 体は挙動の誤りではなくテストの空白
- provenance.data_version の握り潰しの呼び出し元 7 箇所はすべて open な接続を渡している (狭めても壊れる呼び出し元は無い)。先送りは是、ただしバックログを文書に残すこと

## レビュー後に入れたもの (docs とテストだけ。CLAUDE.md の expert-review の対象外。再レビューはしていない)

- docs (prediction-logic の nice-to-have N-a〜N-d): gain の配分の変化は市場オフセットで ±2pt (Fundamental は ±0.7pt)、乱数は「少なくとも列のサンプリングの抽選」、+0.54 は seed 固定の 1 組の観測、β₂ の区間は両世代とも n_boot=300 で ΔLogLoss と対差の区間だけ n=2000
- テスト: meta そのものが無ければ FileNotFoundError で止まる (code-quality の Mb6 が生存していた分岐)。変異 B35 を追加

## バックログ (このブランチでは行わない)

- `predictor/provenance.py` の `data_version` の `except sqlite3.Error` を `OperationalError` に狭める + 閉じた接続で ProgrammingError が伝播するテスト + 台帳なしで "nodata" のテスト (3 点セット、別 PR)
- `snapshot()` に db_path / size / mtime (data_version は取り込み台帳だけの指紋)
- 窓キー ("train", "validation") を定数にして fit 2 本の meta 書き出しとガードで共有 / 片方の窓だけの meta のケース / ガードが build_dataset の前に効くことをテストで固定
- seed を 2-3 本変えた学習で validation 2025 内の補正の seed 間相関を測る (「再現性の床」と裾の広がりの判別不能を解消する。strategy_dev では走らせない)。gain の配分の表を次回の成果物に
- run_step.py の usage / SystemExit / config の既 import の検査 (実行した版は書き換えない。次回のスクリプトで)
- fundamental_eval / market_offset_eval の未使用 import の掃除 (base から)
- compare.py の単体テスト、または scripts/ への昇格
