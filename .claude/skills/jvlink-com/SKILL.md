---
name: jvlink-com
description: JV-Link COM コンポーネント (JRA-VAN Data Lab.) の操作スキル。「JVLink で○○取得して」「dataspec 追加」「リアルタイム取得 (JVRTOpen)」「速報データ」「セットアップ取得」「進捗バー」「JVOpen のエラー」「rc=-202 / -402 / -502 が出た」のような JVLink まわりの実装・デバッグで必ず使う。32bit Python 制約・BSTR ラウンドトリップ・各メソッドのリターンコード・option 値・dataspec の組み合わせ表を全部押さえてあるので、知らずに書くと無限ループや認証エラーで詰まる。
---

# JV-Link COM 操作スキル

## 何のためのスキル？

`jvlink_client/client.py` を拡張するときに必要な COM プロトコル知識を集めたもの。具体的には:
- 32bit Python 必須の理由と回避策
- pywin32 経由で COM を呼ぶときの BSTR ラウンドトリップ問題
- `JVInit / JVOpen / JVRTOpen / JVRead / JVStatus / JVClose / JVSkip / JVCancel / JVFiledelete` の使い分け
- リターンコード一覧と回復方法
- `option` パラメータと `dataspec` の組み合わせ表
- 差分起点 `fromtime` の正しい扱い (前回タイムスタンプ -1 秒)
- 速報系データ (`0B12` 等) と蓄積系データ (`RACE` 等) の違い

## 環境前提

- **32bit Python 必須**。JV-Link は 32bit COM コンポーネント (ProgID: `JVDTLab.JVLink.1`)。64bit Python から `Dispatch` すると `pywintypes.com_error: (-2147221164, ...)` で死ぬ
- 推奨セットアップ: `py -3.x-32 -m venv .venv32` で 32bit 仮想環境を作る
- `pywin32` をインストール (`pip install pywin32` だが必ず 32bit 環境で)
- JV-Link 本体 (Windows ネイティブインストーラ) を別途インストール
- 利用キー (サービスキー) は **JV-Link 本体の設定ダイアログ** で登録する。`JVInit(sid)` の `sid` は **ソフトウェア識別子** であって利用キーではない (混同しやすい)

## メソッド早見表

| メソッド | 用途 | 戻り値 |
|---|---|---|
| `JVInit(sid)` | アプリ初期化。最初に 1 回だけ呼ぶ | 0=正常 / -101〜-103=sid 不正 |
| `JVOpen(dataspec, fromtime, option, ...)` | 蓄積系データの取得開始 | 0+=正常 (4 要素タプル) |
| `JVRTOpen(dataspec, key)` | リアルタイム系データの取得開始 | 0=正常 |
| `JVStatus()` | ダウンロード進捗確認 | 0+=済ファイル数 |
| `JVRead(buf, size, filename)` | データ読み出し | 0+=バイト数 / -1 ファイル切替 / -3 DL 中 / 0 EOF |
| `JVGets(...)` | JVRead と同じだが文字列ベース | (今回は使わない。JVRead で十分) |
| `JVSkip()` | 次ファイルまで読み飛ばし | 0=正常 |
| `JVCancel()` | DL スレッド停止 | 0=正常 |
| `JVClose()` | セッション終了 | 0=正常 |
| `JVFiledelete(filename)` | DL 済異常ファイル削除 | 0=正常 |
| `JVSetUIProperties()` | 利用キー登録ダイアログ表示 | 0=正常 |
| `JVSetServiceKey(key)` | 利用キーをコードから設定 | 0=正常 |
| `JVWatchEvent / JVWatchEventClose` | イベント通知 (出馬表確定・払戻確定 等) | 0+=正常 |

## 標準的な取得フロー

`JVOpen → (JVStatus でDL待ち) → JVRead ループ → JVClose` の 4 ステップ。既存の `JVLinkClient.fetch()` ([jvlink_client/client.py](jvlink_client/client.py)) を参照。重要ポイント:

```python
# 1. 前回 Open のクリーンアップ (必須)
try:
    self._jv.JVClose()  # rc=-202 (前回 Open 残り) 対策
except Exception:
    pass

# 2. JVOpen は 4 要素タプルを返す
rc, readcount, downloadcount, last_timestamp = self._jv.JVOpen(...)

# 3. ダウンロード完了待ち
if downloadcount > 0:
    while True:
        status = self._jv.JVStatus()
        if status >= downloadcount:
            break
        time.sleep(1.0)

# 4. JVRead ループ
while True:
    rc, buf_str, size, filename = self._jv.JVRead("", BUFFER_SIZE, "")
    if rc == 0: break             # EOF
    if rc == -1: continue         # ファイル切替 (新ファイルへ)
    if rc == -3: time.sleep(0.5); continue   # DL 中
    if rc == -402 or rc == -403:  # 異常ファイル
        self._jv.JVFiledelete(filename)
        break
    if rc < 0: raise JVLinkError(...)
    # rc > 0 は SJIS バイト数。buf_str を encode("cp932") で生バイト復元

# 5. 必ず Close
self._jv.JVClose()

# 6. 次回差分起点として last_timestamp を保存
update_timestamp(dataspec, last_timestamp)
```

## **重要**: 読み出しは JVRead でなく JVGets を使う

仕様書 p28 に明記:
> 従来の JVRead は、内部で渡されたメモリを解放し、SJIS で開いたファイルを **UNICODE 変換**して新たに確保したメモリエリアに渡す処理をしている
> JVGets では、メモリ受け渡しをバイト配列型のポインタで行い、その際 **SJIS は SJIS のまま渡す** ことにより、JV-Link 内部での変換および UNICODE → SJIS 変換が不要になる

つまり `JVRead` は **必ず BSTR ラウンドトリップを経由** し、cp932 にマッピングできない文字 (機種依存文字、全角空白の一部、外字) が `?` 等に置換されて **レコード本体長が変動** する。固定長レコード (RA 1272 / SE 555 / HR 719) で位置ベースのフィールド読み出しが破綻するので **絶対に使わない**。

### JVGets の正しい呼び方 (pywin32)

```python
import pythoncom
from win32com.client import VARIANT

buff_var = VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_UI1 | pythoncom.VT_BYREF, [])
fname_var = VARIANT(pythoncom.VT_BSTR | pythoncom.VT_BYREF, "")
rc = jv.JVGets(buff_var, BUFFER_SIZE, fname_var)
data: bytes = bytes(buff_var.value or b"")  # SafeArray(BYTE) → bytes
filename = fname_var.value or ""
```

`buff_var.value` の型は pywin32 のバージョンで変わる (bytes / tuple of int / list)。`bytes()` でラップしておけば全部受け切れる。

### 兆候の見分け方

「JVRead を使っていてデータ破損しているか」は raw ファイルを CRLF 分割して長さ分布を見れば一発で分かる:

```python
data = Path("data/raw/RACE/SEVM*.jvd").read_bytes()
parts = [r for r in data.split(b"\r\n") if r]
print(set(len(r) for r in parts))
# 健全: {553} のみ (SE 仕様 555 から CRLF 2 byte 引いた値)
# 破損: {559, 562, 565, 567, ...} のように散らばる ← BSTR ラウンドトリップ済み
```

破損 raw を再パースしても救えない (どこで何 byte ズレたかは復元不能)。**raw ごと再取得する** しかない。

## option パラメータ早見表

| option | 用途 | 説明 |
|:---:|---|---|
| 1 | 通常データ (累積差分) | サーバ全データから dataspec & fromtime 該当を取得 |
| 2 | 今週データ | 先週レース結果 + 次週関連の約 1 週間ぶん |
| 3 | セットアップデータ (CD/DVD-ROM 確認ダイアログ付き) | 初回バルク。重い。スタートキット提供は 2022 年 3 月終了 |
| 4 | セットアップデータ (ダイアログなし) | 初回のみダイアログ表示、以後はサーバから自動 DL |

### option × dataspec の組み合わせ (重要)

option ごとに使える dataspec が決まっている。**間違うと `rc=-116` (組み合わせが不正)** が返る。

| option | 指定可能 dataspec |
|:---:|---|
| 1 | `TOKU` `RACE` `DIFF` `BLOD` `SNAP` `SLOP` `WOOD` `YSCH` `HOSE` `HOYU` `DIFN` `BLDN` `SNPN` `HOSN` |
| 2 | `TOKU` `RACE` `TCOV` `RCOV` `SNAP` `TCVN` `RCVN` `SNPN` |
| 3,4 | `TOKU` `RACE` `DIFF` `BLOD` `SNAP` `SLOP` `WOOD` `YSCH` `HOSE` `HOYU` `COMM` `MING` `DIFN` `BLDN` `SNPN` `HOSN` |

[references/dataspecs.md](references/dataspecs.md) に各 dataspec で得られるレコード種別を一覧化。

## fromtime の罠

JV-Link の **option=1/2 で fromtime が前回 last_timestamp と完全一致だと `rc=-1` (該当データ無し)** を返す仕様 (実装バグに近い挙動)。回避するには 1 秒戻したものを渡す:

```python
def _shift_back_1s(ts: str) -> str:
    dt = datetime.strptime(ts, "%Y%m%d%H%M%S")
    return (dt - timedelta(seconds=1)).strftime("%Y%m%d%H%M%S")
```

既存 [jvlink_client/state.py](jvlink_client/state.py) で実装済み。境界の最後の 1 ファイルが重複取得されるが DB は UPSERT なので副作用なし。

fromtime のフォーマットは **`yyyymmddHHMMSS` の 14 桁固定**。`yyyymmdd` のみ渡すと `rc=-112` で死ぬ。

初回起動時の fromtime は `19860101000000` (Data Lab. サービス開始日付近) を使う。

## リアルタイム取得 (JVRTOpen)

速報系データ (`0B12` 出馬表, `0B14` 速報開催情報, `0B15` 速報票数, `0B30` 払戻 等) は `JVRTOpen` で取る。`JVOpen` と違って差分管理は不要 (常に最新):

```python
rc = self._jv.JVRTOpen(dataspec, key)  # key 例: "202405040112" = レース指定
# 以降 JVRead は同じ
```

`key` の形式は dataspec によって異なる。レース単位なら `年月日場回日R = yyyymmdd場2桁回2桁日2桁R2桁` の 14 桁。

## イベント駆動 (JVWatchEvent)

「出馬表確定したら自動取得」「払戻確定したら自動取得」のような自動化は `JVWatchEvent` を使う。pywin32 でイベントを受けるには `win32com.client.WithEvents` を使う:

```python
class JVLinkEvents:
    def OnJVEvtPay(self, bstr):
        """払戻確定イベント"""
        # bstr にレース識別キーが入る → JVRTOpen で取得
        ...

jv = win32com.client.Dispatch("JVDTLab.JVLink.1")
events = win32com.client.WithEvents(jv, JVLinkEvents)
jv.JVWatchEvent()
# pywebview や Qt のイベントループに乗せる必要あり
```

実装は [references/events.md](references/events.md) を参照 (現状未実装のため拡張時に新規追加)。

## リターンコード一覧

主要なものだけ抜粋。詳細は [references/return-codes.md](references/return-codes.md)。

### 0 番台 (正常系)
- `0` 正常 / EOF (JVRead では全ファイル読込完了)
- `0+` 正常 (JVStatus は DL 済ファイル数, JVRead はバイト数)

### -1, -3 (JVRead 制御フロー)
- `-1` ファイル切替 (エラーではない。次ファイルへ)
- `-3` ファイル DL 中 (少し待って再試行)

### -1xx (パラメータ系)
- `-101` sid 未設定
- `-102` sid 64 バイト超過
- `-111` dataspec 不正
- `-112` fromtime 不正 (開始時刻)
- `-114` key 不正 (JVRTOpen)
- `-115` option 不正
- `-116` dataspec と option の組み合わせが不正

### -2xx (順序系)
- `-201` JVInit 未呼び出し → JVInit を先に呼ぶ
- `-202` JVClose 呼び忘れ (前回 Open 残り) → 必ず冒頭で `JVClose()` を呼ぶ
- `-203` JVOpen 未呼び出し
- `-211` レジストリ内容が不正

### -3xx (認証系)
- `-301` 認証エラー (利用キー不正 or 複数マシンで同一キー使用)
- `-302` 利用キー有効期限切れ
- `-303` 利用キー未設定 (JV-Link インストール直後)
- `-305` 利用規約未同意

### -4xx (データ系)
- `-402` DL ファイル異常 (サイズ 0) → `JVFiledelete` で削除して再 Open
- `-403` DL ファイル異常 (内容) → 同上
- `-411 / -412 / -413` サーバ HTTP エラー
- `-421` サーバ応答不正

### -5xx (障害系)
- `-501` スタートキット無効 (現在は提供終了)
- `-502` ダウンロード失敗 (通信/ディスクエラー)
- `-503` ファイル消失
- `-504` サーバメンテナンス中

## デバッグ tips

### `rc=-202` が出る
前回の Open 残り。`fetch()` の冒頭で `try: self._jv.JVClose() except: pass` を必ず入れる。既存実装にあり。

### `rc=-301` が出る
利用キーが正しく設定されていない。**`sid` の問題ではない**。`JVSetUIProperties` を呼んで JV-Link 本体のダイアログで利用キーを再登録するか、複数マシンで同一キーを使い回している場合は片方をアンインストールして再発行依頼。

### 取得が無限に止まる (JVStatus がいつまでも < downloadcount)
- ファイアウォール / プロキシで JV-Link の HTTP 通信が遮断されている可能性
- `JVCancel()` で DL スレッドを止めて `JVClose()` してやり直す

### 32bit / 64bit エラー
`pywintypes.com_error: (-2147221164, 'クラスが登録されていません', None, None)` が出たら 64bit Python から呼んでいる。`.venv32\Scripts\python.exe` で実行されているか確認。

### `JVRead` で文字化け
`buf_str.encode("cp932")` を使っているか確認。`buf_str.encode("utf-8")` などにすると壊れる。

## 進捗通知の付け方

長時間処理 (セットアップ時の数 GB DL) で GUI に進捗を出すには `on_progress(stage, info)` コールバックを使う既存パターンを踏襲。GUI 側 (`gui/app.py`) にコールバックを実装して dict をリアルタイム送信する。

```python
def on_progress(stage: str, info: dict) -> None:
    # 例: webview.windows[0].evaluate_js(f"updateProgress({json.dumps(info)})")
    ...

with JVLinkClient() as cli:
    cli.fetch_all(option=1, dataspecs=[...], on_progress=on_progress)
```

stage は `"open"` `"download"` `"read"` `"warn"` `"error"` の 5 種類。

## ENCODING の罠まとめ

| 場面 | 正解 | NG |
|---|---|---|
| BSTR → bytes | `s.encode("cp932")` | `s.encode("utf-8")` / `bytes(s, "latin-1")` |
| ファイル書き込み | `open(path, "wb")` バイナリ | テキストモード |
| 仕様書のバイト位置 | 1-indexed | 0-indexed |
| レコード種別判定 | レコード本体先頭 2 バイト | ファイル名先頭 2 文字 |
| fromtime | `yyyymmddHHMMSS` 14 桁 | `yyyymmdd` 8 桁 |

## まずどう拡張するか

新しいデータを取り込みたいときの判断:

1. **既存 dataspec で済むか?** `dataspecs=["RACE"]` に新しく追加するだけで済むことも多い
2. **新 dataspec が要るか?** 例: `MING` (マイニング) は option=3,4 でしか取れない (セットアップ系)
3. **速報か蓄積か?** 馬体重 (`WH`)・天候 (`WE`) は速報系 → `JVRTOpen` 必要
4. **イベント駆動が要るか?** 「払戻確定したら自動」のような場合は `JVWatchEvent`

各 dataspec で何が取れるかは [references/dataspecs.md](references/dataspecs.md) を参照。
