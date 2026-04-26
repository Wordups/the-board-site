from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from collections import defaultdict


@dataclass
class BoardPlay:
    game_id: str
    sport: str
    team: str
    opponent: str
    player_name: str
    category: str
    line: str
    confidence: int
    score: float
    tier: str
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


MIN_HITTER_SCORE = 28.0
MIN_PITCHER_SCORE = 28.0
CORE_THRESHOLD = 42.0
STRONG_THRESHOLD = 36.0
VALUE_THRESHOLD = 30.0
LONGSHOT_THRESHOLD = 28.0
LEGACY_CORE_CONFIDENCE_THRESHOLD = 72
LEGACY_VALUE_CONFIDENCE_THRESHOLD = 64
MAX_PLAYS_PER_GAME = 6
MAX_HR_CORE = 4
MAX_HR_STRONG = 4
MAX_HR_VALUE = 4
MAX_HR_LONGSHOT = 3

CATEGORY_PRIORITY = {
    "HR": 4, "TB": 3, "HIT": 2, "K": 5,
    "AST": 3, "REB": 3, "3PM": 3, "PTS": 2, "PRA": 1,
}

MLB_TEAM_ALIASES = {
    "angels": "LAA", "astros": "HOU", "athletics": "ATH", "as": "ATH",
    "bluejays": "TOR", "blue_jays": "TOR", "braves": "ATL", "brewers": "MIL",
    "cardinals": "STL", "cubs": "CHC", "diamondbacks": "ARI", "dbacks": "ARI",
    "dodgers": "LAD", "giants": "SF", "guardians": "CLE", "mariners": "SEA",
    "marlins": "MIA", "mets": "NYM", "nationals": "WSH", "nats": "WSH",
    "orioles": "BAL", "o": "BAL", "padres": "SD", "phillies": "PHI",
    "phils": "PHI", "pirates": "PIT", "rangers": "TEX", "rays": "TB",
    "redsox": "BOS", "red_sox": "BOS", "reds": "CIN", "rockies": "COL",
    "royals": "KC", "tigers": "DET", "twins": "MIN", "whitesox": "CWS",
    "white_sox": "CWS", "yankees": "NYY",
}


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
    return int(clamp(round(score), 1, 99))

def make_candidate(*, category, line, raw_score, reason, stats):
    score = normalize_score(raw_score)
    return CandidateScore(
        category=category, line=line, score=score,
        confidence=score_to_confidence(score), reason=reason, stats=stats,
    )

def assign_mlb_tier(score: float) -> str:
    if score >= CORE_THRESHOLD: return "CORE"
    if score >= STRONG_THRESHOLD: return "STRONG"
    if score >= VALUE_THRESHOLD: return "VALUE"
    return "LONGSHOT"

def assign_tier(confidence: int) -> str:
    if confidence >= LEGACY_CORE_CONFIDENCE_THRESHOLD: return "CORE"
    if confidence >= LEGACY_VALUE_CONFIDENCE_THRESHOLD: return "VALUE"
    return "LONGSHOT"

def short_reason(parts: List[str]) -> str:
    clean = [p.strip() for p in parts if p and str(p).strip()]
    return " | ".join(clean[:3])

def normalize_score_model(score: float) -> float:
    return normalize_score(score * 0.5)

def recommendation_line(rec: str, fallback: str) -> str:
    text = str(rec or "").replace("🎯", "").strip()
    if not text: return fallback
    for sep in ("Â·", "·", "?"):
        text = text.replace(sep, "|")
    line = text.split("|", 1)[0].strip()
    return line or fallback

def recommendation_reason(rec: str) -> str:
    text = str(rec or "").replace("🎯", "").strip()
    for sep in ("Â·", "·", "?"):
        text = text.replace(sep, "|")
    parts = [p.strip() for p in text.split("|") if p.strip()]
    return parts[-1] if len(parts) > 1 else text

def opponent_from_game(game_id: str, team: str) -> str:
    parts = [p.strip().upper() for p in str(game_id or "").replace(" ", "").split("@")]
    team = str(team or "").strip().upper()
    if len(parts) != 2 or not team: return ""
    if team == parts[0]: return parts[1]
    if team == parts[1]: return parts[0]
    return ""

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
    raw = ((l5_hr*9)+(l10_hr*4.5)+(barrel*0.85)+(hard_hit*0.18)+(fly_ball*0.16)+(pull*0.10)+(iso*42)+(split_woba*18)+lineup_bonus)*0.55
    return make_candidate(category="HR", line="HR 1+", raw_score=raw,
        reason=short_reason([f"L5 HR {int(l5_hr)}", f"barrel {barrel:.1f}%", f"ISO {iso:.3f}"]),
        stats={"l5_hr": l5_hr, "l10_hr": l10_hr, "barrel_rate": barrel})

def score_mlb_tb(h: Dict[str, Any]) -> CandidateScore:
    l5_tb = safe_num(h.get("l5_tb_avg"))
    l10_tb = safe_num(h.get("l10_tb_avg"))
    xbh = safe_num(h.get("xbh_rate"))
    avg = safe_num(h.get("avg"))
    hard_hit = safe_num(h.get("hard_hit_rate"))
    split_woba = safe_num(h.get("split_woba"))
    lineup_spot = safe_num(h.get("lineup_spot"), 9)
    lineup_bonus = 5 if lineup_spot <= 4 else 2 if lineup_spot <= 6 else 0
    raw = ((l5_tb*18)+(l10_tb*9)+(xbh*32)+(avg*55)+(hard_hit*0.20)+(split_woba*18)+lineup_bonus)*0.55
    return make_candidate(category="TB", line="1.5 TB", raw_score=raw,
        reason=short_reason([f"L5 TB {l5_tb:.1f}", f"AVG {avg:.3f}", f"XBH {xbh:.2f}"]),
        stats={"l5_tb_avg": l5_tb, "l10_tb_avg": l10_tb, "avg": avg})

def score_mlb_hit(h: Dict[str, Any]) -> CandidateScore:
    l5 = safe_num(h.get("l5_hits"))
    l10 = safe_num(h.get("l10_hits"))
    avg = safe_num(h.get("avg"))
    split_woba = safe_num(h.get("split_woba"))
    lineup_spot = safe_num(h.get("lineup_spot"), 9)
    lineup_bonus = 5 if lineup_spot <= 3 else 2 if lineup_spot <= 6 else 0
    raw = ((l5/5*36)+(l10/10*24)+(avg*70)+(split_woba*20)+lineup_bonus)*0.55
    return make_candidate(category="HIT", line="1+ Hit", raw_score=raw,
        reason=short_reason([f"L5 {int(l5)}/5", f"L10 {int(l10)}/10", f"AVG {avg:.3f}"]),
        stats={"l5_hits": l5, "l10_hits": l10, "avg": avg})

def score_mlb_k(p: Dict[str, Any]) -> CandidateScore:
    k_line = int(safe_num(p.get("k_line"), 6))
    l5_k = safe_num(p.get("l5_k_avg"))
    l10_k = safe_num(p.get("l10_k_avg"))
    innings = safe_num(p.get("innings_avg"))
    opp_k = safe_num(p.get("opp_k_rate"))
    penalty = safe_num(p.get("opp_contact_penalty"))
    raw = ((l5_k*5.5)+(l10_k*3.5)+(innings*6)+(opp_k*0.95)-(penalty*4))*0.55
    return make_candidate(category="K", line=f"{k_line}+ K", raw_score=raw,
        reason=short_reason([f"L5 K {l5_k:.1f}", f"IP {innings:.1f}", f"opp K% {opp_k:.1f}"]),
        stats={"k_line": k_line, "l5_k_avg": l5_k, "innings_avg": innings})

def choose_best_hitter_category(h: Dict[str, Any]) -> Optional[CandidateScore]:
    candidates = [c for c in [score_mlb_hr(h), score_mlb_tb(h), score_mlb_hit(h)] if c.score >= MIN_HITTER_SCORE]
    if not candidates: return None
    candidates.sort(key=lambda c: (c.score, CATEGORY_PRIORITY.get(c.category, 0)), reverse=True)
    return candidates[0]

def choose_best_pitcher_category(p: Dict[str, Any]) -> Optional[CandidateScore]:
    k = score_mlb_k(p)
    return k if k.score >= MIN_PITCHER_SCORE else None

def board_play_from_pick(pick: Dict[str, Any], category: str) -> Optional[BoardPlay]:
    if category == "HR":
        score = normalize_score_model(safe_num(pick.get("score")))
        line = recommendation_line(pick.get("hr_rec"), "HR 1+")
        reason = short_reason([f"vs {pick.get('pitcher_name','Unknown')}", recommendation_reason(pick.get("hr_rec",""))])
    elif category == "TB":
        score = normalize_score_model(safe_num(pick.get("tb_score")))
        line = recommendation_line(pick.get("tb_rec"), "Over 1.5 TB")
        reason = short_reason([f"vs {pick.get('pitcher_name','Unknown')}", recommendation_reason(pick.get("tb_rec",""))])
    elif category == "HIT":
        score = normalize_score(normalize_score_model(safe_num(pick.get("tb_score"))) * 0.45)
        line = "1+ Hit"
        reason = short_reason([f"vs {pick.get('pitcher_name','Unknown')}", f"order {int(safe_num(pick.get('batting_order'),9))}"])
    elif category == "K":
        score = normalize_score_model(safe_num(pick.get("k_score")))
        line = recommendation_line(pick.get("k_rec"), "Over 5.5 Ks")
        reason = short_reason([str(pick.get("game","")), recommendation_reason(pick.get("k_rec",""))])
    else:
        return None
    if score < LONGSHOT_THRESHOLD: return None
    game_id = str(pick.get("game") or pick.get("game_id") or "")
    team = str(pick.get("team") or pick.get("pitcher_team") or "???")
    return BoardPlay(
        game_id=game_id, sport="MLB", team=team,
        opponent=str(pick.get("opp_team") or opponent_from_game(game_id, team)),
        player_name=str(pick.get("name") or pick.get("player_name") or "Unknown"),
        category=category, line=line, confidence=score_to_confidence(score),
        score=score, tier=assign_mlb_tier(score), reason=reason, stats=dict(pick),
    )

def dedupe_one_line_per_player(plays: List[BoardPlay]) -> List[BoardPlay]:
    best: Dict[str, BoardPlay] = {}
    for play in plays:
        cur = best.get(play.player_name)
        if cur is None or play.score > cur.score:
            best[play.player_name] = play
    return list(best.values())

def build_game_board_from_results(results: Dict[str, Any], max_plays_per_game: int = MAX_PLAYS_PER_GAME) -> Dict[str, List[BoardPlay]]:
    board: Dict[str, List[BoardPlay]] = defaultdict(list)
    for cat, key in [("HR","hr_picks"),("TB","tb_picks"),("HIT","tb_picks"),("K","k_picks")]:
        for pick in results.get(key, []) or []:
            play = board_play_from_pick(pick, cat)
            if play: board[play.game_id].append(play)
    final: Dict[str, List[BoardPlay]] = {}
    for gid, plays in board.items():
        deduped = dedupe_one_line_per_player(plays)
        ranked = sorted(deduped, key=lambda p: (p.score, CATEGORY_PRIORITY.get(p.category,0)), reverse=True)
        final[gid] = ranked[:max_plays_per_game]
    return final

def build_game_board(hitters, pitchers, basketball_players=None):
    board: Dict[str, List[BoardPlay]] = defaultdict(list)
    for h in hitters:
        if str(h.get("sport","MLB")).upper() != "MLB": continue
        best = choose_best_hitter_category(h)
        if not best: continue
        board[h["game_id"]].append(BoardPlay(
            game_id=h["game_id"], sport="MLB", team=h["team"], opponent=h["opponent"],
            player_name=h["player_name"], category=best.category, line=best.line,
            confidence=best.confidence, score=best.score, tier=assign_mlb_tier(best.score),
            reason=best.reason, stats=best.stats,
        ))
    for p in pitchers:
        if str(p.get("sport","MLB")).upper() != "MLB": continue
        best = choose_best_pitcher_category(p)
        if not best: continue
        board[p["game_id"]].append(BoardPlay(
            game_id=p["game_id"], sport="MLB", team=p["team"], opponent=p["opponent"],
            player_name=p["player_name"], category=best.category, line=best.line,
            confidence=best.confidence, score=best.score, tier=assign_mlb_tier(best.score),
            reason=best.reason, stats=best.stats,
        ))
    final: Dict[str, List[BoardPlay]] = {}
    for gid, plays in board.items():
        deduped = dedupe_one_line_per_player(plays)
        ranked = sorted(deduped, key=lambda p: (p.score, CATEGORY_PRIORITY.get(p.category,0)), reverse=True)
        final[gid] = ranked[:MAX_PLAYS_PER_GAME]
    return final

def filter_board_by_team(board, team_command):
    from typing import Optional
    normalized = str(team_command or "").strip().lower().lstrip("/").replace("-","_").replace(" ","_")
    if not normalized: return board
    team = normalized.upper() if normalized.upper() in set(MLB_TEAM_ALIASES.values()) else MLB_TEAM_ALIASES.get(normalized)
    if not team: return board
    return {gid: plays for gid, plays in board.items()
            if any(p.team.upper()==team or p.opponent.upper()==team for p in plays)
            or team in {part.upper() for part in str(gid).replace(" ","").split("@")}}

def format_score(score: float) -> str:
    return f"{score:.1f}/50"

def format_game_board(board, team_filter=None, slate_name=None):
    if team_filter: board = filter_board_by_team(board, team_filter)
    lines = []
    if slate_name: lines += [f"# {slate_name}", ""]
    for gid, plays in board.items():
        if not plays: continue
        lines.append(f"## {gid}")
        for p in plays:
            lines.append(f"{p.category} {p.player_name} ({p.team}) - {p.line} - {format_score(p.score)} [{p.tier}]")
            lines.append(f"   vs {p.opponent} | {p.reason}")
        lines.append("")
    return "\n".join(lines).strip()

def format_full_slate_board(board, slate_name="MLB Per-Game Board"):
    return format_game_board(board, slate_name=slate_name)

def category_icon(category: str) -> str:
    return {"HR":"HR","TB":"TB","HIT":"HIT","K":"K","AST":"AST","REB":"REB","3PM":"3PM","PTS":"PTS","PRA":"PRA"}.get(category,"*")

def build_hr_stack_view(hitters):
    grouped: Dict[str, List[BoardPlay]] = defaultdict(list)
    for h in hitters:
        if str(h.get("sport","MLB")).upper() != "MLB": continue
        hr = score_mlb_hr(h)
        if hr.score < MIN_HITTER_SCORE: continue
        grouped[h["game_id"]].append(BoardPlay(
            game_id=h["game_id"], sport="MLB", team=h["team"], opponent=h["opponent"],
            player_name=h["player_name"], category="HR", line="HR 1+",
            confidence=hr.confidence, score=hr.score, tier=assign_mlb_tier(hr.score),
            reason=hr.reason, stats=hr.stats,
        ))
    results = {}
    for gid, plays in grouped.items():
        ranked = sorted(plays, key=lambda p: p.score, reverse=True)
        results[gid] = {
            "pick_of_day": ranked[:1],
            "core": [p for p in ranked if p.tier=="CORE"][:MAX_HR_CORE],
            "strong": [p for p in ranked if p.tier=="STRONG"][:MAX_HR_STRONG],
            "value": [p for p in ranked if p.tier=="VALUE"][:MAX_HR_VALUE],
            "longshot": [p for p in ranked if p.tier=="LONGSHOT"][:MAX_HR_LONGSHOT],
        }
    return results
