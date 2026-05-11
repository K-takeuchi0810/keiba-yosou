---
name: jvdata-record
description: JV-Data の固定長バイナリレコード (RA/SE/HR/O1-O6/UM/KS/CH/WH/HC/TK/DM/TM/BT 等) のパーサと SQLite スキーマを追加するためのスキル。「○○レコード追加」「払戻取り込み」「オッズパース」「HR/O1/SE/UM/WH 等のパース」「JV-Data の新しいデータ種別を扱いたい」「dataspec から DB への取り込み追加」のような要求で必ず使う。バイト位置計算・cp932 デコード・BSTR ラウンドトリップ問題・CRLF 分割の落とし穴を全部押さえてあるので、知らずに書くと静かに壊れるパースを防げる。
---

# JV-Data レコード追加スキル

## 何のためのスキル？

`jvlink_client/parser.py` には現在 `RA` (レース) と `SE` (馬毎レース情報) しか定義されていない。残りの 20 種類以上のレコードを追加するときに **毎回同じ罠を踏むのを避ける** ためのスキル。

具体的には:
- 仕様書 PDF (`docs/JV-Data4901.pdf`) のバイト位置を 1-indexed で読む規約
- BSTR ラウンドトリップでレコード長が ±数バイトずれる挙動
- cp932 デコード時の全角空白 trim
- ファイル名先頭 2 文字 ≠ レコード種別 (`RAMM` の例)
- `dataclass` + `parse_xx` + `parse_xx_file` の 3 点セット規約
- `db.py` / `schema.sql` への対応テーブル追加手順
- `ingest.py` のディスパッチ追加

## 全体の流れ (1 種類追加するときの手順)

1. **仕様書のページを特定する** — `references/spec-locations.md` で対象レコードの PDF ページ範囲を引く
2. **生データの実物を確認** — `data/raw/<dataspec>/*.jvd` があれば `scripts/probe_record.py` で先頭バイトを観察
3. **`dataclass` を定義** — `jvlink_client/parser.py` に追加
4. **`parse_xx(rec: bytes) -> XxInfo` を書く** — 後述の規約に従う
5. **`parse_xx_file(path) -> list[XxInfo]` を書く** — 既存のヘルパで 1 行
6. **スキーマを更新** — `data/schema.sql` にテーブル追加
7. **DB レイヤを更新** — `db.py` に `upsert_xx` を追加
8. **取り込みディスパッチを更新** — `jvlink_client/ingest.py` のレコード種別判定に分岐追加
9. **動作確認** — `data/raw/` に既にファイルがあれば `python -m jvlink_client.ingest` でテスト

## 規約: parse 関数の書き方

既存の `parse_ra` / `parse_se` ([jvlink_client/parser.py](jvlink_client/parser.py)) と完全に揃えること。逸脱すると ingest が壊れる。

### 必須パターン

```python
RECORD_LENGTH = 1234  # 仕様書記載の固定長

@dataclass
class XxInfo:
    record_type: str       # 必須: 先頭 2 バイト
    data_div: str          # 必須: データ区分 (3 バイト目)
    data_created: str      # 必須: 作成年月日 (4-11 バイト)
    year: str              # 開催年 4 桁
    month_day: str         # 開催月日 4 桁
    track_code: str        # 競馬場コード 2 桁
    kaiji: str
    nichiji: str
    race_num: str
    # ... 以下、必要なフィールドのみ ...

def parse_xx(rec: bytes) -> XxInfo:
    # 必ず最初に長さ正規化する。BSTR ラウンドトリップで ±数バイト変動する。
    if len(rec) < RECORD_LENGTH:
        rec = rec.ljust(RECORD_LENGTH, b"\x00")
    elif len(rec) > RECORD_LENGTH:
        rec = rec[:RECORD_LENGTH]
    return XxInfo(
        record_type=_ascii(rec, 1, 2),
        data_div=_ascii(rec, 3, 1),
        data_created=_ascii(rec, 4, 8),
        year=_ascii(rec, 12, 4),
        month_day=_ascii(rec, 16, 4),
        track_code=_ascii(rec, 20, 2),
        kaiji=_ascii(rec, 22, 2),
        nichiji=_ascii(rec, 24, 2),
        race_num=_ascii(rec, 26, 2),
        # ... 仕様書のバイト位置をそのまま (1-indexed で) 渡す ...
    )

def parse_xx_file(path: str | Path) -> list[XxInfo]:
    data = Path(path).read_bytes()
    return [parse_xx(rec) for rec in _split_fixed(data, RECORD_LENGTH)]
```

### よくあるミスと対策

| ミス | 何が起きる | 対策 |
|---|---|---|
| 0-indexed でバイト位置を渡す | 全フィールドが 1 バイトずつズレる | 仕様書のバイト位置をそのまま `_slice/_ascii/_str/_int` に渡す。これらヘルパは 1-indexed |
| `_str` の代わりに `_ascii` を全角フィールドに使う | 馬名などが文字化け | 全角混じりは `_str` (cp932 デコード)、半角数字/コードは `_ascii` |
| 長さチェックでエラー raise | BSTR ラウンドトリップで死ぬ | 必ず `ljust` / `[:N]` で正規化 |
| `record_type` をテーブルに保存 | 全行で同じ値の無駄カラム | `db.py` の `_xx_to_row` で `d.pop("record_type", None)` |
| ファイル名先頭 2 文字でディスパッチ | `RAMM*.jvd` (RA だが ML 等が混在) で誤分類 | レコード本体先頭 2 バイトでディスパッチ |
| CRLF 分割を忘れて全体を 1 レコード扱い | 1 ファイル = 1 行になる | `_split_records` を使う ([ingest.py](jvlink_client/ingest.py)) |

### 文字コードヘルパ (既存)

```python
_ascii(rec, pos, length) -> str   # 半角英数 (コード値・数値文字列)
_str(rec, pos, length)   -> str   # 全角文字列 (馬名・人名)。cp932 + 全角空白 trim
_int(rec, pos, length, default=0) -> int  # 数値文字列を int 化、空欄は default
_slice(rec, pos, length) -> bytes # 生バイトが必要な特殊ケース用
```

`pos` は **1-indexed** (仕様書と同じ) で渡す。0-indexed ではない。

## 規約: スキーマと DB レイヤ

### schema.sql

主キーは仕様書の **「レコード識別キー」** に従う。多くのレコードは
`(race_year, race_month_day, track_code, kaiji, nichiji, race_num [, horse_num])`
の 6〜7 カラム複合キー。例外:
- `UM` (競走馬マスタ): `blood_register_num` 単独
- `KS` (騎手マスタ): `jockey_code` 単独
- `CH` (調教師マスタ): `trainer_code` 単独
- `O1`〜`O6` (オッズ): レース複合キー + `data_created` をキーに含める (時刻違いが共存)

カラム名は dataclass のフィールド名と完全一致させる (`upsert_xx` が `asdict` 経由で素直に流すため)。

### db.py

```python
def _xx_to_row(xx: XxInfo) -> dict:
    d = asdict(xx)
    d["race_year"] = d.pop("year")
    d["race_month_day"] = d.pop("month_day")
    d.pop("record_type", None)
    return d

def upsert_xx(conn: sqlite3.Connection, xx: XxInfo) -> None:
    row = _xx_to_row(xx)
    cols = list(row.keys())
    placeholders = ",".join(f":{c}" for c in cols)
    sql = f"INSERT OR REPLACE INTO <table> ({','.join(cols)}) VALUES ({placeholders})"
    conn.execute(sql, row)
```

### ingest.py

`ingest_file_dispatch` のレコード種別判定に分岐追加:

```python
elif rec_type == "XX":
    xx = parse_xx(rec)
    upsert_xx(conn, xx)
    xx_count += 1
```

集計 dict のキーも忘れず追加すること (`summary["XX"] = 0` 初期化、戻り値辞書、record_count 計算)。

## どのレコードを追加するか分からないとき

ユーザの目的別に推奨順序があるので [references/known-records.md](references/known-records.md) を参照。実装済みのレコードや、予想精度向上に効くレコードの優先順位がまとまっている。

## 仕様書の引き方

`docs/JV-Data4901.pdf` は 100 ページ超ある。レコード種別ごとのページ範囲は
[references/spec-locations.md](references/spec-locations.md) に索引化してある。
PDF を頭から読まないこと。Read ツールで `pages: "X-Y"` 指定して該当ページだけ読む。

## 検証

新レコードのパーサを書いたら、必ず実データで一周させる:

```bash
.venv32/Scripts/python.exe -c "
from jvlink_client.parser import parse_xx_file
recs = parse_xx_file('data/raw/<DATASPEC>/sample.jvd')
print(f'{len(recs)} records')
print(recs[0])
"
```

主キー重複・長さズレ・文字化けの 3 つは目視で確認する。`record_type` フィールドが期待値 (例: "HR") になっていれば最低限のディスパッチは合っている。
