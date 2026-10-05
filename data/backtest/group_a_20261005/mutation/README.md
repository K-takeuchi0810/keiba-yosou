# Group A の変異テストの記録 (2026-10-05)

- spec: `tests/mutation_specs/group_a_spec.py` (34 個: scripts/group_a.py 29 + scripts/group_a_class_table.py 5)
- 実行: `git archive <sha>` の隔離コピー (scratchpad、`.git` 無し) + `.venv64` のジャンクション (実行後に `rmdir` で外した)
- run1 (`cc1c711`): KILLED 31 / SURVIVED 3 (G3・G14・G28)
  - G14 (ハンデ戦を斤量の推定に入れる): テストのハンデ戦のゴミ値が ±3 の clip の外で、除外を通らずに捨てられていた → 値を clip の内側に直した
  - G28 (期待勝ち時計から年齢の区分を外す): テストが選んだレースが基準の区分 (係数 0) だった → 2 歳・999 のレースで明示的に確かめた
- run2 (`d5290f2`): KILLED 33 / SURVIVED 1 (G3)
  - G3 (障害の境界 `OBSTACLE_FROM` を 51 → 60) は **等価な変異**: `surface_of` は 10〜29 以外をすべて None (使わない) にするので、
    境界の定数は振る舞いを変えない (定数は定義の明示として残す)
- run3 (`4de77cb`、4 名レビューの must-fix の後): **KILLED 40 / 40**。G30〜G35 (推定の年のガード・全成分が逆符号・凍結物の尺度・
  平地の未知のコード・SD 0・mode=ro) を追加。G3 は、平地の未知の track_type_code で止めるようにしたので等価ではなくなり KILLED
- run4 (`3bfe6fb`、P3 の改訂 B と検出力の経路の後、50 個): KILLED 49 / SURVIVED 1 (P4: Fisher 情報を一様の確率で作る。SE の比較の
  許容 10% では見分けられなかった) → 手計算の小さな例 (市場の確率で重み付けた S の分散) のテストを足した
- run5 (`45295fb`): **KILLED 50 / 50**
- run6 (`e087d0a`、限定再レビューの反映の後、58 個): **KILLED 58 / 58** (G39〜G44・P8〜P9 を追加。G6 / G28 / P2 はコードの変更に合わせて置換前の文字列を更新)
