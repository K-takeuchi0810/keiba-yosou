# データ取得・補完 計画 (2026-06-28)

## 0. 背景と目的

LGBM v5 の特徴量重要度を可視化したところ、**騎手系で gain の 66%** を占め、
「市場残差になりうる」特徴 (上がり3F=展開、コース/距離適性、馬場バイアス、調教) が
ほぼ未使用 (各 ≤2%、多くは gain=0) だった。原因を調査した結果、これらの特徴の
**裏付けデータ自体が DB に欠落** していることが判明 (memory: project_data_quality_gates_2026_06_28)。

本計画は「不足しているデータを全て取得・補完し、市場残差特徴を使える土台を作る」ことを目的とする。
これは回収率改修ロードマップの Step 1 (データ品質) の一部であり、LGBM v6 (Step 5) の前提。

参照: `predictor/lgbm_meta.json` (v5 は 2021-2024 学習), CLAUDE.md ルール3 (JV-Link は 32bit `.venv32`),
`.claude/skills/jvlink-com/`。

---

## 1. 調査で確定したギャップ (実測値)

| # | データ | DB 現状 | raw 状況 | 根本原因 | 重大度 |
|---|---|---|---|---|---|
| G1 | 上がり3F `horse_races.final_3f` | 2020-24 **1.2%** / 2025 55% / 2026 100% | RACE raw の `H1xx` 大型ファイルは SE 非含有 | 過去 RACE 取得が上がり3F無し形式 | 高 |
| G2 | 脚質 `horse_races.leg_quality_code` | 2020-24 ~48% / 2026 99% | 同上 | 同上 (SE 由来) | 中 |
| G3 | 調教タイム `training_times` | **2026-06 のみ** (28,176) | **SLOP 2021+/WOOD 2021+ raw あり** (HC/WC 含む) | HC/WC dispatch が 2026-05-13 追加→旧 raw が未再処理 | 高 |
| G4 | 走破時計 `finish_time` | 2020-24 ~78% / 2026 99% | RACE | SE 由来。G1 と同時に改善 | 低 |
| G5 | マイニング `mining_predictions` | 2021-2026 ✓ / 2020 無 | MING 2021-2026-05 | MING サービスが 2021 開始 (2020 は原理的に無い) | 低 |
| G6 | 特別登録 `special_entries` | **2026 のみ** (403) | TOKU 1 ファイルのみ | 過去 TOKU 未取得 | 低 |
| G7 | 繁殖 `breeding_horses.birth_year` | **6,953 / 6,957 が異常値** | BLOD 2020-2023 | パーサの byte 位置バグ疑い | 中 |
| G8 | 馬体重 `WH` / 天候馬場詳細 `WE` | 未取り込み (dispatch skip) | RACE 内に混在の可能性 | 未対応レコード種別 | 低 (要重複確認) |
| - | 払戻 `payouts` | 2020-2026 ~3,456/年 | RACE | JRA 約 3,400/年 = ほぼ完備 | なし |

数値根拠: 年別充足率クエリ (`final_3f`: 2020-24=1.2%, 2026=100%)、`training_times` の
`training_date` MIN/MAX = 20260604..20260628、`breeding_horses` birth_year valid=4/bad=6953。

注: §1 は「DB に既にある列の欠落」。これとは別に **JV-Link が提供しているのに一切取り込んで
いないレコード種別/dataspec** が多数あることが §1A で判明した (§1 は §1A の部分集合)。

---

## 1B. データ所在の 3 層モデル (重要・コスト前提)

| 層 | 場所 | 状態 |
|---|---|---|
| ① JRA-VAN サーバ | リモート | 全データ |
| ② **JV-Link ローカルキャッシュ** | **`C:\ProgramData\JRA-VAN\Data Lab\data` (3.6GB)** | **既にダウンロード済**。全種別 (SE 2000-2026, O1-O6, H1/H6, BT/KS/CH/BR/RC, JG/WF 等) の .jvd が存在 |
| ③ 本プロジェクト | `data/raw/` → `data/keiba.db` | ②の部分集合のみ取り込み済 |

**実測で確認した事実**:
- ② のキャッシュ .jvd は **zlib 圧縮 + JV-Link 独自フレーミング** (先頭 `   <size>` + `x\x9c` zlib ストリーム)。
  zlib 解凍は可能だが、解凍後も我々のパーサ形式 (CRLF/固定長) と異なり **直接パース不可**。
  → キャッシュを自前で読むのは非推奨。正規の **JVOpen → JVGets** 経由が必須。
- **重要な含意**: 欠落データの大半は **②に既にダウンロード済**。よって取得は
  「JRA-VAN サーバからの数 GB 再ダウンロード」ではなく、**JVOpen がローカルキャッシュを読み出す
  (=高速・ネットワーク DL ほぼ無し)** + 解凍 + 我々のパーサ。ボトルネックは COM 処理時間であり通信ではない。
- 例外: §1A(b) の「raw ディレクトリ自体が無い」dataspec のうち、② にも無いものは実際の DL が要る
  (速報系の一部等)。② に存在するかは取得前に Data Lab を確認すればよい。

→ 結論: **「Data Lab にあるのに DB に無い」= ダウンロード問題ではなく取り込み (JVOpen+parse+ingest) 問題**。
ユーザの指摘どおり、ソースはローカルにある。我々のパイプラインが読み切れていないだけ。

---

## 1A. JV-Link 提供データ 網羅監査 (最重要・検証の大前提)

**結論: 現状、JV-Link 提供データを抜け漏れなく取得できていない。** 既に fetch 済み (raw に存在) で
ありながら parse / DB 投入していないレコード種別が約 20 種、さらに一度も fetch していない
dataspec が複数ある。証拠は `data/raw/*` の全 dataspec を `_split_records` で走査し、
ingest dispatch の対応種別 (RA/SE/HR/O1/UM/HS/DM/TM/HN/SK/HC/WC/TK) と突き合わせた実測。

### (a) raw に存在するが parse 未対応 = 取り込めていない (ダウンロード不要・再 ingest で取得可)

| レコード | 内容 | dataspec | 価値 |
|---|---|---|---|
| **O2** `馬連` **O3** `ワイド` **O4** `馬単` **O5** `三連複` **O6** `三連単` | 各式別オッズ | RACE | 馬券種別 EV/的中検証に必須。現状 O1(単複枠)のみ |
| **H1** `票数(単複枠)` **H6** `票数(三連単)` | 投票数 (市場の資金流入) | RACE | pre-odds の市場シグナル。市場残差研究に有用 |
| **JG** | 競走馬除外/出走時情報 (要確認) | RACE | 出走可否・除外。サンプルで 11k 件と多い |
| **WF** | 重勝式 (WIN5) | RACE | 重勝式オッズ/結果 |
| **KS** `騎手マスタ` | 騎手属性 | DIFN | 騎手特徴の素 (現状は horse_races の rate 集計のみ) |
| **CH** `調教師マスタ` | 厩舎属性 | DIFN | 同上 (厩舎) |
| **BR** `生産者マスタ` | 生産者 | DIFN | 生産者特徴の潜在源 |
| **BN** `馬主(番組?)` / **HY** `馬主` | 馬主 | DIFN / HOYU | HY はサンプルで 13 万件超 |
| **RC** `レコードマスタ` | コースレコード | DIFN | 持ちタイム比較の基準 |
| **BT** `系統` | 血統系統 | BLOD | 系統別適性 (現状 sire/dam_sire の rate のみ) |
| **YS** `開催スケジュール` | 年間日程 | YSCH | 運用・ローテ |
| **CS** `コメント` | 記者コメント | COMM | テキスト特徴 (将来) |
| **WE** `天候馬場` **TC** **AV** | 速報 天候/馬場/異常 | 0B14 | 当日馬場の即時反映 |

### (b) 一度も fetch していない dataspec (raw ディレクトリ自体が無い)

- 速報系 (JVRTOpen): **`0B11`** 速報オッズ, **`0B15`** 速報票数, **`0B16`** 速報開催情報(指定),
  **`0B20`** 速報タイム型マイニング, **`0B30`** 速報払戻, **`0B41`** 速報重勝式オッズ
  (取得済みは 0B12/0B13/0B14/0B17/0B31 のみ)
- 累積成績 (option=2): **`TCOV` / `RCOV`** (および今週版 TCVN/RCVN)

※速報系は主に「当日リアルタイム予想」用途。歴史 backtest には RACE 確定値で足りるが、
ライブ運用の完全性には必要。重複/用途は取得後に判定する。

### (c) 既に対応済み (参考)

RA, SE, HR, O1, UM, HS (競走馬), DM/TM (マイニング), HN/SK (繁殖/産駒), HC/WC (調教), TK (特別登録)。

### 監査の限界

- 上記は raw サンプル走査による「種別の有無」。各種別の**全期間網羅率**は parse 実装後に要再測定。
- レコード種別名 (JG/WF/BN/RC/TC/AV) の正確な定義は `docs/JV-Data4901.pdf` で確認のこと
  (`.claude/skills/jvdata-record/` 使用)。

---

## 2. 対処方針 (3 グループ)

### グループ A — 既存 raw の再取り込みで埋まる (DL 不要・軽量・最優先)

**対象: G3 調教タイム**

- SLOP/WOOD の raw は 2021+ 存在し HC (坂路)/WC (ウッド) レコードを含む。
- HC/WC の DB dispatch は 2026-05-13 に追加されたため、それ以前に取得済みの SLOP/WOOD raw は
  `ingested_files` に記録済み=スキップされ、training_times に入っていない。
- → **既存 raw を強制再取り込み** (`ingest_all(only_files=...)` か該当 ingested_files 行削除後 re-ingest)。
- JV-Link ダウンロード不要、ローカル再パースのみ。

**実行前の実証 (必須)**: temp DB に 2021 の SLOP raw を 1 ファイル ingest し、training_times に
HC レコードが入ることを確認してから本実行する。

**期待結果**: training_times が 2021-2026 に拡大。調教特徴が 2021+ で利用可能に。

### グループ A2 — parse 未対応レコードの実装 → 既存 raw を再 ingest (DL 不要・コード作業)

**対象: §1A(a) の約 20 レコード種別** (O2-O6, H1/H6, JG, WF, KS/CH/BR/BN/HY/RC, BT, YS, CS, WE/TC/AV)。

- いずれも raw に既に存在するため、**parser (`jvlink_client/parser.py`) と dispatch
  (`jvlink_client/ingest.py`) と DB スキーマ/upsert (`db.py`) を追加** すれば、
  既存 raw の再 ingest だけで取り込める (JV-Link ダウンロード不要)。
- 各レコードは固定長バイナリ。byte 位置・cp932・BSTR の罠は `.claude/skills/jvdata-record/` に従う。
- 優先度 (予想価値順):
  1. **O2-O6 (式別オッズ)** — 馬券種別の EV/的中検証の前提。最優先。
  2. **H1/H6 (票数)** — 市場の資金流入 = pre-odds 市場シグナル。
  3. **BT (系統) / KS・CH・BR (マスタ)** — 特徴量拡張の素。
  4. **RC (レコード) / YS / HY / BN / CS / WE / JG / WF** — 文脈・運用・完全性。
- 各種別ごとに: スキーマ追加 → parser → dispatch → upsert → テスト → 再 ingest → 網羅率検証。
- 実装は段階的に (1 種別ずつ expert-review 可能な単位で)。

**期待結果**: JV-Link 提供レコードを取りこぼしなく DB 化。特に式別オッズで馬券種別分析が可能に。

### グループ B — JV-Link COM 経由で再取り込み (要 32bit COM・ただし大半はキャッシュ読み)

**前提 (§1B)**: 対象データの大半は Data Lab キャッシュ (②) に既にある。よって本グループは
「サーバからの数 GB ダウンロード」ではなく **JVOpen がローカルキャッシュを読み出す高速処理**。
ただし JV-Link COM (32bit `.venv32`) の実行と認証は必要。実 DL が発生するのは ② に無い分のみ。

**対象: G1 上がり3F + G2 脚質 + G4 走破時計 (まとめて RACE/SE 再取得)**

- 2020-2024 の `data/raw/RACE` は SE を正しく含まないが、Data Lab には SE (2000-2026) があるため
  JVOpen RACE fromtime=2020 でキャッシュから SE を読み出し upsert。
- `upsert_horse_race` は `ON CONFLICT DO UPDATE` (final_3f は excluded>0 で更新) なので
  既存行が上書き補完される。`scripts/bootstrap.py` は **取得後に強制再 ingest** するため重複問題なし。

**コマンド (ユーザ手動)**:
```
# パイロット (認証・パーサ確認、数分)
.venv32\Scripts\python.exe -m scripts.fetch_smoke

# 本取得 (過去5年・RA/SE 強制再投入、数時間〜半日、5-15GB、resumable)
.venv32\Scripts\python.exe -m scripts.bootstrap --fromtime 20200101000000
```

**注意 (jvlink-com スキル)**: `-301`=利用キー不正 / `-303`=未設定 → JV-Link 本体ダイアログで登録。
`-202`=前回 Open 残り (自動 Close 対策済)。Ctrl-C 中断→キャッシュで再開可。

**対象: §1A(b) 一度も fetch していない dataspec**

- 速報系 `0B11/0B15/0B16/0B20/0B30/0B41` を JVRTOpen で取得 (ライブ運用の完全性)。
  歴史 backtest には不要だが「抜け漏れなく」の要件では取得対象。用途/重複は取得後判定。
- 累積成績 `TCOV/RCOV` (option=2) を取得。
- これらは新規 fetch スクリプト/RT key 実装が要る場合あり (`.claude/skills/jvlink-com/`)。

**対象: G6 特別登録 (任意・優先度低)**

- 過去 TOKU を取得したい場合は bootstrap の dataspec に TOKU を含める (現状 BOOTSTRAP_DATASPECS に含む)。
- ただし special_entries は主に「次走の重賞登録馬」用途で、過去 backtest への寄与は小さい。後回し可。

### グループ C — コード修正 (パーサ / dispatch)

**対象: G7 breeding_horses.birth_year パーサバグ**

- birth_year がほぼ全て異常値 (0011, 9921 等)。HN (繁殖馬) パーサの byte 位置を仕様書で再確認し修正。
- 修正後、既存 BLOD raw を再パースすれば DB 補正可能 (raw 2020-2023 あり)。
- pedigree 特徴 (sire_*/dam_sire_*) は JOIN キー (blood_register_num) で動いており gain>0 なので
  birth_year 自体は現状未使用の可能性。優先度中 (将来 馬齢×血統 特徴を足すなら必要)。
- 対応スキル: `.claude/skills/jvdata-record/`。

**対象: G8 WH (馬体重) / WE (天候・馬場) dispatch 追加の要否**

- 現状 dispatch で skip。ただし `horse_races.horse_weight` (SE 由来) と `races.weather_code/
  turf_condition/dirt_condition` (RA 由来) が既に存在するため **重複の可能性**。
- 先に「既存列で足りているか」を確認し、不足 (例: 直前馬体重の時系列、詳細馬場) があれば追加。
- 優先度低。

---

## 3. 実行順序

```
1. [A]  調教タイム再取り込み実証 → 本実行          (Claude、DL不要、即日)
2. [A2] parse 未対応レコードの実装 → 再 ingest     (Claude、DL不要、段階的)
        優先: O2-O6 → H1/H6 → BT/KS/CH/BR → 残り
3. [B]  RACE/SE 再取得 (final_3f/脚質)             (ユーザ手動、JV-Link、数時間)
4. [B]  未 fetch dataspec (速報系/TCOV/RCOV)       (ユーザ手動 or 要実装)
        - 1〜2 と 3〜4 は独立なので並行可
5. 各取得後に検証スイート (§4) を実行              (Claude)
6. [C]  breeding birth_year パーサ修正             (Claude、要 jvdata-record)
7. [C]  WH/WE 要否判定 (既存列との重複確認)         (Claude)
8. すべて補完後、特徴量 充足率を再可視化            (Claude)
   → 市場残差特徴が使える状態を確認 → LGBM v6 (別計画) へ
```

---

## 4. 検証スイート (各取得後に必ず実行)

年別充足率を再測定し、目標 (~100%) に到達したか確認:

```sql
-- 上がり3F / 脚質 / 走破時計 (G1/G2/G4)
SELECT race_year,
  ROUND(100.0*SUM(CASE WHEN final_3f>0 THEN 1 ELSE 0 END)/COUNT(*),1) f3f,
  ROUND(100.0*SUM(CASE WHEN leg_quality_code NOT IN ('','0') THEN 1 ELSE 0 END)/COUNT(*),1) leg,
  ROUND(100.0*SUM(CASE WHEN finish_time>0 THEN 1 ELSE 0 END)/COUNT(*),1) ft
FROM horse_races WHERE data_div='7' AND race_year>='2020' GROUP BY race_year;

-- 調教タイム (G3)
SELECT substr(training_date,1,4) y, COUNT(*) n FROM training_times GROUP BY y;

-- 繁殖 birth_year (G7)
SELECT CASE WHEN CAST(birth_year AS INT) BETWEEN 1980 AND 2026 THEN 'valid' ELSE 'bad' END k,
       COUNT(*) FROM breeding_horses GROUP BY k;
```

合格基準: G1/G3 が 2021-2024 で ≥95%、G7 valid が大半。

---

## 5. リスク・留意点

- **B は外部サービス (JRA-VAN 契約) への数 GB DL**。認証ダイアログが対話的なためユーザ手動。
- **A の前提**: 旧 SLOP/WOOD raw が intact であること (BSTR 破損なら再 DL 必要)。実証ステップで確認。
- **強制再 ingest の副作用**: upsert は冪等なので安全。ただし ingested_files を消す場合は対象 dataspec のみ。
- 取得後の LGBM v6 学習は別計画。本計画は「データを揃える」ところまで。
- すべての作業は CLAUDE.md ルール (32bit 経路、expert-review、重い計算の pre-flight 1-ter) に従う。

---

## 6. 完了の定義 (Definition of Done)

- [ ] training_times が 2021-2026 をカバー (G3)
- [ ] final_3f / leg_quality / finish_time が 2020-2024 で ≥95% (G1/G2/G4)
- [ ] **§1A(a) の約 20 レコード種別を parse+DB 化** (最低 O2-O6, H1/H6, BT, KS/CH/BR)
- [ ] **§1A(b) 未 fetch dataspec の取得 or 「不要」判定の記録** (速報系/TCOV/RCOV)
- [ ] breeding_horses.birth_year が正常値 (G7)
- [ ] WH/WE の要否を判定し記録 (G8)
- [ ] **「JV-Link 提供レコードを全種別カバー」を網羅監査の再走査で確認**
- [ ] 特徴量 充足率の再可視化で市場残差特徴が使える状態を確認
- [ ] 上記の検証 JSON / scorecard を保存

---

## 7. 実施状況 (2026-06-30 更新)

全 raw (data/raw) を全走査し、「raw に存在するのに DB 未投入」を一掃した。

### 取り込み完了 (raw から再 dispatch で投入、DL 不要)

| バッチ | レコード | 投入行数 (dedup後) | 備考 |
|---|---|---|---|
| マスタ | KS/CH/BR/BN | 1560/1475/10746/8710 | 2026-06-29 |
| B2 式別オッズ | O2-O6 | exotic_odds 58.7M | **全て data_div=5 (確定=発走後)** |
| B2 票数 | H1/H6 | vote_counts 61.6M | 全 8 式別 |
| B2 その他 | JG/WF | race_scratches 291k / win5 332 | |
| B3/B4 | RC/CS/YS/BT/HY/WE/AV/TC | RC474/CS119/YS1732/BT92/HY176810/WE8/AV1/TC3 | |

- 実 ingest = `scripts/backfill_race_extras.py` (RACE) + `ingest_all(force, dataspecs=[...])` (他)。
- byte 位置は全種を実 raw で検証済 (BT 系統名は実データで pos50 と判明し補正)。
- **★PIT 規律**: B2 オッズ/票数は全行 data_div=5 (確定=発走後)。**発走前の特徴量入力に使用禁止**
  (schema.sql にコメント固定)。発走前 速報を残差に使うには下記 JV-Link fetch が必要。
- 被覆: exotic_odds/vote_counts は近年 ~18,927 レース (確定オッズ raw の取得範囲)。
  payouts 43,242 レースより狭く、長期履歴特徴には使えない (B2 は近年のみ)。

### 残るギャップ = JV-Link fetch 必須 (raw に存在せず、32bit COM での DL が要る = ユーザ手動)

全走査の結果、raw に**一度も無い**ため再 dispatch では取得不能なもの:

| 項目 | 内容 | 取得方法 (.venv32 / 32bit JV-Link) |
|---|---|---|
| **final_3f** | 上がり3F (2020-24 が ~1.2% のみ) | `.venv32/Scripts/python.exe -m scripts.bootstrap --fromtime 20200101000000` で RACE を再 fetch (SE 再取得)。完了後 final_3f 充足率を再確認 |
| **WH 馬体重** | 発走前馬体重 (F6) | 速報系 (0B 系) dataspec の fetch が必要。option=4 の過去取得対象外で主に運用 fetch で前向き蓄積。要 JV-Link 調査 |
| **JC 騎手変更** | 発走前騎手変更 | 同上 (速報系) |
| **CC コース変更** | 発走前コース変更 | 同上 (速報系) |

注: これらは CLAUDE.md ルール 3 (32bit 経路) / 1-ter (重い fetch の pre-flight) に従って実行する。
final_3f 再取得は数時間規模なので bg + pre-flight checklist 必須。Claude 側からは COM を起動できない
(ユーザ手動)。
