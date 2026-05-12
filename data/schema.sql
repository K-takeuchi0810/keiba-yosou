-- 競馬予想アプリ ローカル DB スキーマ
-- JV-Data RA / SE をベースに、追加 dataspec 対応時にテーブルを足していく

-- レース詳細（RA レコード）
CREATE TABLE IF NOT EXISTS races (
    race_year         TEXT NOT NULL,
    race_month_day    TEXT NOT NULL,
    track_code        TEXT NOT NULL,
    kaiji             TEXT NOT NULL,
    nichiji           TEXT NOT NULL,
    race_num          TEXT NOT NULL,
    data_div          TEXT,
    data_created      TEXT,
    weekday_code      TEXT,
    special_race_num  TEXT,
    race_name         TEXT,
    race_subtitle     TEXT,
    race_paren        TEXT,
    race_short10      TEXT,
    race_short6       TEXT,
    grade_code        TEXT,
    race_type_code    TEXT,
    race_symbol_code  TEXT,
    weight_type_code  TEXT,
    distance          INTEGER,
    track_type_code   TEXT,
    course_div        TEXT,
    start_time        TEXT,
    registered_count  INTEGER,
    starter_count     INTEGER,
    weather_code      TEXT,
    turf_condition    TEXT,
    dirt_condition    TEXT,
    PRIMARY KEY (race_year, race_month_day, track_code, kaiji, nichiji, race_num)
);

CREATE INDEX IF NOT EXISTS idx_races_date
    ON races (race_year, race_month_day);

-- 馬毎レース情報（SE レコード）
CREATE TABLE IF NOT EXISTS horse_races (
    race_year                TEXT NOT NULL,
    race_month_day           TEXT NOT NULL,
    track_code               TEXT NOT NULL,
    kaiji                    TEXT NOT NULL,
    nichiji                  TEXT NOT NULL,
    race_num                 TEXT NOT NULL,
    horse_num                TEXT NOT NULL,
    data_div                 TEXT,
    data_created             TEXT,
    waku_num                 TEXT,
    blood_register_num       TEXT,
    horse_name               TEXT,
    horse_symbol_code        TEXT,
    sex_code                 TEXT,
    breed_code               TEXT,
    coat_code                TEXT,
    age                      INTEGER,
    east_west_code           TEXT,
    trainer_code             TEXT,
    trainer_short_name       TEXT,
    owner_code               TEXT,
    owner_name               TEXT,
    burden_weight            INTEGER,
    blinker                  TEXT,
    jockey_code              TEXT,
    jockey_short_name        TEXT,
    jockey_apprentice_code   TEXT,
    horse_weight             TEXT,
    weight_change_sign       TEXT,
    weight_change_diff       TEXT,
    abnormal_code            TEXT,
    finish_order             INTEGER,
    confirmed_order          INTEGER,
    same_finish              TEXT,
    finish_time              INTEGER,
    win_odds                 INTEGER,
    win_popularity           INTEGER,
    odds_fetched_at          TEXT,
    odds_dataspec            TEXT,
    final_3f                 INTEGER,
    mining_time              INTEGER,
    mining_predicted_order   INTEGER,
    leg_quality_code         TEXT,
    PRIMARY KEY (race_year, race_month_day, track_code, kaiji, nichiji, race_num, horse_num)
);

CREATE INDEX IF NOT EXISTS idx_horse_races_horse
    ON horse_races (blood_register_num);
CREATE INDEX IF NOT EXISTS idx_horse_races_jockey
    ON horse_races (jockey_code);
CREATE INDEX IF NOT EXISTS idx_horse_races_trainer
    ON horse_races (trainer_code);
CREATE INDEX IF NOT EXISTS idx_horse_races_date
    ON horse_races (race_year, race_month_day);
CREATE INDEX IF NOT EXISTS idx_horse_races_blood_datekey
    ON horse_races (blood_register_num, (race_year || race_month_day) DESC)
    WHERE confirmed_order > 0;
CREATE INDEX IF NOT EXISTS idx_horse_races_jockey_datekey
    ON horse_races (jockey_code, (race_year || race_month_day) DESC)
    WHERE confirmed_order > 0;
CREATE INDEX IF NOT EXISTS idx_horse_races_trainer_datekey
    ON horse_races (trainer_code, (race_year || race_month_day) DESC)
    WHERE confirmed_order > 0;

-- 払戻（HR レコード）。今は単・複・馬連・3連複の 4 券種のみ。
-- 馬単・ワイド・3連単・枠連は parser/Payout 拡張時に列追加する。
CREATE TABLE IF NOT EXISTS payouts (
    race_year         TEXT NOT NULL,
    race_month_day    TEXT NOT NULL,
    track_code        TEXT NOT NULL,
    kaiji             TEXT NOT NULL,
    nichiji           TEXT NOT NULL,
    race_num          TEXT NOT NULL,
    data_div          TEXT,
    data_created      TEXT,
    registered_count  INTEGER,
    starter_count     INTEGER,
    -- 単勝 (3 同着)
    tan_horse_num1    TEXT, tan_payout1    INTEGER, tan_pop1    INTEGER,
    tan_horse_num2    TEXT, tan_payout2    INTEGER, tan_pop2    INTEGER,
    tan_horse_num3    TEXT, tan_payout3    INTEGER, tan_pop3    INTEGER,
    -- 複勝 (5 同着)
    fuku_horse_num1   TEXT, fuku_payout1   INTEGER, fuku_pop1   INTEGER,
    fuku_horse_num2   TEXT, fuku_payout2   INTEGER, fuku_pop2   INTEGER,
    fuku_horse_num3   TEXT, fuku_payout3   INTEGER, fuku_pop3   INTEGER,
    fuku_horse_num4   TEXT, fuku_payout4   INTEGER, fuku_pop4   INTEGER,
    fuku_horse_num5   TEXT, fuku_payout5   INTEGER, fuku_pop5   INTEGER,
    -- 馬連 (3 同着)
    umaren_combo1     TEXT, umaren_payout1 INTEGER, umaren_pop1 INTEGER,
    umaren_combo2     TEXT, umaren_payout2 INTEGER, umaren_pop2 INTEGER,
    umaren_combo3     TEXT, umaren_payout3 INTEGER, umaren_pop3 INTEGER,
    -- 3 連複 (3 同着)
    sanrenpuku_combo1 TEXT, sanrenpuku_payout1 INTEGER, sanrenpuku_pop1 INTEGER,
    sanrenpuku_combo2 TEXT, sanrenpuku_payout2 INTEGER, sanrenpuku_pop2 INTEGER,
    sanrenpuku_combo3 TEXT, sanrenpuku_payout3 INTEGER, sanrenpuku_pop3 INTEGER,
    PRIMARY KEY (race_year, race_month_day, track_code, kaiji, nichiji, race_num)
);

CREATE INDEX IF NOT EXISTS idx_payouts_date
    ON payouts (race_year, race_month_day);

CREATE TABLE IF NOT EXISTS horse_masters (
    blood_register_num     TEXT PRIMARY KEY,
    data_div               TEXT,
    data_created           TEXT,
    horse_name             TEXT,
    sex_code               TEXT,
    breed_code             TEXT,
    sire_breeding_num      TEXT,
    sire_name              TEXT,
    dam_sire_breeding_num  TEXT,
    dam_sire_name          TEXT,
    leg_tendency_code      TEXT
);

CREATE INDEX IF NOT EXISTS idx_horse_masters_sire
    ON horse_masters (sire_breeding_num);

CREATE INDEX IF NOT EXISTS idx_horse_masters_dam_sire
    ON horse_masters (dam_sire_breeding_num);

-- どのファイルをいつ取り込んだかの記録（重複取り込み回避）
CREATE TABLE IF NOT EXISTS ingested_files (
    filename       TEXT PRIMARY KEY,
    dataspec       TEXT NOT NULL,
    record_count   INTEGER,
    ingested_at    TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ========================================================================
-- Phase 1 (2026-05-13): JV-Link 未活用 dataspec 取り込み用テーブル
-- 5 dataspec: MING (DM/TM) / BLOD (HN, SK) / SLOP (HC) / WOOD (WC) / TOKU (TK)
-- ========================================================================

-- JRA-VAN マイニング予想 (DM=タイム型 / TM=対戦型)
CREATE TABLE IF NOT EXISTS mining_predictions (
    race_year       TEXT NOT NULL,
    race_month_day  TEXT NOT NULL,
    track_code      TEXT NOT NULL,
    kaiji           TEXT NOT NULL,
    nichiji         TEXT NOT NULL,
    race_num        TEXT NOT NULL,
    horse_num       TEXT NOT NULL,
    record_type     TEXT NOT NULL,   -- 'DM' or 'TM'
    data_div        TEXT,
    data_created    TEXT,
    predicted_time  INTEGER,         -- DM: 1/10 秒
    error_plus      INTEGER,         -- DM: 誤差 + 側 (1/10 秒)
    error_minus     INTEGER,         -- DM: 誤差 - 側 (1/10 秒)
    predicted_rank  INTEGER,         -- 推定順位 (1=best)
    score           INTEGER,         -- TM: 対戦評価点 (0-100 等)
    PRIMARY KEY (race_year, race_month_day, track_code, kaiji, nichiji, race_num, horse_num, record_type)
);
CREATE INDEX IF NOT EXISTS idx_mining_race
    ON mining_predictions (race_year, race_month_day, track_code, kaiji, nichiji, race_num);

-- 繁殖馬マスタ (HN レコード)
CREATE TABLE IF NOT EXISTS breeding_horses (
    breeding_num    TEXT PRIMARY KEY,
    data_div        TEXT,
    data_created    TEXT,
    horse_name      TEXT,
    blood_register_num TEXT,
    sex_code        TEXT,
    breed_code      TEXT,
    coat_code       TEXT,
    birth_year      TEXT,
    sire_breeding_num    TEXT,
    sire_name            TEXT,
    dam_breeding_num     TEXT,
    dam_name             TEXT,
    dam_sire_breeding_num TEXT,
    dam_sire_name        TEXT
);

-- 産駒マスタ (SK レコード)
CREATE TABLE IF NOT EXISTS offspring_master (
    blood_register_num   TEXT PRIMARY KEY,
    data_div             TEXT,
    data_created         TEXT,
    birth_year           TEXT,
    sex_code             TEXT,
    breed_code           TEXT,
    coat_code            TEXT,
    sire_breeding_num    TEXT,
    sire_name            TEXT,
    dam_breeding_num     TEXT,
    dam_name             TEXT,
    dam_sire_breeding_num TEXT,
    dam_sire_name        TEXT
);
CREATE INDEX IF NOT EXISTS idx_offspring_sire
    ON offspring_master (sire_breeding_num);
CREATE INDEX IF NOT EXISTS idx_offspring_dam_sire
    ON offspring_master (dam_sire_breeding_num);

-- 調教タイム (HC=坂路 / WC=ウッドチップ)
CREATE TABLE IF NOT EXISTS training_times (
    blood_register_num   TEXT NOT NULL,
    training_date        TEXT NOT NULL,   -- YYYYMMDD
    training_time_str    TEXT,            -- HHMM
    training_type        TEXT NOT NULL,   -- 'slope' (HC) / 'wood' (WC)
    course_code          TEXT,
    times_total          INTEGER,         -- 全距離タイム (1/10 秒)
    times_last_600m      INTEGER,
    times_last_400m      INTEGER,
    times_last_200m      INTEGER,
    lap_last_300m        INTEGER,         -- ラスト 1F (1/10 秒)
    rider_code           TEXT,
    PRIMARY KEY (blood_register_num, training_date, training_type, course_code)
);
CREATE INDEX IF NOT EXISTS idx_training_blood_date
    ON training_times (blood_register_num, training_date DESC);

-- 特別登録馬 (TK)
CREATE TABLE IF NOT EXISTS special_entries (
    race_year         TEXT NOT NULL,
    race_month_day    TEXT NOT NULL,
    track_code        TEXT NOT NULL,
    kaiji             TEXT NOT NULL,
    nichiji           TEXT NOT NULL,
    race_num          TEXT NOT NULL,
    blood_register_num TEXT NOT NULL,
    data_div          TEXT,
    data_created      TEXT,
    entry_priority    INTEGER,
    burden_weight     INTEGER,
    jockey_code       TEXT,
    east_west_code    TEXT,
    trainer_code      TEXT,
    PRIMARY KEY (race_year, race_month_day, track_code, kaiji, nichiji, race_num, blood_register_num)
);
CREATE INDEX IF NOT EXISTS idx_special_race
    ON special_entries (race_year, race_month_day, track_code, kaiji, nichiji, race_num);
