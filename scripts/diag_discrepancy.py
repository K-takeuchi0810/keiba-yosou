"""フェーズ3 不一致分析 (仮説出し専用、学習には絶対使わない)。

馬券分析 baken.db (read-only) の bets / bet_legs / pred_cache を keiba.db と
6 列キーで join し、「予想◎ (keiba-yosou rank1) が勝てず、ユーザーの馬券が
的中したレース」を抽出。その的中レースの実勝ち馬が持っていた特徴
(人気・オッズ・脚質・上がり3F・JRA-VAN mining 予測順位・keiba-yosou が
与えた順位/印/確率) を観察し、新特徴量の仮説を立てるための材料を出す。

baken.db は MODE=ro で開く。書き込みは一切しない。
pred_cache の mark は cp932 由来で文字化けするため、◎ 判定は rank==1 を使う。

usage:
    python -m scripts.diag_discrepancy --baken "C:/Users/kizun/dev/馬券分析/data/baken.db"
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db import SQL_VALID_HORSE_NUM, open_db

KEY = ("race_year", "race_month_day", "track_code", "kaiji", "nichiji", "race_num")


def ni(x) -> int:
    try:
        return int(str(x).strip())
    except (ValueError, TypeError):
        return -1


def leg_name(code) -> str:
    return {1: "逃げ", 2: "先行", 3: "差し", 4: "追込", 5: "好位", 6: "自在"}.get(ni(code), f"?{code}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--baken", default="C:/Users/kizun/dev/馬券分析/data/baken.db")
    ap.add_argument("--db", default=None, help="keiba.db path")
    args = ap.parse_args()

    bp = Path(args.baken)
    bcon = sqlite3.connect(f"file:{bp.as_posix()}?mode=ro", uri=True)
    bcon.row_factory = sqlite3.Row

    # bet races: key -> {hit, n_bets, types}
    bet_races: dict[tuple, dict] = {}
    for r in bcon.execute(
        "SELECT race_year,race_month_day,track_code,kaiji,nichiji,race_num,"
        "bet_type,hit,payout_yen,stake_yen FROM bets"
    ):
        k = tuple(r[c] for c in KEY)
        d = bet_races.setdefault(k, {"hit": 0, "n": 0, "types": Counter(),
                                     "stake": 0, "payout": 0})
        d["n"] += 1
        d["hit"] = max(d["hit"], r["hit"])  # レース単位で 1 件でも的中なら hit
        d["types"][r["bet_type"]] += 1
        d["stake"] += r["stake_yen"] or 0
        d["payout"] += r["payout_yen"] or 0

    # pred_cache: key -> list of {horse_num, rank, win_probability, tentative, is_buy_candidate}
    preds: dict[tuple, list[dict]] = defaultdict(list)
    for r in bcon.execute(
        "SELECT race_year,race_month_day,track_code,kaiji,nichiji,race_num,"
        "horse_num,rank,win_probability,tentative,is_buy_candidate FROM pred_cache"
    ):
        k = tuple(r[c] for c in KEY)
        preds[k].append({
            "horse_num": r["horse_num"], "rank": r["rank"],
            "p": r["win_probability"], "tentative": r["tentative"],
            "buy": r["is_buy_candidate"],
        })
    bcon.close()

    # keiba.db からレース結果 + 馬特徴を bet レース分だけ prefetch する。
    # `with` で接続を確定的に閉じる (P24 data-pipeline review: 旧実装の
    # 手動 __enter__/__exit__ は例外時に conn を leak する欠陥だった)。
    horses_by_key: dict[tuple, list[dict]] = {}
    with open_db(args.db) if args.db else open_db() as kcon:
        for k in bet_races:
            rows = kcon.execute(
                "SELECT horse_num,finish_order,confirmed_order,win_popularity,win_odds,"
                "leg_quality_code,final_3f,mining_predicted_order,horse_weight,"
                "weight_change_diff,age,sex_code FROM horse_races "
                "WHERE race_year=? AND race_month_day=? AND track_code=? AND kaiji=? "
                f"AND nichiji=? AND race_num=? AND {SQL_VALID_HORSE_NUM}",
                k,
            ).fetchall()
            horses_by_key[k] = [dict(r) for r in rows]

    def horses(k: tuple) -> list[dict]:
        return horses_by_key.get(k, [])

    # 統計
    n_bet_races = 0
    n_resolved = 0          # pred_cache + 結果が揃ったレース
    n_maru_win = 0          # ◎ が 1 着
    n_maru_place = 0        # ◎ が 3 着内
    winner_rank_by_maru = Counter()   # 実勝ち馬に keiba-yosou が与えた rank の分布
    discrepancy = []        # ◎敗北 & ユーザー的中
    # 不一致レースでの勝ち馬特徴
    disc_winner_pop = Counter()
    disc_winner_leg = Counter()
    disc_winner_yrank = Counter()     # keiba-yosou rank of the winner
    disc_winner_mining = Counter()    # JRA-VAN mining pred order of winner
    disc_winner_odds = []

    for k, bd in bet_races.items():
        n_bet_races += 1
        hs = horses(k)
        plist = preds.get(k, [])
        if not hs or not plist:
            continue
        # actual winner(s): finish_order == 1 (confirmed_order 優先)
        def fo(h):
            return ni(h.get("confirmed_order")) if ni(h.get("confirmed_order")) > 0 else ni(h.get("finish_order"))
        winners = [h for h in hs if fo(h) == 1]
        if not winners:
            continue
        # keiba-yosou ◎ = rank==1
        maru = next((p for p in plist if p["rank"] == 1), None)
        if not maru:
            continue
        n_resolved += 1
        maru_hn = ni(maru["horse_num"])
        maru_h = next((h for h in hs if ni(h["horse_num"]) == maru_hn), None)
        maru_fo = fo(maru_h) if maru_h else -1
        rank_by_hn = {ni(p["horse_num"]): p["rank"] for p in plist}

        if maru_fo == 1:
            n_maru_win += 1
        if 1 <= maru_fo <= 3:
            n_maru_place += 1

        for w in winners:
            yr = rank_by_hn.get(ni(w["horse_num"]), None)
            winner_rank_by_maru[yr if yr is not None else "圏外(予想なし)"] += 1

        # 不一致: ◎ が 1 着でない & ユーザー馬券がこのレースで的中
        if maru_fo != 1 and bd["hit"] == 1:
            w = winners[0]
            yr = rank_by_hn.get(ni(w["horse_num"]), None)
            discrepancy.append({"key": k, "winner": w, "maru_hn": maru_hn,
                                "maru_fo": maru_fo, "winner_yrank": yr,
                                "types": dict(bd["types"])})
            pop = ni(w["win_popularity"])
            disc_winner_pop[("1-3" if 1 <= pop <= 3 else "4-6" if pop <= 6
                             else "7-9" if pop <= 9 else "10+" if pop > 0 else "?")] += 1
            disc_winner_leg[leg_name(w.get("leg_quality_code"))] += 1
            disc_winner_yrank[yr if yr is not None else "圏外"] += 1
            disc_winner_mining[ni(w.get("mining_predicted_order"))] += 1
            od = w.get("win_odds")
            if od:
                disc_winner_odds.append(od / 10.0)

    # ---- 出力 ----
    print("# フェーズ3 不一致分析 (馬券分析 baken.db × keiba.db、仮説出し専用)\n")
    print(f"- ユーザー馬券のあったレース数: **{n_bet_races}**")
    print(f"- pred_cache + 結果が揃い ◎(rank1) 特定できたレース: **{n_resolved}**")
    print(f"- うち ◎ が 1 着: **{n_maru_win}** ({n_maru_win/n_resolved*100:.1f}%)" if n_resolved else "")
    print(f"- うち ◎ が 3 着内: **{n_maru_place}** ({n_maru_place/n_resolved*100:.1f}%)" if n_resolved else "")
    print(f"- ◎敗北 & ユーザー馬券的中 (不一致): **{len(discrepancy)}** レース")

    print("\n## 実勝ち馬に keiba-yosou が与えた予想順位の分布 (全 bet レース)\n")
    print("| keiba-yosou rank | 勝ち馬数 |")
    print("|---|--:|")
    for rk in sorted(winner_rank_by_maru, key=lambda x: (isinstance(x, str), x)):
        print(f"| {rk} | {winner_rank_by_maru[rk]} |")

    print("\n## 不一致レースの実勝ち馬の特徴 (新特徴量の仮説材料)\n")
    print("### 勝ち馬の人気帯\n")
    for b in ["1-3", "4-6", "7-9", "10+", "?"]:
        if disc_winner_pop.get(b):
            print(f"- {b}番人気: {disc_winner_pop[b]}")
    print("\n### 勝ち馬の脚質 (leg_quality_code)\n")
    for leg, c in disc_winner_leg.most_common():
        print(f"- {leg}: {c}")
    print("\n### 勝ち馬への keiba-yosou 予想順位\n")
    for rk in sorted(disc_winner_yrank, key=lambda x: (isinstance(x, str), x)):
        print(f"- rank {rk}: {disc_winner_yrank[rk]}")
    print("\n### 勝ち馬の JRA-VAN mining 予測順位\n")
    for mo, c in sorted(disc_winner_mining.items()):
        print(f"- mining_order {mo}: {c}")
    if disc_winner_odds:
        import statistics
        print(f"\n### 勝ち馬の単勝オッズ (倍率): median={statistics.median(disc_winner_odds):.1f} "
              f"min={min(disc_winner_odds):.1f} max={max(disc_winner_odds):.1f} n={len(disc_winner_odds)}")

    print("\n## 不一致レース個票 (先頭 25)\n")
    print("| 日付 | 場 | R | ◎馬番(着) | 勝ち馬番 | 勝ち馬の予想rank | 馬券種 |")
    print("|---|---|---|---|---|---|---|")
    for d in discrepancy[:25]:
        k = d["key"]
        date = f"{k[0]}/{k[1]}"
        print(f"| {date} | {k[2]} | {k[5]} | {d['maru_hn']}({d['maru_fo']}着) | "
              f"{ni(d['winner']['horse_num'])} | {d['winner_yrank']} | "
              f"{','.join(d['types'].keys())} |")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
