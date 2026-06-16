"""JV-Link ラッパ。

JV-Link は 32bit COM コンポーネント（ProgID: JVDTLab.JVLink.1）。
本モジュールは 32bit Python + pywin32 環境で動作する前提。

設計メモ:
- JVInit(sid): sid はソフトウェアID（識別子）。実利用キーは JV-Link 本体の
  設定ダイアログで登録済みであることが前提。
- 読み出しには **JVGets** を使う。JVRead を使うと内部で SJIS → UTF-16 変換が走り、
  cp932 にラウンドトリップ不能な文字 (主に全角空白 / 機種依存文字) が `?` 等に
  置換され、結果として SE 等の固定長レコードのバイト位置がズレる。仕様書 p28
  にも「SJIS は SJIS のまま渡す」のが JVGets と明記されている。
- 取得した生バイトはまず `data/raw/{dataspec}/{filename}` にそのまま保存し、
  解析（フォーマット仕様書に従ったレコード分解）は後段モジュールに委ねる。
"""

from __future__ import annotations

import logging
import sys
import time
import os
from pathlib import Path

# pywin32 (pythoncom / win32com) は 32-bit COM 専用なので 64-bit venv では
# import 不可。64-bit 側から ALL_DATASPECS 等の定数を参照するケースで壊れない
# ようにここでは try/except でラップする。JVLinkClient を実際に使う箇所
# (32-bit でしか動かない) で AttributeError が出れば理由が明確になる。
try:
    import pythoncom  # type: ignore[import-not-found]
    import win32com.client  # type: ignore[import-not-found]
    from win32com.client import VARIANT  # type: ignore[import-not-found]
    _COM_AVAILABLE = True
except ModuleNotFoundError:
    pythoncom = None  # type: ignore[assignment]
    win32com = None  # type: ignore[assignment]
    VARIANT = None  # type: ignore[assignment]
    _COM_AVAILABLE = False

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import DATA_DIR, JVLINK_SID
from jvlink_client.state import get_fromtime, update_timestamp

# 観測性: 旧コードでは JVClose / JVFiledelete などの「失敗しても運用継続したい」
# 操作を `except Exception: pass` で握り潰していたため、サイレント失敗が
# GUI 上に何の痕跡も残さずバグの根本原因が追えない問題があった。
# 全部 logger.warning(..., exc_info=True) に統一して、トラブル時に
# どこで例外が起きたかを stderr / 任意の logging handler で追えるようにする。
logger = logging.getLogger(__name__)

# 中長期予想向けフルセット
ALL_DATASPECS: list[str] = [
    "RACE",  # 競走情報（競走・出走馬・払戻 等）
    "DIFN",  # 当日差分（速報）
    "BLOD",  # 血統
    "SLOP",  # 坂路調教
    "WOOD",  # ウッドチップ調教
    "MING",  # マイニング予想
    "RCOV",  # レース別成績
    "TOKU",  # 特別登録馬
    "HOSE",  # 競走馬基本
    "HOYU",  # 馬主
    "COMM",  # コメント
    "YSCH",  # 開催スケジュール
]

RAW_DIR = DATA_DIR / "raw"
BUFFER_SIZE = 110_000  # 1 レコード最大長より十分大きく

TRANSIENT_OPEN_RCS = {-411, -412, -413, -421, -431, -502, -504}
RC_MESSAGES = {
    -411: "サーバーエラー(HTTP 404)",
    -412: "サーバーエラー(HTTP 403)",
    -413: "サーバー/通信エラー(HTTP 200/403/404以外)。セキュリティソフトの通信許可も確認してください",
    -421: "サーバー応答不正",
    -431: "サーバーアプリケーション内部エラー",
    -502: "ダウンロード失敗",
    -504: "サーバーメンテナンス中",
}


def _retry_attempts() -> int:
    try:
        return max(1, int(os.environ.get("JVLINK_OPEN_RETRIES", "4")))
    except ValueError:
        return 4


def _retry_delay(attempt: int) -> int:
    delays = [5, 15, 45]
    return delays[min(attempt - 1, len(delays) - 1)]


def _rc_message(rc: int) -> str:
    return RC_MESSAGES.get(rc, "JV-Linkエラー")


def _coerce_bytes(buff) -> bytes:
    """JVGets が返す buff を bytes に正規化する。

    pywin32 のバージョンによって SAFEARRAY(BYTE) の受け取り方が変わる:
    - 新しめのバージョン: bytes としてそのまま
    - 古めのバージョン: tuple/list of int
    - 最古のバージョン: cp932 デコード済みの str (本来期待しない経路)
    どのケースでも raw bytes に揃える。
    """
    if buff is None:
        return b""
    if isinstance(buff, bytes):
        return buff
    if isinstance(buff, (tuple, list)):
        return bytes(buff)
    if isinstance(buff, str):
        # 万が一 BSTR 経由で来た場合のフォールバック (情報損失あり)
        return buff.encode("cp932", errors="replace")
    return bytes(buff)


class JVLinkError(RuntimeError):
    pass


class JVLinkClient:
    PROG_ID = "JVDTLab.JVLink.1"

    def __init__(self, sid: str = JVLINK_SID) -> None:
        if not _COM_AVAILABLE:
            raise RuntimeError(
                "JVLinkClient requires 32-bit Python + pywin32 (COM). "
                "Run from .venv32, not .venv64. JV-Link COM DLL is 32-bit fixed."
            )
        self.sid = sid
        self._jv = win32com.client.Dispatch(self.PROG_ID)
        self._initialized = False

    def __enter__(self) -> "JVLinkClient":
        rc = self._jv.JVInit(self.sid)
        if rc != 0:
            raise JVLinkError(f"JVInit failed: rc={rc} (sid={self.sid!r})")
        self._initialized = True
        return self

    def __exit__(self, *_exc) -> None:
        if self._initialized:
            try:
                self._jv.JVClose()
            except Exception:
                logger.warning("JVClose at __exit__ failed", exc_info=True)
            self._initialized = False

    def fetch(
        self,
        dataspec: str,
        fromtime: str,
        option: int = 1,
        on_progress=None,
        retry_attempts: int | None = None,
    ) -> dict:
        """指定 dataspec のデータを取得し、ファイル単位で raw に保存する。

        option:
            1 = 通常データ（累積差分）
            2 = 今週データ
            3 = セットアップデータ（初回バルク。重い）
            4 = ダイアログなしセットアップデータ
        on_progress: callable(stage: str, info: dict) ログ通知用フック
        戻り値: 取得サマリ dict
        """
        # 前回の Open 状態が残っていると -202 になるので必ず Close してから Open
        try:
            self._jv.JVClose()
        except Exception:
            logger.warning("JVClose before fetch(%s) failed", dataspec, exc_info=True)

        attempts = retry_attempts or _retry_attempts()
        last_result = None
        for attempt in range(1, attempts + 1):
            result = self._jv.JVOpen(dataspec, fromtime, option, 0, 0, "")
            rc = result[0]
            last_result = result
            if rc >= 0 or rc not in TRANSIENT_OPEN_RCS or attempt == attempts:
                break
            delay = _retry_delay(attempt)
            if on_progress:
                on_progress(
                    "retry",
                    {
                        "dataspec": dataspec,
                        "option": option,
                        "fromtime": fromtime,
                        "rc": rc,
                        "message": _rc_message(rc),
                        "attempt": attempt,
                        "max_attempts": attempts,
                        "wait_sec": delay,
                    },
                )
            try:
                self._jv.JVClose()
            except Exception:
                logger.warning("JVClose during retry of %s failed", dataspec, exc_info=True)
            time.sleep(delay)

        result = last_result
        rc = result[0]
        readcount = result[1]
        downloadcount = result[2]
        last_timestamp = result[3]
        if rc < 0:
            raise JVLinkError(
                f"JVOpen failed: dataspec={dataspec} option={option} "
                f"fromtime={fromtime} rc={rc} ({_rc_message(rc)})"
            )
        if on_progress:
            on_progress(
                "open",
                {
                    "dataspec": dataspec,
                    "readcount": readcount,
                    "downloadcount": downloadcount,
                    "last_timestamp": last_timestamp,
                },
            )

        # ダウンロード完了を待つ
        if downloadcount > 0:
            while True:
                status = self._jv.JVStatus()
                if status < 0:
                    raise JVLinkError(f"JVStatus failed: rc={status}")
                if on_progress:
                    on_progress(
                        "download",
                        {"dataspec": dataspec, "remaining": downloadcount - status},
                    )
                if status >= downloadcount:
                    break
                time.sleep(1.0)

        # 読み出しループ（ストリーム書き込み + 進捗報告）
        out_dir = RAW_DIR / dataspec
        out_dir.mkdir(parents=True, exist_ok=True)
        records_total = 0
        files_done = 0
        current_filename: str | None = None
        current_handle = None
        last_progress = time.time()
        bad_files: list[str] = []  # rc=-403 で破損していたファイル
        # この fetch で書き出したファイル名。呼び出し側が ingest_all(only_files=...)
        # に渡すことで「同名ファイルの内容更新 (週次 RACE)」を確実に再取込する
        # (2026-06-13 v2 監査: only_files 機構が誰にも配線されていなかった)。
        filenames: list[str] = []

        try:
            while True:
                # JVGets: SJIS バイト列を SafeArray(BYTE) で受け取る (BSTR 経由しない)。
                # pywin32 の動的ディスパッチに [in,out] バイト配列パラメータを推論させる
                # ため、空 bytes / 空 str を渡すと戻り値タプルに展開して返す。
                # 戻り値タプル構造 (JVRead と同じ): (rc, buff, size, filename)
                result = self._jv.JVGets(b"", BUFFER_SIZE, "")
                rc = result[0]
                buf = _coerce_bytes(result[1])
                filename = result[3] if len(result) > 3 else (result[2] or "")

                if rc == 0:
                    break  # 全件読み込み完了
                if rc == -1:
                    # ファイル切替: 現在のファイルを閉じる
                    if current_handle is not None:
                        current_handle.close()
                        current_handle = None
                        current_filename = None
                        files_done += 1
                    continue
                if rc == -3:
                    time.sleep(0.5)  # ダウンロード未完
                    continue
                if rc == -402 or rc == -403:
                    # ダウンロードしたファイルが異常 → JVFiledelete で削除して継続
                    bad_files.append(filename)
                    if on_progress:
                        on_progress(
                            "warn",
                            {"dataspec": dataspec, "rc": rc,
                             "skipped_file": filename},
                        )
                    if current_handle is not None:
                        current_handle.close()
                        current_handle = None
                        current_filename = None
                    try:
                        self._jv.JVFiledelete(filename)
                    except Exception:
                        logger.warning(
                            "JVFiledelete(%r) failed for bad file in %s",
                            filename, dataspec, exc_info=True,
                        )
                    # この dataspec は途中で打ち切り（一部欠損許容）。
                    break
                if rc < 0:
                    raise JVLinkError(f"JVGets failed: rc={rc}")

                # ファイル変更（filename 変化）でハンドル切替
                if filename != current_filename:
                    if current_handle is not None:
                        current_handle.close()
                        files_done += 1
                    current_filename = filename
                    current_handle = open(out_dir / filename, "wb")
                    filenames.append(filename)

                # rc は SJIS バイト数。buf にそのバイト列が入っているのでそのまま書き込む。
                current_handle.write(buf)
                records_total += 1

                now = time.time()
                if on_progress and (now - last_progress) >= 5.0:
                    on_progress(
                        "read",
                        {
                            "dataspec": dataspec,
                            "files_done": files_done,
                            "records": records_total,
                            "file": current_filename,
                        },
                    )
                    last_progress = now
        finally:
            if current_handle is not None:
                current_handle.close()
                files_done += 1
            # この fetch のセッションを必ず閉じる（次の JVOpen 用）
            try:
                self._jv.JVClose()
            except Exception:
                logger.warning(
                    "JVClose at fetch(%s) finally failed", dataspec, exc_info=True,
                )

        # 次回の差分起点として保存
        update_timestamp(dataspec, last_timestamp)

        return {
            "dataspec": dataspec,
            "files_written": files_done,
            "records_total": records_total,
            "last_timestamp": last_timestamp,
            "bad_files": bad_files,
            "filenames": filenames,
        }

    def fetch_all(
        self,
        fromtime: str | None = None,
        option: int = 1,
        dataspecs: list[str] | None = None,
        on_progress=None,
        retry_attempts: int | None = None,
    ) -> list[dict]:
        """複数 dataspec を順次取得。

        fromtime が None の場合は dataspec ごとに保存された前回タイムスタンプを使う。
        まだ取得したことがない dataspec はデフォルト（古い日付）から開始される。
        """
        targets = dataspecs or ALL_DATASPECS
        summaries: list[dict] = []
        for ds in targets:
            actual_from = fromtime if fromtime else get_fromtime(ds)
            try:
                summary = self.fetch(
                    ds,
                    actual_from,
                    option=option,
                    on_progress=on_progress,
                    retry_attempts=retry_attempts,
                )
                summaries.append(summary)
            except JVLinkError as e:
                summaries.append({"dataspec": ds, "error": str(e)})
                if on_progress:
                    on_progress("error", {"dataspec": ds, "message": str(e)})
        return summaries

    def fetch_realtime(
        self,
        dataspec: str,
        key: str,
        on_progress=None,
        retry_attempts: int | None = None,
    ) -> dict:
        """Fetch realtime JV-Data with JVRTOpen and save raw records."""
        try:
            self._jv.JVClose()
        except Exception:
            logger.warning(
                "JVClose before fetch_realtime(%s, %s) failed",
                dataspec, key, exc_info=True,
            )

        attempts = retry_attempts or _retry_attempts()
        rc = 0
        for attempt in range(1, attempts + 1):
            rc = self._jv.JVRTOpen(dataspec, key)
            if rc >= 0 or rc not in TRANSIENT_OPEN_RCS or attempt == attempts:
                break
            delay = _retry_delay(attempt)
            if on_progress:
                on_progress(
                    "rt_retry",
                    {
                        "dataspec": dataspec,
                        "key": key,
                        "rc": rc,
                        "message": _rc_message(rc),
                        "attempt": attempt,
                        "max_attempts": attempts,
                        "wait_sec": delay,
                    },
                )
            try:
                self._jv.JVClose()
            except Exception:
                logger.warning(
                    "JVClose during rt_retry of %s/%s failed",
                    dataspec, key, exc_info=True,
                )
            time.sleep(delay)
        if rc == -1:
            # JVRTOpen の -1 は「該当データなし」(JVRead の -1=ファイル切替とは別意味)。
            # 未開催・配信前・キーが該当データを持たない、等の正常応答なので、
            # ここで例外にすると外側ループ (fetch_odds など) が止まり、
            # 残りのレースが取得できなくなる。空 result を返してスキップ。
            try:
                self._jv.JVClose()
            except Exception:
                logger.warning(
                    "JVClose after rt_no_data(%s, %s) failed",
                    dataspec, key, exc_info=True,
                )
            if on_progress:
                on_progress(
                    "rt_no_data",
                    {
                        "dataspec": dataspec,
                        "key": key,
                        "message": "該当データなし (未開催/配信前)",
                    },
                )
            return {
                "dataspec": dataspec,
                "key": key,
                "no_data": True,
                "files_written": 0,
                "records_total": 0,
                "filenames": [],
            }
        if rc < 0:
            raise JVLinkError(
                f"JVRTOpen failed: dataspec={dataspec} key={key} "
                f"rc={rc} ({_rc_message(rc)})"
            )
        if on_progress:
            on_progress("rt_open", {"dataspec": dataspec, "key": key})

        out_dir = RAW_DIR / dataspec
        out_dir.mkdir(parents=True, exist_ok=True)
        records_total = 0
        files_done = 0
        current_filename = f"{dataspec}_{key}_{int(time.time())}.jvd"
        current_handle = open(out_dir / current_filename, "wb")
        filenames: list[str] = []

        def close_current_file() -> None:
            nonlocal current_handle, files_done
            if current_handle is None:
                return
            path = Path(current_handle.name)
            current_handle.close()
            current_handle = None
            try:
                if path.stat().st_size == 0:
                    path.unlink()
                else:
                    files_done += 1
                    filenames.append(path.name)
            except OSError:
                logger.warning("failed to finalize realtime raw file: %s", path, exc_info=True)

        # rc=-3 (未配信) は時間が経てば届くことが多いが、未開催レース等で
        # 永久に届かないケースがある。このタイムアウトに到達したら諦めて抜ける。
        # JVLINK_REALTIME_NO_DATA_SEC=0 で無効化可。
        try:
            no_data_timeout = max(0, int(os.environ.get("JVLINK_REALTIME_NO_DATA_SEC", "30")))
        except ValueError:
            no_data_timeout = 30
        no_data_started: float | None = None
        last_heartbeat = time.time()
        timed_out = False

        try:
            while True:
                result = self._jv.JVGets(b"", BUFFER_SIZE, "")
                rc = result[0]
                buf = _coerce_bytes(result[1])
                filename = result[3] if len(result) > 3 and result[3] else current_filename

                if rc == 0:
                    break
                if rc == -1:
                    close_current_file()
                    current_filename = f"{filename or dataspec}_{key}_{int(time.time())}.jvd"
                    current_handle = open(out_dir / current_filename, "wb")
                    no_data_started = None
                    continue
                if rc == -3:
                    now = time.time()
                    if no_data_started is None:
                        no_data_started = now
                    waited = now - no_data_started
                    # 進捗コールバック: GUI 側の _check_cancel が動くので
                    # 中止ボタンが効くようになる。
                    if on_progress and (now - last_heartbeat) >= 2.0:
                        on_progress(
                            "rt_wait",
                            {
                                "dataspec": dataspec,
                                "key": key,
                                "waited_sec": int(waited),
                                "records": records_total,
                                "message": f"realtime data not ready ({int(waited)}s)",
                            },
                        )
                        last_heartbeat = now
                    if no_data_timeout and waited >= no_data_timeout:
                        timed_out = True
                        if on_progress:
                            on_progress(
                                "rt_timeout",
                                {
                                    "dataspec": dataspec,
                                    "key": key,
                                    "waited_sec": int(waited),
                                    "message": "no realtime data; skip this race",
                                },
                            )
                        break
                    time.sleep(0.5)
                    continue
                if rc < 0:
                    raise JVLinkError(f"JVGets realtime failed: rc={rc}")

                # 実データを受信できたので未配信タイマーをリセット
                no_data_started = None

                if filename != current_filename:
                    close_current_file()
                    current_filename = filename
                    current_handle = open(out_dir / current_filename, "wb")
                current_handle.write(buf)
                records_total += 1

                now = time.time()
                if on_progress and (now - last_heartbeat) >= 5.0:
                    on_progress(
                        "rt_read",
                        {
                            "dataspec": dataspec,
                            "key": key,
                            "records": records_total,
                            "files_done": files_done,
                        },
                    )
                    last_heartbeat = now
        finally:
            close_current_file()
            try:
                self._jv.JVClose()
            except Exception:
                logger.warning(
                    "JVClose at fetch_realtime(%s, %s) finally failed",
                    dataspec, key, exc_info=True,
                )

        return {
            "dataspec": dataspec,
            "key": key,
            "timed_out": timed_out,
            "files_written": files_done,
            "records_total": records_total,
            "filenames": filenames,
        }
