from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from collections import defaultdict


# =========================
# MODELS
# =========================

@dataclass
class BoardPlay:
    game_id: str
    sport: str
    team: str
    opponent: str
    player_name: str
    category: str          # HR / TB / HIT / K / AST / REB / 3PM / etc
    line: str              # "HR 1+", "1.5 TB", "1+ Hit", "6+ K"
    confidence: int        # 0-100
    score: float
    tier: str              # CORE / STRONG / VALUE / LONGSHOT
    reason: str
    stats: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CandidateScore:
    category: str
    line: str
    score: float
    confidence: int
    reason: str
    stats: Dict[str, Any] = field(default_factory=dict)


# =========================
# CONFIG
# =========================

MIN_HITTER_SCORE = 28.0
MIN_PITCHER_SCORE = 28.0

CORE_THRESHOLD = 42.0
STRONG_THRESHOLD = 36.0
VALUE_THRESHOLD = 30.0
LONGSHOT_THRESHOLD = 28.0

LEGACY_CORE_CONFIDENCE_THRESHOLD = 72
LEGACY_VALUE_CONFIDENCE_THRESHOLD = 64

MAX_PLAYS_PER_GAME = 6
MAX_TEAM_PLAYS_PER_GAME = 14
MAX_HR_CORE = 4
MAX_HR_STRONG = 4
MAX_HR_VALUE = 4
MAX_HR_LONGSHOT = 3

MAX_GENERAL_CORE = 4
MAX_GENERAL_STRONG = 4
MAX_GENERAL_VALUE = 4
MAX_GENERAL_LONGSHOT = 3

# If categories are very close, use tie-break priority.
CATEGORY_PRIORITY = {
    "HR": 4,
    "TB": 3,
    "HIT": 2,
    "K": 5,
    "AST": 3,
    "REB": 3,
    "3PM": 3,
    "PTS": 2,
    "PRA": 1,
}

MLB_TEAM_ALIASES = {
    "angels": "LAA",
    "astros": "HOU",
    "athletics": "ATH",
    "as": "ATH",
    "bluejays": "TOR",
    "blue_jays": "TOR",
    "braves": "ATL",
    "brewers": "MIL",
    "cardinals": "STL",
    "cubs": "CHC",
    "diamondbacks": "ARI",
    "dbacks": "ARI",
    "dodgers": "LAD",
    "giants": "SF",
    "guardians": "CLE",
    "mariners": "SEA",
    "marlins": "MIA",
    "mets": "NYM",
    "nationals": "WSH",
    "nats": "WSH",
    "orioles": "BAL",
    "o": "BAL",
    "padres": "SD",
    "phillies": "PHI",
    "phils": "PHI",
    "pirates": "PIT",
    "rangers": "TEX",
    "rays": "TB",
    "redsox": "BOS",
    "red_sox": "BOS",
    "reds": "CIN",
    "rockies": "COL",
    "royals": "KC",
    "tigers": "DET",
    "twins": "MIN",
    "whitesox": "CWS",
    "white_sox": "CWS",
    "yankees": "NYY",
}


# =========================
# HELPERS
# =========================

def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def safe_num(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def first_num(data: Dict[str, Any], *keys: str, default: float = 0.0) -> float:
    for key in keys:
        if key in data and data.get(key) not in (None, ""):
            return safe_num(data.get(key), default)
    return default


def normalize_score(score: float) -> float:
    return round(clamp(score, 0.0, 50.0), 2)


def score_to_confidence(score: float) -> int:
    return int(clamp(round(score * 2), 1, 99))


def pct_to_confidence(score: float) -> int:
    """
    Legacy confidence mapping retained for basketball stubs.
    """
    return int(clamp(round(score), 1, 99))


def make_candidate(
    *,
    category: str,
    line: str,
    raw_score: float,
    reason: str,
    stats: Dict[str, Any],
) -> CandidateScore:
    score = normalize_score(raw_score)
    return CandidateScore(
        category=category,
        line=line,
        score=score,
        confidence=score_to_confidence(score),
        reason=reason,
        stats=stats,
    )


def assign_mlb_tier(score: float) -> str:
    if score >= CORE_THRESHOLD:
        return "CORE"
    if score >= STRONG_THRESHOLD:
        return "STRONG"
    if score >= VALUE_THRESHOLD:
        return "VALUE"
    return "LONGSHOT"


def assign_tier(confidence: int) -> str:
    if confidence >= LEGACY_CORE_CONFIDENCE_THRESHOLD:
        return "CORE"
    if confidence >= LEGACY_VALUE_CONFIDENCE_THRESHOLD:
        return "VALUE"
    return "LONGSHOT"


def category_sort_key(play: BoardPlay) -> Tuple[int, float]:
    return (CATEGORY_PRIORITY.get(play.category, 0), play.score)


def short_reason(parts: List[str]) -> str:
    clean = [p.strip() for p in parts if p and str(p).strip()]
    return " | ".join(clean[:3])


def hr_power_metrics(stats: Dict[str, Any]) -> Dict[str, float]:
    season_hr = first_num(stats, "season_hr", "homeRuns", "home_runs")
    season_ab = first_num(stats, "season_ab", "atBats", "ab")
    season_pa = first_num(stats, "season_pa", "plateAppearances", "pa")
    season_ops = first_num(stats, "season_ops", "ops", "OPS")
    season_slg = first_num(stats, "season_slg", "slg", "SLG")
    prev_hr = first_num(stats, "prev_hr")
    prev_ab = first_num(stats, "prev_ab")
    prev_ops = first_num(stats, "prev_ops")
    prev_slg = first_num(stats, "prev_slg")
    iso = first_num(stats, "iso", "ISO")
    barrel = first_num(stats, "barrel_pct", "barrel_rate")
    l5_hr = first_num(stats, "l5_hr")
    l10_hr = first_num(stats, "l10_hr")
    hr_per_ab = season_ab / season_hr if season_hr > 0 and season_ab > 0 else 0.0
    prev_hr_per_ab = prev_ab / prev_hr if prev_hr > 0 and prev_ab > 0 else 0.0
    has_season = any(
        value > 0
        for value in (
            season_hr,
            season_ab,
            season_pa,
            season_ops,
            season_slg,
            prev_hr,
            prev_ab,
            prev_ops,
            prev_slg,
        )
    )

    return {
        "season_hr": season_hr,
        "season_ab": season_ab,
        "season_pa": season_pa,
        "season_ops": season_ops,
        "season_slg": season_slg,
        "prev_hr": prev_hr,
        "prev_ab": prev_ab,
        "prev_ops": prev_ops,
        "prev_slg": prev_slg,
        "iso": iso,
        "barrel": barrel,
        "l5_hr": l5_hr,
        "l10_hr": l10_hr,
        "hr_per_ab": hr_per_ab,
        "prev_hr_per_ab": prev_hr_per_ab,
        "has_season": 1.0 if has_season else 0.0,
    }


def has_heavy_hr_power(stats: Dict[str, Any]) -> bool:
    m = hr_power_metrics(stats)
    return (
        m["season_hr"] >= 7
        or (m["hr_per_ab"] > 0 and m["hr_per_ab"] <= 12)
        or m["season_ops"] >= 0.900
        or m["season_slg"] >= 0.520
        or m["prev_hr"] >= 35
        or (m["prev_hr_per_ab"] > 0 and m["prev_hr_per_ab"] <= 15)
        or m["prev_ops"] >= 0.850
        or m["prev_slg"] >= 0.500
        or m["iso"] >= 0.240
        or m["barrel"] >= 12
    )


def has_heater_hr_power(stats: Dict[str, Any]) -> bool:
    m = hr_power_metrics(stats)
    return (
        has_heavy_hr_power(stats)
        or m["season_hr"] >= 4
        or (m["hr_per_ab"] > 0 and m["hr_per_ab"] <= 18)
        or m["season_ops"] >= 0.800
        or m["season_slg"] >= 0.460
        or m["prev_hr"] >= 25
        or m["prev_ops"] >= 0.780
        or m["prev_slg"] >= 0.450
        or m["iso"] >= 0.200
        or m["barrel"] >= 9
        or m["l5_hr"] >= 2
        or m["l10_hr"] >= 3
    )


def is_low_power_hr_profile(stats: Dict[str, Any]) -> bool:
    m = hr_power_metrics(stats)
    if not m["has_season"]:
        return False
    return (
        m["season_hr"] <= 2
        and m["season_ops"] < 0.760
        and m["season_slg"] < 0.420
        and m["iso"] < 0.170
        and m["barrel"] < 8
    )


def classify_hr_lane(play: BoardPlay) -> str:
    if play.category != "HR":
        return ""
    stats = play.stats or {}
    if has_heavy_hr_power(stats):
        return "heavy"
    if is_low_power_hr_profile(stats):
        return "longshot"
    if has_heater_hr_power(stats) or play.score >= STRONG_THRESHOLD:
        return "heater"
    return "longshot"


def hr_power_context(stats: Dict[str, Any]) -> str:
    m = hr_power_metrics(stats or {})
    parts = []
    if m["season_hr"] > 0:
        if m["season_ab"] > 0:
            parts.append(f"{int(m['season_hr'])} HR/{int(m['season_ab'])} AB")
        else:
            parts.append(f"{int(m['season_hr'])} HR")
    if m["prev_hr"] >= 25:
        parts.append(f"prev {int(m['prev_hr'])} HR")
    if m["season_ops"] > 0:
        parts.append(f"OPS {m['season_ops']:.3f}")
    elif m["season_slg"] > 0:
        parts.append(f"SLG {m['season_slg']:.3f}")
    elif m["prev_hr"] > 0:
        parts.append(f"prev {int(m['prev_hr'])} HR")
    elif m["prev_ops"] > 0:
        parts.append(f"prev OPS {m['prev_ops']:.3f}")
    elif m["barrel"] > 0:
        parts.append(f"barrel {m['barrel']:.1f}%")
    if len(parts) < 2 and m["prev_hr"] > 0 and not any("prev" in part for part in parts):
        parts.append(f"prev {int(m['prev_hr'])} HR")
    return " | ".join(parts[:2])


def adjust_hr_score_for_power(score: float, stats: Dict[str, Any]) -> float:
    adjusted = score
    if has_heavy_hr_power(stats):
        adjusted += 3.5
    elif has_heater_hr_power(stats):
        adjusted += 1.5

    m = hr_power_metrics(stats)
    if m["prev_hr"] >= 45 and m["season_hr"] >= 2:
        adjusted = max(adjusted, 30.0)
    elif m["prev_hr"] >= 35 and m["season_hr"] >= 3:
        adjusted = max(adjusted, 29.0)

    if is_low_power_hr_profile(stats):
        adjusted = min(adjusted, 29.9)
    else:
        if m["has_season"] and m["season_hr"] <= 2 and not has_heater_hr_power(stats):
            adjusted = min(adjusted, 34.9)

    return normalize_score(adjusted)


def normalize_team_command(command: str) -> str:
    return str(command or "").strip().lower().lstrip("/").replace("-", "_").replace(" ", "_")


def resolve_mlb_team(command: str) -> Optional[str]:
    normalized = normalize_team_command(command)
    if not normalized:
        return None
    if normalized.upper() in set(MLB_TEAM_ALIASES.values()):
        return normalized.upper()
    return MLB_TEAM_ALIASES.get(normalized)


def filter_board_by_team(
    board: Dict[str, List[BoardPlay]],
    team_command: Optional[str],
) -> Dict[str, List[BoardPlay]]:
    """
    Filters an already-generated board to games involving a team command like
    /orioles, /yankees, or /dodgers. No board rebuild happens here.
    """
    team = resolve_mlb_team(team_command or "")
    if not team:
        return board

    filtered: Dict[str, List[BoardPlay]] = {}
    for game_id, plays in board.items():
        if any(play.team.upper() == team or play.opponent.upper() == team for play in plays):
            filtered[game_id] = plays
            continue

        teams_from_id = {part.upper() for part in str(game_id).replace(" ", "").split("@")}
        if team in teams_from_id:
            filtered[game_id] = plays

    return filtered


def format_team_command(board: Dict[str, List[BoardPlay]], command_name: str) -> str:
    return format_game_board(board, team_filter=command_name)


def format_score(score: float) -> str:
    return f"{score:.1f}/50"


def normalize_model_score(score: float) -> float:
    return normalize_score(score * 0.5)


def recommendation_line(rec: str, fallback: str) -> str:
    text = str(rec or "").replace("🎯", "").strip()
    if not text:
        return fallback
    for separator in ("Â·", "·", "?"):
        text = text.replace(separator, "|")
    line = text.split("|", 1)[0].strip()
    return line or fallback


def recommendation_reason(rec: str) -> str:
    text = str(rec or "").replace("🎯", "").strip()
    for separator in ("Â·", "·", "?"):
        text = text.replace(separator, "|")
    parts = [part.strip() for part in text.split("|") if part.strip()]
    if len(parts) > 1:
        return parts[-1]
    return text


def opponent_from_game(game_id: str, team: str) -> str:
    parts = [part.strip().upper() for part in str(game_id or "").replace(" ", "").split("@")]
    team = str(team or "").strip().upper()
    if len(parts) != 2 or not team:
        return ""
    if team == parts[0]:
        return parts[1]
    if team == parts[1]:
        return parts[0]
    return ""


def board_play_from_pick(pick: Dict[str, Any], category: str) -> Optional[BoardPlay]:
    if category == "HR":
        score = adjust_hr_score_for_power(
            normalize_model_score(safe_num(pick.get("score"))),
            pick,
        )
        line = recommendation_line(pick.get("hr_rec"), "HR 1+")
        reason = short_reason([
            f"vs {pick.get('pitcher_name', 'Unknown')}",
            hr_power_context(pick),
            recommendation_reason(pick.get("hr_rec")),
        ])
    elif category == "TB":
        score = normalize_model_score(safe_num(pick.get("tb_score")))
        line = recommendation_line(pick.get("tb_rec"), "Over 1.5 TB")
        reason = short_reason([
            f"vs {pick.get('pitcher_name', 'Unknown')}",
            recommendation_reason(pick.get("tb_rec")),
        ])
    elif category == "HIT":
        l1_hits = safe_num(pick.get("l1_hits"))
        l5_hits = safe_num(pick.get("l5_hits"))
        l10_hits = safe_num(pick.get("l10_hits"))
        lineup_spot = safe_num(pick.get("batting_order"), 9)
        tb_signal = normalize_model_score(safe_num(pick.get("tb_score")))
        lineup_bonus = 3.0 if lineup_spot <= 3 else 2.0 if lineup_spot <= 6 else 0.0
        score = normalize_score(
            (tb_signal * 0.45) +
            (clamp(l5_hits / 5.0, 0, 2.0) * 8.0) +
            (clamp(l10_hits / 10.0, 0, 2.0) * 7.0) +
            (clamp(l1_hits, 0, 3.0) * 1.5) +
            lineup_bonus
        )
        line = "1+ Hit"
        reason = short_reason([
            f"vs {pick.get('pitcher_name', 'Unknown')}",
            f"TB signal {tb_signal:.1f}",
            f"order {int(lineup_spot)}",
        ])
    elif category == "K":
        score = normalize_model_score(safe_num(pick.get("k_score")))
        line = recommendation_line(pick.get("k_rec"), "Over 5.5 Ks")
        reason = short_reason([
            str(pick.get("game", "")),
            recommendation_reason(pick.get("k_rec")),
        ])
    else:
        return None

    if score < LONGSHOT_THRESHOLD:
        return None

    game_id = str(pick.get("game") or pick.get("game_id") or "")
    team = str(pick.get("team") or pick.get("pitcher_team") or "???")
    opponent = str(pick.get("opp_team") or opponent_from_game(game_id, team))

    return BoardPlay(
        game_id=game_id,
        sport="MLB",
        team=team,
        opponent=opponent,
        player_name=str(pick.get("name") or pick.get("player_name") or "Unknown"),
        category=category,
        line=line,
        confidence=score_to_confidence(score),
        score=score,
        tier=assign_mlb_tier(score),
        reason=reason,
        stats=dict(pick),
    )


def build_game_board_from_results(
    results: Dict[str, Any],
    max_plays_per_game: int = MAX_PLAYS_PER_GAME,
) -> Dict[str, List[BoardPlay]]:
    board_by_game: Dict[str, List[BoardPlay]] = defaultdict(list)

    for pick in results.get("hr_picks", []) or []:
        play = board_play_from_pick(pick, "HR")
        if play:
            board_by_game[play.game_id].append(play)

    for pick in results.get("tb_picks", []) or []:
        play = board_play_from_pick(pick, "TB")
        if play:
            board_by_game[play.game_id].append(play)

    for pick in results.get("tb_picks", []) or []:
        play = board_play_from_pick(pick, "HIT")
        if play:
            board_by_game[play.game_id].append(play)

    for pick in results.get("k_picks", []) or []:
        play = board_play_from_pick(pick, "K")
        if play:
            board_by_game[play.game_id].append(play)

    final_board: Dict[str, List[BoardPlay]] = {}
    for game_id, plays in board_by_game.items():
        deduped = dedupe_one_line_per_player(plays)
        ranked = sorted(
            deduped,
            key=lambda p: (p.score, CATEGORY_PRIORITY.get(p.category, 0)),
            reverse=True,
        )
        final_board[game_id] = ranked[:max_plays_per_game]

    return final_board


# =========================
# MLB SCORING
# =========================

def score_mlb_hr(h: Dict[str, Any]) -> CandidateScore:
    l5_hr = safe_num(h.get("l5_hr"))
    l10_hr = safe_num(h.get("l10_hr"))
    barrel = safe_num(h.get("barrel_rate"))
    hard_hit = safe_num(h.get("hard_hit_rate"))
    fly_ball = safe_num(h.get("fly_ball_rate"))
    pull = safe_num(h.get("pull_rate"))
    iso = safe_num(h.get("iso"))
    split_woba = safe_num(h.get("split_woba"))
    lineup_spot = safe_num(h.get("lineup_spot"), 9)

    lineup_bonus = 6 if lineup_spot <= 4 else 3 if lineup_spot <= 6 else 0

    raw_score = (
        (l5_hr * 9.0) +
        (l10_hr * 4.5) +
        (barrel * 0.85) +
        (hard_hit * 0.18) +
        (fly_ball * 0.16) +
        (pull * 0.10) +
        (iso * 42.0) +
        (split_woba * 18.0) +
        lineup_bonus
    ) * 0.55

    reason = short_reason([
        f"L5 HR {int(l5_hr)}",
        f"barrel {barrel:.1f}%",
        f"ISO {iso:.3f}",
    ])

    return make_candidate(
        category="HR",
        line="HR 1+",
        raw_score=raw_score,
        reason=reason,
        stats={
            "l5_hr": l5_hr,
            "l10_hr": l10_hr,
            "barrel_rate": barrel,
            "hard_hit_rate": hard_hit,
        },
    )


def score_mlb_tb(h: Dict[str, Any]) -> CandidateScore:
    l5_tb = safe_num(h.get("l5_tb_avg"))
    l10_tb = safe_num(h.get("l10_tb_avg"))
    xbh_rate = safe_num(h.get("xbh_rate"))
    avg = safe_num(h.get("avg"))
    hard_hit = safe_num(h.get("hard_hit_rate"))
    split_woba = safe_num(h.get("split_woba"))
    lineup_spot = safe_num(h.get("lineup_spot"), 9)

    lineup_bonus = 5 if lineup_spot <= 4 else 2 if lineup_spot <= 6 else 0

    raw_score = (
        (l5_tb * 18.0) +
        (l10_tb * 9.0) +
        (xbh_rate * 32.0) +
        (avg * 55.0) +
        (hard_hit * 0.20) +
        (split_woba * 18.0) +
        lineup_bonus
    ) * 0.55

    reason = short_reason([
        f"L5 TB {l5_tb:.1f}",
        f"AVG {avg:.3f}",
        f"XBH rate {xbh_rate:.2f}",
    ])

    return make_candidate(
        category="TB",
        line="1.5 TB",
        raw_score=raw_score,
        reason=reason,
        stats={
            "l5_tb_avg": l5_tb,
            "l10_tb_avg": l10_tb,
            "avg": avg,
            "xbh_rate": xbh_rate,
        },
    )


def score_mlb_hit(h: Dict[str, Any]) -> CandidateScore:
    l5_hits = safe_num(h.get("l5_hits"))
    l10_hits = safe_num(h.get("l10_hits"))
    avg = safe_num(h.get("avg"))
    split_woba = safe_num(h.get("split_woba"))
    lineup_spot = safe_num(h.get("lineup_spot"), 9)

    hit_rate_l5 = l5_hits / 5.0
    hit_rate_l10 = l10_hits / 10.0
    lineup_bonus = 5 if lineup_spot <= 3 else 2 if lineup_spot <= 6 else 0

    raw_score = (
        (hit_rate_l5 * 36.0) +
        (hit_rate_l10 * 24.0) +
        (avg * 70.0) +
        (split_woba * 20.0) +
        lineup_bonus
    ) * 0.55

    reason = short_reason([
        f"L5 {int(l5_hits)}/5",
        f"L10 {int(l10_hits)}/10",
        f"AVG {avg:.3f}",
    ])

    return make_candidate(
        category="HIT",
        line="1+ Hit",
        raw_score=raw_score,
        reason=reason,
        stats={
            "l5_hits": l5_hits,
            "l10_hits": l10_hits,
            "avg": avg,
        },
    )


def score_mlb_k(p: Dict[str, Any]) -> CandidateScore:
    k_line = int(safe_num(p.get("k_line"), 6))
    l5_k = safe_num(p.get("l5_k_avg"))
    l10_k = safe_num(p.get("l10_k_avg"))
    innings = safe_num(p.get("innings_avg"))
    opp_k_rate = safe_num(p.get("opp_k_rate"))
    opp_contact_penalty = safe_num(p.get("opp_contact_penalty"))

    raw_score = (
        (l5_k * 5.5) +
        (l10_k * 3.5) +
        (innings * 6.0) +
        (opp_k_rate * 0.95) -
        (opp_contact_penalty * 4.0)
    ) * 0.55

    reason = short_reason([
        f"L5 K {l5_k:.1f}",
        f"IP {innings:.1f}",
        f"opp K% {opp_k_rate:.1f}",
    ])

    return make_candidate(
        category="K",
        line=f"{k_line}+ K",
        raw_score=raw_score,
        reason=reason,
        stats={
            "k_line": k_line,
            "l5_k_avg": l5_k,
            "l10_k_avg": l10_k,
            "innings_avg": innings,
            "opp_k_rate": opp_k_rate,
        },
    )


def choose_best_hitter_category(h: Dict[str, Any]) -> Optional[CandidateScore]:
    candidates = [
        score_mlb_hr(h),
        score_mlb_tb(h),
        score_mlb_hit(h),
    ]

    candidates = [c for c in candidates if c.score >= MIN_HITTER_SCORE]
    if not candidates:
        return None

    by_category = {c.category: c for c in candidates}
    hr = by_category.get("HR")
    tb = by_category.get("TB")
    if hr and tb and tb.score < hr.score + 3.0:
        candidates = [c for c in candidates if c.category != "TB"]

    candidates.sort(
        key=lambda c: (c.score, CATEGORY_PRIORITY.get(c.category, 0)),
        reverse=True,
    )

    return candidates[0]


def choose_best_pitcher_category(p: Dict[str, Any]) -> Optional[CandidateScore]:
    k = score_mlb_k(p)
    if k.score < MIN_PITCHER_SCORE:
        return None
    return k


# =========================
# FUTURE NBA / WNBA SUPPORT
# Expected player keys can be sport-specific.
# For now, included as stubs so your bot structure is ready.
# =========================

def score_basketball_ast(player: Dict[str, Any]) -> CandidateScore:
    l5 = safe_num(player.get("l5_ast"))
    l10 = safe_num(player.get("l10_ast"))
    minutes = safe_num(player.get("minutes"))
    usage = safe_num(player.get("usage"))

    score = (l5 * 7.5) + (l10 * 4.0) + (minutes * 0.6) + (usage * 0.3)
    return CandidateScore(
        category="AST",
        line=f"{int(safe_num(player.get('ast_line'), 5))}+ AST",
        score=score,
        confidence=pct_to_confidence(score),
        reason=short_reason([f"L5 AST {l5:.1f}", f"MIN {minutes:.1f}", f"USG {usage:.1f}"]),
        stats={"l5_ast": l5, "l10_ast": l10},
    )


def score_basketball_reb(player: Dict[str, Any]) -> CandidateScore:
    l5 = safe_num(player.get("l5_reb"))
    l10 = safe_num(player.get("l10_reb"))
    minutes = safe_num(player.get("minutes"))

    score = (l5 * 7.0) + (l10 * 4.0) + (minutes * 0.5)
    return CandidateScore(
        category="REB",
        line=f"{int(safe_num(player.get('reb_line'), 6))}+ REB",
        score=score,
        confidence=pct_to_confidence(score),
        reason=short_reason([f"L5 REB {l5:.1f}", f"MIN {minutes:.1f}"]),
        stats={"l5_reb": l5, "l10_reb": l10},
    )


def score_basketball_3pm(player: Dict[str, Any]) -> CandidateScore:
    l5 = safe_num(player.get("l5_3pm"))
    l10 = safe_num(player.get("l10_3pm"))
    attempts = safe_num(player.get("three_pa"))

    score = (l5 * 9.0) + (l10 * 4.5) + (attempts * 1.5)
    return CandidateScore(
        category="3PM",
        line=f"{int(safe_num(player.get('threes_line'), 2))}+ 3PM",
        score=score,
        confidence=pct_to_confidence(score),
        reason=short_reason([f"L5 3PM {l5:.1f}", f"3PA {attempts:.1f}"]),
        stats={"l5_3pm": l5, "l10_3pm": l10},
    )


def choose_best_basketball_category(player: Dict[str, Any]) -> Optional[CandidateScore]:
    candidates = [
        score_basketball_ast(player),
        score_basketball_reb(player),
        score_basketball_3pm(player),
    ]
    candidates.sort(key=lambda c: (c.score, CATEGORY_PRIORITY.get(c.category, 0)), reverse=True)
    best = candidates[0]
    if best.score < 58:
        return None
    return best


# =========================
# BUILD BOARD
# =========================

def build_game_board(
    hitters: List[Dict[str, Any]],
    pitchers: List[Dict[str, Any]],
    basketball_players: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, List[BoardPlay]]:
    """
    Returns:
    {
      "ATH@SEA": [BoardPlay, BoardPlay, ...],
      "BOS@NYY": [...],
    }
    """
    board_by_game: Dict[str, List[BoardPlay]] = defaultdict(list)

    for h in hitters:
        sport = str(h.get("sport", "MLB")).upper()
        if sport != "MLB":
            continue

        best = choose_best_hitter_category(h)
        if not best:
            continue

        play = BoardPlay(
            game_id=h["game_id"],
            sport=sport,
            team=h["team"],
            opponent=h["opponent"],
            player_name=h["player_name"],
            category=best.category,
            line=best.line,
            confidence=best.confidence,
            score=best.score,
            tier=assign_mlb_tier(best.score),
            reason=best.reason,
            stats=best.stats,
        )
        board_by_game[h["game_id"]].append(play)

    for p in pitchers:
        sport = str(p.get("sport", "MLB")).upper()
        if sport != "MLB":
            continue

        best = choose_best_pitcher_category(p)
        if not best:
            continue

        play = BoardPlay(
            game_id=p["game_id"],
            sport=sport,
            team=p["team"],
            opponent=p["opponent"],
            player_name=p["player_name"],
            category=best.category,
            line=best.line,
            confidence=best.confidence,
            score=best.score,
            tier=assign_mlb_tier(best.score),
            reason=best.reason,
            stats=best.stats,
        )
        board_by_game[p["game_id"]].append(play)

    if basketball_players:
        for player in basketball_players:
            sport = str(player.get("sport", "")).upper()
            if sport not in {"NBA", "WNBA"}:
                continue

            best = choose_best_basketball_category(player)
            if not best:
                continue

            play = BoardPlay(
                game_id=player["game_id"],
                sport=sport,
                team=player["team"],
                opponent=player["opponent"],
                player_name=player["player_name"],
                category=best.category,
                line=best.line,
                confidence=best.confidence,
                score=best.score,
                tier=assign_tier(best.confidence),
                reason=best.reason,
                stats=best.stats,
            )
            board_by_game[player["game_id"]].append(play)

    # sort and cap each game
    final_board: Dict[str, List[BoardPlay]] = {}

    for game_id, plays in board_by_game.items():
        deduped = dedupe_one_line_per_player(plays)
        ranked = sorted(
            deduped,
            key=lambda p: (p.score, CATEGORY_PRIORITY.get(p.category, 0)),
            reverse=True,
        )
        final_board[game_id] = ranked[:MAX_PLAYS_PER_GAME]

    return final_board


def dedupe_one_line_per_player(plays: List[BoardPlay]) -> List[BoardPlay]:
    """
    Ensures one best line per player per game.
    """
    best_by_player: Dict[str, BoardPlay] = {}

    for play in plays:
        current = best_by_player.get(play.player_name)
        if current is None:
            best_by_player[play.player_name] = play
            continue

        if current.category == "HR" and play.category == "TB" and play.score < current.score + 3.0:
            continue

        if play.category == "HR" and current.category == "TB" and current.score < play.score + 3.0:
            best_by_player[play.player_name] = play
            continue

        if play.score > current.score:
            best_by_player[play.player_name] = play
            continue

        if abs(play.score - current.score) < 2.0:
            # tie-break by category priority
            if CATEGORY_PRIORITY.get(play.category, 0) > CATEGORY_PRIORITY.get(current.category, 0):
                best_by_player[play.player_name] = play

    return list(best_by_player.values())


# =========================
# OPTIONAL: HR STACK VIEW
# This preserves the "gold" feel you liked from that one-game HR sheet.
# Use this when you want a same-game HR attack board.
# =========================

def build_hr_stack_view(hitters: List[Dict[str, Any]]) -> Dict[str, Dict[str, List[BoardPlay]]]:
    """
    Returns by game:
    {
      "ATH@SEA": {
         "pick_of_day": [BoardPlay],
         "core": [...],
         "strong": [...],
         "value": [...],
         "longshot": [...]
      }
    }
    """
    results: Dict[str, Dict[str, List[BoardPlay]]] = {}

    grouped: Dict[str, List[BoardPlay]] = defaultdict(list)

    for h in hitters:
        sport = str(h.get("sport", "MLB")).upper()
        if sport != "MLB":
            continue

        hr = score_mlb_hr(h)
        if hr.score < MIN_HITTER_SCORE:
            continue

        play = BoardPlay(
            game_id=h["game_id"],
            sport=sport,
            team=h["team"],
            opponent=h["opponent"],
            player_name=h["player_name"],
            category="HR",
            line="HR 1+",
            confidence=hr.confidence,
            score=hr.score,
            tier=assign_mlb_tier(hr.score),
            reason=hr.reason,
            stats=hr.stats,
        )
        grouped[h["game_id"]].append(play)

    for game_id, plays in grouped.items():
        ranked = sorted(plays, key=lambda p: p.score, reverse=True)

        core = [p for p in ranked if p.tier == "CORE"][:MAX_HR_CORE]
        strong = [p for p in ranked if p.tier == "STRONG"][:MAX_HR_STRONG]
        value = [p for p in ranked if p.tier == "VALUE"][:MAX_HR_VALUE]
        longshot = [p for p in ranked if p.tier == "LONGSHOT"][:MAX_HR_LONGSHOT]

        pick_of_day = ranked[:1]

        results[game_id] = {
            "pick_of_day": pick_of_day,
            "core": core,
            "strong": strong,
            "value": value,
            "longshot": longshot,
        }

    return results


# =========================
# FORMATTERS
# =========================

def format_full_slate_board(
    board: Dict[str, List[BoardPlay]],
    slate_name: str = "MLB Per-Game Board",
) -> str:
    return format_game_board(board, slate_name=slate_name)


def format_game_board(
    board: Dict[str, List[BoardPlay]],
    team_filter: Optional[str] = None,
    slate_name: Optional[str] = None,
) -> str:
    if team_filter:
        board = filter_board_by_team(board, team_filter)

    lines: List[str] = []
    if slate_name:
        lines.append(f"# {slate_name}")
        lines.append("")

    for game_id, plays in board.items():
        if not plays:
            continue

        lines.append(f"## {game_id}")
        for p in plays:
            icon = category_icon(p.category)
            lines.append(
                f"{icon} {p.player_name} ({p.team}) - {p.category} - {p.line} - "
                f"{format_score(p.score)} [{p.tier}]"
            )
            lines.append(f"   vs {p.opponent} | {p.reason}")
        lines.append("")

    return "\n".join(lines).strip()


def format_hr_stack_view(stacks: Dict[str, Dict[str, List[BoardPlay]]]) -> str:
    lines: List[str] = []

    for game_id, buckets in stacks.items():
        lines.append(f"## {game_id}")

        if buckets["pick_of_day"]:
            p = buckets["pick_of_day"][0]
            lines.append("Pick of the Day")
            lines.append(f"{p.player_name} ({p.team}) - {p.line} - {format_score(p.score)}")
            lines.append(f"vs {p.opponent} | {p.reason}")
            lines.append("")

        for label, heading in [
            ("core", "CORE"),
            ("strong", "STRONG"),
            ("value", "VALUE"),
            ("longshot", "LONGSHOT"),
        ]:
            plays = buckets.get(label, [])
            if not plays:
                continue
            lines.append(heading)
            for p in plays:
                lines.append(
                    f"- {p.player_name} ({p.team}) - {p.line} - {format_score(p.score)} | {p.reason}"
                )
            lines.append("")

    return "\n".join(lines).strip()


def category_icon(category: str) -> str:
    return {
        "HR": "HR",
        "TB": "TB",
        "HIT": "HIT",
        "K": "K",
        "AST": "AST",
        "REB": "REB",
        "3PM": "3PM",
        "PTS": "PTS",
        "PRA": "PRA",
    }.get(category, "*")


# =========================
# EXAMPLE USAGE
# =========================

if __name__ == "__main__":
    hitters = [
        {
            "player_name": "Luke Raley",
            "team": "SEA",
            "opponent": "ATH",
            "game_id": "ATH@SEA",
            "sport": "MLB",
            "lineup_spot": 3,
            "l5_hr": 2,
            "l10_hr": 4,
            "l5_hits": 4,
            "l10_hits": 7,
            "l5_tb_avg": 2.2,
            "l10_tb_avg": 1.8,
            "barrel_rate": 14.5,
            "hard_hit_rate": 49.0,
            "fly_ball_rate": 41.0,
            "pull_rate": 44.0,
            "iso": 0.240,
            "avg": 0.271,
            "xbh_rate": 0.31,
            "split_woba": 0.372,
        },
        {
            "player_name": "Julio Rodriguez",
            "team": "SEA",
            "opponent": "ATH",
            "game_id": "ATH@SEA",
            "sport": "MLB",
            "lineup_spot": 2,
            "l5_hr": 1,
            "l10_hr": 2,
            "l5_hits": 5,
            "l10_hits": 8,
            "l5_tb_avg": 1.6,
            "l10_tb_avg": 1.5,
            "barrel_rate": 10.0,
            "hard_hit_rate": 43.0,
            "fly_ball_rate": 33.0,
            "pull_rate": 39.0,
            "iso": 0.180,
            "avg": 0.292,
            "xbh_rate": 0.21,
            "split_woba": 0.361,
        },
    ]

    pitchers = [
        {
            "player_name": "Bryan Woo",
            "team": "SEA",
            "opponent": "ATH",
            "game_id": "ATH@SEA",
            "sport": "MLB",
            "k_line": 6,
            "l5_k_avg": 7.2,
            "l10_k_avg": 6.8,
            "innings_avg": 6.0,
            "opp_k_rate": 24.1,
            "opp_contact_penalty": 0.0,
        }
    ]

    board = build_game_board(hitters, pitchers)
    print(format_game_board(board))

    print("\n" + "=" * 60 + "\n")

    hr_stack = build_hr_stack_view(hitters)
    print(format_hr_stack_view(hr_stack))
