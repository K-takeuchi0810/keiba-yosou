# 採点 2026-08-22 12:10

**改修内容**: fresh odds 6 日間停止の復旧 + 発走後オッズ刻印ガード/修復 + auto_predict 出走馬ゲート + 買い候補フィルタのサスペンド
**対象ファイル**: `db.py` / `config.py` + `predictor/filter.py` / `scripts/fetch_fresh_odds.{bat,py}` + `scripts/repair_odds_stamps.py` (新規) / `scripts/auto_predict.py` / `web/generator.py` + `web/templates/index.html.j2` + `gui/app.py`
**コミット**: `744bd63` (コード 23 ファイル) / `3b53b4b` (証跡 116 ファイル)、branch `fix/fresh-odds-recovery-and-filter-suspension`
**採点時の状態**: 未コミット作業ツリー (各 agent は `git diff` で読了)。採点後に指摘を是正して上記 2 commit に確定

## 総合スコア (項目平均) の推移

| 専門家 | 今回 | 前回 (20260808) | 差分 |
|---|---|---|---|
| GUI / UX 監査人 | 3.4 | 3.6 | -0.2 |
| モバイル HTML レビュアー | **4.2** | 4.0 | **+0.2** |
| 予想ロジック分析官 | **3.9** | 4.8 | **-0.9 ⚠ 後退** |
| 収益性 / 投資判断 | 4.2 | 4.2 | ±0 |
| データパイプライン技術者 | **3.6** | 4.0 | **-0.4 ⚠ 後退** |
| コード品質レビュアー | **3.8** | 4.2 | **-0.4 ⚠ 後退** |
| 検証プロセス監査人 | **3.4** | 4.0 | **-0.6 ⚠ 後退** |
| **全体平均** | **3.79** | 4.11 | **-0.32** |

**判定**: PASS 3 名 (モバイル / 収益性 / 予想ロジック) / HOLD 4 名 (GUI / データ基盤 / コード品質 / 検証)

⚠ **4 名が -0.3 以上の後退**。ただし 4 名全員が「改修品質の低下ではない」と明記している:
本改修が初めて `BUY_FILTER_DEFAULT` と backtest 契約に踏み込んだため、従来は
predictor 非接触の運用改修では露出しなかった構造欠陥 (キーリスト伝播漏れ、
sweep の鮮度ゲート欠如、commit の非自己完結) が可視化されたことによる。

## 各専門家の所見

個別 scorecard は `20260822_1210_fresh_odds_recovery__<agent>.md` を参照。要旨:

- **GUI / UX (3.4, HOLD)**: 公開 HTML はサスペンドを開示するのに GUI は 0 件理由を
  「EV/信頼度条件を満たすレースは見送り」と虚偽表示。フィルタパネルも稼働中に見え、
  入力欄が silent no-op になる。検証モード警告も自己矛盾。→ 4 経路を config 分岐に是正
- **モバイル HTML (4.2, PASS)**: 情報密度/誤読防止が 4→5。ゼロ状態開示のベストプラクティス
  (理由・開始日・復帰条件) を満たし、新規文言の AA コントラストを実測 PASS (5.31〜11.45:1)。
  公開経路 560KB。残課題は引数なし生成 2.58MB と waku 4/6/7/8 の AA 未達 (3 回目の持ち越し)
- **予想ロジック (3.9, PASS)**: post-start ガードは PIT 規律と意味論が一致。修復の復元分岐は
  市場人気加点を発火させうるため apply 前後で backtest 互換が切れる。fresh_rate 46.7% で
  calibrator compat の前提分布が激変。印と P の別ランカー構造 (◎≠最高P 39.2%) は不変で、
  サスペンドは現時点で取り得る正しい封じ込め。`buy_filter_from_generator` の suspended 脱落を検出
- **収益性 (4.2, PASS)**: 全数値を独立再導出。「価値破壊を確認」は z≈1.0 で有意でなく over-claim、
  新規窓は通年窓の部分集合で独立証拠でない、賞味期限 3 ヶ月は未超過 (2.3 ヶ月) の 3 点を指摘。
  正しい根拠は「便益の正の証拠が 3 窓すべてで不在」。撤回規律の実行を本プロジェクト初と評価
- **データパイプライン (3.6, HOLD)**: commit した db.py が未コミットの JC/CC parser に依存し
  clean checkout で `import db` が ImportError = 復旧経路の全滅を検出 (最重要)。6 日間停止の実在を
  coverage JSONL で独立確認。repair --apply 未実行のため母数消失は未修復
- **コード品質 (3.8, HOLD)**: 明示キーリストによる「config にキーを足すと backtest に届かない」
  失敗モードが本 diff 内で実際に発生。repair のテストゼロ、`source` → `odds_dataspec` の
  ドメイン混在、開始日の 3 重記述、db.py の重複デフォルト行を指摘
- **検証プロセス (3.4, HOLD)**: 解除機構である filter_sweep に鮮度ゲートが無く、かつ修復前 DB で
  走っているため走行中 sweep の結果は使用不可。env 追跡キー欠落。修復後の再ベースライン未了。
  2 run 合算 (1,893 戦) を撤回した判断は正しいと確認

## 本セッションで実施した是正 (採点後)

| 指摘 | 是正 |
|---|---|
| HEAD が import 不能 (JC/CC 混入) | 履歴を作り直し db.py を自分の変更のみに分離。別 worktree で import 実測 OK |
| suspended が backtest に伝播せず文書と矛盾 | 「backtest は計測器なので伝播させない」を契約化 + 契約テスト 2 本 + env_keys 登録 |
| filter_sweep に鮮度ゲートなし | backtest と同一ゲートを移植 (`--no-odds-gate` で ablation) + テスト。走行中 sweep は破棄 |
| GUI の虚偽表示 | 0 件警告 / 検証モード / JS 空状態 / パネル注記の 4 経路を config 単一出典で分岐 + 契約テスト |
| repair のテストゼロ / ドメイン混在 | 単体テスト 4 本 (境界 >= / restore / clear / dry-run) + `odds_dataspec` 保持に修正 |
| watchdog が他者の lock を消しうる | 解放前に lock の PID と自 PID を照合 |
| config の over-claim / 事実誤認 | 「有意には示せない、根拠は便益の証拠の不在」に修正。「賞味期限超過」を削除 |
| 開始日の 3 重記述 | `config.BUY_FILTER_SUSPENDED_SINCE` に一元化 |
| 実運用集計の定義未文書 | commit message に集計規約を明記 |

tests: **444 passed / 4 skipped** (採点時 436 → 是正で +8)

## 横断的に見た優先課題

1. **`repair_odds_stamps --apply` の実行と、その後の再ベースライン** (担当: data-pipeline-engineer +
   validation-process-auditor + prediction-logic-analyst の 3 名が一致)
   - 7,444 行 / 544 レースの汚染が残存し、母数回復 (2026 H1 1,177 → 1,568) は未達
   - 正しい順序: repair --apply → 同 2 窓の backtest 再実行 → monitor baseline 再凍結 →
     鮮度ゲート付き `filter_sweep --recent-3fold` で再選定
   - この順以外では baseline が即陳腐化し、再選定は汚染母数で回る
2. **買い候補復活の前提条件を明文化** (担当: profitability-judge + prediction-logic-analyst)
   - 再選定が解除基準 (3 fold 点推定 ≥80% かつ CI 下限 ≥50%) を満たしても、回収率 CI 下限が
     100% を超えない限り「観察用」から上げない
   - 印 (ルールスコア) と gating を同一ランカーに統一、または印定義の HTML 明示を前提条件に含める
   - サスペンド中の前向き記録が途切れるため `build_daily_results` に would_be_candidate 列を追加
3. **モバイルの持ち越し 2 件** (担当: mobile-html-reviewer)
   - 引数なし生成 2.58MB が警告止まりで書き出される (誤経路 publish のリスク)
   - waku 4/6/7/8 の白文字コントラスト AA 未達 (3 回連続の持ち越し)
