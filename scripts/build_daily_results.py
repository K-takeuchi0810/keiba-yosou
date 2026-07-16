"""2026-06-21 等の特定日について、予測 (朝の HTML から parse) + 結果 (DB) を
join した検証用 CSV 5 種を `data/results/<date>/` に出力する。

目的: 後から「モデルが市場より高く評価した馬は、実際に市場より良かったか」を
評価できる形でデータを **固定** する。ここで作る CSV は読み取り専用の証跡として
扱い、後から書き換えない (改ざん防止のため SHA256 を summary に併記)。

入力:
  --date YYYYMMDD                 (必須)
  --html PATH                     朝の予測 HTML (デフォルト:
                                  data/results/<date>/predictions_source_*.html)
  --db PATH                       SQLite DB (デフォルト: data/keiba.db)
  --output-dir PATH               出力先 (デフォルト: data/results/<date>/)

出力:
  data/results/<date>/predictions.csv         朝の予測 (HTML 由来)
  data/results/<date>/final_odds.csv          最終オッズ (DB 由来)
  data/results/<date>/race_results.csv        着順 (DB confirmed_order)
  data/results/<date>/payouts.csv             払戻 (DB payouts)
  data/results/<date>/evaluation_summary.csv  統合表 (主分析対象)

注意:
- HTML の `<table class="entries">` には全馬の mark / num / name / 朝オッズ /
  人気 は出るが、win_probability / EV / confidence は top picks セクションのみ。
- そのため全馬には model_rank を「印からマッピング (◎=1 / ○=2 / ▲=3 / △=4 / ☆=5、
  印なし=None)」で導出する。top picks 馬は win_probability / EV / confidence
  も併記する。
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sqlite3
import subprocess
import sys
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path

from db import SQL_VALID_HORSE_NUM

ROOT = Path(__file__).resolve().parent.parent

MARK_TO_RANK = {"◎": 1, "○": 2, "▲": 3, "△": 4, "☆": 5}


class IndexHtmlParser(HTMLParser):
    """朝の予測 HTML を parse して race / horse / top_pick を取り出す state machine。

    抽出する情報:
      - races: [{race_id, race_num, track_code, race_name, start_time, race_anchor,
                 horses: [...], top_picks: [...]}]
      - horse row 列: mark, num, name, odds, popularity, rationale
      - top pick 列: mark, num, win_probability, expected_value, confidence, bet_candidate
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.races: list[dict] = []
        self._current_race: dict | None = None

        # state machine flags
        self._in_race_details = False
        self._in_entries_tbody = False
        self._in_entries_thead = False
        self._in_top_picks = False
        self._in_race_head = False
        self._in_race_name = False
        self._in_race_time = False
        self._in_horse_row = False
        self._current_horse: dict | None = None
        self._current_td_class: str | None = None
        self._current_td_title: str | None = None
        self._td_buf: list[str] = []
        self._current_td_span_class: str | None = None
        self._td_span_buf: list[str] = []
        self._in_pick_line = False
        self._current_pick: dict | None = None
        self._current_pick_span_class: str | None = None
        self._pick_span_buf: list[str] = []

    # ---- helpers ----
    def _attr(self, attrs: list[tuple[str, str | None]], key: str) -> str | None:
        for k, v in attrs:
            if k == key:
                return v
        return None

    def _attr_classes(self, attrs: list[tuple[str, str | None]]) -> list[str]:
        cls = self._attr(attrs, "class") or ""
        return [c for c in cls.split() if c]

    # ---- handle_starttag ----
    def handle_starttag(self, tag: str, attrs):
        cls = self._attr_classes(attrs)
        if tag == "details" and "race" in cls:
            self._in_race_details = True
            anchor = self._attr(attrs, "id") or ""
            self._current_race = {
                "race_anchor": anchor,
                "race_num": None,
                "track_code": None,
                "race_name": None,
                "start_time": None,
                "horses": [],
                "top_picks": [],
                "has_bet": "buy-race" in cls,
            }
            # anchor 例: "race-2026-06-21-05-12" -> track=05, race_num=12
            m = re.search(r"-(\d{2})-(\d{1,2})$", anchor)
            if m:
                self._current_race["track_code"] = m.group(1)
                self._current_race["race_num"] = int(m.group(2))
            return
        if not self._in_race_details:
            return
        if tag == "summary" and "race-head" in cls:
            self._in_race_head = True
        elif tag == "span" and self._in_race_head and "race-name" in cls:
            self._in_race_name = True
        elif tag == "div" and self._in_race_head and "race-time" in cls:
            self._in_race_time = True
        elif tag == "div" and self._in_race_details and "pick-line" in cls:
            self._in_pick_line = True
            self._current_pick = {
                "mark": None, "num": None, "name": None,
                "win_probability": None, "expected_value": None,
                "confidence": None, "bet_candidate": False,
                "odds": None, "popularity": None,
            }
        elif tag == "span" and self._in_pick_line:
            self._current_pick_span_class = " ".join(cls)
            self._pick_span_buf = []
        elif (
            tag == "span"
            and self._in_horse_row
            and self._current_td_class is not None
            and "pick-reason" in cls
        ):
            self._current_td_span_class = " ".join(cls)
            self._td_span_buf = []
        elif tag == "table" and "entries" in cls:
            self._in_entries_tbody = False  # will flip in tbody
        elif tag == "thead":
            self._in_entries_thead = True
        elif tag == "tbody":
            self._in_entries_thead = False
            self._in_entries_tbody = True
        elif tag == "tr" and self._in_entries_tbody:
            self._in_horse_row = True
            self._current_horse = {
                "mark": "", "num": None, "waku": None, "name": None,
                "odds": None, "popularity": None, "rationale": None,
            }
        elif tag == "td" and self._in_horse_row:
            self._current_td_class = " ".join(cls)
            self._current_td_title = self._attr(attrs, "title")
            self._td_buf = []
            if "mark-cell" in cls and self._current_td_title:
                self._current_horse["rationale"] = self._current_td_title
            if "horse-num" in cls:
                for c in cls:
                    if c.startswith("waku-"):
                        self._current_horse["waku"] = c.split("-", 1)[1]

    # ---- handle_endtag ----
    def handle_endtag(self, tag: str):
        if tag == "details" and self._in_race_details:
            if self._current_race:
                self.races.append(self._current_race)
            self._current_race = None
            self._in_race_details = False
            return
        if not self._in_race_details:
            return
        if tag == "summary" and self._in_race_head:
            self._in_race_head = False
        elif tag == "span" and self._in_race_name:
            self._in_race_name = False
        elif tag == "div" and self._in_race_time:
            self._in_race_time = False
        elif tag == "td" and self._in_horse_row:
            buf = "".join(self._td_buf).strip()
            cls = self._current_td_class or ""
            if "mark-cell" in cls:
                self._current_horse["mark"] = buf
            elif "horse-num" in cls:
                self._current_horse["num"] = buf
            elif "horse-name" in cls:
                self._current_horse["name"] = buf
            elif "col-sex" in cls:
                pass  # sex/age 結合表示は別カラム化しない
            elif "col-burden" in cls:
                pass
            elif "col-trainer" in cls:
                pass
            else:
                # オッズは td 直下テキストのみ。人気は pick-reason span で別途読む。
                m_odds = re.match(r"^\s*([\d.]+)", buf)
                if m_odds:
                    try:
                        self._current_horse["odds"] = float(m_odds.group(1))
                    except ValueError:
                        pass
            self._current_td_class = None
            self._current_td_title = None
            self._td_buf = []
        elif tag == "tr" and self._in_horse_row:
            if self._current_horse and self._current_horse.get("num"):
                self._current_race["horses"].append(self._current_horse)
            self._current_horse = None
            self._in_horse_row = False
        elif tag == "tbody":
            self._in_entries_tbody = False
        elif tag == "thead":
            self._in_entries_thead = False
        elif tag == "span" and self._current_td_span_class is not None:
            buf = "".join(self._td_span_buf).strip()
            if "pick-reason" in self._current_td_span_class:
                m_pop = re.search(r"(\d+)人気", buf)
                if m_pop:
                    self._current_horse["popularity"] = int(m_pop.group(1))
            self._current_td_span_class = None
            self._td_span_buf = []
        elif tag == "span" and self._in_pick_line:
            buf = "".join(self._pick_span_buf).strip()
            sc = self._current_pick_span_class or ""
            if "mark" == sc.strip():
                self._current_pick["mark"] = buf
            elif "pick-num" in sc:
                self._current_pick["num"] = buf
            elif "odds-note" in sc:
                m_o = re.match(r"^([\d.]+)倍", buf)
                if m_o:
                    try:
                        self._current_pick["odds"] = float(m_o.group(1))
                    except ValueError:
                        pass
                m_p = re.search(r"(\d+)人気", buf)
                if m_p:
                    self._current_pick["popularity"] = int(m_p.group(1))
            elif "conf-tag" in sc:
                m_wp = re.match(r"^P\s+([\d.]+)%", buf)
                m_ev = re.match(r"^EV\s+([\d.]+)", buf)
                if m_wp:
                    try:
                        self._current_pick["win_probability"] = float(m_wp.group(1)) / 100.0
                    except ValueError:
                        pass
                elif m_ev:
                    try:
                        self._current_pick["expected_value"] = float(m_ev.group(1))
                    except ValueError:
                        pass
                else:
                    # confidence 値 (高信頼/標準/接戦/混戦/暫定)
                    if buf in ("高信頼", "標準", "接戦", "混戦", "暫定"):
                        self._current_pick["confidence"] = buf
            elif "bet-tag" in sc:
                self._current_pick["bet_candidate"] = True
            self._current_pick_span_class = None
            self._pick_span_buf = []
        elif tag == "div" and self._in_pick_line:
            self._in_pick_line = False
            if self._current_pick and self._current_pick.get("num"):
                # mark が後で来ない構造なので、span mark の値で埋まる
                # (span mark がない場合は printable text を直前で吸収できていないことがある)
                self._current_race["top_picks"].append(self._current_pick)
            self._current_pick = None

    # ---- handle_data ----
    def handle_data(self, data: str):
        if self._in_race_name:
            self._current_race["race_name"] = (self._current_race.get("race_name") or "") + data.strip()
        elif self._in_race_time and self._current_race:
            txt = data.strip()
            if txt and not self._current_race.get("start_time"):
                self._current_race["start_time"] = txt
        elif self._in_horse_row and self._current_td_span_class is not None:
            self._td_span_buf.append(data)
        elif self._in_horse_row and self._current_td_class is not None:
            self._td_buf.append(data)
        elif self._in_pick_line and self._current_pick_span_class is not None:
            self._pick_span_buf.append(data)
        elif self._in_pick_line and self._current_pick_span_class is None:
            # pick-line 直下のテキスト (馬名等) — span 外
            if self._current_pick and not self._current_pick.get("name"):
                t = data.strip()
                if t and not t.startswith("/"):
                    self._current_pick["name"] = t


def parse_predictions_html(html_path: Path) -> tuple[list[dict], dict]:
    """HTML を parse して races の list を返す + meta (calibrator/lgbm/git)。"""
    text = html_path.read_text(encoding="utf-8")
    parser = IndexHtmlParser()
    parser.feed(text)
    # version snapshot を抽出 (footer の calibrator: ... / lgbm: ... / git: ...)
    meta = {}
    m = re.search(r"calibrator:\s*([^/]+?)\s*/\s*lgbm:\s*([^/]+?)\s*/\s*git:\s*(\S+)", text)
    if m:
        meta["calibrator"] = m.group(1).strip()
        meta["lgbm"] = m.group(2).strip()
        meta["git_sha"] = m.group(3).strip()
    return parser.races, meta


def sha256_of(p: Path) -> str:
    H = hashlib.sha256()
    with open(p, "rb") as f:
        while True:
            c = f.read(1024 * 1024)
            if not c:
                break
            H.update(c)
    return H.hexdigest()


def write_csv(path: Path, columns: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=columns)
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c) for c in columns})


def git_provenance() -> tuple[str, bool]:
    sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, check=True,
        capture_output=True, text=True,
    ).stdout.strip()
    status = subprocess.run(
        ["git", "status", "--porcelain", "--", ".", ":!data/results"],
        cwd=ROOT, check=True, capture_output=True, text=True,
    ).stdout.strip()
    return sha, bool(status)


def normalize_horse_num(value: object) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    return text.lstrip("0") or None


def race_num_of(race_num: int | str | None) -> str:
    return f"{int(race_num) if race_num is not None else 0:02d}"


def classify_post_start_rows(
    horse_rows: list[dict], race_rows: list[dict], date: str
) -> tuple[int, int]:
    """Return (post-start, unclassified) odds timestamp row counts.

    Null odds timestamps are counted by a separate warning. A non-null timestamp
    is unclassified when its race start or timestamp cannot be parsed.
    """
    starts: dict[tuple[str, str, str, str], str] = {}
    for race in race_rows:
        raw = "".join(ch for ch in str(race.get("start_time") or "") if ch.isdigit())
        if len(raw) == 3:
            raw = f"0{raw}"
        if len(raw) == 4:
            starts[(
                str(race.get("track_code") or ""), str(race.get("kaiji") or ""),
                str(race.get("nichiji") or ""), str(race.get("race_num") or ""),
            )] = raw

    post_start = 0
    unclassified = 0
    for horse in horse_rows:
        raw_stamp = horse.get("odds_fetched_at")
        start_hhmm = starts.get((
            str(horse.get("track_code") or ""), str(horse.get("kaiji") or ""),
            str(horse.get("nichiji") or ""), str(horse.get("race_num") or ""),
        ))
        if not raw_stamp:
            continue
        if not start_hhmm:
            unclassified += 1
            continue
        try:
            stamped_at = datetime.fromisoformat(str(raw_stamp).replace("Z", "+00:00"))
            race_start = datetime.strptime(
                f"{date}{start_hhmm}", "%Y%m%d%H%M"
            ).replace(tzinfo=stamped_at.tzinfo)
        except (TypeError, ValueError):
            unclassified += 1
            continue
        if stamped_at > race_start:
            post_start += 1
    return post_start, unclassified


def count_post_start_stamped_rows(
    horse_rows: list[dict], race_rows: list[dict], date: str
) -> int:
    return classify_post_start_rows(horse_rows, race_rows, date)[0]


def validate_output_quality(
    predictions: list[dict], *horse_row_groups: list[dict],
    starter_count_by_race: dict[str, int] | None = None,
) -> list[str]:
    errors: list[str] = []
    starter_count_by_race = starter_count_by_race or {}
    bad_popularity = [
        r for r in predictions
        if r.get("morning_popularity") not in (None, "")
        and not 1 <= int(r["morning_popularity"]) <= (
            int(starter_count_by_race.get(r.get("race_id")) or 18)
        )
    ]
    if bad_popularity:
        errors.append(
            "morning_popularity outside 1..starter_count "
            f"(fallback 18): {len(bad_popularity)} rows"
        )

    invalid_horse_rows = 0
    for rows in (predictions, *horse_row_groups):
        for row in rows:
            num = str(row.get("horse_num") or "").strip()
            if not num or not num.lstrip("0"):
                invalid_horse_rows += 1
    if invalid_horse_rows:
        errors.append(
            f"invalid horse_num ('00'/empty/None): {invalid_horse_rows} rows"
        )
    return errors


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--date", required=True, help="YYYYMMDD")
    ap.add_argument("--html", default=None,
                    help="朝の予測 HTML (デフォルト: data/results/<date>/predictions_source_*.html)")
    ap.add_argument("--db", default=str(ROOT / "data" / "keiba.db"))
    ap.add_argument("--output-dir", default=None,
                    help="出力先 (デフォルト: data/results/<date>/)")
    args = ap.parse_args()

    date = args.date
    if len(date) != 8 or not date.isdigit():
        print(f"--date は YYYYMMDD 形式: got {date!r}", file=sys.stderr)
        return 2

    output_dir = Path(args.output_dir) if args.output_dir else (ROOT / "data" / "results" / f"{date[:4]}-{date[4:6]}-{date[6:8]}")
    output_dir.mkdir(parents=True, exist_ok=True)
    old_manifest_path = output_dir / "manifest.json"
    supersedes_manifest_sha256 = (
        sha256_of(old_manifest_path) if old_manifest_path.exists() else None
    )
    # trackedな出力CSVを自分で更新した結果をdirty扱いしないよう、書出し前に固定する。
    builder_git_sha, builder_git_dirty = git_provenance()

    if args.html:
        html_path = Path(args.html)
    else:
        candidates = sorted(output_dir.glob("predictions_source_*.html"))
        if not candidates:
            print(f"HTML が見つからない: {output_dir}/predictions_source_*.html", file=sys.stderr)
            return 2
        html_path = candidates[-1]

    print(f"date={date} html={html_path}")
    html_sha = sha256_of(html_path)
    print(f"html sha256: {html_sha}")

    # 1. HTML parse
    races, meta = parse_predictions_html(html_path)
    print(f"parsed: races={len(races)}, horses_total={sum(len(r['horses']) for r in races)}, top_picks_total={sum(len(r['top_picks']) for r in races)}")

    # 2. DB から最終 odds / 着順 / payouts を取る
    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    excluded_placeholder_rows = conn.execute(
        "SELECT COUNT(*) FROM horse_races "
        "WHERE race_year=? AND race_month_day=? AND horse_num='00'",
        (date[:4], date[4:8]),
    ).fetchone()[0]
    cur = conn.execute(f"""
        SELECT race_year, race_month_day, track_code, kaiji, nichiji, race_num,
               horse_num, horse_name, win_odds, win_popularity, confirmed_order,
               odds_fetched_at
         FROM horse_races
         WHERE race_year = ? AND race_month_day = ?
           AND {SQL_VALID_HORSE_NUM}
         ORDER BY track_code, race_num, horse_num
    """, (date[:4], date[4:8]))
    horse_rows = [dict(r) for r in cur.fetchall()]
    cur = conn.execute("""
        SELECT race_year, race_month_day, track_code, kaiji, nichiji, race_num,
               tan_horse_num1, tan_payout1,
               fuku_horse_num1, fuku_payout1, fuku_horse_num2, fuku_payout2,
               fuku_horse_num3, fuku_payout3, fuku_horse_num4, fuku_payout4,
               fuku_horse_num5, fuku_payout5
          FROM payouts
         WHERE race_year = ? AND race_month_day = ?
         ORDER BY track_code, race_num
    """, (date[:4], date[4:8]))
    payout_rows = [dict(r) for r in cur.fetchall()]
    cur = conn.execute("""
        SELECT race_year, race_month_day, track_code, kaiji, nichiji, race_num,
               race_name, distance, track_type_code, grade_code, starter_count,
               turf_condition, dirt_condition, weather_code, start_time
          FROM races
         WHERE race_year = ? AND race_month_day = ?
         ORDER BY track_code, race_num
    """, (date[:4], date[4:8]))
    race_rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    print(f"db: races={len(race_rows)}, horse_races={len(horse_rows)}, payouts={len(payout_rows)}")

    # 3. race_id を組む helper
    def race_id_of(track_code: str, race_num: int | str) -> str:
        return f"{date}-{track_code}-{race_num_of(race_num)}"

    # ---- predictions.csv (HTML 由来) ----
    predictions: list[dict] = []
    for r in races:
        tc = r.get("track_code") or ""
        rn = r.get("race_num") or 0
        rid = race_id_of(tc, rn)
        # top picks: num -> (win_prob, ev, confidence, bet_candidate)
        tp_by_num = {p["num"].lstrip("0"): p for p in r["top_picks"] if p.get("num")}
        for h in r["horses"]:
            num = (h.get("num") or "").lstrip("0") or "0"
            mark = h.get("mark") or ""
            model_rank = MARK_TO_RANK.get(mark)
            tp = tp_by_num.get(num)
            predictions.append({
                "race_id": rid,
                "track_code": tc,
                "race_num": race_num_of(rn),
                "horse_num": num,
                "horse_name": h.get("name"),
                "mark": mark,
                "model_rank_by_mark": model_rank,
                "morning_odds": h.get("odds"),
                "morning_popularity": h.get("popularity"),
                "rationale": h.get("rationale"),
                "win_probability": tp["win_probability"] if tp else None,
                "expected_value": tp["expected_value"] if tp else None,
                "confidence": tp["confidence"] if tp else None,
                "bet_candidate": (tp["bet_candidate"] if tp else False),
            })

    # ---- final_odds.csv (DB 由来、確定 win_odds = 最終オッズ) ----
    final_odds: list[dict] = []
    for h in horse_rows:
        rid = race_id_of(h["track_code"], h["race_num"])
        # win_odds は整数で 10 倍 (例: 35 = 3.5 倍)
        wo = h.get("win_odds")
        odds_dec = (wo / 10.0) if wo else None
        final_odds.append({
            "race_id": rid,
            "track_code": h["track_code"],
            "race_num": race_num_of(h["race_num"]),
            "horse_num": normalize_horse_num(h.get("horse_num")),
            "horse_name": h.get("horse_name"),
            "final_odds": odds_dec,
            "final_popularity": h.get("win_popularity"),
            "odds_fetched_at": h.get("odds_fetched_at"),
        })

    # ---- race_results.csv (DB 由来、confirmed_order) ----
    race_results: list[dict] = []
    for h in horse_rows:
        rid = race_id_of(h["track_code"], h["race_num"])
        race_results.append({
            "race_id": rid,
            "track_code": h["track_code"],
            "race_num": race_num_of(h["race_num"]),
            "horse_num": normalize_horse_num(h.get("horse_num")),
            "horse_name": h.get("horse_name"),
            "confirmed_order": h.get("confirmed_order") or 0,
        })

    # ---- payouts.csv (DB 由来、単勝 + 複勝) ----
    payouts: list[dict] = []
    for p in payout_rows:
        rid = race_id_of(p["track_code"], p["race_num"])
        payouts.append({
            "race_id": rid,
            "track_code": p["track_code"],
            "race_num": race_num_of(p["race_num"]),
            "tan_horse_num1": normalize_horse_num(p.get("tan_horse_num1")),
            "tan_payout1": p.get("tan_payout1"),
            "fuku_horse_num1": normalize_horse_num(p.get("fuku_horse_num1")),
            "fuku_payout1": p.get("fuku_payout1"),
            "fuku_horse_num2": normalize_horse_num(p.get("fuku_horse_num2")),
            "fuku_payout2": p.get("fuku_payout2"),
            "fuku_horse_num3": normalize_horse_num(p.get("fuku_horse_num3")),
            "fuku_payout3": p.get("fuku_payout3"),
        })

    # ---- evaluation_summary.csv (統合表) ----
    # build helpers
    race_info = {race_id_of(r["track_code"], r["race_num"]): r for r in race_rows}
    final_by = {(o["race_id"], o["horse_num"]): o for o in final_odds}
    result_by = {(r["race_id"], r["horse_num"]): r for r in race_results}
    # payout を horse_num に展開
    win_payout_by: dict[tuple[str, str], int] = {}
    place_payout_by: dict[tuple[str, str], int] = {}
    for p in payout_rows:
        rid = race_id_of(p["track_code"], p["race_num"])
        if p.get("tan_horse_num1"):
            win_payout_by[(rid, str(p["tan_horse_num1"]).lstrip("0") or "0")] = int(p.get("tan_payout1") or 0)
        for i in range(1, 6):
            hn = p.get(f"fuku_horse_num{i}")
            py = p.get(f"fuku_payout{i}")
            if hn and py:
                place_payout_by[(rid, str(hn).lstrip("0") or "0")] = int(py)

    eval_rows: list[dict] = []
    for pred in predictions:
        rid = pred["race_id"]
        hn = pred["horse_num"]
        race = race_info.get(rid, {})
        fo = final_by.get((rid, hn), {})
        rr = result_by.get((rid, hn), {})
        odds = fo.get("final_odds")
        # market_probability = 1 / final_odds (race 内正規化はせず、単馬の implied)
        market_prob = (1.0 / odds) if odds and odds > 0 else None
        confirmed = rr.get("confirmed_order") or 0
        win_pay = win_payout_by.get((rid, hn), 0)
        place_pay = place_payout_by.get((rid, hn), 0)
        # 100 円ベース profit_loss (買い判定 (bet_candidate=True) のとき 100 円賭けた前提で計算)
        if pred.get("bet_candidate"):
            profit = (win_pay - 100) if win_pay > 0 else -100
        else:
            profit = 0
        ev_morning = pred.get("expected_value")
        eval_rows.append({
            "race_id": rid,
            "track_code": pred["track_code"],
            "race_num": pred["race_num"],
            "race_name": race.get("race_name"),
            "distance": race.get("distance"),
            "track_type_code": race.get("track_type_code"),
            "starter_count": race.get("starter_count"),
            "horse_num": hn,
            "horse_name": pred.get("horse_name"),
            "mark": pred.get("mark"),
            "model_rank_by_mark": pred.get("model_rank_by_mark"),
            "morning_odds": pred.get("morning_odds"),
            "morning_popularity": pred.get("morning_popularity"),
            "final_odds": odds,
            "final_popularity": fo.get("final_popularity"),
            "market_probability": round(market_prob, 4) if market_prob else None,
            "win_probability": pred.get("win_probability"),
            "expected_value_morning": ev_morning,
            "confidence": pred.get("confidence"),
            "bet_candidate": pred.get("bet_candidate"),
            "confirmed_order": confirmed,
            "win_payout": win_pay,
            "place_payout": place_pay,
            "profit_loss_yen_100unit": profit,
        })

    quality_errors = validate_output_quality(
        predictions, final_odds, race_results, eval_rows,
        starter_count_by_race={
            race_id: int(race.get("starter_count") or 18)
            for race_id, race in race_info.items()
        },
    )
    if quality_errors:
        for error in quality_errors:
            print(f"QUALITY GATE FAILED: {error}", file=sys.stderr)
        return 1

    # 品質ゲート通過後にだけCSVを固定する。
    write_csv(output_dir / "predictions.csv", [
        "race_id", "track_code", "race_num", "horse_num", "horse_name",
        "mark", "model_rank_by_mark", "morning_odds", "morning_popularity",
        "rationale", "win_probability", "expected_value", "confidence", "bet_candidate",
    ], predictions)
    write_csv(output_dir / "final_odds.csv", [
        "race_id", "track_code", "race_num", "horse_num", "horse_name",
        "final_odds", "final_popularity", "odds_fetched_at",
    ], final_odds)
    write_csv(output_dir / "race_results.csv", [
        "race_id", "track_code", "race_num", "horse_num", "horse_name",
        "confirmed_order",
    ], race_results)
    write_csv(output_dir / "payouts.csv", [
        "race_id", "track_code", "race_num",
        "tan_horse_num1", "tan_payout1",
        "fuku_horse_num1", "fuku_payout1", "fuku_horse_num2", "fuku_payout2",
        "fuku_horse_num3", "fuku_payout3",
    ], payouts)
    write_csv(output_dir / "evaluation_summary.csv", [
        "race_id", "track_code", "race_num", "race_name", "distance", "starter_count",
        "horse_num", "horse_name", "mark", "model_rank_by_mark",
        "morning_odds", "morning_popularity", "final_odds", "final_popularity",
        "market_probability", "win_probability", "expected_value_morning",
        "confidence", "bet_candidate", "confirmed_order", "win_payout", "place_payout",
        "profit_loss_yen_100unit",
    ], eval_rows)

    # ---- integrity manifest (生成 CSV の SHA256 で改ざん防止) ----
    manifest = {
        "date": date,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source_html": str(html_path),
        "source_html_sha256": html_sha,
        "version_meta": meta,
        "builder_git_sha": builder_git_sha,
        "builder_git_dirty": builder_git_dirty,
        "supersedes_manifest_sha256": supersedes_manifest_sha256,
        "warnings": {
            "schema": 2,
            "excluded_placeholder_rows": excluded_placeholder_rows,
            "null_odds_fetched_at_rows": sum(
                not h.get("odds_fetched_at") for h in horse_rows
            ),
            "post_start_stamped_rows": count_post_start_stamped_rows(
                horse_rows, race_rows, date
            ),
            "post_start_unclassified_rows": classify_post_start_rows(
                horse_rows, race_rows, date
            )[1],
            "morning_popularity_populated_rows": sum(
                p.get("morning_popularity") not in (None, "") for p in predictions
            ),
        },
        "counts": {
            "html_races_parsed": len(races),
            "html_horses_parsed": sum(len(r["horses"]) for r in races),
            "html_top_picks_parsed": sum(len(r["top_picks"]) for r in races),
            "predictions": len(predictions),
            "final_odds": len(final_odds),
            "race_results": len(race_results),
            "payouts": len(payouts),
            "evaluation_summary": len(eval_rows),
        },
        "csv_sha256": {
            name: sha256_of(output_dir / name) for name in [
                "predictions.csv", "final_odds.csv", "race_results.csv",
                "payouts.csv", "evaluation_summary.csv",
            ]
        },
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print()
    print("--- summary ---")
    for k, v in manifest["counts"].items():
        print(f"  {k}: {v}")
    print()
    print(f"output: {output_dir}/")
    print(f"manifest: {output_dir}/manifest.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
