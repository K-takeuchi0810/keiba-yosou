"""予想の自動生成 + Discord 通知 (F4, 2026-07-03 ユーザ要件・案A)。

条件判定 → web.generator 生成 → docs/predictions/latest.md を commit+push →
Discord webhook に「commit URL + 閲覧は iCloud」を通知。

生成条件 (自己判断): **今日** に出馬表 (races) が存在し、かつその日の
**出走馬が実際に取り込まれている** こと。無ければ生成せず終了 (非開催日は
静かに skip)。Task Scheduler から毎朝実行される前提。
生成は 1 日分ずつ (2026-09-13 日別化)。翌日分は翌朝の起動で出す。

使い方: .venv64/Scripts/python.exe -m scripts.auto_predict [--dry-run] [--force-notify]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import (  # noqa: E402
    DB_PATH,
    ICLOUD_PUBLISH_DIR,
    PROJECT_ROOT,
    artifact_drift,
)
from db import SQL_VALID_HORSE_NUM  # noqa: E402
from scripts.notify_dedup import JST, decide, jst_today, record  # noqa: E402
from scripts.notify_discord import notify_discord  # noqa: E402
import os  # noqa: E402
import sqlite3  # noqa: E402

MARKER = PROJECT_ROOT / "docs" / "predictions_latest.md"
# GitHub Pages 公開先 (docs/index.html を main /docs から配信)。スマホでレンダリング表示。
PAGES_HTML = PROJECT_ROOT / "docs" / "index.html"
GENERATED_HTML = PROJECT_ROOT / "web" / "dist" / "index.html"
PAGES_URL = "https://k-takeuchi0810.github.io/keiba-yosou/"
PY = str(PROJECT_ROOT / ".venv64" / "Scripts" / "python.exe")


def _stage_publish_artifacts(
    target_date: str, sync_status_path: Path | None = None
) -> list[Path]:
    archive_dir = (
        PROJECT_ROOT / "data" / "results" /
        f"{target_date[:4]}-{target_date[4:6]}-{target_date[6:]}"
    )
    paths = [PAGES_HTML, PAGES_HTML.parent / ".nojekyll", MARKER]
    status_path = sync_status_path or ICLOUD_PUBLISH_DIR / "_sync_status.json"
    archive = None
    try:
        status = json.loads(status_path.read_text(encoding="utf-8"))
        raw_archive = status.get("repository_archive")
        if raw_archive:
            candidate = Path(raw_archive)
            if candidate.is_file():
                archive = candidate
    except (OSError, TypeError, ValueError):
        pass
    if archive is not None:
        paths.append(archive)
    else:
        paths.extend(sorted(archive_dir.glob("predictions_source_*.html")))
    subprocess.run(
        ["git", "add", *(str(path) for path in paths)],
        cwd=PROJECT_ROOT,
        check=True,
    )
    return paths


def _race_days(conn, days: list[str]) -> list[tuple[str, int]]:
    out = []
    for d in days:
        n = conn.execute(
            "SELECT COUNT(*) FROM races WHERE race_year=? AND race_month_day=?",
            (d[:4], d[4:]),
        ).fetchone()[0]
        if n > 0:
            out.append((d, n))
    return out


def _entry_coverage(conn, day: str) -> tuple[int, int]:
    """その日の (出走馬が入っているレース数, レース総数) を返す。

    `races` 行はレース定義 (schedule) が来た時点で作られるため、出走馬 (SE) が
    未取り込みでも 36 レース分そろって見える。この差を見ずに生成すると
    「全 36 レース 出走馬未取得」の空ページを publish してしまう
    (2026-07-25 / 08-01 に実際に発生。v6 期 12 開催日のうち 2 日が空振り)。
    """
    total = conn.execute(
        "SELECT COUNT(*) FROM races WHERE race_year=? AND race_month_day=?",
        (day[:4], day[4:]),
    ).fetchone()[0]
    with_entries = conn.execute(
        f"""
        SELECT COUNT(*) FROM (
            SELECT 1 FROM horse_races
             WHERE race_year=? AND race_month_day=? AND {SQL_VALID_HORSE_NUM}
             GROUP BY track_code, kaiji, nichiji, race_num
        )
        """,
        (day[:4], day[4:]),
    ).fetchone()[0]
    return with_entries, total


def _notify(text: str) -> bool:
    """Compatibility wrapper around the shared best-effort notifier."""
    return notify_discord(text)


def _notify_once(notification_type: str, subject: str, payload: dict,
                 text: str, force: bool = False,
                 supersedes: bool = True) -> bool:
    """同じ内容なら送らない。変わったときは「変更点 + 全文」を送る。

    Task Scheduler が同じ日に 3 回起動するので、3 回とも同じ結果なら同じ本文が
    3 通届いていた (2026-09-19 是正)。判定は **通知層だけ**で行い、予測・
    特徴量・DB 取込・PIT・評価処理には触れない。

    判定に失敗したら送る側に倒す。中止通知を握り潰すのが最悪の事故なので、
    重複を 1 通許す方がまし。
    """
    def audit(decision: str, attempted: bool, delivered, recorded) -> None:
        """1 行で「起動 → 判定 → 送信 → 記録」を追えるようにする。

        **Discord を静かにしても監査ログまで静かにしてはいけない。**
        「通知が来なかった」だけでは、抑止が効いたのか処理自体が走らなかったのか
        区別できない。grep しやすい固定書式で毎回 1 行出す。
        """
        def tri(v):
            return "-" if v is None else ("ok" if v else "failed")
        print(f"notify-audit type={notification_type} subject={subject} "
              f"decision={decision} attempted={'yes' if attempted else 'no'} "
              f"delivered={tri(delivered)} recorded={tri(recorded)}")

    if force:
        ok = _notify(text)
        audit("forced", True, ok, None)
        return ok
    d = decide(notification_type, subject, payload, text)
    if not d.should_send:
        print(f"notify suppressed ({notification_type}:{subject}): {d.reason}")
        audit(d.reason, False, None, None)
        return True
    if d.degraded:
        print(f"WARN: 重複判定に失敗したので送信します ({d.reason})")
    ok = _notify(d.text)
    recorded = None
    if ok:
        # **送れてから記録する。** 送信前に記録すると、POST が失敗したのに
        # 「送った」ことになり、次の起動で抑止されて永久に届かなくなる。
        recorded = record(notification_type, subject, payload,
                          supersedes=supersedes)
    else:
        print(f"WARN: 送信に失敗したので記録しません (次回再送します): "
              f"{notification_type}:{subject}")
    audit(d.reason, True, ok, recorded)
    return ok


# 最終起動の時刻。`scripts/register_auto_predict_task.ps1` の `ThirdStartTime` と
# **必ず一致させる** (テストで固定してある)。Task Scheduler はトリガごとに別の
# 引数を渡せないので、最終起動かどうかはこちら側で JST 時刻から判断する。
FINAL_ATTEMPT_HOUR = 11


def _is_final_attempt() -> bool:
    """この起動がその日の最終予定起動か (JST で判断)。"""
    return datetime.now(JST).hour >= FINAL_ATTEMPT_HOUR


def _final_confirmation_message(reason: str) -> str:
    """最終確認の heartbeat。**中止通知の再送ではない、別の意味の通知**。

    重複抑止を入れたことで「依然中止」と「タスクが起動しなかった」が Discord 上で
    区別できなくなった (以前は同文 3 通が暗黙の生存信号だった)。最終起動が実際に
    走ったことをこの 1 通で示す。

      通常起動が成功し状態も変わらない → 無通知
      最終起動まで中止が続いた         → この 1 通
      最終起動自体が動かなかった       → この 1 通が来ない

    3 つ目を読み取れることが目的なので、**中止が続いたときだけ**送る。
    """
    d = jst_today()
    return "\n".join([
        f"🕚 **本日の最終確認** ({d[:4]}/{d[4:6]}/{d[6:]})",
        f"中止状態が継続しています ({reason})。最終確認処理は正常に実行されました。",
        "⚠ 観察専用 (実弾根拠となるエッジは未証明)",
    ])


def _completion_payload(n_races: int, version: str, push_ok: bool) -> dict:
    """生成完了通知の「中身」。重複判定はこれだけを見る。

    **生成時刻・URL・本文は入れないこと。** 入れた瞬間に毎回違う payload に
    なり、抑止が 1 通も効かなくなる (本文で判定していたのと同じ状態に戻る)。
    キー集合はテストで固定してある。
    """
    return {"n_races": n_races, "version": version, "push_ok": push_ok}


def _completion_message(target_date: str, n_races: int, version: str,
                        push_ok: bool) -> str:
    """生成完了の Discord 通知文を組み立てる。

    日別化 (2026-09-13) で対象日が常に 1 日になったので、旧来の
    「09/12〜09/13」という範囲表記はやめ、**日付 + 曜日** を出す。
    ユーザは Discord の通知だけを見て「どっちの日の予想が出たのか」を
    判断するため、曜日が無いと土日どちらの分か分からない。

    「観察専用」の一文は必須。これが落ちると通知だけを見た人が実弾の根拠と
    誤読しうる (資金喪失経路)。テストで固定してある。
    """
    wd = "月火水木金土日"[datetime.strptime(target_date, "%Y%m%d").weekday()]
    web_line = (f"🌐 Web版: {PAGES_URL} (数分で更新)" if push_ok
                else "🌐 Web版: main push 失敗のため未更新 (手動確認要)")
    return (
        f"🏇 **予想生成完了** "
        f"{target_date[:4]}/{target_date[4:6]}/{target_date[6:]}({wd}) "
        f"({n_races}R, {version})\n"
        f"📱 今すぐ見る(確実): iPhone ファイルApp → iCloud Drive → 競馬予想 → index.html\n"
        f"{web_line}\n"
        f"⚠ 観察専用 (実弾根拠となるエッジは未証明)"
    )


def _final_confirmation(args, day: str, reason: str) -> None:
    """最終起動で中止が続いていたら、最終確認を 1 通だけ送る。"""
    if not (args.final_attempt or _is_final_attempt()):
        return
    # supersedes=False: これは結末の通知ではないので、中止通知の記録を消さない。
    # 消すと、そのあと同じ中止通知をもう 1 通送ってしまう。
    _notify_once("final_confirmation", day, {"reason": reason},
                 _final_confirmation_message(reason),
                 force=args.force_notify, supersedes=False)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="生成せず対象日のみ表示")
    ap.add_argument(
        "--final-attempt", action="store_true",
        help="その日の最終予定起動として扱い、中止が続いていれば最終確認を 1 通送る。"
             "既定は JST 時刻から自動判定 (11 時以降)",
    )
    ap.add_argument(
        "--force-notify", action="store_true",
        help="重複判定を通さず必ず通知する。docstring には以前から書いてあったが "
             "**実装されていなかった** (2026-09-19 に重複判定を入れる際に発見)",
    )
    ap.add_argument(
        "--min-entry-coverage",
        type=float,
        default=float(os.environ.get("AUTO_PREDICT_MIN_ENTRY_COVERAGE", "0.8")),
        help="直近開催日で出走馬が入っているレースの最低割合。これを下回ったら "
             "publish せず exit 2 (既定 0.8)",
    )
    args = ap.parse_args()
    min_coverage = args.min_entry_coverage

    today = date.today()
    # 生成対象は **今日のみ** (2026-09-13 ユーザ指示で日別化)。
    # 以前は今日+明日を 1 ページに出していたが、JRA の出馬表は前日確定なので
    # 土曜朝の時点で日曜分は大半が「出走馬未取得」の空レースになり、スマホで
    # 当日分が埋もれていた。実測でも前日に予想を付けられていたのは日曜 36R 中
    # 2R だけ (日曜の出馬表確定は土曜 11:28 で最終起動に間に合わない) なので、
    # 前日先出しをやめて失うものはほぼ無い。
    # 翌日分は翌朝の各トリガ (register_auto_predict_task.ps1) で生成する。
    cand = [today.strftime("%Y%m%d")]
    conn = sqlite3.connect(DB_PATH)
    targets = _race_days(conn, cand)
    conn.close()
    if not targets:
        print(f"skip: {cand} に出馬表なし (開催日でない)")
        return 0
    # 対象は常に 1 日 (cand が今日だけなので targets も高々 1 件)。
    day, n_races = targets[0]
    print(f"generate: {day} ({n_races} races)")

    # 出走馬取り込みゲート (2026-08-22 追加)。
    # その日の出走馬がそろっていなければ publish しない。空ページを
    # 出すよりも「出さずに通知して次の起動で再試行」のほうが実害が小さい
    # (2026-07-25 / 08-01 は全 36 レース「出走馬未取得」の 46KB ページを公開して
    # しまい、その日の予想が丸ごと失われた)。閾値は env で調整可。
    conn = sqlite3.connect(DB_PATH)
    try:
        with_entries, total = _entry_coverage(conn, day)
    finally:
        conn.close()
    coverage = (with_entries / total) if total else 0.0
    print(f"entry coverage {day}: {with_entries}/{total} ({coverage:.0%})")
    if coverage < min_coverage:
        msg = (
            f"⚠ 予想生成を中止: {day} の出走馬が未取り込み "
            f"({with_entries}/{total} = {coverage:.0%} < {min_coverage:.0%})。"
            "次の起動で再試行します (空ページは publish しません)。"
        )
        print(msg)
        if not args.dry_run:
            _notify_once("coverage_abort", day,
                         {"with_entries": with_entries, "total": total,
                          "min_coverage": min_coverage},
                         msg, force=args.force_notify)
            _final_confirmation(args, day,
                                f"{with_entries}/{total} 出走馬未取り込み")
        return 2
    # F3 封印中はモデルを変えない (2026-09-14)。12 月の判定は「封印窓のあいだ
    # 同じモデルが予想し続けた」ことを前提にしており、途中で重み・calibrator・
    # LGBM が変わると封印窓に 2 種類の予想が混ざって判定が成立しなくなる。
    # 「見ない」ことと同じくらい「変えない」ことが前提なので、生成の前に検査する。
    drift = artifact_drift()
    if drift:
        msg = ("【中止】F3 封印中なのにモデルが変わっています\n"
               + "\n".join(f"  - {d}" for d in drift)
               + "\n意図的な差し替えなら config.SEALED_ARTIFACTS を更新し、"
                 "封印窓を捨てて再開始するか判定を先に行うこと。")
        print(msg)
        if not args.dry_run:
            # drift は順序が揺れうるので、並べ替えてから payload にする
            # (本質的でない並び順の差で再通知しないため)。
            _notify_once("artifact_drift_abort", day,
                         {"drift": sorted(drift)}, msg,
                         force=args.force_notify)
            _final_confirmation(args, day, "封印モデルの変更を検知")
        return 3

    if args.dry_run:
        return 0

    r = subprocess.run([PY, "-m", "web.generator", "--from", day, "--to", day,
                        "--log-predictions"],
                       capture_output=True, text=True, cwd=PROJECT_ROOT)
    if r.returncode != 0:
        _notify_once("generation_failed", day, {"returncode": r.returncode},
                     f"⚠ 予想生成に失敗 ({day})。ログ確認要。",
                     force=args.force_notify)
        print(r.stdout[-500:], r.stderr[-500:])
        return 1

    # 版情報
    meta = json.loads((PROJECT_ROOT / "predictor" / "lgbm_meta.json").read_text(encoding="utf-8"))
    ver = meta.get("rule_version", "?")

    # GitHub Pages へ公開: 生成 HTML を docs/index.html にコピーして commit+push。
    # commit URL はレンダリングされないので通知には Pages URL を載せる (案A 改)。
    PAGES_HTML.parent.mkdir(parents=True, exist_ok=True)
    PAGES_HTML.write_bytes(GENERATED_HTML.read_bytes())
    (PAGES_HTML.parent / ".nojekyll").touch()
    MARKER.write_text(
        f"# 最新予想生成\n\n- 対象: {day} ({n_races} レース)\n"
        f"- 生成時刻: {datetime.now().isoformat(timespec='seconds')}\n"
        f"- モデル: {ver}\n- 閲覧: {PAGES_URL} (GitHub Pages) / iCloud Drive index.html\n",
        encoding="utf-8")
    _stage_publish_artifacts(day)
    c = subprocess.run(["git", "commit", "-m",
                        f"predictions: {day} published to Pages ({ver})"],
                       cwd=PROJECT_ROOT, capture_output=True, text=True)
    # Pages は main (デフォルトブランチ) からデプロイされるので main へ push する。
    # 非 fast-forward なら git が安全に reject → 通知して手動判断 (force はしない)。
    push_ok = True
    if c.returncode == 0:
        # ブランチガード: 共有 checkout が feature ブランチに居るとき、スケジュール実行が
        # HEAD:main へ push すると未レビュー commit が main へ流入する。main 上でのみ push。
        branch = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=PROJECT_ROOT,
            capture_output=True, text=True).stdout.strip()
        if branch != "main":
            push_ok = False
            print(f"WARN: HEAD が main でない ({branch}) ため main への push を中止しました。")
        else:
            subprocess.run(["git", "fetch", "origin", "main", "-q"], cwd=PROJECT_ROOT,
                           capture_output=True, text=True)
            p = subprocess.run(["git", "push", "origin", "HEAD:main"], cwd=PROJECT_ROOT,
                               capture_output=True, text=True)
            push_ok = p.returncode == 0
            if not push_ok:
                print("WARN: push to main failed:\n", p.stderr[-400:])

    # payload に生成時刻・URL は入れない。中身が同じなら送らない。
    sent = _notify_once("generation_complete", day,
                        _completion_payload(n_races, ver, push_ok),
                        _completion_message(day, n_races, ver, push_ok),
                        force=args.force_notify)
    # 抑止・送信失敗のときに "notified." と出すと、直前の suppressed / WARN 行と
    # 矛盾してログが読めなくなる。結果をそのまま出す。
    print(f"notify: {'ok' if sent else 'failed'}. push_ok={push_ok}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
