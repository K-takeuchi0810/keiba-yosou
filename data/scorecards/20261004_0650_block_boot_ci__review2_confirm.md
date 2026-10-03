# Phase 0.5-5 の主検定の区間 (block_boot_ci / primary_block_ci) — レビュー (2026-10-04)

- 対象: branch `block-boot-ci-20261004`。b647988 → (指摘の反映) → ad2ea7e
- 外部の指示者の指定: validation (統計の契約に関わるので必須) + code-quality

| 担当 | b647988 | ad2ea7e (確認) |
|---|---|---|
| validation-process-auditor | PASS (条件付き) 4.0 | **PASS 4.4** |
| code-quality-reviewer | PASS 4.3 | — |

## validation の must-fix (解消済み)
1. レース単位の再抽出の behavioral なテストが無かった (馬単位・最後のレースを引かない・1 本多く引く の変異が生存)
   → 2 頭ずつ 2 レースで平均は {0, 5, 10} だけ・頭数は常に 4、のテスト
2. 登録 seed 20261004 の乱数列がメタデータでしか固定されていなかった (seed + 1 の変異が生存)
   → 固定の標本で primary_block_ci の lo / hi を golden 値 (−0.18383339415685848 / 0.1454146544589627) で固定
- 変異 18/18 KILLED (data/backtest/block_boot_ci_20261004/mutation_run2.txt)。validation が spec 外の変異 (numpy の乱数・定数 20261005 など) も golden テストで殺せることを確認

## code-quality の指摘 (反映したもの)
- max_discard_frac の型の検査 (bool / 文字列 / None)、max_discard の浮動小数の丸め、空の標本を止める、境界値のテスト、
  標本の順序で区間が変わることの明記 (主検定のコードは決定的な順序で渡し入力の sha256 を残す)、事前登録 §8-4 に関数名の注記
- 主検定のコードは primary_block_ci だけを使い、block_boot / coefficient_ci (95%) を使わない (docstring と事前登録に明記)

## 次の工程への申し送り (主検定のコードを書くとき)
- 判定は `valid` を先に見る (`float("nan") > 0` は False なので、`lo > 0` だけだと無効な区間が PRIMARY_FAIL に化ける)。そのテストを付ける
- 戻り値の dict (水準・回数・seed・捨てた回数) を丸ごと成果物に残し、`level == 0.99 and n_boot == 5000` を assert
- 条件付きロジットの係数の主検定用に primary_coefficient_ci のような入口を用意し、95% の coefficient_ci を使わない
- 空の集合を例外で落とすか PRIMARY_INCONCLUSIVE にするかを呼び出し側で明示する
- scripts/frontrun_analysis.py の独自の _block_boot は eval_stats の block_boot の別名に置き換えられる (別件)
