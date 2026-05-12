"""ルールベース予想ロジック。

シグナル:
- 直近 3 走の平均着順 / 最高着順
- 同種トラック（芝/ダート）勝利数
- 同距離（±100m）出走数・トップ 3 回数
- 重賞経験
- 騎手の直近勝率
- 調教師の直近勝率
- マイニング予想（あれば優先）
- 単勝人気（オッズ確定時）
- 異常区分（取消・除外で減点）

スコア = baseline 50 + 上記の重み付き加減算。同点なら馬番昇順で並べる。
"""

from __future__ import annotations

import logging
import os
import math
import json
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from .features import compute_features

logger = logging.getLogger(__name__)

MARKS = ["◎", "○", "▲", "△", "☆"]

# 環境変数で OP/重賞専用ロジック (Phase 1 / v2-grade) の有効/無効を切替可能にし、
# v1 (旧重み) との A/B 比較ができるようにする。デフォルトは有効 (=1)。
V2_GRADE_ENABLED = os.environ.get("V2_GRADE", "1") != "0"
# Phase 2-A: 長距離 (>2200m) の距離適性精緻化を有効化するかどうか。
# 同距離バケット top3 / 脚質 (逃・先) ボーナス。デフォルトは有効。
V2_DIST_ENABLED = os.environ.get("V2_DIST", "1") != "0"
CALIBRATOR_PATH = Path(__file__).resolve().parent / "calibrator.json"
WEIGHTS_PATH = Path(__file__).resolve().parent / "weights.json"
_CALIBRATOR_CACHE: tuple[float, dict] | None = None
_WEIGHTS_CACHE: tuple[float, dict] | None = None


def _weights() -> dict:
    global _WEIGHTS_CACHE
    if not WEIGHTS_PATH.exists():
        return {}
    mtime = WEIGHTS_PATH.stat().st_mtime
    if _WEIGHTS_CACHE and _WEIGHTS_CACHE[0] == mtime:
        return _WEIGHTS_CACHE[1]
    data = json.loads(WEIGHTS_PATH.read_text(encoding="utf-8"))
    _WEIGHTS_CACHE = (mtime, data)
    return data


def _w(path: str, default: float) -> float:
    cur = _weights()
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return default
        cur = cur[part]
    try:
        return float(cur)
    except (TypeError, ValueError):
        return default


@dataclass
class Prediction:
    horse_num: str
    score: float
    rank: int
    mark: str
    rationale: str
    confidence: str = "標準"
    confidence_gap: float = 0.0
    value_score: float = 0.0
    win_probability: float = 0.0
    fair_odds: float = 0.0
    expected_value: float = 0.0
    kelly_fraction: float = 0.0
    feature_warnings: list[str] = field(default_factory=list)


def _score_one(horse: dict, feat: dict) -> tuple[float, list[str]]:
    score = 50.0
    reasons: list[str] = []
    past_count = feat.get("past_count", 0)
    current_level = feat.get("current_race_level", 0) or 0
    blood_weight = 1.35 if past_count <= 2 else 1.0

    # 直近 3 走平均着順
    # 重賞では「平均着順」より「内容 (着差・相手関係)」が重要なので、
    # current_level >= 5 (OP/重賞) では重みを 0.6 倍に下げて影響を抑える。
    avg = feat.get("recent_avg_finish")
    if avg is not None:
        avg_weight = 0.6 if (V2_GRADE_ENABLED and current_level >= 5) else 1.0
        if avg <= 2.0:
            score += _w("recent_avg.excellent", 25) * avg_weight
            reasons.append(f"直近3走平均{avg:.1f}着")
        elif avg <= 4.0:
            score += _w("recent_avg.good", 12) * avg_weight
            reasons.append(f"直近3走平均{avg:.1f}着")
        elif avg <= 6.0:
            score += _w("recent_avg.ok", 4) * avg_weight
            reasons.append(f"直近3走平均{avg:.1f}着")
        elif avg <= 10.0:
            score += _w("recent_avg.poor", -4)
            reasons.append(f"直近平均{avg:.1f}着")
        else:
            score += _w("recent_avg.bad", -12)
            reasons.append(f"直近平均{avg:.1f}着")

    finish_rate = feat.get("recent_avg_finish_rate")
    if finish_rate is not None:
        if finish_rate <= 0.18:
            score += _w("finish_rate.top", 6)
            reasons.append(f"頭数補正上位{finish_rate * 100:.0f}%")
        elif avg is not None and avg <= 4.0 and finish_rate >= 0.45:
            score += _w("finish_rate.small_field_penalty", -6)
            reasons.append(f"少頭数好走補正{finish_rate * 100:.0f}%")
        elif avg is not None and avg >= 7.0 and finish_rate <= 0.35:
            score += _w("finish_rate.large_field_credit", 3)
            reasons.append(f"多頭数健闘{finish_rate * 100:.0f}%")

    # 直近最高着順（1着あれば強気）
    best = feat.get("recent_best_finish")
    if best == 1:
        score += _w("recent_best_win", 8)
        reasons.append("直近で1着あり")

    # 直近 3 走由来 (連続好走 / トレンド)
    recent_top3 = feat.get("recent_top3_count", 0) or 0
    recent_wins = feat.get("recent_win_count", 0) or 0
    if recent_wins >= 2:
        score += _w("recent_form.wins_2plus_bonus", 4)
        reasons.append(f"直近勝利{recent_wins}回")
    elif recent_top3 >= 2:
        score += _w("recent_form.top3_2plus_bonus", 3)
        reasons.append(f"直近3着内{recent_top3}回")
    trend = feat.get("recent_trend_delta")
    if trend is not None:
        if trend <= -3:
            score += _w("recent_form.trend_up_bonus", 2)
            reasons.append("近走上昇")
        elif trend >= 4:
            score += _w("recent_form.trend_down_penalty", -2)
            reasons.append("近走下降")

    # 同種トラック (芝/ダート) 実績
    stt_top3 = feat.get("same_track_type_top3", 0)
    stt_wins = feat.get("same_track_type_wins", 0)
    if stt_wins >= 1:
        score += min(stt_wins, 3) * _w("track_type.win_per_count", 5)
        reasons.append(f"同種T{stt_wins}勝")
    elif stt_top3 >= 2:
        score += _w("track_type.top3_count_threshold", 4)
        reasons.append(f"同種T複勝{stt_top3}回")

    # 同距離適性 (±100m)
    sd_runs = feat.get("same_distance_runs", 0)
    sd_top3 = feat.get("same_distance_top3", 0)
    if sd_top3 >= 1:
        score += sd_top3 * _w("distance.top3_per_count", 4)
        reasons.append(f"同距離複勝{sd_top3}回")
    elif sd_runs >= 3:
        score += _w("distance.runs_threshold", 3)
        reasons.append(f"同距離{sd_runs}走")

    # 長距離適性 (Phase 2-A): 距離バケットで同一の実績は ±100m より広く拾えるので、
    # 2201m+ (long バケット) のレースで「適性ありを強く評価/未経験を強く減点」する。
    if V2_DIST_ENABLED and feat.get("current_bucket") == "long":
        sb_runs = feat.get("same_bucket_runs", 0) or 0
        sb_top3 = feat.get("same_bucket_top3", 0) or 0
        sb_wins = feat.get("same_bucket_wins", 0) or 0
        if sb_wins >= 1:
            score += min(sb_wins, 2) * _w("distance.long_win_per_count", 6)
            reasons.append(f"長距離{sb_wins}勝")
        elif sb_top3 >= 2:
            score += _w("distance.long_top3_count", 8)
            reasons.append(f"長距離複勝{sb_top3}回")
        elif sb_top3 == 1:
            score += _w("distance.long_top3_single", 4)
            reasons.append("長距離複勝あり")
        elif sb_runs == 0 and feat.get("past_count", 0) >= 3:
            score += _w("distance.long_unproven_penalty", -6)
            reasons.append("長距離未経験")
        elif sb_runs >= 3 and sb_top3 == 0:
            score += _w("distance.long_poor_penalty", -5)
            reasons.append(f"長距離不振{sb_runs}走")
        # 脚質: 長距離は前残りが効きやすい (1=逃, 2=先)
        leg = feat.get("leg_code") or ""
        if leg in ("1", "2"):
            score += _w("distance.long_front_leg_bonus", 3)
            note = "長距離向き脚質"
            if not feat.get("leg_quality_available") and feat.get("estimated_leg_code"):
                note += f"(推定{feat.get('estimated_leg_samples', 0)}走)"
            reasons.append(note)

    # 同競馬場・同馬場・距離帯のコース適性
    sc_runs = feat.get("same_course_runs", 0)
    sc_wins = feat.get("same_course_wins", 0)
    sc_top3 = feat.get("same_course_top3", 0)
    scd_runs = feat.get("same_course_distance_runs", 0)
    scd_top3 = feat.get("same_course_distance_top3", 0)
    if sc_wins >= 1:
        score += min(sc_wins, 2) * _w("course.win_per_count", 4)
        reasons.append(f"同場{sc_wins}勝")
    elif sc_top3 >= 2:
        score += _w("course.top3_count_threshold", 5)
        reasons.append(f"同場複勝{sc_top3}回")
    elif sc_runs >= 3 and sc_top3 == 0:
        score += _w("course.poor_penalty", -3)
        reasons.append(f"同場不振{sc_runs}走")
    if scd_top3 >= 1:
        score += min(scd_top3, 2) * _w("course.course_distance_top3_per_count", 3)
        reasons.append(f"同場距離帯複勝{scd_top3}回")
    elif scd_runs >= 3:
        score += _w("course.course_distance_poor_penalty", -2)
        reasons.append(f"同場距離帯不振{scd_runs}走")

    # 重賞経験
    if feat.get("had_grade_run"):
        score += _w("had_grade_run_bonus", 5)
        reasons.append("重賞経験あり")

    class_rise = feat.get("class_rise_points", 0) or 0
    class_drop = feat.get("class_drop_points", 0) or 0
    best_top3_level = feat.get("best_top3_race_level", 0) or 0
    if class_rise >= 2:
        score += _w("class_level.rise_penalty", -6)
        reasons.append(f"格上挑戦+{class_rise}")
    elif class_rise >= 1 and current_level >= 5:
        score += _w("class_level.rise_minor_penalty", -3)
        reasons.append("上級条件で実績薄")
    elif class_drop >= 2:
        score += _w("class_level.drop_bonus", 4)
        reasons.append("相手関係緩和")
    if current_level >= 7 and best_top3_level and best_top3_level <= current_level - 2:
        score += _w("class_level.graded_unproven_penalty", -8)
    elif current_level >= 5 and best_top3_level and best_top3_level <= current_level - 2:
        score += _w("class_level.elevated_unproven_penalty", -3)
    if current_level >= 5:
        class_runs = feat.get("class_level_runs", 0) or 0
        class_wins = feat.get("class_level_wins", 0) or 0
        class_top3 = feat.get("class_level_top3", 0) or 0
        class_condition_top3 = feat.get("class_condition_top3", 0) or 0
        if class_wins:
            win_bonus = (
                _w("class_level.graded_win_bonus", 8)
                if current_level >= 7
                else _w("class_level.non_graded_win_bonus", 5)
            )
            score += min(class_wins, 2) * win_bonus
            reasons.append(f"同格以上{class_wins}勝")
        elif class_top3 >= 2:
            score += _w("class_level.top3_threshold", 7)
            reasons.append(f"同格以上複勝{class_top3}回")
        elif class_top3 == 1:
            score += _w("class_level.top3_single", 4)
            reasons.append("同格以上複勝あり")
        elif class_runs >= 3:
            score += (
                _w("class_level.graded_runs_penalty", -8)
                if current_level >= 7
                else _w("class_level.non_graded_runs_penalty", -5)
            )
            reasons.append("同格以上実績不足")
        if class_condition_top3:
            condition_bonus = (
                _w("class_level.graded_condition_bonus", 4)
                if current_level >= 7
                else _w("class_level.non_graded_condition_bonus", 3)
            )
            score += min(class_condition_top3, 2) * condition_bonus
            reasons.append(f"同格条件複勝{class_condition_top3}回")

        # 同格以上の「接戦敗」: 着外でも勝ち馬から +0.5 秒以内なら地力評価。
        if V2_GRADE_ENABLED:
            close_loss = feat.get("high_grade_close_loss", 0) or 0
            midfield_close = feat.get("high_grade_midfield_close", 0) or 0
            if close_loss >= 1:
                base_bonus = (
                    _w("class_level.close_loss_graded_bonus", 5)
                    if current_level >= 7
                    else _w("class_level.close_loss_non_graded_bonus", 3)
                )
                score += min(close_loss, 3) * base_bonus
                reasons.append(f"同格以上接戦敗{close_loss}回")
            if midfield_close >= 1:
                score += min(midfield_close, 2) * _w("class_level.midfield_close_bonus", 2)
                reasons.append(f"同格以上中位コンマ差{midfield_close}回")

        if V2_GRADE_ENABLED and 5 <= current_level < 7 and class_top3 == 0 and (feat.get("high_grade_close_loss", 0) or 0) == 0 and (feat.get("high_grade_midfield_close", 0) or 0) == 0:
            score -= _w("risk.op_unproven_score_penalty", 4)
            reasons.append("OP risk")
    days_since_last = feat.get("days_since_last")
    if days_since_last is not None:
        if days_since_last >= 100:
            score += _w("condition.rest_long_penalty", -6)
            reasons.append(f"休み明け{days_since_last}日")
        elif days_since_last >= 70:
            score += _w("condition.rest_medium_penalty", -3)
            reasons.append(f"間隔長め{days_since_last}日")

    last_finish = feat.get("last_finish")
    if last_finish is not None:
        if last_finish >= 12:
            score += _w("condition.last_finish_bad_penalty", -5)
            reasons.append(f"前走大敗{last_finish}着")
        elif last_finish >= 8:
            score += _w("condition.last_finish_poor_penalty", -3)
            reasons.append(f"前走{last_finish}着")

    burden_delta = feat.get("burden_delta")
    if burden_delta is not None and burden_delta >= 20:
        score += _w("burden.increase_penalty", -3)
        reasons.append(f"斤量増{burden_delta / 10:.1f}kg")
    elif burden_delta is not None and burden_delta <= -20:
        score += _w("burden.decrease_bonus", 2)
        reasons.append(f"斤量減{abs(burden_delta) / 10:.1f}kg")

    sign = (horse.get("weight_change_sign") or "").strip()
    diff_text = (horse.get("weight_change_diff") or "").strip()
    if sign == "-" and diff_text.isdigit():
        weight_drop = int(diff_text)
        if weight_drop >= 14:
            score += _w("condition.weight_drop_heavy_penalty", -5)
            reasons.append(f"馬体減-{weight_drop}kg")
        elif weight_drop >= 10:
            score += _w("condition.weight_drop_moderate_penalty", -3)
            reasons.append(f"馬体減-{weight_drop}kg")

    # 騎手勝率（直近 100 騎乗）
    jr = feat.get("jockey_win_rate")
    jn = feat.get("jockey_rides", 0)
    if jr is not None and jn >= 30:
        if jr >= 0.20:
            score += _w("jockey.elite_bonus", 12)
            reasons.append(f"騎手勝率{jr * 100:.0f}%")
        elif jr >= 0.12:
            score += _w("jockey.good_bonus", 6)
            reasons.append(f"騎手勝率{jr * 100:.0f}%")
        elif jr < 0.04:
            score += _w("jockey.weak_penalty", -4)
            reasons.append(f"騎手勝率{jr * 100:.0f}%")

    # 調教師勝率
    tr = feat.get("trainer_win_rate")
    tn = feat.get("trainer_runs", 0)
    if tr is not None and tn >= 30:
        if tr >= 0.18:
            score += _w("trainer.elite_bonus", 6)
            reasons.append(f"調教師勝率{tr * 100:.0f}%")
        elif tr >= 0.10:
            score += _w("trainer.good_bonus", 2)
            reasons.append(f"調教師勝率{tr * 100:.0f}%")

    # マイニング予想（直前のみ入る。最強シグナル）
    # ただし高重賞 (G1/G2/G3 = level>=7) はマイニングと結果の相関が下がる傾向
    # (相手関係や枠順・展開・血統が支配的) なので、重みを 0.8 倍に下げる。
    mp = horse.get("mining_predicted_order") or 0
    if 1 <= mp <= 18:
        mining_weight = _w("mining.graded_multiplier", 0.8) if (V2_GRADE_ENABLED and current_level >= 7) else 1.0
        score += max(_w("mining.base", 20) - mp * _w("mining.per_rank", 1.2), 0) * mining_weight
        reasons.append(f"マイニング{mp}位")

    leg = feat.get("leg_code") or ""
    front_count = feat.get("front_runner_count", 0) or 0
    same_leg_rivals = feat.get("same_leg_rivals", 0) or 0
    if leg in ("1", "2"):
        if front_count >= 5:
            score += _w("pace.front_conflict", -5)
            reasons.append(f"先行競合{front_count}頭")
        elif front_count <= 2:
            score += _w("pace.front_favor", 4)
            reasons.append("前残り展開")
    elif leg in ("3", "4"):
        if front_count >= 5:
            score += _w("pace.closer_favor", 3)
            reasons.append("差し向き展開")
        elif front_count <= 1:
            score += _w("pace.closer_wait", -3)
            reasons.append("展開待ち")
    if same_leg_rivals >= 5:
        score += _w("pace.same_leg_many", -2)
        reasons.append("同脚質過多")
    if leg and not feat.get("leg_quality_available") and feat.get("estimated_leg_code"):
        reasons.append(f"脚質推定{leg}({feat.get('estimated_leg_samples', 0)}走)")

    # 異常区分（取消・除外）。これは「数値ペナルティ」ではなく
    # 「最下位確定マーカー」(他のシグナル合計を確実に上回る大値) なので、
    # weights.json の調整対象外。意図的に直書き。
    abnormal = (horse.get("abnormal_code") or "").strip()
    if abnormal and abnormal != "0":
        score -= 1000
        reasons.append(f"異常区分{abnormal}")

    day_bias = feat.get("same_day_bias_score", 0) or 0
    if day_bias:
        score += day_bias
        reasons.append(feat.get("same_day_bias_note") or "当日脚質傾向")
    gate_bias = feat.get("same_day_gate_bias_score", 0) or 0
    if gate_bias:
        score += gate_bias
        reasons.append(feat.get("same_day_gate_bias_note") or "当日枠傾向")
    if not feat.get("same_day_bias_available"):
        reasons.append("当日傾向: データなし")

    going = feat.get("current_going") or ""
    if going in ("2", "3", "4"):
        sg_runs = feat.get("same_going_runs", 0) or 0
        sg_top3 = feat.get("same_going_top3", 0) or 0
        if sg_top3 >= 2:
            score += _w("going.good_bonus", 5)
            reasons.append(f"道悪実績{sg_top3}/{sg_runs}")
        elif sg_runs >= 3 and sg_top3 == 0:
            score += _w("going.poor_penalty", -4)
            reasons.append(f"道悪不振{sg_runs}走")

    best_3f = feat.get("best_final_3f")
    avg_3f = feat.get("avg_final_3f")
    # 短距離 (sprint <= 1400m) は上がり脚 / トップスピードの依存度が高い。
    # 直近 2 日の backtest で sprint 回収率 21.6% (25 戦 2 勝) と劣勢のため、
    # sprint バケットで上がり 3F 系の評価を厚くする。
    is_sprint = feat.get("current_bucket") == "sprint"
    sprint_mul = _w("final3f.sprint_multiplier", 1.5) if is_sprint else 1.0
    if best_3f:
        if best_3f <= 345:
            score += _w("final3f.elite", 4) * sprint_mul
            reasons.append(f"上がり最速級{best_3f / 10:.1f}")
        elif best_3f <= 360:
            score += _w("final3f.good", 2) * sprint_mul
            reasons.append(f"上がり良好{best_3f / 10:.1f}")
    if is_sprint and (feat.get("same_distance_top3", 0) or 0) == 0 and (not best_3f or best_3f > 360):
        score -= _w("risk.sprint_unproven_score_penalty", 3)
        reasons.append("sprint risk")
    if avg_3f and avg_3f >= 390 and feat.get("past_count", 0) >= 3:
        score += _w("time_signal.best_per100m_penalty", -3)
        reasons.append(f"上がり鈍い{avg_3f / 10:.1f}")

    best_time = feat.get("best_time_per_100m")
    if best_time:
        if best_time <= 5.9:
            score += _w("time_signal.best_per100m_bonus", 3)
            reasons.append("持ち時計優秀")
        elif best_time >= 6.8 and feat.get("past_count", 0) >= 3:
            score += _w("time_signal.best_per100m_penalty", -2)
            reasons.append("持ち時計平凡")
    rel_time = feat.get("best_relative_time_diff")
    if rel_time is not None:
        if rel_time <= 2:
            score += _w("time_signal.relative_time_excellent", 4)
            reasons.append("相対時計優秀")
        elif rel_time >= 12 and feat.get("past_count", 0) >= 3:
            score += _w("time_signal.relative_time_poor", -3)
            reasons.append("相対時計不足")
    final3_rank = feat.get("best_final_3f_rank")
    if final3_rank is not None:
        if final3_rank == 1:
            score += _w("time_signal.final3f_rank1", 4)
            reasons.append("上がり1位経験")
        elif final3_rank <= 3:
            score += _w("time_signal.final3f_rank2to3", 2)
            reasons.append(f"上がり{final3_rank}位経験")

    sr = feat.get("sire_surface_top3_rate")
    sn = feat.get("sire_surface_samples", 0)
    if sr is not None and sn >= 30:
        if sr >= 0.38:
            score += _w("bloodline.sire_surface_strong", 5) * blood_weight
            reasons.append(f"父系同馬場複勝{sr * 100:.0f}%")
        elif sr <= 0.18:
            score += _w("bloodline.sire_surface_weak", -3) * blood_weight
            reasons.append(f"父系同馬場低調{sr * 100:.0f}%")
    elif not feat.get("bloodline_data_available", True):
        reasons.append("血統データ未投入")

    sdr = feat.get("sire_distance_top3_rate")
    sdn = feat.get("sire_distance_samples", 0)
    if sdr is not None and sdn >= 30:
        if sdr >= 0.40:
            score += _w("bloodline.sire_distance_strong", 4) * blood_weight
            reasons.append(f"父系距離帯複勝{sdr * 100:.0f}%")
        elif sdr <= 0.18:
            score += _w("bloodline.sire_distance_weak", -3) * blood_weight
            reasons.append(f"父系距離帯低調{sdr * 100:.0f}%")

    dsr = feat.get("dam_sire_surface_top3_rate")
    dsn = feat.get("dam_sire_surface_samples", 0)
    if dsr is not None and dsn >= 30:
        if dsr >= 0.38:
            score += _w("bloodline.dam_sire_surface_strong", 3) * blood_weight
            reasons.append(f"母父同馬場複勝{dsr * 100:.0f}%")
        elif dsr <= 0.18:
            score += _w("bloodline.dam_sire_surface_weak", -2) * blood_weight
            reasons.append(f"母父同馬場低調{dsr * 100:.0f}%")

    ddr = feat.get("dam_sire_distance_top3_rate")
    ddn = feat.get("dam_sire_distance_samples", 0)
    if ddr is not None and ddn >= 30:
        if ddr >= 0.40:
            score += _w("bloodline.dam_sire_distance_strong", 3) * blood_weight
            reasons.append(f"母父距離帯複勝{ddr * 100:.0f}%")
        elif ddr <= 0.18:
            score += _w("bloodline.dam_sire_distance_weak", -2) * blood_weight
            reasons.append(f"母父距離帯低調{ddr * 100:.0f}%")

    sgr = feat.get("sire_going_top3_rate")
    sgn = feat.get("sire_going_samples", 0)
    if going in ("2", "3", "4") and sgr is not None and sgn >= 20:
        if sgr >= 0.38:
            score += _w("bloodline.sire_going_strong", 5) * blood_weight
            reasons.append(f"父系道悪{sgr * 100:.0f}%")
        elif sgr <= 0.18:
            score += _w("bloodline.sire_going_weak", -4) * blood_weight
            reasons.append(f"父系道悪低調{sgr * 100:.0f}%")

    dsgr = feat.get("dam_sire_going_top3_rate")
    dsgn = feat.get("dam_sire_going_samples", 0)
    if going in ("2", "3", "4") and dsgr is not None and dsgn >= 20:
        if dsgr >= 0.38:
            score += _w("bloodline.dam_sire_going_strong", 3) * blood_weight
            reasons.append(f"母父道悪{dsgr * 100:.0f}%")
        elif dsgr <= 0.18:
            score += _w("bloodline.dam_sire_going_weak", -2) * blood_weight
            reasons.append(f"母父道悪低調{dsgr * 100:.0f}%")

    if V2_DIST_ENABLED and feat.get("current_bucket") == "long":
        long_blood_ok = (
            (sdr is not None and sdn >= 30 and sdr >= 0.40)
            or (ddr is not None and ddn >= 30 and ddr >= 0.40)
        )
        long_bucket_top3 = feat.get("same_bucket_top3", 0) or 0
        if long_bucket_top3 >= 1 and long_blood_ok:
            score += _w("bloodline.long_blood_backup", 3)
            reasons.append("長距離血統裏付け")
        elif long_bucket_top3 == 0 and not long_blood_ok and past_count >= 3:
            score += _w("bloodline.long_blood_lacking", -4)
            reasons.append("長距離裏付け薄")

    strong_blood = 0
    if sr is not None and sn >= 30 and sr >= 0.42:
        strong_blood += 1
    if sdr is not None and sdn >= 30 and sdr >= 0.44:
        strong_blood += 1
    if dsr is not None and dsn >= 30 and dsr >= 0.40:
        strong_blood += 1
    if ddr is not None and ddn >= 30 and ddr >= 0.42:
        strong_blood += 1
    condition_fit = (
        feat.get("same_track_type_wins", 0) >= 1
        or feat.get("same_distance_top3", 0) >= 2
        or feat.get("same_course_distance_top3", 0) >= 1
        or day_bias > 0
        or gate_bias > 0
    )
    stable_team = (
        (jr is not None and jn >= 30 and jr >= 0.12)
        or (tr is not None and tn >= 30 and tr >= 0.12)
    )
    if strong_blood >= 2 and condition_fit:
        score += _w("bloodline.matched_combo_bonus", 4)
        reasons.append("血統条件一致")
    if past_count <= 2 and strong_blood >= 2 and stable_team:
        score += _w("bloodline.young_horse_with_blood_team", 3)
        reasons.append("少キャリア血統陣営")

    # 過去走なし
    if feat.get("past_count", 0) == 0 and not reasons:
        reasons.append("過去走なし")

    # 市場 (人気) ボーナス。直近 backtest で「予想モデルが 1〜2 人気を
    # ランキング下位に置いて勝ち馬を取り逃す」例が多発 (5/2-3 の 72 レース中
    # 6 件で勝ち馬を予想 7 位以下)。多頭数レースでは人気は強いシグナル
    # なので、極端な乖離を抑える方向にスコアを補正する。
    # 少頭数 (< 12 頭) では人気が薄いので補正なし。
    starter_count = feat.get("current_starter_count", 0) or 0
    popularity = horse.get("win_popularity") or 0
    if starter_count >= _w("popularity.min_field", 12):
        if popularity == 1:
            score += _w("popularity.first", 6)
            reasons.append("市場1人気")
        elif popularity == 2:
            score += _w("popularity.second", 3)
            reasons.append("市場2人気")
        elif popularity == 3:
            score += _w("popularity.third", 1)

    return score, reasons


def _stability_score(horse: dict, feat: dict) -> float:
    stable = 0.0
    avg = feat.get("recent_avg_finish")
    if avg is not None:
        if avg <= 2.0:
            stable += 8
        elif avg <= 4.0:
            stable += 5
        elif avg <= 6.0:
            stable += 2
        elif avg >= 9.0:
            stable -= 4
    stable += min(feat.get("same_track_type_wins", 0), 3) * 2
    stable += min(feat.get("same_track_type_top3", 0), 4)
    stable += min(feat.get("same_distance_top3", 0), 4)
    stable += min(feat.get("same_course_wins", 0), 2) * 2
    stable += min(feat.get("same_course_distance_top3", 0), 3)
    if feat.get("past_count", 0) >= 3:
        stable += 2
    elif feat.get("past_count", 0) == 0:
        stable -= 3
    jr = feat.get("jockey_win_rate")
    if jr is not None:
        if jr >= 0.20:
            stable += 2
        elif jr < 0.04:
            stable -= 2
    tr = feat.get("trainer_win_rate")
    if tr is not None and tr >= 0.15:
        stable += 1
    sr = feat.get("sire_surface_top3_rate")
    sn = feat.get("sire_surface_samples", 0)
    if sr is not None and sn >= 30:
        if sr >= 0.38:
            stable += 3
        elif sr <= 0.18:
            stable -= 4
    sdr = feat.get("sire_distance_top3_rate")
    sdn = feat.get("sire_distance_samples", 0)
    if sdr is not None and sdn >= 30:
        if sdr >= 0.40:
            stable += 3
        elif sdr <= 0.18:
            stable -= 3
    dsr = feat.get("dam_sire_surface_top3_rate")
    dsn = feat.get("dam_sire_surface_samples", 0)
    if dsr is not None and dsn >= 30:
        if dsr >= 0.38:
            stable += 2
        elif dsr <= 0.18:
            stable -= 2
    if feat.get("current_bucket") == "long":
        if feat.get("same_bucket_top3", 0) >= 1:
            stable += 2
        elif feat.get("same_bucket_runs", 0) >= 2:
            stable -= 2
    mp = horse.get("mining_predicted_order") or 0
    if 1 <= mp <= 3:
        stable += 1
    elif mp >= 10:
        stable -= 2
    return stable


def _has_negative_signal(reasons: list[str]) -> bool:
    for r in reasons:
        if "父系同馬場低調" in r or "父系距離帯低調" in r:
            return True
        if (
            r.startswith("休み明け")
            or r.startswith("間隔長め")
            or r.startswith("前走")
            or r.startswith("斤量増")
            or r.startswith("馬体減")
            or r.startswith("格上挑戦")
            or r == "上級条件で実績薄"
        ):
            return True
        if r.startswith("騎手勝率"):
            try:
                rate = int(r.replace("騎手勝率", "").replace("%", ""))
            except ValueError:
                continue
            if rate < 5:
                return True
    return False


def _confidence(scored: list[tuple[dict, float, list[str], float]]) -> tuple[str, float, bool]:
    if len(scored) < 2:
        return "標準", 0.0, False
    scores = [s for _, s, _, _ in scored]
    score_range = max(scores) - min(scores)
    gap = scored[0][1] - scored[1][1]
    stability = scored[0][3]
    if score_range < 1.5:
        return "暫定", gap, True
    if gap <= 5:
        return "混戦", gap, False
    if gap <= 10:
        return "接戦", gap, False
    # 「接戦扱い」を狭めに引き直す閾値も外出し。直近で「高信頼」のまま
    # 大外しが複数あったので、認定基準を厳しくする (既定 score≥100, gap≥20,
    # stability≥10)。weights.json の confidence セクションで上書き可。
    if _has_negative_signal(scored[0][2]) and gap <= _w("confidence.negative_gap", 20):
        return "接戦", gap, False
    if (
        scored[0][1] >= _w("confidence.min_score", 100)
        and gap >= _w("confidence.min_gap", 20)
        and stability >= _w("confidence.min_stability", 10)
        and not _has_negative_signal(scored[0][2])
    ):
        return "高信頼", gap, False
    return "標準", gap, False


def _score_probabilities(
    scored: list[tuple[dict, float, list[str], float]],
    confidence: str,
) -> dict[str, float]:
    if not scored:
        return {}
    max_score = max(s for _, s, _, _ in scored)
    temperature = float(os.environ.get("PRED_PROB_TEMPERATURE", "30.0"))
    weights = []
    for h, score, _, _ in scored:
        if score <= -900:
            w = 0.0
        else:
            w = math.exp((score - max_score) / temperature)
        weights.append((h.get("horse_num") or "", w))
    total = sum(w for _, w in weights)
    if total <= 0:
        return {num: 0.0 for num, _ in weights}
    raw = {num: w / total for num, w in weights}
    active = [num for num, w in weights if w > 0]
    if not active:
        return raw
    uniform = 1.0 / len(active)
    shrink = {
        "高信頼": 0.20,
        "標準": 0.32,
        "接戦": 0.45,
        "混戦": 0.55,
        "暫定": 0.70,
    }.get(confidence, 0.35)
    return {num: raw.get(num, 0.0) * (1.0 - shrink) + uniform * shrink for num in raw}


def _load_calibrator() -> dict | None:
    global _CALIBRATOR_CACHE
    if os.environ.get("PRED_DISABLE_CALIBRATOR") == "1":
        return None
    if not CALIBRATOR_PATH.exists():
        return None
    mtime = CALIBRATOR_PATH.stat().st_mtime
    if _CALIBRATOR_CACHE and _CALIBRATOR_CACHE[0] == mtime:
        return _CALIBRATOR_CACHE[1]
    data = json.loads(CALIBRATOR_PATH.read_text(encoding="utf-8"))
    # 期間メタが入っていれば 1 回だけログ (再現性監査の起点)。
    tf, tt = data.get("trained_from"), data.get("trained_to")
    if tf and tt:
        logger.info(
            "calibrator loaded: trained %s-%s (n=%s, gen=%s)",
            tf, tt, data.get("source_count"), data.get("generated_at", "?"),
        )
    else:
        logger.warning(
            "calibrator has no trained_from/trained_to metadata. "
            "Re-fit with `python -m scripts.backtest --save-calibrator "
            "--from <train_from> --to <train_to>` to record provenance."
        )
    _CALIBRATOR_CACHE = (mtime, data)
    return data


def _apply_calibrator(probabilities: dict[str, float]) -> dict[str, float]:
    """bin ベース calibrator + Bayesian shrinkage + 少数 bin 恒等寄せ。

    bin に入ったサンプル数が少ないと、観測した actual_win_rate が
    ノイズに引っ張られて極端な値になる (例: 0.15-0.20 bin で count=27 が
    `calibrated 0.33` を出すと、オッズ × 校正確率の EV が暴れて偽の高 EV
    候補を量産する)。次の 2 段で対処:

    1. **少数 bin 恒等寄せ**: count < min_count なら calibrated を捨てて
       `q = p` (raw のまま)。少サンプル bin がそもそも信用できない、という
       前提に基づく強めの安全弁。`min_count` は calibrator.json と
       環境変数 `PRED_CALIBRATOR_MIN_COUNT` で上書き可。
    2. **Bayesian shrinkage** (count >= min_count の bin に適用):
       `q = (count * calibrated + alpha * p) / (count + alpha)`
       count が大きいほど calibrated を信用、小さいほど raw に寄せる。
       `alpha` は calibrator.json の `shrinkage_alpha` (既定 30)。
    """
    calibrator = _load_calibrator()
    if not calibrator:
        return probabilities
    ctype = calibrator.get("type")
    if ctype == "isotonic":
        # Phase 3 (2026-05-13): Isotonic regression による単調校正。
        # bin の段差問題を解消。x_knots / y_knots の線形補間を `apply_isotonic`
        # で実装 (純 Python、numpy 不要)。
        from predictor.calibration import apply_isotonic
        adjusted_iso: dict[str, float] = {}
        for num, p in probabilities.items():
            adjusted_iso[num] = max(0.0, min(1.0, apply_isotonic(calibrator, p)))
        total = sum(adjusted_iso.values())
        if total <= 0:
            return probabilities
        return {num: p / total for num, p in adjusted_iso.items()}
    if ctype != "bin":
        logger.warning(
            "calibrator disabled: unsupported type=%r in calibrator.json",
            ctype,
        )
        return probabilities
    bins = calibrator.get("bins") or []
    try:
        alpha_default = float(calibrator.get("shrinkage_alpha", 30))
    except (TypeError, ValueError):
        alpha_default = 30.0
    try:
        alpha = float(os.environ.get("PRED_CALIBRATOR_ALPHA", alpha_default))
    except ValueError:
        alpha = alpha_default
    alpha = max(0.0, alpha)
    try:
        min_count_default = float(calibrator.get("min_count", 50))
    except (TypeError, ValueError):
        min_count_default = 50.0
    try:
        min_count = float(os.environ.get("PRED_CALIBRATOR_MIN_COUNT", min_count_default))
    except ValueError:
        min_count = min_count_default
    min_count = max(0.0, min_count)
    adjusted: dict[str, float] = {}
    for num, p in probabilities.items():
        q = p
        for b in bins:
            if b.get("lower", 0.0) <= p < b.get("upper", 1.0) or (p >= 1.0 and b.get("upper") == 1.0):
                cal = float(b.get("calibrated_probability", p))
                count = float(b.get("count", 0) or 0)
                # 少数 bin は丸ごと信用しない (恒等寄せ)
                if count < min_count:
                    q = p
                # 通常 bin は Bayesian shrinkage
                elif count + alpha > 0:
                    q = (count * cal + alpha * p) / (count + alpha)
                else:
                    q = cal
                break
        adjusted[num] = max(0.0, min(1.0, q))
    total = sum(adjusted.values())
    if total <= 0:
        return probabilities
    return {num: p / total for num, p in adjusted.items()}


def _market_probabilities(scored: list[tuple[dict, float, list[str], float]]) -> dict[str, float]:
    implied: list[tuple[str, float]] = []
    for h, _, _, _ in scored:
        odds = (h.get("win_odds") or 0) / 10.0
        implied.append((h.get("horse_num") or "", 1.0 / odds if odds > 1.0 else 0.0))
    total = sum(p for _, p in implied)
    if total <= 0:
        return {}
    return {num: p / total for num, p in implied}


def _investment_probability(
    model_probability: float,
    market_probability: float,
    confidence: str,
    odds: float,
) -> float:
    """投資判断用の確率。

    - calibrator 適用済み model_probability と市場確率を信頼度別重みで blend
    - オッズ帯別 discount は重複ヒューリスティックで EV を消滅させがちなので、
      `weights.json` の `discount` で外出し、環境変数 `PRED_DISABLE_DISCOUNT=1`
      で全無効化 (= 1.0) できるようにした。デフォルトは現行値を維持。
    """
    if model_probability <= 0:
        return 0.0
    model_weight = {
        "高信頼": _w("model_blend.high", 0.72),
        "標準": _w("model_blend.standard", 0.62),
        "接戦": _w("model_blend.close", 0.50),
        "混戦": _w("model_blend.tight", 0.42),
        "暫定": _w("model_blend.tentative", 0.30),
    }.get(confidence, _w("model_blend.default", 0.55))
    if market_probability <= 0:
        blended = model_probability
    else:
        blended = model_probability * model_weight + market_probability * (1.0 - model_weight)
    if os.environ.get("PRED_DISABLE_DISCOUNT") == "1":
        return blended
    discount = _w("discount.base", 0.92)
    if odds >= 30.0:
        discount *= _w("discount.over30", 0.72)
    elif odds >= 15.0:
        discount *= _w("discount.over15", 0.82)
    elif odds >= 8.0:
        discount *= _w("discount.over8", 0.90)
    return blended * discount


def _bet_metrics(horse: dict, win_probability: float) -> tuple[float, float, float]:
    odds = (horse.get("win_odds") or 0) / 10.0
    if win_probability <= 0:
        return 0.0, 0.0, 0.0
    fair_odds = 1.0 / win_probability
    if odds <= 1.0:
        return round(fair_odds, 2), 0.0, 0.0
    expected_value = win_probability * odds
    b = odds - 1.0
    kelly = (b * win_probability - (1.0 - win_probability)) / b
    return round(fair_odds, 2), round(expected_value, 3), round(max(0.0, min(kelly, 0.05)), 4)


def _value_score(
    horse: dict,
    score: float,
    confidence: str,
    expected_value: float = 0.0,
) -> float:
    """買い目候補用。オッズは予想スコアではなく、この値だけに使う。"""
    odds = (horse.get("win_odds") or 0) / 10.0
    popularity = horse.get("win_popularity") or 0
    feat = horse.get("_features") or {}
    value = (expected_value - 1.0) * 100 if expected_value else score - 70
    if expected_value == 0.0 and 7.0 <= odds <= 30.0:
        value += min(odds, 30.0) / 3.0
    if feat.get("current_bucket") == "long":
        value -= _w("risk.long_value_penalty", 10)
    current_level = feat.get("current_race_level", 0) or 0
    if current_level >= 7:
        value -= _w("risk.graded_value_penalty", 10)
    elif current_level >= 5:
        value -= _w("risk.op_value_penalty", 8)
    if feat.get("current_bucket") == "sprint" and not feat.get("same_distance_top3", 0):
        value -= _w("risk.sprint_unproven_value_penalty", 4)
    if odds >= 8.0:
        value -= _w("risk.longshot_value_penalty", 18)
    if feat.get("current_track_code") in {"03", "06", "10"}:
        value -= _w("risk.low_roi_track_value_penalty", 6)
    if 1 <= popularity <= 3 and odds and odds < 5.0:
        value -= 8
    if confidence in ("暫定", "混戦"):
        value -= 12
    elif confidence == "高信頼":
        value += 6
    return round(value, 1)


def predict_race(
    horses: list[dict],
    conn: sqlite3.Connection | None = None,
    race: dict | None = None,
    cache: dict | None = None,
) -> list[Prediction]:
    """1 レース分の予想。

    conn と race が両方与えられた場合は過去走ベースの本格スコアリング。
    無い場合は当日の出馬表だけから簡易スコアリング（旧 v0 互換）。
    """
    scored: list[tuple[dict, float, list[str], float]] = []
    use_features = conn is not None and race is not None
    feature_cache: dict = cache if cache is not None else {}
    leg_counts: dict[str, int] = {}
    precomputed: dict[str, dict] = {}
    if use_features:
        for h in horses:
            feat = compute_features(conn, h, race, cache=feature_cache)
            precomputed[h.get("horse_num") or ""] = feat
            leg = feat.get("leg_code") or ""
            if leg:
                leg_counts[leg] = leg_counts.get(leg, 0) + 1
    else:
        for h in horses:
            leg = (h.get("leg_quality_code") or "").strip()
            if leg:
                leg_counts[leg] = leg_counts.get(leg, 0) + 1
    front_runner_count = leg_counts.get("1", 0) + leg_counts.get("2", 0)

    for h in horses:
        if use_features:
            feat = precomputed.get(h.get("horse_num") or "") or compute_features(conn, h, race, cache=feature_cache)
            leg = feat.get("leg_code") or ""
            feat["front_runner_count"] = front_runner_count
            feat["same_leg_rivals"] = max(leg_counts.get(leg, 0) - 1, 0) if leg else 0
            h["_features"] = feat
            score, reasons = _score_one(h, feat)
            stability = _stability_score(h, feat)
        else:
            # フォールバック（DB なし）
            score = 0.0
            reasons = []
            mp = h.get("mining_predicted_order") or 0
            if 1 <= mp <= 18:
                score += max(20 - mp * 1.2, 0)
                reasons.append(f"マイニング{mp}位")
            if not reasons:
                reasons.append("事前情報のみ")
            stability = 0.0
            feat = {}
        warnings = []
        if use_features:
            if not feat.get("leg_quality_available"):
                warnings.append("leg_quality_unavailable")
            if feat.get("estimated_leg_code"):
                warnings.append("leg_quality_estimated")
            if not feat.get("same_day_bias_available"):
                warnings.append("same_day_bias_unavailable")
            for flag in feat.get("needs_post_race_data") or []:
                warnings.append(f"post_race:{flag}")
        h["_feature_warnings"] = warnings
        scored.append((h, score, reasons, stability))

    # スコア降順、同点なら安定性、馬番昇順
    scored.sort(key=lambda x: (-x[1], -x[3], int(x[0].get("horse_num") or "99")))

    # 上位僅差時だけ、安定性で◎/○を再評価する。
    if len(scored) >= 2:
        top_gap = scored[0][1] - scored[1][1]
        stability_gap = scored[1][3] - scored[0][3]
        if (top_gap <= 5 and stability_gap >= 4) or (top_gap <= 10 and stability_gap >= 7):
            scored[0], scored[1] = scored[1], scored[0]
            scored[0][2].append(f"上位再評価(安定性差{stability_gap:.1f})")

    confidence, gap, all_tied = _confidence(scored)
    raw_rule_prob = _score_probabilities(scored, confidence)
    # LightGBM Ensemble: rule prob と LGBM prob を重み blend。
    # LGBM model 不在時は ml_model.predict_lgbm_probs が空 dict を返し、blend は
    # rule prob をそのまま返す。重みは PRED_BLEND_W_RULE 環境変数で上書き可
    # (既定 0.5)。LGBM 信頼度確立後は 0.3 等に下げる。
    if use_features:
        try:
            from predictor.ml_model import blend as _blend, predict_lgbm_probs
            raw_lgbm_prob = predict_lgbm_probs(
                horses, race, conn=conn, feature_cache=feature_cache,
            )
            w_rule = float(os.environ.get("PRED_BLEND_W_RULE", "0.5"))
            blended = _blend(raw_rule_prob, raw_lgbm_prob, w_rule=w_rule)
        except Exception as e:
            logger.warning("LGBM blend failed, falling back to rule-only: %s", e)
            blended = raw_rule_prob
    else:
        blended = raw_rule_prob
    probability_by_num = _apply_calibrator(blended)
    market_probability_by_num = _market_probabilities(scored)

    out: list[Prediction] = []
    for rank, (h, score, reasons, _stability) in enumerate(scored, start=1):
        win_probability = probability_by_num.get(h.get("horse_num") or "", 0.0)
        odds = (h.get("win_odds") or 0) / 10.0
        investment_probability = _investment_probability(
            win_probability,
            market_probability_by_num.get(h.get("horse_num") or "", 0.0),
            confidence,
            odds,
        )
        fair_odds, expected_value, kelly_fraction = _bet_metrics(h, investment_probability)
        if all_tied:
            mark = MARKS[rank - 1] if rank <= 3 else ""
            rationale = "暫定（予想根拠不足・馬番順）"
        else:
            mark = MARKS[rank - 1] if rank <= len(MARKS) else ""
            rationale = "; ".join(reasons) if reasons else "情報不足"
            if rank == 1:
                rationale = f"{rationale}; 信頼度={confidence}(2位差{gap:.1f})"
        out.append(
            Prediction(
                horse_num=h.get("horse_num") or "",
                score=score,
                rank=rank,
                mark=mark,
                rationale=rationale,
                confidence=confidence,
                confidence_gap=gap,
                value_score=_value_score(h, score, confidence, expected_value),
                win_probability=round(investment_probability, 4),
                fair_odds=fair_odds,
                expected_value=expected_value,
                kelly_fraction=kelly_fraction,
                feature_warnings=list(h.get("_feature_warnings") or []),
            )
        )
    return out


def is_tentative(predictions: list[Prediction]) -> bool:
    return all("暫定" in p.rationale for p in predictions if p.mark)
