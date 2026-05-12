"""JV-Data RA / SE レコードパーサ。

仕様書: docs/JV-Data4901.pdf §2 (RA), §3 (SE)
- 全フィールドを取らず、予想・表示で当面必要なものに絞っている
- 追加項目が必要になったら dataclass にフィールドを足し、parse_xx() を更新する
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

RA_LENGTH = 1272
SE_LENGTH = 555
HR_LENGTH = 719
O1_LENGTH = 962
UM_LENGTH = 1609
HS_LENGTH = 194

# Phase 1 (2026-05-13): 未活用 dataspec
DM_LENGTH = 303      # MING タイム型マイニング予想
TM_LENGTH = 141      # MING 対戦型マイニング予想
HN_LENGTH = 251      # BLOD 繁殖馬マスタ
SK_LENGTH = 208      # BLOD 産駒マスタ
HC_LENGTH = 60       # SLOP 坂路調教
WC_LENGTH = 105      # WOOD ウッドチップ調教
TK_LENGTH = 21657    # TOKU 特別登録馬


def _slice(rec: bytes, pos: int, length: int) -> bytes:
    """仕様書 1-indexed 位置からバイト列を切り出し。"""
    return rec[pos - 1 : pos - 1 + length]


def _str(rec: bytes, pos: int, length: int) -> str:
    raw = _slice(rec, pos, length)
    return raw.decode("cp932", errors="replace").rstrip("　 \x00")


def _ascii(rec: bytes, pos: int, length: int) -> str:
    return _slice(rec, pos, length).decode("ascii", errors="replace").strip()


def _int(rec: bytes, pos: int, length: int, default: int = 0) -> int:
    text = _ascii(rec, pos, length)
    if not text:
        return default
    try:
        return int(text)
    except ValueError:
        return default


@dataclass
class RaceInfo:
    record_type: str
    data_div: str
    data_created: str
    year: str
    month_day: str
    track_code: str
    kaiji: str
    nichiji: str
    race_num: str
    weekday_code: str
    special_race_num: str
    race_name: str
    race_subtitle: str
    race_paren: str
    race_short10: str
    race_short6: str
    grade_code: str
    race_type_code: str
    race_symbol_code: str
    weight_type_code: str
    distance: int
    track_type_code: str
    course_div: str
    start_time: str
    registered_count: int
    starter_count: int
    weather_code: str
    turf_condition: str
    dirt_condition: str

    @property
    def race_id(self) -> str:
        return f"{self.year}{self.month_day}_{self.track_code}_{self.kaiji}_{self.nichiji}_{self.race_num}"


def parse_ra(rec: bytes) -> RaceInfo:
    # BSTR 経由のレコードは cp932 ラウンドトリップで長さがブレることがあるので、
    # RA_LENGTH に正規化（短ければゼロパディング、長ければ末尾切り捨て）。
    if len(rec) < RA_LENGTH:
        rec = rec.ljust(RA_LENGTH, b"\x00")
    elif len(rec) > RA_LENGTH:
        rec = rec[:RA_LENGTH]
    return RaceInfo(
        record_type=_ascii(rec, 1, 2),
        data_div=_ascii(rec, 3, 1),
        data_created=_ascii(rec, 4, 8),
        year=_ascii(rec, 12, 4),
        month_day=_ascii(rec, 16, 4),
        track_code=_ascii(rec, 20, 2),
        kaiji=_ascii(rec, 22, 2),
        nichiji=_ascii(rec, 24, 2),
        race_num=_ascii(rec, 26, 2),
        weekday_code=_ascii(rec, 28, 1),
        special_race_num=_ascii(rec, 29, 4),
        race_name=_str(rec, 33, 60),
        race_subtitle=_str(rec, 93, 60),
        race_paren=_str(rec, 153, 60),
        race_short10=_str(rec, 573, 20),
        race_short6=_str(rec, 593, 12),
        grade_code=_ascii(rec, 615, 1),
        race_type_code=_ascii(rec, 617, 2),
        race_symbol_code=_ascii(rec, 619, 3),
        weight_type_code=_ascii(rec, 622, 1),
        distance=_int(rec, 698, 4),
        track_type_code=_ascii(rec, 706, 2),
        course_div=_ascii(rec, 710, 2),
        start_time=_ascii(rec, 874, 4),
        registered_count=_int(rec, 882, 2),
        starter_count=_int(rec, 884, 2),
        weather_code=_ascii(rec, 888, 1),
        turf_condition=_ascii(rec, 889, 1),
        dirt_condition=_ascii(rec, 890, 1),
    )


@dataclass
class HorseRaceInfo:
    record_type: str
    data_div: str
    data_created: str
    year: str
    month_day: str
    track_code: str
    kaiji: str
    nichiji: str
    race_num: str
    waku_num: str
    horse_num: str
    blood_register_num: str
    horse_name: str
    horse_symbol_code: str
    sex_code: str
    breed_code: str
    coat_code: str
    age: int
    east_west_code: str
    trainer_code: str
    trainer_short_name: str
    owner_code: str
    owner_name: str
    burden_weight: int  # 0.1kg 単位
    blinker: str
    jockey_code: str
    jockey_short_name: str
    jockey_apprentice_code: str
    horse_weight: str  # 999=計量不能, 000=出走取消
    weight_change_sign: str
    weight_change_diff: str
    abnormal_code: str
    finish_order: int  # 入線順位
    confirmed_order: int  # 確定着順
    same_finish: str
    finish_time: int  # 9分99秒9 → 99T (例 1234 = 1分23秒4)
    win_odds: int  # 999.9 倍を ×10 した整数
    win_popularity: int
    final_3f: int  # 後3F 99.9秒
    mining_time: int
    mining_predicted_order: int
    leg_quality_code: str  # 1=逃 2=先 3=差 4=追

    @property
    def race_id(self) -> str:
        return f"{self.year}{self.month_day}_{self.track_code}_{self.kaiji}_{self.nichiji}_{self.race_num}"


def parse_se(rec: bytes) -> HorseRaceInfo:
    if len(rec) < SE_LENGTH:
        rec = rec.ljust(SE_LENGTH, b"\x00")
    elif len(rec) > SE_LENGTH:
        rec = rec[:SE_LENGTH]
    return HorseRaceInfo(
        record_type=_ascii(rec, 1, 2),
        data_div=_ascii(rec, 3, 1),
        data_created=_ascii(rec, 4, 8),
        year=_ascii(rec, 12, 4),
        month_day=_ascii(rec, 16, 4),
        track_code=_ascii(rec, 20, 2),
        kaiji=_ascii(rec, 22, 2),
        nichiji=_ascii(rec, 24, 2),
        race_num=_ascii(rec, 26, 2),
        waku_num=_ascii(rec, 28, 1),
        horse_num=_ascii(rec, 29, 2),
        blood_register_num=_ascii(rec, 31, 10),
        horse_name=_str(rec, 41, 36),
        horse_symbol_code=_ascii(rec, 77, 2),
        sex_code=_ascii(rec, 79, 1),
        breed_code=_ascii(rec, 80, 1),
        coat_code=_ascii(rec, 81, 2),
        age=_int(rec, 83, 2),
        east_west_code=_ascii(rec, 85, 1),
        trainer_code=_ascii(rec, 86, 5),
        trainer_short_name=_str(rec, 91, 8),
        owner_code=_ascii(rec, 99, 6),
        owner_name=_str(rec, 105, 64),
        burden_weight=_int(rec, 289, 3),
        blinker=_ascii(rec, 295, 1),
        jockey_code=_ascii(rec, 297, 5),
        jockey_short_name=_str(rec, 307, 8),
        jockey_apprentice_code=_ascii(rec, 323, 1),
        horse_weight=_ascii(rec, 325, 3),
        weight_change_sign=_ascii(rec, 328, 1),
        weight_change_diff=_ascii(rec, 329, 3),
        abnormal_code=_ascii(rec, 332, 1),
        finish_order=_int(rec, 333, 2),
        confirmed_order=_int(rec, 335, 2),
        same_finish=_ascii(rec, 337, 1),
        finish_time=_int(rec, 339, 4),
        win_odds=_int(rec, 360, 4),
        win_popularity=_int(rec, 364, 2),
        final_3f=_int(rec, 391, 3),
        mining_time=_int(rec, 538, 5),
        mining_predicted_order=_int(rec, 551, 2),
        leg_quality_code=_ascii(rec, 553, 1),
    )


def _split_fixed(data: bytes, length: int) -> list[bytes]:
    if len(data) % length:
        raise ValueError(f"file size {len(data)} not multiple of {length}")
    return [data[i : i + length] for i in range(0, len(data), length)]


def parse_ra_file(path: str | Path) -> list[RaceInfo]:
    data = Path(path).read_bytes()
    return [parse_ra(rec) for rec in _split_fixed(data, RA_LENGTH)]


def parse_se_file(path: str | Path) -> list[HorseRaceInfo]:
    data = Path(path).read_bytes()
    return [parse_se(rec) for rec in _split_fixed(data, SE_LENGTH)]


@dataclass
class Payout:
    """払戻 (HR レコード)。docs/JV-Data4901.pdf §4。

    JRA 公式払戻金。発売券種ごとに 3〜5 同着分の繰返しエリアを持つ。
    今は単・複・馬連・3 連複の 4 券種だけ取り込む (バックテスト最小要件)。
    馬単・ワイド・3 連単・枠連が必要になったらフィールドを追加する。
    """
    record_type: str
    data_div: str
    data_created: str
    year: str
    month_day: str
    track_code: str
    kaiji: str
    nichiji: str
    race_num: str
    registered_count: int
    starter_count: int

    # 単勝 (1 件 13 バイト × 3 同着分)
    tan_horse_num1: str; tan_payout1: int; tan_pop1: int
    tan_horse_num2: str; tan_payout2: int; tan_pop2: int
    tan_horse_num3: str; tan_payout3: int; tan_pop3: int

    # 複勝 (1 件 13 バイト × 5 同着分)
    fuku_horse_num1: str; fuku_payout1: int; fuku_pop1: int
    fuku_horse_num2: str; fuku_payout2: int; fuku_pop2: int
    fuku_horse_num3: str; fuku_payout3: int; fuku_pop3: int
    fuku_horse_num4: str; fuku_payout4: int; fuku_pop4: int
    fuku_horse_num5: str; fuku_payout5: int; fuku_pop5: int

    # 馬連 (1 件 16 バイト × 3 同着分)
    umaren_combo1: str; umaren_payout1: int; umaren_pop1: int
    umaren_combo2: str; umaren_payout2: int; umaren_pop2: int
    umaren_combo3: str; umaren_payout3: int; umaren_pop3: int

    # 3 連複 (1 件 18 バイト × 3 同着分)
    sanrenpuku_combo1: str; sanrenpuku_payout1: int; sanrenpuku_pop1: int
    sanrenpuku_combo2: str; sanrenpuku_payout2: int; sanrenpuku_pop2: int
    sanrenpuku_combo3: str; sanrenpuku_payout3: int; sanrenpuku_pop3: int

    @property
    def race_id(self) -> str:
        return f"{self.year}{self.month_day}_{self.track_code}_{self.kaiji}_{self.nichiji}_{self.race_num}"


def _parse_tan_block(rec: bytes, base: int, idx: int) -> tuple[str, int, int]:
    """単勝/複勝ブロック (13 バイト): 馬番(2) + 払戻金(9) + 人気順(2)。

    base は仕様書 1-indexed 起点 (項番 42 なら 103)、idx は 0,1,2,(3,4)。
    """
    pos = base + idx * 13
    return (
        _ascii(rec, pos, 2),
        _int(rec, pos + 2, 9),
        _int(rec, pos + 11, 2),
    )


def _parse_pair_block(rec: bytes, base: int, idx: int) -> tuple[str, int, int]:
    """馬連/ワイド/馬単ブロック (16 バイト): 組番(4) + 払戻金(9) + 人気順(3)。"""
    pos = base + idx * 16
    return (
        _ascii(rec, pos, 4),
        _int(rec, pos + 4, 9),
        _int(rec, pos + 13, 3),
    )


def _parse_triple_block(rec: bytes, base: int, idx: int, combo_len: int = 6) -> tuple[str, int, int]:
    """3 連複/3 連単ブロック: 組番(combo_len) + 払戻金(9) + 人気順(3)。

    3 連複は 18 バイト (組番 6 + 払戻 9 + 人気 3)
    3 連単は 19 バイト (組番 6 + 払戻 9 + 人気 4) — 今は未対応
    """
    block_len = combo_len + 9 + 3
    pos = base + idx * block_len
    return (
        _ascii(rec, pos, combo_len),
        _int(rec, pos + combo_len, 9),
        _int(rec, pos + combo_len + 9, 3),
    )


def parse_hr(rec: bytes) -> Payout:
    if len(rec) < HR_LENGTH:
        rec = rec.ljust(HR_LENGTH, b"\x00")
    elif len(rec) > HR_LENGTH:
        rec = rec[:HR_LENGTH]

    tan = [_parse_tan_block(rec, 103, i) for i in range(3)]
    fuku = [_parse_tan_block(rec, 142, i) for i in range(5)]
    umaren = [_parse_pair_block(rec, 246, i) for i in range(3)]
    sanrenpuku = [_parse_triple_block(rec, 550, i, combo_len=6) for i in range(3)]

    return Payout(
        record_type=_ascii(rec, 1, 2),
        data_div=_ascii(rec, 3, 1),
        data_created=_ascii(rec, 4, 8),
        year=_ascii(rec, 12, 4),
        month_day=_ascii(rec, 16, 4),
        track_code=_ascii(rec, 20, 2),
        kaiji=_ascii(rec, 22, 2),
        nichiji=_ascii(rec, 24, 2),
        race_num=_ascii(rec, 26, 2),
        registered_count=_int(rec, 28, 2),
        starter_count=_int(rec, 30, 2),
        tan_horse_num1=tan[0][0], tan_payout1=tan[0][1], tan_pop1=tan[0][2],
        tan_horse_num2=tan[1][0], tan_payout2=tan[1][1], tan_pop2=tan[1][2],
        tan_horse_num3=tan[2][0], tan_payout3=tan[2][1], tan_pop3=tan[2][2],
        fuku_horse_num1=fuku[0][0], fuku_payout1=fuku[0][1], fuku_pop1=fuku[0][2],
        fuku_horse_num2=fuku[1][0], fuku_payout2=fuku[1][1], fuku_pop2=fuku[1][2],
        fuku_horse_num3=fuku[2][0], fuku_payout3=fuku[2][1], fuku_pop3=fuku[2][2],
        fuku_horse_num4=fuku[3][0], fuku_payout4=fuku[3][1], fuku_pop4=fuku[3][2],
        fuku_horse_num5=fuku[4][0], fuku_payout5=fuku[4][1], fuku_pop5=fuku[4][2],
        umaren_combo1=umaren[0][0], umaren_payout1=umaren[0][1], umaren_pop1=umaren[0][2],
        umaren_combo2=umaren[1][0], umaren_payout2=umaren[1][1], umaren_pop2=umaren[1][2],
        umaren_combo3=umaren[2][0], umaren_payout3=umaren[2][1], umaren_pop3=umaren[2][2],
        sanrenpuku_combo1=sanrenpuku[0][0], sanrenpuku_payout1=sanrenpuku[0][1], sanrenpuku_pop1=sanrenpuku[0][2],
        sanrenpuku_combo2=sanrenpuku[1][0], sanrenpuku_payout2=sanrenpuku[1][1], sanrenpuku_pop2=sanrenpuku[1][2],
        sanrenpuku_combo3=sanrenpuku[2][0], sanrenpuku_payout3=sanrenpuku[2][1], sanrenpuku_pop3=sanrenpuku[2][2],
    )


def parse_hr_file(path: str | Path) -> list[Payout]:
    data = Path(path).read_bytes()
    return [parse_hr(rec) for rec in _split_fixed(data, HR_LENGTH)]


@dataclass
class O1Odds:
    record_type: str
    data_div: str
    data_created: str
    year: str
    month_day: str
    track_code: str
    kaiji: str
    nichiji: str
    race_num: str
    announced_at: str
    registered_count: int
    starter_count: int
    win_odds: list[tuple[str, int, int]]

    @property
    def race_id(self) -> str:
        return f"{self.year}{self.month_day}_{self.track_code}_{self.kaiji}_{self.nichiji}_{self.race_num}"


def parse_o1(rec: bytes) -> O1Odds:
    if len(rec) < O1_LENGTH:
        rec = rec.ljust(O1_LENGTH, b"\x00")
    elif len(rec) > O1_LENGTH:
        rec = rec[:O1_LENGTH]

    wins: list[tuple[str, int, int]] = []
    for i in range(28):
        pos = 44 + i * 8
        horse_num = _ascii(rec, pos, 2)
        odds = _int(rec, pos + 2, 4)
        popularity = _int(rec, pos + 6, 2)
        if horse_num and odds > 0:
            wins.append((horse_num, odds, popularity))

    return O1Odds(
        record_type=_ascii(rec, 1, 2),
        data_div=_ascii(rec, 3, 1),
        data_created=_ascii(rec, 4, 8),
        year=_ascii(rec, 12, 4),
        month_day=_ascii(rec, 16, 4),
        track_code=_ascii(rec, 20, 2),
        kaiji=_ascii(rec, 22, 2),
        nichiji=_ascii(rec, 24, 2),
        race_num=_ascii(rec, 26, 2),
        announced_at=_ascii(rec, 28, 8),
        registered_count=_int(rec, 36, 2),
        starter_count=_int(rec, 38, 2),
        win_odds=wins,
    )


def parse_o1_file(path: str | Path) -> list[O1Odds]:
    data = Path(path).read_bytes()
    return [parse_o1(rec) for rec in _split_fixed(data, O1_LENGTH)]


@dataclass
class HorseMaster:
    record_type: str
    data_div: str
    data_created: str
    blood_register_num: str
    horse_name: str
    sex_code: str
    breed_code: str
    sire_breeding_num: str
    sire_name: str
    dam_sire_breeding_num: str
    dam_sire_name: str
    leg_tendency_code: str


def _pedigree_item(rec: bytes, idx: int) -> tuple[str, str]:
    pos = 205 + idx * 46
    return _ascii(rec, pos, 10), _str(rec, pos + 10, 36)


def parse_um(rec: bytes) -> HorseMaster:
    if len(rec) < UM_LENGTH:
        rec = rec.ljust(UM_LENGTH, b"\x00")
    elif len(rec) > UM_LENGTH:
        rec = rec[:UM_LENGTH]
    sire_num, sire_name = _pedigree_item(rec, 0)
    dam_sire_num, dam_sire_name = _pedigree_item(rec, 4)
    return HorseMaster(
        record_type=_ascii(rec, 1, 2),
        data_div=_ascii(rec, 3, 1),
        data_created=_ascii(rec, 4, 8),
        blood_register_num=_ascii(rec, 12, 10),
        horse_name=_str(rec, 47, 36),
        sex_code=_ascii(rec, 201, 1),
        breed_code=_ascii(rec, 202, 1),
        sire_breeding_num=sire_num,
        sire_name=sire_name,
        dam_sire_breeding_num=dam_sire_num,
        dam_sire_name=dam_sire_name,
        leg_tendency_code=_ascii(rec, 1593, 4),
    )


def parse_um_file(path: str | Path) -> list[HorseMaster]:
    data = Path(path).read_bytes()
    return [parse_um(rec) for rec in _split_fixed(data, UM_LENGTH)]


def parse_hs(rec: bytes) -> HorseMaster:
    """競走馬市場取引価格(HS)から血統登録番号と父/母の繁殖登録番号を取り出す。"""
    if len(rec) < HS_LENGTH:
        rec = rec.ljust(HS_LENGTH, b"\x00")
    elif len(rec) > HS_LENGTH:
        rec = rec[:HS_LENGTH]
    return HorseMaster(
        record_type=_ascii(rec, 1, 2),
        data_div=_ascii(rec, 3, 1),
        data_created=_ascii(rec, 4, 8),
        blood_register_num=_ascii(rec, 12, 10),
        horse_name="",
        sex_code="",
        breed_code="",
        sire_breeding_num=_ascii(rec, 22, 8),
        sire_name="",
        dam_sire_breeding_num=_ascii(rec, 30, 8),
        dam_sire_name="",
        leg_tendency_code="",
    )


# ================================================================
# Phase 1 (2026-05-13): JV-Link 未活用 dataspec parser
# 仕様書: docs/JV-Data4901.pdf §1 (TK), §18 (HN), §19 (SK), §22 (HC),
#         §27 (WC), §28 (DM), §29 (TM)
# 共通レイアウト (JV-Data 標準):
#   1-2:   record_type
#   3:     data_div
#   4-11:  data_created (yyyymmdd)
# レース紐付きレコードはその後 12-27 に race_id 6 フィールドが続く。
# 馬個体紐付きレコードは 12-21 に blood_register_num が続く。
# ================================================================


@dataclass
class MiningPrediction:
    """DM (タイム型) / TM (対戦型) の per-horse 予想エントリ。"""
    record_type: str       # 'DM' or 'TM'
    data_div: str
    data_created: str
    year: str
    month_day: str
    track_code: str
    kaiji: str
    nichiji: str
    race_num: str
    horse_num: str
    predicted_time: int = 0   # DM: 1/10 秒。TM では 0
    error_plus: int = 0       # DM: 誤差 + 側 (1/10 秒)。TM では 0
    error_minus: int = 0      # DM: 誤差 - 側 (1/10 秒)。TM では 0
    predicted_rank: int = 0   # DM/TM 共通: 1=本命
    score: int = 0            # TM: 対戦評価点 (0-100 等)。DM では 0

    @property
    def race_id(self) -> str:
        return f"{self.year}{self.month_day}_{self.track_code}_{self.kaiji}_{self.nichiji}_{self.race_num}"


def _race_id_fields(rec: bytes) -> tuple[str, str, str, str, str, str, str, str]:
    """JV-Data race-bound レコード共通の 1-27 byte を抽出。"""
    return (
        _ascii(rec, 1, 2),   # record_type
        _ascii(rec, 3, 1),   # data_div
        _ascii(rec, 4, 8),   # data_created
        _ascii(rec, 12, 4),  # year
        _ascii(rec, 16, 4),  # month_day
        _ascii(rec, 20, 2),  # track_code
        _ascii(rec, 22, 2),  # kaiji
        _ascii(rec, 24, 2),  # nichiji
    )


def parse_dm(rec: bytes) -> list[MiningPrediction]:
    """DM (タイム型データマイニング予想) 303 byte → 1 record 内に 18 頭分。

    仕様書 §28 (PDF page 26)。**byte offset は実データで再検証必要**。
    現状は race_id + 各馬の (horse_num, predicted_time, error_+, error_-) を
    保守的に取り出す。スコア欄が無い (= DM はタイム型) ので score=0。
    予測順位 (predicted_rank) は predicted_time の昇順から事後計算。
    """
    if len(rec) < DM_LENGTH:
        rec = rec.ljust(DM_LENGTH, b"\x00")
    elif len(rec) > DM_LENGTH:
        rec = rec[:DM_LENGTH]
    rec_type, data_div, data_created, year, month_day, track_code, kaiji, nichiji = _race_id_fields(rec)
    race_num = _ascii(rec, 26, 2)
    # 28 以降に 18 頭分のエントリ (1 頭 15 byte 仮定: horse_num(2) + time(4) + err+(3) + err-(3) + reserve(3))
    # 18 * 15 = 270 byte (303 - 28 - 5 (CRLF + reserve) = 270 でちょうど合う)
    entries: list[MiningPrediction] = []
    base = 28
    block = 15
    for i in range(18):
        pos = base + i * block
        horse_num = _ascii(rec, pos, 2).strip("\x00 ")
        if not horse_num or horse_num == "00":
            continue
        pred_time = _int(rec, pos + 2, 4)
        err_plus = _int(rec, pos + 6, 3)
        err_minus = _int(rec, pos + 9, 3)
        entries.append(
            MiningPrediction(
                record_type=rec_type,
                data_div=data_div,
                data_created=data_created,
                year=year, month_day=month_day, track_code=track_code,
                kaiji=kaiji, nichiji=nichiji, race_num=race_num,
                horse_num=horse_num,
                predicted_time=pred_time,
                error_plus=err_plus,
                error_minus=err_minus,
            )
        )
    # predicted_time 昇順から rank を計算 (1=最速)。0 は除外して並べる。
    timed = [e for e in entries if e.predicted_time > 0]
    timed.sort(key=lambda e: e.predicted_time)
    for r, e in enumerate(timed, start=1):
        e.predicted_rank = r
    return entries


def parse_tm(rec: bytes) -> list[MiningPrediction]:
    """TM (対戦型データマイニング予想) 141 byte → 1 record 内に 18 頭分。

    仕様書 §29 (PDF page 26)。**byte offset は実データで再検証必要**。
    score (対戦評価点) + rank を per-horse 抽出。
    """
    if len(rec) < TM_LENGTH:
        rec = rec.ljust(TM_LENGTH, b"\x00")
    elif len(rec) > TM_LENGTH:
        rec = rec[:TM_LENGTH]
    rec_type, data_div, data_created, year, month_day, track_code, kaiji, nichiji = _race_id_fields(rec)
    race_num = _ascii(rec, 26, 2)
    # 28 以降に 18 頭分 (1 頭 6 byte 仮定: horse_num(2) + score(3) + reserve(1))
    # 18 * 6 = 108 byte (141 - 28 - 5 = 108)
    entries: list[MiningPrediction] = []
    base = 28
    block = 6
    for i in range(18):
        pos = base + i * block
        horse_num = _ascii(rec, pos, 2).strip("\x00 ")
        if not horse_num or horse_num == "00":
            continue
        score = _int(rec, pos + 2, 3)
        entries.append(
            MiningPrediction(
                record_type=rec_type,
                data_div=data_div,
                data_created=data_created,
                year=year, month_day=month_day, track_code=track_code,
                kaiji=kaiji, nichiji=nichiji, race_num=race_num,
                horse_num=horse_num,
                score=score,
            )
        )
    # score 降順 (= 評価点が高い順) で rank。
    scored = [e for e in entries if e.score > 0]
    scored.sort(key=lambda e: -e.score)
    for r, e in enumerate(scored, start=1):
        e.predicted_rank = r
    return entries


@dataclass
class BreedingHorse:
    """HN (繁殖馬マスタ) 251 byte。"""
    record_type: str
    data_div: str
    data_created: str
    breeding_num: str           # 繁殖登録番号 (10 byte)
    blood_register_num: str     # 血統登録番号 (10 byte、JRA現役なら存在)
    horse_name: str
    sex_code: str
    breed_code: str
    coat_code: str
    birth_year: str
    sire_breeding_num: str
    dam_breeding_num: str


def parse_hn(rec: bytes) -> BreedingHorse:
    """HN (繁殖馬マスタ) parser。仕様書 §18 (PDF page 20)。

    1-2: rec_type / 3: data_div / 4-11: data_created
    12-21: breeding_num / 30-39: blood_register_num / 41-76: horse_name
    197-200: birth_year / 201: sex_code / 202: breed_code / 203-204: coat
    230-239: sire_breeding_num / 240-249: dam_breeding_num
    """
    if len(rec) < HN_LENGTH:
        rec = rec.ljust(HN_LENGTH, b"\x00")
    elif len(rec) > HN_LENGTH:
        rec = rec[:HN_LENGTH]
    return BreedingHorse(
        record_type=_ascii(rec, 1, 2),
        data_div=_ascii(rec, 3, 1),
        data_created=_ascii(rec, 4, 8),
        breeding_num=_ascii(rec, 12, 10),
        blood_register_num=_ascii(rec, 30, 10),
        horse_name=_str(rec, 41, 36),
        sex_code=_ascii(rec, 201, 1),
        breed_code=_ascii(rec, 202, 1),
        coat_code=_ascii(rec, 203, 2),
        birth_year=_ascii(rec, 197, 4),
        sire_breeding_num=_ascii(rec, 230, 10),
        dam_breeding_num=_ascii(rec, 240, 10),
    )


@dataclass
class OffspringMaster:
    """SK (産駒マスタ) 208 byte。3 代血統情報あり。"""
    record_type: str
    data_div: str
    data_created: str
    blood_register_num: str
    birth_year: str
    sex_code: str
    breed_code: str
    coat_code: str
    sire_breeding_num: str
    dam_breeding_num: str
    dam_sire_breeding_num: str


def parse_sk(rec: bytes) -> OffspringMaster:
    """SK (産駒マスタ) parser。仕様書 §19 (PDF page 20)。

    1-2: rec_type / 3: data_div / 4-11: data_created
    12-21: blood_register_num / 22-29: birth_date (yyyymmdd)
    30: sex_code / 31: breed_code / 32-33: coat
    67-: 3代血統 14 codes × 10 bytes (sire, dam, sire_sire, sire_dam,
        dam_sire, dam_dam, sire_sire_sire, ...). 父=index 0, 母=index 1,
        母父=index 4.
    """
    if len(rec) < SK_LENGTH:
        rec = rec.ljust(SK_LENGTH, b"\x00")
    elif len(rec) > SK_LENGTH:
        rec = rec[:SK_LENGTH]
    pedigree_base = 67
    return OffspringMaster(
        record_type=_ascii(rec, 1, 2),
        data_div=_ascii(rec, 3, 1),
        data_created=_ascii(rec, 4, 8),
        blood_register_num=_ascii(rec, 12, 10),
        birth_year=_ascii(rec, 22, 4),
        sex_code=_ascii(rec, 30, 1),
        breed_code=_ascii(rec, 31, 1),
        coat_code=_ascii(rec, 32, 2),
        sire_breeding_num=_ascii(rec, pedigree_base + 0 * 10, 10),
        dam_breeding_num=_ascii(rec, pedigree_base + 1 * 10, 10),
        dam_sire_breeding_num=_ascii(rec, pedigree_base + 4 * 10, 10),
    )


@dataclass
class TrainingTime:
    """HC (坂路) / WC (ウッドチップ) 調教タイム。"""
    record_type: str           # 'HC' or 'WC'
    data_div: str
    data_created: str
    training_date: str         # yyyymmdd
    training_time_str: str     # hhmm
    blood_register_num: str
    training_type: str         # 'slope' / 'wood' (DB 統一)
    course_code: str
    times_total: int           # 全距離タイム (1/10 秒)
    times_last_600m: int = 0
    times_last_400m: int = 0
    times_last_200m: int = 0
    lap_last_300m: int = 0
    rider_code: str = ""


def parse_hc(rec: bytes) -> TrainingTime:
    """HC (坂路調教) 60 byte。仕様書 §22 (PDF page 24)。

    1-2: rec_type / 3: data_div / 4-11: data_created
    12: training_center_div (0:栗東 1:美浦)
    13-20: training_date / 21-24: training_time
    25-34: blood_register_num
    35-38: 4 ハロン total (800M-0M) 1/10 秒
    39-41 / 42-44 / 45-47 / 48-50: lap (800-600 / 600-400 / 400-200 / 200-0)
    """
    if len(rec) < HC_LENGTH:
        rec = rec.ljust(HC_LENGTH, b"\x00")
    elif len(rec) > HC_LENGTH:
        rec = rec[:HC_LENGTH]
    return TrainingTime(
        record_type=_ascii(rec, 1, 2),
        data_div=_ascii(rec, 3, 1),
        data_created=_ascii(rec, 4, 8),
        training_date=_ascii(rec, 13, 8),
        training_time_str=_ascii(rec, 21, 4),
        blood_register_num=_ascii(rec, 25, 10),
        training_type="slope",
        course_code=_ascii(rec, 12, 1),
        times_total=_int(rec, 35, 4),
        times_last_600m=_int(rec, 39, 3),
        times_last_400m=_int(rec, 42, 3),
        times_last_200m=_int(rec, 45, 3),
        lap_last_300m=_int(rec, 48, 3),
    )


def parse_wc(rec: bytes) -> TrainingTime:
    """WC (ウッドチップ調教) 105 byte。仕様書 §27 (PDF page 27)。

    HC と類似構造 + course_code 詳細 + rider_code。
    1-2: rec_type / 3: data_div / 4-11: data_created
    12: training_center_div / 13-20: training_date / 21-24: training_time
    25-34: blood_register_num / 35-36: course_code (W コース種別)
    37-: lap times (8 ハロン構造、HC より長い)
    """
    if len(rec) < WC_LENGTH:
        rec = rec.ljust(WC_LENGTH, b"\x00")
    elif len(rec) > WC_LENGTH:
        rec = rec[:WC_LENGTH]
    return TrainingTime(
        record_type=_ascii(rec, 1, 2),
        data_div=_ascii(rec, 3, 1),
        data_created=_ascii(rec, 4, 8),
        training_date=_ascii(rec, 13, 8),
        training_time_str=_ascii(rec, 21, 4),
        blood_register_num=_ascii(rec, 25, 10),
        training_type="wood",
        course_code=_ascii(rec, 35, 2),
        times_total=_int(rec, 37, 4),
        times_last_600m=_int(rec, 41, 3),
        times_last_400m=_int(rec, 44, 3),
        times_last_200m=_int(rec, 47, 3),
        lap_last_300m=_int(rec, 50, 3),
    )


@dataclass
class SpecialEntry:
    """TK (特別登録馬) per-horse エントリ。1 レース 1 record に最大 300 頭。"""
    record_type: str
    data_div: str
    data_created: str
    year: str
    month_day: str
    track_code: str
    kaiji: str
    nichiji: str
    race_num: str
    blood_register_num: str
    entry_priority: int
    burden_weight: int     # 0.1kg
    jockey_code: str
    east_west_code: str


def parse_tk(rec: bytes) -> list[SpecialEntry]:
    """TK (特別登録馬) 21657 byte。仕様書 §1 (PDF page 10)。

    1-27: race_id 共通エリア / 28: weekday_code / 29-32: special_race_num
    ... (race-level fields) ...
    656-: <登録馬情報> 300 entries × 70 bytes each。
    1 entry のレイアウト (1-indexed within entry):
      1-3: 連番 / 4-13: blood_register_num / 14-49: horse_name (36 byte)
      50-51: horse_symbol / 52: sex / 53: jockey_apprentice
      54-58: jockey_code / 59-66: jockey_short_name
      67-69: burden_weight (0.1kg) / 70: east_west_code
    """
    if len(rec) < TK_LENGTH:
        rec = rec.ljust(TK_LENGTH, b"\x00")
    elif len(rec) > TK_LENGTH:
        rec = rec[:TK_LENGTH]
    rec_type, data_div, data_created, year, month_day, track_code, kaiji, nichiji = _race_id_fields(rec)
    race_num = _ascii(rec, 26, 2)
    entries: list[SpecialEntry] = []
    base = 656
    block = 70
    for i in range(300):
        pos = base + i * block
        priority = _int(rec, pos, 3)
        blood_num = _ascii(rec, pos + 3, 10).strip("\x00 ")
        if not blood_num or blood_num.strip("0") == "":
            # 空きスロット (全0 or NUL) は登録なし
            continue
        entries.append(
            SpecialEntry(
                record_type=rec_type,
                data_div=data_div,
                data_created=data_created,
                year=year, month_day=month_day, track_code=track_code,
                kaiji=kaiji, nichiji=nichiji, race_num=race_num,
                blood_register_num=blood_num,
                entry_priority=priority,
                burden_weight=_int(rec, pos + 66, 3),
                jockey_code=_ascii(rec, pos + 53, 5),
                east_west_code=_ascii(rec, pos + 69, 1),
            )
        )
    return entries
