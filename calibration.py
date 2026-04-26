# calibration.py
"""
Maps raw 0-100 composite scores from hr_model.py into realistic
probability bands. The raw score is a RANKING tool, not a probability.

Empirical base rates (MLB 2023-25):
  - HR in a game for a starting hitter: ~13% avg, top tier ~22-25%
  - Over 1.5 TB: ~38% avg, top tier ~52-56%
  - Over 4.5 Ks for a starter: ~55% league, top arms ~75-80%
"""
from math import exp


def _logistic(x, midpoint, steepness):
    return 1.0 / (1.0 + exp(-(x - midpoint) / steepness))


def calibrate_hr_prob(raw_score):
    """Raw score 0-100 → HR probability ~4% to ~26%."""
    return round(0.04 + 0.22 * _logistic(raw_score, 55, 9), 3)


def calibrate_tb_prob(raw_score):
    """Raw score 0-100 → Over 1.5 TB prob ~20% to ~58%."""
    return round(0.20 + 0.38 * _logistic(raw_score, 55, 10), 3)


def calibrate_k_prob(raw_score, line=4.5):
    """Raw score 0-100 → Over {line} Ks prob. Line-adjusted."""
    base = 0.35 + 0.47 * _logistic(raw_score, 55, 11)
    if line >= 7.5:   base *= 0.55
    elif line >= 6.5: base *= 0.72
    elif line >= 5.5: base *= 0.88
    return round(min(0.90, base), 3)


def prob_to_american_odds(p):
    """Fair American odds for a probability."""
    if p <= 0 or p >= 1:
        return None
    if p >= 0.5:
        return int(round(-100 * p / (1 - p)))
    return int(round(100 * (1 - p) / p))


def parlay_prob(probs):
    """Independent parlay probability (no correlation adjustment)."""
    result = 1.0
    for p in probs:
        result *= p
    return round(result, 4)


def confidence_label(p, prop_type):
    """Honest lean based on calibrated probability."""
    if prop_type == "hr":
        if p >= 0.20: return "💣 Strong lean"
        if p >= 0.15: return "🎯 Good value"
        if p >= 0.11: return "🟡 Slight edge"
        return "🔴 Thin"
    if prop_type == "tb":
        if p >= 0.50: return "💣 Strong lean"
        if p >= 0.42: return "🎯 Good value"
        if p >= 0.35: return "🟡 Slight edge"
        return "🔴 Thin"
    if prop_type == "k":
        if p >= 0.68: return "💣 Strong lean"
        if p >= 0.58: return "🎯 Good value"
        if p >= 0.50: return "🟡 Floor play"
        return "🔴 Thin"
    return ""
