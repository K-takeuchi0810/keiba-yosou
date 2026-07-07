"""プロジェクト共通設定。

パス・サービスキー等の入口。ハードコード値はここに集約し、
他モジュールはこのモジュールを import する。
"""

from __future__ import annotations

import os
from pathlib import Path

# python-dotenv は任意依存にする。診断/監査系を素の `python` (dotenv 未導入) で
# 起動しても config が ModuleNotFoundError で落ちないよう、無ければ .env を素朴に
# 読む no-op フォールバックにする (2026-07-06: audit を素の python で実行 →
# `No module named 'dotenv'` で全ツールが起動不能だった実機報告への対処)。
try:
    from dotenv import load_dotenv
except ModuleNotFoundError:
    def load_dotenv(path: "Path | str | None" = None, *_a, **_k) -> bool:
        """dotenv 未導入時の簡易フォールバック。KEY=VALUE 行だけ環境変数へ流し込む
        (export/クォート/補間等は非対応。本格運用は python-dotenv を導入すること)。"""
        if path is None:
            return False
        p = Path(path)
        if not p.exists():
            return False
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))
        return True

PROJECT_ROOT = Path(__file__).resolve().parent

load_dotenv(PROJECT_ROOT / ".env")

# 取得・予想生成の中間成果物
DATA_DIR = PROJECT_ROOT / "data"
DB_PATH = DATA_DIR / "keiba.db"

# Web 配信用に生成する HTML（プレビュー兼公開元）
WEB_DIST = PROJECT_ROOT / "web" / "dist"

# 公開先（iCloud Drive 配下）。iPhone Files アプリから閲覧。
ICLOUD_PUBLISH_DIR = Path.home() / "iCloudDrive" / "競馬予想"

# JV-Link に渡すソフトウェアID（アプリ識別子）。
# 利用キー（サービスキー）は JV-Link 本体の設定ダイアログで登録済みであることが前提。
JVLINK_SID = os.environ.get("JVLINK_SID", "UNKNOWN")


# データ期間の正規分割 (2026-05-12 5 年分割版)。
# 過去、calibrator の学習窓と filter sweep の評価窓が不明確で in-sample 化が
# 発生していた。以後は **必ずこの 3 期間に従う**:
#   TRAIN      : calibrator fit + weights ハンドチューニング素材。3 年分。
#   TEST       : filter / weight 採用判断、A/B 比較。**TRAIN と必ず disjoint**
#   PRODUCTION : 本番運用 = 当日まで遡って features を構築し予測。
#                副次的に「採用 *決定後*」の HOLDOUT としても扱う。
# 各期間境界は `from <= race_date <= to` の閉区間。
#
# 注意: 過去 win_odds (発走前単勝オッズ) は JV-Data の O1 records 由来で、JV-Link
# は過去履歴を保持しない。当プロジェクトでは 2025-05 から累積開始。よって:
#   - 2024 以前: RA/SE/HR (race info / 出走馬 / 払戻) のみ → calibrator fit OK、
#     ベタ買い回収率 OK、`wl_odds_8_20` 系の buy filter は 0 件評価になる。
#   - 2025+ : 全部揃う → filter sweep 完全動作。
# このため filter_sweep --walk-forward の数値は実質 TEST 期間内 2025 部分が支配的。
DATA_PERIODS: dict[str, dict[str, str]] = {
    "train":      {"from": "20210101", "to": "20231231"},   # 3 年 / calibrator + weights
    "test":       {"from": "20240101", "to": "20251231"},   # 2 年 / 採用判断・A/B
    "production": {"from": "20260101", "to": "20261231"},   # 本番 + HOLDOUT
}

# コーナー通過順位 (corner_order_*) のバイト位置が実 .jvd で検証済みか。
# probe_corner_offsets --expect/--ra を実機で緑化したら True に反転する。
# webapp はこのフラグ 1 箇所で「先行力(暫定)」ラベルの要否を決める (probe 状態と
# 表示ラベルの単一情報源。緑化後の (暫定) 外し忘れ防止 — 2026-07-06 検証監査)。
CORNER_BYTES_VERIFIED: bool = False

# HN (繁殖馬マスタ) の産地名を webapp で表示してよいか (バイト位置確定 + DB 反映済みか)。
# バイト位置は 2026-07-06 実 .jvd で -2 ずれと確定し parse_hn を 208 に修正済み。ただし
# 既存 DB は旧オフセットの文字化け値を保持しているため、BLOD 再取込 (OPERATION.md §9-4) +
# 産地の目視検証を通すまで False で据え置く (誤データを出さない単一情報源)。再取込・検証後に True。
HN_BIRTHPLACE_VERIFIED: bool = False


# 買い目フィルタの既定値。アプリ全体で **必ずここを唯一の出典** とする。
# 利用箇所: web/generator.py (公開 HTML 用) / gui/app.py:_is_buy_candidate
#         / scripts/backtest.py (デフォルト引数) / GUI dashboard JS の input value
# この値が変わったら data/backtest/ で新たに rule_version 付きで保存し直すこと
# (過去 backtest と直接比較できなくなるため)。
BUY_FILTER_DEFAULT: dict = {
    # --- P15 採用 (2026-05-16): wl_kelly_ge_05 ---
    # LGBM v5 (Tier 2.3 込 98 features) で recent-3fold sweep し直し、
    # 8 つの robust 戦略 (v4 sweep の 1 個から大幅増) のうち、min return が
    # 最高の wl_kelly_ge_05 を採用。
    #
    # 戦略の中身:
    #   - 場 = 新潟 (04) + 阪神 (09) — P14 と同じ場 (recent-3fold で逆転 robust)
    #   - Kelly fraction >= 0.05 — LGBM の信頼度 + EV 内包条件
    #
    # 直近 1.5 年 3-fold:
    #   - 2025-H1: 112 戦 / 9.8% / 104.7%
    #   - 2025-H2: 120 戦 / 13.3% / 152.8%
    #   - 2026-Q1+: 56 戦 / 12.5% / 86.4%
    #   - min return 86.4% (P14 81.4% から +5pt)
    #   - 戦数 288 / 1.5 年 (P14 437 より少なめだが、最低保証が高い)
    #
    # P14 (only_t04_09_ev_ge_110) との違い:
    #   - P14: min_ev >= 1.10 だけで絞る
    #   - P15: min_kelly >= 0.05 で絞る (Kelly は EV と確率信頼度を内包)
    #   → Kelly のほうがモデル的に「賭けるべき」を直接示し、min が +5pt 改善
    #
    # 義務化された運用ルール (CLAUDE.md 必須ルール 4 参照):
    #   1. weekly_monitor.bat 週次自動実行 (Brier drift >+20% で警告)
    #   2. Brier 警告 → 即サスペンド (whitelist_tracks=[])
    #   3. 月次で TRAIN を rolling forward して LGBM 再訓練
    #   4. 四半期ごとに --recent-3fold を再実行
    #   5. 採用後 3 ヶ月で必ず再選定 (賞味期限管理)
    #
    # 採用後の hold-out 検証は 2026-05-11 以降の前向きデータで継続実施。
    #
    # 過去採用変遷:
    #   - wl_odds_8_20 (P05): TEST in-sample 116% → out-of-sample 34% (崩壊)
    #   - wl5_pop_1_2 (P12): TEST 184% → PROD 45% (崩壊)
    #   - only_t04_09_ev_ge_110 (P14): recent-3fold 82-168% (採用 → P15 に移行)
    #   - wl_kelly_ge_05 (P15): recent-3fold 86-153% (現採用)
    "min_ev": None,                 # min_kelly が EV エッジを内包
    "min_value": None,
    "min_odds": None,
    "max_odds": None,
    # ----- min_kelly: 撤廃 (2026-06-14 答え合わせ診断) -----
    # 旧 P15-A2 では min_kelly>=0.05 を主絞り条件にしていたが、全 JRA
    # 2024-2026 dump (8,509 戦) の答え合わせで **モデルの EV/Kelly/value 信号は
    # anti-predictive** と確証 (data/scorecards/20260614_0700_pred_accuracy.md):
    #   - EV bucket → 実回収率: TEST EV[1.5+)=72.6% / EV[0.8,1.0)=100.6%、
    #     2026 EV[1.5+)=31.5% — 高 EV ほど実回収が低い (理想と逆)
    #   - 4-fold 単勝回収 MIN: 現行 kelly>=.05 構成=45% << all ◎ベタ=62%
    # filter.py の「kelly_fraction>0 (=EV>1)」ハードゲートが買い候補を
    # anti-predictive な高 EV 馬に強制限定していた。閾値 0.05 はその上に重ねて
    # 更に反予測側へ寄せていたため撤廃 (None)。ゲート自体は betting 意味論維持の
    # ため filter.py に残置。利益エッジは主張しない (下記 popularity 参照)。
    "min_kelly": None,
    # ----- max_predicted_p: 高 p 帯破綻防御 (S5-3 で追加、2026-05-17) -----
    # Phase A2 完了後の Step 3 holdout で、bin [0.50, 0.55) actual=5.4% /
    # bin [0.70+] actual=0% という reliability 破綻が観測された。S5-1 の
    # Isotonic mapping 解析で「LGBM v5 の高 p 帯予測は構造的に楽観的、
    # Isotonic はダウンマップしているが race-internal 正規化で再び高 p 帯に
    # 浮かび上がる」構造が判明。
    # この破綻区間を運用上カットする防御策。Phase B/C で LGBM v6 再訓練
    # するまでの暫定対処。0.40 は「[0.35, 0.40) で gap -0.24 まで許容、
    # それ以上は不安定すぎる」という Step 3 reliability bins からの判断。
    "max_predicted_p": 0.40,
    # ----- popularity 1-3 必須 (2026-06-14 答え合わせ診断) -----
    # 答え合わせで **唯一頑健な正信号は「◎が市場人気馬 (1-3 番人気) か」** と判明。
    # ◎の単勝/複勝回収を 4-fold (2024 / 2025H1 / 2025H2 / 2026P) で見ると:
    #   - pop1-3:   単勝 MIN 68% / 複勝 MIN 81% (唯一 all ◎ベタ を上回り頑健)
    #   - pop4+:    単勝 19-79% (反選択域、◎が市場逆張りした非人気本命は人気馬に負ける)
    # Phase3 不一致分析でも、◎が外れユーザー的中の 51 戦中 34 戦は勝ち馬が
    # 1-3 番人気で、モデルはそれらを rank 2-6 に降格していた (逆張りの失敗)。
    # ★重要: pop1-3 でも 2026 holdout は単勝 68%/複勝 81% で 100% (控除率) 未満。
    #   = 利益エッジは存在しない。本フィルタは「観察用に最も妥当な候補」を出す
    #   ためのもので、実弾投入を推奨するものではない (memory:現状の買い候補を…)。
    # モデル内部の anti-predictivity 是正 (market_blend 引き下げ / 校正後 race内
    # 再正規化の見直し / LGBM v6) は検証付きで別セッション (follow-up) に持ち越し。
    "min_popularity": 1,
    "max_popularity": 3,
    "exclude_confidence": [],
    "max_odds_age_min": 30,
    # ----- 場別 whitelist (S5-3 で全場開放、2026-05-17) -----
    # 旧 P15 では `whitelist_tracks=["04", "09"]` (新潟+阪神) としていたが、
    # Step 3 holdout (PRODUCTION 1,380 races) の場別実測で:
    #   - 阪神 (09): 13.0% hit / 137.2% return (CI [9.1%, 18.1%]、唯一統計有意)
    #   - 新潟 (04):  9.7% hit /  66.1% return (CI [4.8%, 18.7%]、東京と差ナシ)
    # 新潟は P15 採用時の recent-3fold の偶然性 (1.5 ヶ月 smoke で 161% だった)
    # で WL に入っていたが、PRODUCTION では他場と差なく控除率以下。
    # 阪神は本物の好成績だが、阪神のみに絞ると機会が極めて薄くなる。
    # 「全場開放 + 市場人気 pop1-3 + max_predicted_p で絞る」方針 (P24, 2026-06-14
    # で min_kelly→pop1-3 に転換。min_kelly は anti-predictive ゆえ撤廃)。
    # 場別の優位性は `filter_sweep --recent-3fold` 場別解析で再評価。
    "whitelist_mode": False,
    "whitelist_grades": [],
    "whitelist_tracks": [],
}


# ----- 賭金サイジング既定 (2026-06-07 P20: HTML 表示 Kelly 是正) -----
# predictor.risk.kelly_size / recommended_fraction がこの 3 定数を import して
# 既定値に使う (= 単一出典)。risk → config の一方向依存で循環なし。
# 過去 HTML (web/generator.py) は predictor が返す full Kelly (kelly_fraction,
# 0-1 連続値) をそのまま「K xx%」と表示していたが、これは実際の推奨賭金
# (= 1/4 Kelly + per-bet cap) の ~3-4 倍に相当する過大表示で、買い候補 8 件の
# full Kelly 合計が bankroll の 115% に達する (= 物理的に賭けられない) 事故を
# 招いていた (2026-06-06 dist で実測)。表示を recommended_fraction に揃える。
#
# 重要 (variance 抑制 ≠ calibration): quarter + cap は「予想勝率 p が正しい前提」
# での分散抑制。現行モデルは中穴〜大穴の p を市場 implied の 2-7 倍に過大評価する
# reliability gap を持つため、これらの定数では over-confidence は矯正されない。
# 確率自体の矯正は Phase B1 (LGBM v6 再訓練 + 再校正) 領域。HTML 側でも
# .calib-caveat で「表示 P/EV は未校正で過大」とユーザーに開示する。
BET_KELLY_MODE = "quarter"          # full / half / quarter (= 1/4 Kelly, 推奨)
BET_KELLY_MAX_PCT = 0.05            # 1 点あたり bankroll の上限割合 (safety cap)
BET_PORTFOLIO_MAX_PCT = 0.25        # 1 日合計の推奨投資率上限 (超過時は HTML で警告)


def buy_whitelist_enabled() -> bool:
    """環境変数で `whitelist_mode` の既定値を上書き可能にする。"""
    raw = os.environ.get("BET_WHITELIST")
    if raw is None:
        return bool(BUY_FILTER_DEFAULT.get("whitelist_mode", False))
    return raw not in ("0", "false", "False", "")


def is_whitelisted_race(race: dict) -> bool:
    """race (dict) が「ホワイトリスト条件 (重賞 OR 得意競馬場)」を満たすか。

    `whitelist_mode=False` のときは常に True (= 通常運用)。
    呼び出し側は `_is_buy_candidate` 等から横断的にこの関数を使う。
    """
    if not buy_whitelist_enabled():
        return True
    grade = (race.get("grade_code") or "").strip()
    track = (race.get("track_code") or "").strip()
    if grade and grade in BUY_FILTER_DEFAULT["whitelist_grades"]:
        return True
    if track and track in BUY_FILTER_DEFAULT["whitelist_tracks"]:
        return True
    return False


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    WEB_DIST.mkdir(parents=True, exist_ok=True)
    ICLOUD_PUBLISH_DIR.mkdir(parents=True, exist_ok=True)
