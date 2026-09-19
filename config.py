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

# ---------------------------------------------------------------------------
# F3 封印ホールドアウト (2026-07-03 ユーザ合意 / docs/F3_MARKET_RESIDUAL_DESIGN.md D2)
# ---------------------------------------------------------------------------
# 「エッジがあるか」を一度だけ公正に判定するため、**2026-10-01 以降に蓄積される
# データは判定まで一切見ない**と事前宣言してある。dev 窓 = 2026-07-04〜09-30。
# 判定は封印窓が 800 レースに達した時点 (12 月上旬見込み) で **一度だけ**。
#
# なぜコードで縛るか: 宣言だけでは守れない。既定の集計窓が全期間 (00000000〜
# 99999999) のスクリプトや、rolling で「直近 30 日」を見る週次監視が複数あり、
# 10/01 を過ぎた瞬間に **自動で封印窓を読みに行く**。一度でも中身を見たら、
# 12 月の判定は「事前に決めた一発勝負」ではなくなる (見た結果に合わせて
# 仮説を選べてしまうため)。2026-09-14 にユーザが「厳格に封印する」を選択。
#
# ここを書き換えるのはプロトコル違反にあたる。判定を実施したら
# SEALED_JUDGMENT_DONE を True にして封印解除する (そのとき封印窓は次仮説の
# dev 窓に転用できる)。
# ---------------------------------------------------------------------------
# データ 4 分割 (憲法 方針 8 / Phase 0、2026-09-17)
# ---------------------------------------------------------------------------
# docs/CHARTER_2026_09_17.md は 学習 / Validation / Strategy Development /
# Final Lockbox の 4 分割を要求する。旧 DATA_PERIODS (train/test/production) は
# 「採用判断」用の 3 分割で、Strategy Development と Lockbox を区別していない。
#
# **律速する制約: 発走前 (T−10) のオッズは 2026-05-09 以降しか存在しない。**
# (2026-09-17 実測で確定。odds_snapshots は 05-02 から行があるが、05-02〜05-06 は
#  後から埋めた backfill_0B31 で取得時刻が発走後。PIT ゲートは fail-closed なので
#  実害は無いが、期間の起点を 05-02 と書くのは事実と 1 週ずれる)
# 方針 7 は「最終オッズで購入判定してはいけない」と定めるので、**購入判断を
# 含む検証に使えるのは 2026-05 以降だけ**。それ以前 (2021-2025) は確定オッズ
# しかないため、
#   - オッズを使わない基礎モデル (P_fundamental) の学習には使える
#   - 「市場のどこが誤りか」の学習にも使えるが、確定オッズ時点の市場であって
#     T−10 時点の市場ではないので、転移するとは限らない (要検証)
#   - **購入判断とその評価には使えない**
#
# PIT 正しいデータは **週 66 レース (実測、年 ≈ 3,450)** で積み上がる。
# 全レースの 20% を購入する戦略なら週 13 件なので、**865 件に約 15 ヶ月**。
# しかも 865 件は「検出力 50%」の数字で、実用的な 80% なら 1,764 件 = 約 30 ヶ月。
# これは設計で短縮できない。Lockbox の開始時期はこの制約から逆算すること。
# 期間は旧 DATA_PERIODS と **同じ境界**に揃えてある (train=2021-2023 /
# validation=2024-2025)。名前だけ変えて境界をずらすと、同名の "train" が
# 2 つの期間を指し、旧経路で学習した期間を新経路で評価する事故が起きる
# (2026-09-17 コード品質レビュー指摘)。
DATA_SPLIT: dict[str, dict[str, str | None]] = {
    # **2021 は burn-in 専用** (学習には使わない)。2020 以前の raw がバイト破損で
    # 使えないため、2021 年初頭の過去成績は左打ち切りされている。
    # 365 日のローリング特徴なら、2022 年の開始時点で 1 年ぶんの信頼できる履歴が
    # 確保できる (Phase 0.5-4B 基盤修復、2026-09-19)。
    "warmup": {"from": "20210101", "to": "20211231"},
    # 基礎モデル (オッズ不使用) の学習。確定オッズしか無い期間も使える。
    "train": {"from": "20220101", "to": "20241231"},
    # 手法の妥当性確認。まだ購入判断の検証には使わない。
    "validation": {"from": "20250101", "to": "20251231"},
    # **市場の誤りを探す作業はここだけで行う**。T−10 オッズがある期間に限る。
    # 開始は 2026-05-09 (後述の実測)。
    "strategy_dev": {"from": "20260509", "to": "20260831"},
    # 候補が出るまで手を付けない。開始日は SEALED_FROM と同じ扱い (現在は未定)。
    "lockbox": {"from": None, "to": None},
}

# **消費済み窓の台帳** (2026-09-17 検証レビュー指摘で新設)。
#
# 「未使用の期間」と思っていた窓を、実は自分の分析で既に見ていた、という事故を
# 防ぐ。2026-09-01〜09-13 は本人 (Claude) が residual_learn / MODEL_VS_MARKET の
# 検証窓として使っており、**clean ではない**。
# 窓を 1 度でも「結果を見る目的で」使ったら、必ずここに追記すること。
CONSUMED_WINDOWS: list[dict[str, str]] = [
    {"from": "20260701", "to": "20260913", "by": "residual_learn / fundamentals",
     "note": "市場オフセット学習の検証窓として結果を確認済み (2026-09-17)"},
    {"from": "20260817", "to": "20260913", "by": "prod_combine / prod_disagree",
     "note": "本番モデル vs 市場の 2 段結合の検証窓 (2026-09-15)"},
    {"from": "20260504", "to": "20260816", "by": "sim_ceiling / screen_*",
     "note": "天井シミュレーションと候補選別で全面的に使用 (2026-09-14〜15)"},
    # --- strategy_dev 窓 (2026-05-09〜08-31) の消費記録 ---
    # 検証レビューで「多重観察の会計が無い」と 2 回指摘されたので集約する。
    # 同じ窓を何度も見れば、見るたびに偶然の良い数字を拾う確率が上がる。
    {"from": "20260509", "to": "20260831", "by": "phase05_3 fundamental_eval",
     "note": "Fundamental vs T−10 市場の比較 (2026-09-18、1 回)"},
    {"from": "20260509", "to": "20260831", "by": "phase05_4A market_offset_eval",
     "note": "事前登録どおりの本番 1 回 + バグ修正による再実行 2 回 = 計 3 回 "
             "(2026-09-19)。主要仮説と金額は 3 回とも同一"},
    {"from": "20260509", "to": "20260831", "by": "phase05_4B market_offset_eval",
     "note": "基盤修復後の再評価 (2026-09-19)。仕様は 2021-2025 とデータ構造"
             "だけで固定してから実行"},
    {"from": "20260509", "to": "20260831", "by": "feature_domain_audit",
     "note": "特徴の分布のみ (成績は見ていない)。学習域外率の測定 (2026-09-19)"},
]

# 候補の事前登録後に「1 度だけ」使う確認窓の開始日。
# 上の台帳で消費済みの日より **後** でなければならない。
CONFIRM_FROM: str = "20260914"


def consumed_until() -> str:
    """台帳上、結果を見てしまった最後の日。"""
    return max((w["to"] for w in CONSUMED_WINDOWS), default="00000000")


def data_split(name: str) -> tuple[str | None, str | None]:
    """4 分割の期間を返す。存在しない名前は例外。"""
    if name not in DATA_SPLIT:
        raise KeyError(
            f"未知の分割名 {name!r}。使えるのは {sorted(DATA_SPLIT)} "
            "(docs/CHARTER_2026_09_17.md 方針 8)")
    d = DATA_SPLIT[name]
    return d["from"], d["to"]


# **DATA_SPLIT が旧 DATA_PERIODS と意図的に食い違っている箇所**。
#
# 同名なのに期間が違う状態を黙って作ると、旧 train で学習して新 train で評価する
# ような in-sample 事故が何も落ちずに通る。そこで「食い違ってよい」と宣言した
# ものだけを許し、それ以外は tests が落ちるようにする。
# **DATA_SPLIT が旧 DATA_PERIODS と意図的に食い違っている箇所**。
#
# 同名なのに期間が違う状態を黙って作ると、旧 train で学習して新 train で評価する
# ような in-sample 事故が何も落ちずに通る。そこで「食い違ってよい」と宣言した
# ものだけを許す。
#
# **期間そのものも書く。** 初版は理由文だけを持たせていたが、それだと
# 「一度宣言した分割は以後どこへ動かしても無音」というラチェットになる
# (専門家レビューが mutation で実証: 宣言を残したまま train.from を
# 20230101 にしても素通りした)。値を pin しておけば、期間を動かす人は
# 必ず理由文にも触ることになる。
SPLIT_DIVERGENCE: dict[str, dict[str, str]] = {
    "train": {
        "from": "20220101", "to": "20241231",
        "reason": (
            "Phase 0.5-4B 基盤修復 (2026-09-19)。2020 以前の raw がバイト破損で"
            "使えず、2021 年初頭の過去成績が左打ち切りされている。2021 を burn-in"
            "専用にして学習を 2022 から始める。旧 DATA_PERIODS は filter_sweep / "
            "bias_scan / monitor / webapp の凍結済みベースラインが参照しているので"
            "動かさない。**両者を混ぜて学習・評価しないこと**。")},
    "validation": {
        "from": "20250101", "to": "20251231",
        "reason": "同上。train を 1 年後ろにずらしたぶん、検証は 2025 単年になる。"},
}


def splits_are_disjoint() -> bool:
    """分割どうしが重なっていないこと。重なると OOS が成立しない。"""
    spans = [(v["from"], v["to"]) for v in DATA_SPLIT.values()
             if v["from"] and v["to"]]
    spans.sort()
    return all(spans[i][1] < spans[i + 1][0] for i in range(len(spans) - 1))


# 2026-09-17 ユーザ決定により **封印開始を延期** (None = 開始日未定)。
#
# 憲法 (docs/CHARTER_2026_09_17.md) 方針 8 は「Final Lockbox は開発完了まで
# 一切見ない」と定める。現時点で試す価値のある候補が無い (本番モデルの市場に
# 対する重みは −0.130) 状態で 10/01 に開始すると、一度きりの Lockbox を
# 「既知の答えの確認」に費やすことになる。
#
# 開始条件: Strategy Development 期間で見つけた候補が Validation を通過し、
#           事前登録を commit した日に、その翌日以降の日付をここに入れる。
# 開始したら SEALED_UNTIL も同時に (開始日の前日) に設定すること。
SEALED_FROM: str | None = None         # 開始日 (None = 未定 = 封印していない)
SEALED_UNTIL: str | None = None        # 分析が見てよい最終日 (開始日の前日)
SEALED_JUDGMENT_DONE: bool = False     # 判定を実施したら True にして封印解除

# 封印を破った事実を残す監査ログ。--allow-sealed で意図的に覗いた場合に追記する。
# 判定時にこのファイルが空でなければ、その判定は「一発勝負」として扱えない。
SEALED_ACCESS_LOG = PROJECT_ROOT / "data" / "runtime" / "sealed_access_log.jsonl"


# 封印中に凍結しておくモデル成果物と、その指紋 (2026-09-14 採取)。
#
# なぜ要るか: 12 月の判定は「封印窓のあいだ **同じモデル** が予想し続けた」
# ことを前提にしている。途中で重み・calibrator・LGBM が変われば、封印窓には
# 2 種類の予想が混ざり、出てきた回収率が「どのモデルの成績か」を言えなくなる。
# 「見ない」ことと同じくらい「変えない」ことが判定の前提。
#
# 判定後 (SEALED_JUDGMENT_DONE=True) は検査しない。封印中に意図的に
# 差し替えるときは、その時点で封印窓を捨てて再開始する判断とセットで行うこと。
SEALED_ARTIFACTS: dict[str, str] = {
    "predictor/weights.json": "6cd05d34a90a2ac4e2758de5e41c321f234276e13ffeeb07f20cf55c452f5dbc",
    "predictor/calibrator.json": "1cde95e02444f4926527b89eae1d8d70b989111bff31c9016ad29cc36e80db2a",
    "predictor/lgbm_model.txt": "afa6fe4717991b4fd607815b1249939418e3760eeda0498baa6ef859e9fc4aea",
    "predictor/lgbm_meta.json": "a46a26200339acc2df04f0a6933e7dd54e690380b44430c38f41a54ac354352a",
    "predictor/lgbm_features.json": "a62c0a379e891122d1ad1cdbec2d2371ec46581744c15872e3e66ad5f97912bc",
    "predictor/second_blend.json": "f7380bb331a89d258711f88289fe707a2b4bdc5169a8da03d2a0161fb69b3cea",
}


def sealed_window_started(today: str | None = None) -> bool:
    """封印窓が **もう始まっているか** (判定未実施 かつ 今日が SEALED_FROM 以降)。

    `sealed_window_active()` (= 判定がまだ) との違いに注意。封印開始日より前は
    まだ dev 窓なので、モデルの改修は自由でなければならない。
    """
    from datetime import date

    if not sealed_window_active():
        return False
    now = today or date.today().strftime("%Y%m%d")
    return SEALED_FROM is not None and now >= SEALED_FROM


def artifact_drift() -> list[str]:
    """凍結対象のモデル成果物が変化していないか調べ、変化したものを返す。

    空リストなら「封印開始時と同じモデル」。

    **封印窓が始まる前は常に空を返す**。開始日より前はまだ dev 窓で、モデルを
    直すのは正常な作業だから。ここを区別せずに「判定が未実施なら常に凍結」と
    していたため、封印開始前 (dev 窓の残り) にモデルを改修できない状態だった
    (2026-09-14 に発覚)。
    """
    import hashlib

    if not sealed_window_started():
        return []
    drifted: list[str] = []
    for rel, want in SEALED_ARTIFACTS.items():
        path = PROJECT_ROOT / rel
        if not path.exists():
            drifted.append(f"{rel} (消失)")
            continue
        got = hashlib.sha256(path.read_bytes()).hexdigest()
        if got != want:
            drifted.append(f"{rel} ({got[:12]} != {want[:12]})")
    return drifted


def sealed_window_active() -> bool:
    """封印が有効か。

    開始日が未定 (SEALED_FROM is None) なら封印していないので False。
    判定を実施済み (SEALED_JUDGMENT_DONE) でも False。
    """
    return SEALED_FROM is not None and not SEALED_JUDGMENT_DONE


def guard_analysis_window(
    from_date: str,
    to_date: str,
    *,
    allow_sealed: bool = False,
    context: str = "",
) -> tuple[str, str, dict]:
    """分析の集計窓を封印窓の手前で打ち切る。

    戻り値は (from_date, to_date, info)。info は呼び出し側が結果 JSON の meta に
    そのまま入れられる形にしてある (「この数字はどこまでのデータで出したか」を
    成果物自身に残すため)。

    allow_sealed=True は **意図的な封印破り**。窓はそのまま通すが、監査ログに
    追記する。判定時にこのログを見て、覗きがあったかを確認する。

    予想の生成 (live) はこの関数を通さない。封印窓のデータを *作る* 側であって
    *見る* 側ではないため。
    """
    for label, value in (("from_date", from_date), ("to_date", to_date)):
        if not (len(value) == 8 and value.isdigit()):
            # YYYYMMDD 以外を渡されると文字列比較が破綻する。実測: "2026-12-31" は
            # "-" < "1" のため SEALED_FROM より小さいと判定され、門を素通りした。
            raise ValueError(
                f"guard_analysis_window: {label} は YYYYMMDD で渡すこと (got {value!r})")
    info: dict = {
        "sealed_from": SEALED_FROM,
        "sealed_active": sealed_window_active(),
        "requested_to": to_date,
        "clamped": False,
        "allow_sealed": bool(allow_sealed),
    }
    if not sealed_window_active():
        return from_date, to_date, info
    if to_date < SEALED_FROM:
        return from_date, to_date, info

    if allow_sealed:
        _log_sealed_access(from_date, to_date, context)
        info["sealed_access_logged"] = True
        return from_date, to_date, info

    info["clamped"] = True
    info["effective_to"] = SEALED_UNTIL
    info["fully_sealed"] = from_date > SEALED_UNTIL
    return from_date, SEALED_UNTIL, info


class SealedAuditError(RuntimeError):
    """封印破りを記録できなかった。記録できないなら覗かせない。"""


def _log_sealed_access(from_date: str, to_date: str, context: str) -> None:
    """封印窓を意図的に読んだ事実を追記する。

    **書けなかったら例外を投げて封印破りを止める** (fail-closed)。判定手順は
    「このログが空なら一発勝負として扱える」と定義しているので、書き込み失敗を
    握り潰すと「覗いたのにログが空」= 判定の正当性が偽陽性になる。
    通常運用では追記コストはゼロなので、失敗は異常事態として扱ってよい。
    """
    import json
    from datetime import datetime

    try:
        SEALED_ACCESS_LOG.parent.mkdir(parents=True, exist_ok=True)
        with SEALED_ACCESS_LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps({
                "at": datetime.now().isoformat(timespec="seconds"),
                "from_date": from_date,
                "to_date": to_date,
                "context": context,
            }, ensure_ascii=False) + "\n")
    except OSError as exc:
        raise SealedAuditError(
            f"封印破りを監査ログに記録できませんでした ({SEALED_ACCESS_LOG}): {exc}。"
            "記録できない状態で封印窓を読むことは許可されていません。"
        ) from exc


def sealed_notice(info: dict) -> str:
    """guard_analysis_window の結果を人間向け 1 行にする (空文字なら出力不要)。"""
    if not info.get("sealed_active"):
        return ""
    if info.get("allow_sealed") and info.get("sealed_access_logged"):
        return (
            f"【注意】封印窓 ({SEALED_FROM}〜) を意図的に読みました。"
            f"監査ログに記録済み: {SEALED_ACCESS_LOG.name}。"
            "この結果を 12 月の判定材料にはできません。"
        )
    if info.get("fully_sealed"):
        return (
            f"【注意】指定された期間は全体が封印窓 ({SEALED_FROM}〜) の中にあります。"
            "対象データはありません (F3 判定まで参照禁止)。"
        )
    if info.get("clamped"):
        return (
            f"封印窓のため集計を {SEALED_UNTIL} までに制限しました "
            f"(指定は {info.get('requested_to')})。"
        )
    return ""


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


# F3 PIT ゲート (2026-07-03 ユーザ確定, docs/F3_MARKET_RESIDUAL_DESIGN.md D1)。
# 市場スナップショット特徴に使ってよいのは fetched_at ≤ 発走時刻 − この分数 のみ。
# 実運用で購入判断できる時刻から導出した値であり、backtest と live で必ず同一値を使う
# (これより後のオッズで backtest すると見かけのエッジを製造する)。変更はユーザ承認必須。
PIT_GATE_MINUTES = 10

# 買い目フィルタの既定値。アプリ全体で **必ずここを唯一の出典** とする。
# 利用箇所: web/generator.py (公開 HTML 用) / gui/app.py:_is_buy_candidate
#         / scripts/backtest.py (デフォルト引数) / GUI dashboard JS の input value
# この値が変わったら data/backtest/ で新たに rule_version 付きで保存し直すこと
# (過去 backtest と直接比較できなくなるため)。
#
# ★位置づけ (2026-07-03 profitability 監査): 現行フィルタは「採用戦略」ではなく
#   **観察マーカー**。v5/v6 どちらのモデルでも buy_only < all (価値破壊) が
#   OOS で継続しており (v6: 56.3% < 63.5% / v5: 54.1% < 68.9%、20260101-0614)、
#   実弾フィルタ候補から降格。実弾昇格条件 = OOS で buy_only 回収率 CI 下限 > 100%。
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
    # ----- サスペンド (2026-08-22): 便益の証拠が全窓で不在 -----
    # 必須ルール 4 (CLAUDE.md) の「収益劣化 → 即サスペンド → 再選定」に基づく。
    #
    # 2026 OOS 実測 (repair_odds_stamps --apply 後の正本、
    # data/backtest/20260822_153653_tan_p26-oos-2026ytd-0816-repaired-filtered.json、
    # calibration_in_sample=False、post-start 除外 0 件):
    #   - ◎ベタ買い     : 1,932 戦 / 22.7% / 回収 66.2% (CI [59.4%, 73.3%])
    #   - 本フィルタ適用 :   186 戦 / 11.8% / 回収 52.6% (CI [33.2%, 73.2%])
    # 新規窓のみ (2026-06-15〜08-16、20260822_160848_...-repaired-filtered.json。
    # 上の窓の部分集合であり独立証拠ではない):
    #   - ◎ベタ買い     :   606 戦 / 24.8% / 回収 72.4% (CI [61.4%, 85.8%])
    #   - 本フィルタ適用 :    66 戦 /  7.6% / 回収 31.8% (CI [6.2%, 61.4%])
    # (修復前の初回測定 1,460 戦 65.3% / 142 戦 53.4% と結論一致。買い候補の
    #  CI 上限は 80.1% → 73.2% に締まり、サスペンド根拠はむしろ強まった)
    # 実運用 HTML の答え合わせ (v6 期 12 開催日) でも買い候補 32 戦 68.8% <
    # ◎ベタ 360 戦 70.2%。
    #
    # 統計的な言い方の限界 (2026-08-22 収益性・検証監査の指摘を反映): CI は大きく
    # 重なるので「絞ると悪化する」ことは **有意には示せていない**。停止の根拠は
    # 「点推定が全窓でベタ買いを下回り、便益の正の証拠がどこにも無い」こと。
    # 買い推奨表示には便益の証拠が必要で、有害の証明は不要という非対称性による。
    # なお採用は 2026-06-14 なので、賞味期限 3 ヶ月には未到達 (約 2.3 ヶ月)。
    #
    # True の間 `predictor.filter.is_buy_candidate` は常に False を返し、GUI と
    # HTML の買い候補はゼロ件になる (誤った推奨表示を止める)。
    # 計測経路との契約:
    #   - backtest / filter_sweep は spec を直接組み立てる
    #     (`scripts.backtest.buy_filter_from_generator` は suspended を渡さない)
    #     ので、サスペンド中も buy_only 系列の計測は継続する。
    #   - full spec が渡る経路 (GUI 計測など) でサスペンドを外したいときだけ
    #     `BET_FILTER_IGNORE_SUSPENSION=1` を使う。backtest では meta.env_overrides
    #     に記録される。
    # 解除条件: `scripts.filter_sweep --recent-3fold` (オッズ鮮度ゲート ON、
    # repair_odds_stamps --apply 済みの DB) で 3 fold すべて robust (点推定 ≥ 80%
    # かつ CI 下限 ≥ 50%) の戦略を選び直したとき。ただし回収率 CI 下限が 100% を
    # 超えない限り、再選定しても「観察用」から上げてはならない。
    "suspended": True,
    # ----- 市場情報が無いレースの扱い (2026-08-24 実測にもとづく) -----
    # 発走 T−n 分の時点でオッズが 1 頭も取れなかったレースでは、モデルは
    # 市場情報ゼロで ◎ を決めることになる。そのときの成績が極端に悪い:
    #   オッズ取得できた 793 戦: 的中 24.6% / 回収 76.7%
    #   取得できなかった 239 戦: 的中 20.9% / 回収 **50.0%**  ← 26.7pt 劣化
    # (data/backtest/20260824_224655_tan_p31-log-score-filtered.json の
    #  pit_bet_log を has_market で分解。239 戦はすべて coverage 0% = 完全欠測で、
    #  部分取得のケースは 1 件も無かった)
    #
    # 「予想の質を上げる」より「情報が無いときに無理をしない」ほうが効果が
    # 大きいことを示す唯一の明確な数値差なので、市場情報が無いレースは
    # 買い候補から外す (印と根拠は観察用に出す。EV は市場が無いと計算できない)。
    "require_market": True,
}

# サスペンド開始日の単一出典 (HTML / GUI の文言が参照する)。
BUY_FILTER_SUSPENDED_SINCE = "2026-08-22"


def buy_filter_suspended() -> bool:
    """買い候補フィルタがサスペンド中か。

    `BET_FILTER_IGNORE_SUSPENSION=1` のときは False を返す。これは
    「サスペンド中の仕様を計測だけしたい」backtest / sweep 用の抜け道で、
    運用 (GUI / HTML 生成) では使わない。
    """
    if os.environ.get("BET_FILTER_IGNORE_SUSPENSION") in ("1", "true", "True"):
        return False
    return bool(BUY_FILTER_DEFAULT.get("suspended", False))


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
