"""F3 封印ホールドアウトの門 (2026-09-14 ユーザ決定「厳格に封印する」)。

## なぜコードで縛るか

「2026-10-01 以降のデータは 12 月の判定まで見ない」と事前宣言してあるが、
宣言だけでは守れない。既定の集計窓が全期間 (00000000〜99999999) のスクリプトや、
rolling で「直近 30 日」を見る週次監視 (Task Scheduler 登録済み) が複数あり、
**10/01 を過ぎた瞬間に自動で封印窓を読みに行く**。一度でも中身を見たら、
12 月の判定は「事前に決めた一発勝負」ではなくなる。

## 落ちたときの直し方

分析経路が封印窓を読もうとしている。集計窓を config.guard_analysis_window に
通すこと。予想生成・オッズ取得のような「データを作る側」は live=True で除外する。
**SEALED_FROM を書き換えて通すのは禁止** — それはプロトコル違反そのもの。
"""
from __future__ import annotations

import importlib
import sqlite3

import pytest

import config


# 2026-09-17 以降、封印の開始日は **未定** (config.SEALED_FROM is None)。
# 憲法 (docs/CHARTER_2026_09_17.md) 方針 8 により、試す価値のある候補が出るまで
# Lockbox を開けない。
#
# そこで本ファイルは 2 種類のテストを持つ:
#   1. 「今は封印していない」ことの確認 (下の test_seal_is_not_scheduled_yet)
#   2. **開始日を入れたときに仕組みが正しく働くか** の確認 (それ以外すべて)
# 2 のために、既定で開始日を入れた状態を作る fixture を置く。
SCHEDULED_FROM = "20261001"
SCHEDULED_UNTIL = "20260930"


def _apply_schedule(monkeypatch, start=SCHEDULED_FROM, until=SCHEDULED_UNTIL):
    """封印開始日を入れた状態を作る。

    `from config import SEALED_FROM` で **値をコピーして持っている**モジュールが
    あるので、そちらも合わせて差し替える。ここを忘れると、config だけ変えても
    monitor / tickets / gui は古い値を見続けてテストが嘘をつく。
    """
    monkeypatch.setattr(config, "SEALED_FROM", start)
    monkeypatch.setattr(config, "SEALED_UNTIL", until)
    monkeypatch.setattr(config, "SEALED_JUDGMENT_DONE", False)
    for modname in ("scripts.monitor", "predictor.tickets"):
        try:
            mod = importlib.import_module(modname)
        except Exception:
            continue
        if hasattr(mod, "SEALED_FROM"):
            monkeypatch.setattr(mod, "SEALED_FROM", start)
        if hasattr(mod, "SEALED_UNTIL"):
            monkeypatch.setattr(mod, "SEALED_UNTIL", until)


@pytest.fixture(autouse=True)
def _seal_active(monkeypatch):
    _apply_schedule(monkeypatch)


def test_seal_is_not_scheduled_yet(monkeypatch):
    """**現在は封印していない** こと (2026-09-17 ユーザ決定で延期)。

    憲法 方針 8: Final Lockbox は開発完了まで一切見ない。試す価値のある候補が
    無いまま開始すると、一度きりの Lockbox を「既知の答えの確認」に費やす。

    開始するときは config.SEALED_FROM に開始日を、SEALED_UNTIL にその前日を入れる。
    このテストはそのとき落ちるので、**封印を始めたことを必ず自覚できる**。
    """
    monkeypatch.undo()   # fixture の仮スケジュールを外して実際の設定を見る
    importlib.reload(config)

    assert config.SEALED_FROM is None, (
        "封印開始日が入っている。開始したのなら本テストを更新し、"
        "事前登録 (docs/F3_PREREG_*.md) も同時に commit すること")
    assert config.SEALED_UNTIL is None
    assert config.sealed_window_active() is False
    assert config.sealed_window_started() is False
    # 封印していないので分析は制限されない
    f, t, info = config.guard_analysis_window("00000000", "99999999")
    assert (f, t) == ("00000000", "99999999")
    assert config.sealed_notice(info) == ""
    assert config.artifact_drift() == []


def test_until_is_the_day_before_from():
    """SEALED_UNTIL は必ず SEALED_FROM の前日であること。

    2 つを別々に宣言しているので、片方だけ直すとゲートに穴が空く
    (1 日ぶん見えてしまう / 1 日ぶん余計に隠れる)。
    """
    from datetime import date, timedelta

    start = date(int(config.SEALED_FROM[:4]), int(config.SEALED_FROM[4:6]),
                 int(config.SEALED_FROM[6:]))
    assert config.SEALED_UNTIL == (start - timedelta(days=1)).strftime("%Y%m%d")


def test_window_before_the_seal_is_untouched():
    f, t, info = config.guard_analysis_window("20260101", "20260930")
    assert (f, t) == ("20260101", "20260930")
    assert info["clamped"] is False
    assert config.sealed_notice(info) == "", "制限していないなら黙っている"


def test_all_time_default_window_is_clamped():
    """既定が全期間のスクリプトが封印窓を読みに行かないこと。

    prediction_accuracy の既定は 00000000-99999999 で、10/01 を過ぎると
    無引数実行がそのまま封印窓を読む。ここが本命の防御。
    """
    f, t, info = config.guard_analysis_window("00000000", "99999999")
    assert t == "20260930"
    assert info["clamped"] is True
    assert "20260930" in config.sealed_notice(info)


def test_window_entirely_inside_the_seal_is_reported_as_empty():
    _, _, info = config.guard_analysis_window("20261001", "20261231")
    assert info["fully_sealed"] is True
    assert "対象データはありません" in config.sealed_notice(info)


def test_allow_sealed_passes_through_but_is_recorded(tmp_path, monkeypatch):
    """意図的な封印破りは通すが、必ず監査ログに残す。

    12 月の判定時にこのログが空でなければ、その判定は「一発勝負」として
    扱えない。黙って覗ける経路を残さないことが目的。
    """
    log = tmp_path / "sealed_access_log.jsonl"
    monkeypatch.setattr(config, "SEALED_ACCESS_LOG", log)

    f, t, info = config.guard_analysis_window(
        "20260101", "99999999", allow_sealed=True, context="test")

    assert (f, t) == ("20260101", "99999999"), "窓はそのまま通す"
    assert info["clamped"] is False
    assert log.exists(), "覗いた事実が記録されていない"
    assert "test" in log.read_text(encoding="utf-8")
    assert "判定材料にはできません" in config.sealed_notice(info)


def test_seal_lifts_after_judgment(monkeypatch):
    """判定を実施したら封印解除される (封印窓は次の dev 窓に転用可)。"""
    monkeypatch.setattr(config, "SEALED_JUDGMENT_DONE", True)
    f, t, info = config.guard_analysis_window("20260101", "99999999")
    assert (f, t) == ("20260101", "99999999")
    assert info["sealed_active"] is False


# ---------------------------------------------------------------------------
# 分析の共通入口 (list_races) に門が効いていること
# ---------------------------------------------------------------------------

def _db_with_races(dates) -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE races (race_year TEXT, race_month_day TEXT, track_code TEXT,"
        " kaiji TEXT, nichiji TEXT, race_num TEXT, distance INTEGER,"
        " data_div TEXT)")
    for d in dates:
        conn.execute("INSERT INTO races VALUES (?,?,?,?,?,?,?,'6')",
                     (d[:4], d[4:], "05", "01", "01", "01", 1600))
    conn.commit()
    return conn


def test_list_races_hides_sealed_races_from_analysis():
    from scripts.backtest import list_races

    conn = _db_with_races(["20260930", "20261001", "20261115"])
    try:
        got = list_races(conn, "20260101", "99999999")
    finally:
        conn.close()

    dates = [r["race_year"] + r["race_month_day"] for r in got]
    assert dates == ["20260930"], f"封印窓のレースが分析に混ざっている: {dates}"


def test_list_races_still_serves_prediction_generation():
    """予想生成は封印窓でも動くこと (データを作る側なので対象外)。

    ここを塞ぐと 10/01 以降に予想が 1 件も出なくなり、封印窓に貯めるべき
    データ自体が消える。封印の目的は「見ないこと」であって「止めること」ではない。
    """
    from scripts.backtest import list_races

    conn = _db_with_races(["20261115"])
    try:
        got = list_races(conn, "20261115", "20261115", live=True)
    finally:
        conn.close()

    assert len(got) == 1, "live 経路まで封印すると本番の予想生成が止まる"


# 封印を免除してよい (= データを作る側の) 呼び出し元。ここに無いファイルが
# live=True を使い始めたら、それは封印の抜け道なのでテストで気づけるようにする。
LIVE_ALLOWLIST = {
    "scripts/predict.py": 1,
    "scripts/fetch_odds.py": 1,
    "gui/app.py": 2,
}


def _live_call_sites() -> dict[str, int]:
    """`list_races(..., live=True)` の呼び出しをソースから数える (AST)。

    文字列検索だとコメント中の "live=True" でも一致してしまい、実際に kwarg を
    外してもテストが通る (2026-09-14 に実際そうなっていた)。構文木で数える。
    """
    import ast
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    found: dict[str, int] = {}
    for path in list((root / "scripts").glob("*.py")) + list((root / "gui").glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", "")
            if name != "list_races":
                continue
            for kw in node.keywords:
                if (kw.arg == "live" and isinstance(kw.value, ast.Constant)
                        and kw.value.value is True):
                    rel = path.relative_to(root).as_posix()
                    found[rel] = found.get(rel, 0) + 1
    return found


def test_live_exemptions_match_the_allowlist():
    """封印の免除 (live=True) が許可リストと完全一致すること。

    増えていれば「新しい抜け道が開いた」、減っていれば「10/01 以降に本番が
    静かに止まる」。どちらも黙って起きると気づけないので、両方向で落とす。
    """
    got = _live_call_sites()

    assert got == LIVE_ALLOWLIST, (
        f"live=True の免除が許可リストと違う。\n"
        f"  現在: {got}\n"
        f"  許可: {LIVE_ALLOWLIST}\n"
        "増えているなら封印の抜け道。減っているなら本番が止まる。"
    )


def test_prediction_html_generator_does_not_go_through_the_gate():
    """予想ページの生成が封印の門を通らないこと。

    web/generator.py は独自 SQL でレースを引くので門の影響を受けない。
    これが安全性の根拠なので、将来 list_races に寄せられて予想ページが
    10 月以降に空になる事故を防ぐため固定する。
    """
    from pathlib import Path

    src = (Path(__file__).resolve().parent.parent
           / "web" / "generator.py").read_text(encoding="utf-8")

    if "list_races" in src:
        assert "live=True" in src, (
            "generator が list_races を使い始めた。live=True を渡さないと "
            "10/01 以降に予想ページが空になる"
        )


def test_notice_text_is_printable_on_a_japanese_windows_console():
    """通知文が cp932 で出せること。

    Windows のコンソールは既定が cp932 で、"⚠" (U+26A0) を print すると
    UnicodeEncodeError でスクリプトごと落ちる。封印の門は分析を止めるための
    ものであって、例外で落とすためのものではない (2026-09-14 に
    prediction_accuracy で実機再現)。
    """
    for f, t in (("00000000", "99999999"), ("20261001", "20261231")):
        _, _, info = config.guard_analysis_window(f, t)
        config.sealed_notice(info).encode("cp932")   # 落ちなければ OK


def test_window_must_be_yyyymmdd():
    """ハイフン付き日付が門を素通りしないこと。

    "2026-12-31" は文字列比較で "-" < "1" となり SEALED_FROM より小さいと
    判定され、封印窓を素通りしていた (2026-09-14 実測)。
    """
    import pytest as _pytest

    with _pytest.raises(ValueError, match="YYYYMMDD"):
        config.guard_analysis_window("2026-09-01", "2026-12-31")


# ---------------------------------------------------------------------------
# モデル凍結 (判定のもう一つの前提)
# ---------------------------------------------------------------------------

def test_freeze_is_inactive_before_the_seal_starts(monkeypatch):
    """封印開始日より前はモデルを変えてよいこと。

    開始日までは dev 窓で、そこでモデルを直すのは正常な作業。「判定が未実施なら
    常に凍結」にしていたため、封印開始前なのに改修がブロックされていた
    (2026-09-14 に発覚)。凍結は **開始日以降** だけ効く。
    """
    monkeypatch.setattr(config, "SEALED_ARTIFACTS",
                        {"predictor/weights.json": "0" * 64})

    assert config.sealed_window_started("20260914") is False
    assert config.sealed_window_started("20261005") is True
    # 実際の今日 (開始前) では検査が働かない
    if config.sealed_window_started():
        pytest.skip("封印開始後に実行されている")
    assert config.artifact_drift() == [], "封印開始前なのに凍結が効いている"


def test_model_artifacts_are_unchanged_during_the_seal():
    """封印中はモデルが変わっていないこと。

    12 月の判定は「封印窓のあいだ同じモデルが予想し続けた」ことを前提に
    している。途中で重み・calibrator・LGBM が変われば封印窓に 2 種類の予想が
    混ざり、出てきた回収率が「どのモデルの成績か」を言えなくなる。
    「見ない」ことと同じくらい「変えない」ことが判定の前提。

    意図的に差し替えたなら config.SEALED_ARTIFACTS を更新すること。ただし
    それは封印窓を捨てて再開始するか、判定を先に行うかの判断とセット。
    """
    if not config.sealed_window_started():
        pytest.skip("封印開始前 (dev 窓) なので凍結は効かない")
    drift = config.artifact_drift()
    assert not drift, (
        "封印中にモデル成果物が変わっている:\n  " + "\n  ".join(drift))


def test_artifact_drift_actually_detects_a_change(tmp_path, monkeypatch):
    """凍結検査が本当に変化を検出すること (検査自体が空振りしていないか)。"""
    monkeypatch.setattr(config, "SEALED_ARTIFACTS",
                        {"predictor/weights.json": "0" * 64})
    _apply_schedule(monkeypatch, "20200101", "20191231")   # 開始済みに見立てる
    assert config.artifact_drift(), "変化しているのに検出できていない"


def test_artifact_freeze_is_not_checked_after_judgment(monkeypatch):
    """判定後は凍結を強制しない (封印解除後はモデルを更新してよい)。"""
    monkeypatch.setattr(config, "SEALED_JUDGMENT_DONE", True)
    monkeypatch.setattr(config, "SEALED_ARTIFACTS",
                        {"predictor/weights.json": "0" * 64})
    _apply_schedule(monkeypatch, "20200101", "20191231")
    monkeypatch.setattr(config, "SEALED_JUDGMENT_DONE", True)
    assert config.artifact_drift() == []


# ---------------------------------------------------------------------------
# 結果表示の封印 (予想生成は止めず、答え合わせ表示だけ止める)
# ---------------------------------------------------------------------------

def test_payout_display_is_sealed_but_prediction_is_not():
    """封印窓のレースは払戻を返さないこと。

    ここは GUI ダッシュボードと予想 HTML の「推奨買い目 (的中・回収)」表示の
    入口。予想の生成は封印対象外だが **結果の表示は対象**。10 月以降のレースの
    的中が画面に出れば、それを見た時点で封印が破れる。
    """
    from predictor.tickets import payout_row_for_race

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE payouts (race_year TEXT, race_month_day TEXT, track_code TEXT,"
        " kaiji TEXT, nichiji TEXT, race_num TEXT, tan_payout1 INTEGER)")
    for d in ("20260930", "20261115"):
        conn.execute("INSERT INTO payouts VALUES (?,?,?,?,?,?,?)",
                     (d[:4], d[4:], "05", "01", "01", "01", 640))
    conn.commit()

    def race(d):
        return {"race_year": d[:4], "race_month_day": d[4:], "track_code": "05",
                "kaiji": "01", "nichiji": "01", "race_num": "01"}

    try:
        assert payout_row_for_race(conn, race("20260930")) is not None, (
            "封印前のレースまで隠している")
        assert payout_row_for_race(conn, race("20261115")) is None, (
            "封印窓の払戻が表示経路に流れている")
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 週次監視の窓 (自動実行なので空振りが一番危ない)
# ---------------------------------------------------------------------------

def test_monitor_window_freezes_at_the_seal_instead_of_going_empty():
    """封印後の週次監視が「対象 0 件」で空振りしないこと。

    直近 30 日をそのまま取ると 10 月以降は窓のほとんどが封印窓に入り、
    list_races が空を返して監視が黙って無効化される。Task Scheduler で
    自動実行されるため、空振りに気づけないのが最も危険な壊れ方。
    終端を 09/30 で止めて 30 日ぶんを確保する。
    """
    import datetime
    from unittest import mock

    from scripts import monitor

    with mock.patch.object(monitor, "datetime") as dt:
        dt.now.return_value = datetime.datetime(2026, 12, 10)
        dt.strptime = datetime.datetime.strptime
        from_date, to_date, frozen = monitor._monitor_window(30)

    assert to_date == "20260930", "監視窓が封印窓に入り込んでいる"
    assert from_date == "20260831", "30 日ぶんの窓が確保されていない"
    assert frozen is True, "凍結していることを呼び出し側に伝えていない"


def test_monitor_window_is_normal_before_the_seal():
    import datetime
    from unittest import mock

    from scripts import monitor

    with mock.patch.object(monitor, "datetime") as dt:
        dt.now.return_value = datetime.datetime(2026, 9, 14)
        dt.strptime = datetime.datetime.strptime
        _, to_date, frozen = monitor._monitor_window(30)

    assert to_date == "20260914"
    assert frozen is False


# ---------------------------------------------------------------------------
# 新しいスクリプトが門を素通りしないための検出
# ---------------------------------------------------------------------------

# 結果列 (confirmed_order / payouts) を読むが封印の門を通さなくてよいもの。
# 「作る側」= 取り込み・生成・運用監視に限る。ここに足すときは、そのスクリプトが
# **成績を人に見せない** ことを確認すること。
GATE_EXEMPT = {
    # 取り込み・生成 (データを作る側)
    "scripts/fetch_full.py", "scripts/fetch_results.py", "scripts/fetch_odds.py",
    "scripts/fetch_mining.py", "scripts/fetch_fresh_odds.py",
    "scripts/fetch_morning_odds.py", "scripts/predict.py", "scripts/predict_t10.py",
    "scripts/repair_odds_stamps.py", "scripts/cleanup_placeholder_horse_rows.py",
    # 運用監視 (入力が揃っているかを見るだけで、当たり外れは見ない)
    "scripts/monitor.py", "scripts/check_fresh_odds_health.py",
    "scripts/fresh_odds_coverage.py",
    # 確定払戻の滞留監視。confirmed_order / payouts を読むが **件数だけ**で、
    # 誰が勝ったか・配当がいくらかは一切出さない。免除を口約束にしないよう、
    # 出力に成績が混ざらないことを
    # tests/test_payout_finality_monitor.py で固定してある。
    "scripts/payout_finality_monitor.py",
    # 門そのもの
    "scripts/backtest.py",
    # PIT 監査・取得率の偏り調査 (成績ではなく「データが取れているか」を見る)
    "scripts/pit_audit.py", "scripts/pit_coverage_bias.py",
    "scripts/backfill_announced_at.py",
    # 入力が既に封印済みの経路から来るもの。
    #   - data/results/<date>/ の CSV は build_daily_results が作るが、そちらは
    #     封印窓の日付では出力しない
    #   - data/dump_picks_*.csv は dump_predictions が作るが、そちらは
    #     list_races 経由で打ち切られる
    "scripts/analyze_misses.py",          # data/results/<date>/*.csv を読む
    "scripts/diag_pred_accuracy.py",      # dump_predictions の CSV を読む
    "scripts/fold_sensitivity_analyze.py",  # 同上
    "scripts/odds_tier_analyze.py",         # 同上
    # 固定窓 (封印開始より前) がソースに直書きされているもの
    "scripts/theoretical_w.py",           # '20250101'〜'20260517' 固定
    # 取り込み・パーサの動作確認ツール (集計をしない)
    "scripts/fetch_smoke_jvgets.py", "scripts/parse_smoke.py",
    "scripts/probe_corner_offsets.py",
    # 外部の馬券記録 (馬券分析/baken.db) と突き合わせる手動診断。
    # ユーザ自身が実際に賭けた結果を見るもので、そもそも本人は結果を知っている。
    # ここはコードでは封印できない領域 (だから事前登録が要る)。
    "scripts/diag_discrepancy.py",
}


def test_no_new_script_reads_results_without_the_gate():
    """結果を読む分析スクリプトが必ず門を通ること。

    封印は「宣言」ではなく「既定で守られる状態」でないと守れない。新しい分析
    スクリプトを書いた人が独自 SQL で confirmed_order / payouts を読むと、
    門を通らずに封印窓を覗ける。実際、この検査を入れた時点で 5 本が素通り
    していた (analyze_cross_pool / oracle_diagnose / eval_lgbm_oos /
    analyze_simple_edges / build_daily_results)。

    落ちたら: そのスクリプトの集計窓を config.guard_analysis_window に通すか、
    「結果を人に見せない」ことを確認したうえで GATE_EXEMPT に足す。
    """
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    ungated = []
    for path in sorted((root / "scripts").glob("*.py")):
        rel = path.relative_to(root).as_posix()
        if rel in GATE_EXEMPT:
            continue
        src = path.read_text(encoding="utf-8")
        reads_results = "confirmed_order" in src or "payouts" in src
        gated = ("guard_analysis_window" in src or "list_races" in src
                 or "SEALED_" in src)
        if reads_results and not gated:
            ungated.append(rel)

    assert not ungated, (
        "結果を読むのに封印の門を通っていないスクリプト:\n  "
        + "\n  ".join(ungated)
        + "\nguard_analysis_window を通すか、成績を見せないことを確認して "
          "GATE_EXEMPT に追加すること。"
    )


def test_gui_backtest_card_declares_the_freeze():
    """GUI の「直近バックテスト」カードが凍結を画面に出すこと。

    封印すると成績カードは 09/30 で止まる。理由が画面に出ないと、ユーザは
    「取込が止まった」「DB が壊れた」と読む。さらに悪いのは 30 日レンジで、
    期間表示は 10〜11 月なのに中身は 9 月の凍結値という **画面が嘘をつく**
    状態になり、件数が出るぶん警告も出ない (2026-09-14 に実測で再現)。

    gui.app は pywebview 依存で venv64 から import できないので、
    Python 側が組む値と JS 側の読み出しをソースで突き合わせる
    (tests/test_gui_js_contract.py と同じ方式)。
    """
    from pathlib import Path

    src = (Path(__file__).resolve().parent.parent
           / "gui" / "app.py").read_text(encoding="utf-8")

    # Python 側: 集計窓を封印手前に寄せ、凍結情報を返している
    assert 'context="gui._recent_backtest"' in src, (
        "GUI の成績集計が封印の門を通っていない (期間表示だけ 10 月になる)")
    assert '"sealed_frozen": sealed_frozen' in src
    assert '"sealed_note"' in src

    # JS 側: それを実際に描画している
    assert "bt.sealed_frozen" in src, "凍結情報を受け取っても画面に出していない"
    assert "bt.sealed_note" in src
    # 「件数不足 (low_n)」と同じ見た目にすると取込障害と誤読される
    assert "bt-sealed" in src, "凍結を low_n と区別できる表示になっていない"
