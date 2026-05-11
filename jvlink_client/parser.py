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
