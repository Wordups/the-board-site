# hr_model.py
"""
MLB Scoring Engine — HR, TB, K.

Uses Statcast season data + L14 recent form. All team-tagging is explicit
(team = own team, opp_team = opponent) — no more Peralta-as-CHC bugs.
"""
import warnings
warnings.filterwarnings("ignore")

import requests
import pandas as pd
from datetime import date, timedelta
from pybaseball import (
    statcast_pitcher_exitvelo_barrels,
    statcast_batter_exitvelo_barrels,
    cache,
)
from config import (
    PARK_FACTORS, PARK_NAMES, WEIGHTS, TB_WEIGHTS, K_WEIGHTS,
    MIN_PA, MIN_BBE, TOP_HR_BOARD, TOP_TB_BOARD, TOP_K_BOARD,
)

cache.enable()


# ── Normalization ─────────────────────────────────────────────────────────────

def normalize_df(df, id_candidates):
    rename = {}
    for col in id_candidates:
        if col in df.columns and col != "mlbam_id":
            rename[col] = "mlbam_id"; break
    stat_map = {
        "barrel_batted_rate": "barrel_pct", "brl_percent": "barrel_pct",
        "hard_hit_percent":   "hard_hit_pct", "hard_hit%":  "hard_hit_pct",
        "last_name, first_name": "name", "last_name,first_name": "name",
        "player_name": "name", "k_percent": "k_pct", "bb_percent": "bb_pct",
    }
    for src, dst in stat_map.items():
        if src in df.columns and dst not in df.columns:
            rename[src] = dst
    df = df.rename(columns=rename)
    if "mlbam_id" not in df.columns:
        df["mlbam_id"] = range(len(df))
    return df


# ── Stat pulls ────────────────────────────────────────────────────────────────

def get_pitcher_stats(year=None):
    if year is None: year = date.today().year
    df = statcast_pitcher_exitvelo_barrels(year, minBBE=MIN_BBE)
    df = normalize_df(df, ["pitcher", "player_id", "pitcherId", "mlbam_id"])
    if "barrel_pct" not in df.columns and "brl_percent" in df.columns:
        df["barrel_pct"] = df["brl_percent"]
    try:
        from pybaseball import statcast_pitcher_expected_stats
        exp = statcast_pitcher_expected_stats(year, minPA=20)
        exp = exp.rename(columns={"player_id": "mlbam_id"})
        keep = [c for c in ["mlbam_id", "xwoba", "xslg", "xba"] if c in exp.columns]
        if "mlbam_id" in exp.columns:
            df = df.merge(exp[keep], on="mlbam_id", how="left")
    except Exception as e:
        print(f"[WARN] Pitcher expected stats: {e}")
    for col in ["hr_per_9", "hr_fb_pct", "k9", "k_pct", "swstr_pct", "fb_pct"]:
        if col not in df.columns:
            df[col] = None
    return df


def get_batter_stats(year=None):
    if year is None: year = date.today().year
    df = statcast_batter_exitvelo_barrels(year, minBBE=MIN_BBE)
    df = normalize_df(df, ["batter", "player_id", "batterId", "mlbam_id"])
    if "barrel_pct" not in df.columns and "brl_percent" in df.columns:
        df["barrel_pct"] = df["brl_percent"]
    try:
        from pybaseball import statcast_batter_expected_stats
        exp = statcast_batter_expected_stats(year, minPA=MIN_PA)
        exp = exp.rename(columns={"player_id": "mlbam_id", "slg": "SLG",
                                  "est_slg": "xslg", "est_woba": "xwOBA"})
        keep = [c for c in ["mlbam_id", "SLG", "xslg", "xwOBA"] if c in exp.columns]
        if "mlbam_id" in exp.columns and "mlbam_id" in df.columns:
            df["mlbam_id"] = df["mlbam_id"].astype(int)
            exp["mlbam_id"] = exp["mlbam_id"].astype(int)
            df = df.merge(exp[keep], on="mlbam_id", how="left")
            if "SLG" in df.columns:
                df["ISO"] = (df["SLG"] - df.get("ba", 0)).clip(lower=0)
    except Exception as e:
        print(f"[WARN] Batter expected stats: {e}")
    for col in ["ISO", "SLG", "ISO_vsL", "ISO_vsR", "SLG_vsL", "SLG_vsR", "K%", "xwOBA"]:
        if col not in df.columns:
            df[col] = None
    return df


def get_recent_batter_stats(year=None):
    """L14 Statcast bulk pull. Uses statcast() not statcast_batter()."""
    try:
        from pybaseball import statcast
        end = date.today()
        start = end - timedelta(days=14)
        df = statcast(start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"))
        if df.empty:
            return {}
        df["is_hard_hit"] = df["launch_speed"].fillna(0) >= 95
        # barrel column not always present in newer pybaseball — detect
        agg_dict = {
            "recent_bbe": ("launch_speed", "count"),
            "recent_hh_pct": ("is_hard_hit", "mean"),
        }
        if "barrel" in df.columns:
            agg_dict["recent_barrel_pct"] = ("barrel", "mean")
        elif "launch_angle" in df.columns:
            # Approximate barrel: 98+ mph EV AND 26-30° launch angle
            df["is_barrel"] = (
                (df["launch_speed"].fillna(0) >= 98) &
                (df["launch_angle"].fillna(-99).between(26, 30))
            )
            agg_dict["recent_barrel_pct"] = ("is_barrel", "mean")
        agg = df.groupby("batter").agg(**agg_dict).reset_index()
        agg["recent_hh_pct"] = agg["recent_hh_pct"] * 100
        if "recent_barrel_pct" in agg.columns:
            agg["recent_barrel_pct"] = agg["recent_barrel_pct"] * 100
        print(f"[recent] L14 stats loaded for {len(agg)} batters.")
        return agg.set_index("batter").to_dict("index")
    except Exception as e:
        print(f"[WARN] Recent batter stats failed: {e}")
        return {}


# ── Scoring ───────────────────────────────────────────────────────────────────

def clamp(val, lo=0, hi=100):
    return max(lo, min(hi, val))


def score_hr(brow, prow, park_factor, p_hand, recent_stats):
    s = 0.0
    b_bar = float(brow.get("barrel_pct") or 0)
    p_bar = float(prow.get("barrel_pct") or 8.0)
    s += WEIGHTS["barrel_matchup"] * clamp((b_bar / max(p_bar, 1)) * 50)

    hr_fb = float(prow.get("hr_fb_pct") or 10.0)
    s += WEIGHTS["hr_fb_pct"] * clamp(hr_fb * 4.5)

    if p_hand == "R":
        iso = float(brow.get("ISO_vsR") or brow.get("ISO") or 0)
        slg = float(brow.get("SLG_vsR") or brow.get("SLG") or 0)
    else:
        iso = float(brow.get("ISO_vsL") or brow.get("ISO") or 0)
        slg = float(brow.get("SLG_vsL") or brow.get("SLG") or 0)
    s += WEIGHTS["iso_platoon"] * clamp(iso * 280)
    s += WEIGHTS["slg_platoon"] * clamp(slg * 140)
    s += WEIGHTS["park_factor"] * clamp(((park_factor - 0.85) / 0.55) * 100)

    pid = brow.get("mlbam_id")
    if pid and pid in recent_stats:
        r = recent_stats[pid]
        s += WEIGHTS["recent_form"] * clamp(float(r.get("recent_hh_pct") or 0) * 2.5)
    return round(s, 2)


def score_tb(brow, prow, park_factor, p_hand, batting_order):
    s = 0.0
    if p_hand == "R":
        slg = float(brow.get("SLG_vsR") or brow.get("SLG") or 0)
    else:
        slg = float(brow.get("SLG_vsL") or brow.get("SLG") or 0)
    s += TB_WEIGHTS["slg_platoon"] * clamp(slg * 145)

    b_hard = float(brow.get("hard_hit_pct") or 0)
    p_hard = float(prow.get("hard_hit_pct") or 36.0)
    s += TB_WEIGHTS["hard_hit_matchup"] * clamp((b_hard / max(p_hard, 1)) * 55)

    k_pct = float(brow.get("K%") or 0.22)
    s += TB_WEIGHTS["contact_rate"] * clamp((1 - k_pct) * 100)

    xwoba = float(brow.get("xwOBA") or 0.320)
    s += TB_WEIGHTS["xwoba"] * clamp((xwoba / 0.420) * 100)

    order_score = max(0, (10 - batting_order) / 9 * 100)
    s += TB_WEIGHTS["batting_order"] * clamp(order_score)
    s += TB_WEIGHTS["park_factor"] * clamp(((park_factor - 0.85) / 0.55) * 100)
    return round(s, 2)


def score_k(prow):
    s = 0.0
    k9 = float(prow.get("k9") or 0)
    s += K_WEIGHTS["k9"] * clamp(k9 / 15 * 100)

    k_pct = float(prow.get("k_pct") or 0)
    if k_pct > 1: k_pct = k_pct / 100
    s += K_WEIGHTS["k_pct"] * clamp(k_pct * 380)

    swstr = float(prow.get("swstr_pct") or 0)
    if swstr > 1: swstr = swstr / 100
    s += K_WEIGHTS["swstr_pct"] * clamp(swstr * 800)

    fb_pct = float(prow.get("fb_pct") or 0)
    if fb_pct > 1: fb_pct = fb_pct / 100
    s += K_WEIGHTS["fb_pct"] * clamp(fb_pct * 250)
    return round(s, 2)


# ── Recommendations ───────────────────────────────────────────────────────────

def recommend_hr(pick):
    score = pick.get("score", 0)
    barrel = pick.get("barrel_pct", 0)
    if score >= 75 and barrel >= 15: return "🎯 HR 1+ · Strong lean"
    if score >= 65:                  return "🎯 HR 1+ · Good value"
    return "🎯 HR 1+ · Slight edge"


def recommend_tb(pick):
    slg = pick.get("slg", 0)
    order = pick.get("batting_order", 5)
    score = pick.get("tb_score", 0)
    pa_est = 4.2 if order <= 3 else 3.8 if order <= 6 else 3.2
    exp_tb = round(slg * pa_est, 1)
    if exp_tb >= 3.5 or score >= 70: return "🎯 Over 2.5 TB · Strong lean"
    if exp_tb >= 2.5 or score >= 60: return "🎯 Over 1.5 TB · Good value"
    return "🎯 Over 1.5 TB · Slight edge"


def recommend_k(pick):
    k9 = pick.get("k9", 0)
    score = pick.get("k_score", 0)
    if k9 >= 11 or score >= 75: return "🎯 Over 7.5 Ks · Strong lean"
    if k9 >= 9  or score >= 65: return "🎯 Over 6.5 Ks · Good value"
    if k9 >= 7  or score >= 55: return "🎯 Over 5.5 Ks · Slight edge"
    return "🎯 Over 4.5 Ks · Floor play"


def has_platoon_advantage(bat_side, pitcher_hand):
    return bat_side != pitcher_hand
