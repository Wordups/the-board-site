from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional
from zoneinfo import ZoneInfo

from board_logic import build_game_board_from_results, board_play_from_pick
from nba_model import run_nba_model
from run_daily import run as run_mlb_pipeline


ET = ZoneInfo("America/New_York")


def _now_label() -> str:
    return datetime.now(ET).strftime("%B %d, %Y")


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return default
        return float(value)
    except Exception:
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value in (None, ""):
            return default
        return int(value)
    except Exception:
        return default


def _normalize_market(value: str) -> str:
    return str(value or "").strip().lower()


def _title_market(value: str) -> str:
    token = str(value or "").strip().upper()
    return token or "PROP"


def _record(hits: Any, games: int) -> str:
    if hits in (None, ""):
        return "--"
    try:
        return f"{int(hits)}/{games}"
    except Exception:
        return "--"


def _avg_label(value: Any) -> str:
    if value in (None, ""):
        return "--"
    return f"{_safe_float(value):.1f} avg"


def _tb_label(value: Any) -> str:
    if value in (None, ""):
        return "--"
    return f"{_safe_int(value)} TB"


def _score_signal(score: float) -> str:
    if score >= 42:
        return "A"
    if score >= 36:
        return "B"
    if score >= 30:
        return "C"
    return "D"


def _format_game_time_utc(raw: Any) -> str:
    text = str(raw or "").strip()
    if not text:
        return "TBD"
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(ET)
        return dt.strftime("%-I:%M %p ET")
    except Exception:
        return text


def _extract_line_from_rec(rec: str, fallback: str) -> str:
    raw = str(rec or "").strip()
    if not raw:
        return fallback
    line = raw.split("·", 1)[0].strip()
    line = line.replace("🎯", "").strip()
    return line or fallback


def _extract_reason_from_rec(rec: str, fallback: str) -> str:
    raw = str(rec or "").strip()
    if "·" not in raw:
        return fallback
    return raw.split("·", 1)[1].strip() or fallback


def _mlb_game_lookup(results: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    lookup: Dict[str, Dict[str, Any]] = {}
    for game in results.get("games", []) or []:
        title = f"{game.get('awayTeam', 'AWAY')} @ {game.get('homeTeam', 'HOME')}"
        lookup[title] = game
    return lookup


def _mlb_row_from_pick(pick: Dict[str, Any], category: str) -> Optional[Dict[str, Any]]:
    play = board_play_from_pick(pick, category)
    if not play:
        return None

    stats = play.stats or {}
    if category == "HR":
        last10 = _record(stats.get("l10_hr"), 10)
        last5 = _record(stats.get("l5_hr"), 5)
        last3 = _record(stats.get("l3_hr"), 3)
    elif category == "HIT":
        last10 = _record(stats.get("l10_hits"), 10)
        last5 = _record(stats.get("l5_hits"), 5)
        last3 = _record(stats.get("l3_hits"), 3)
    elif category == "TB":
        last10 = _tb_label(stats.get("l10_tb"))
        last5 = _tb_label(stats.get("l5_tb"))
        last3 = _tb_label(stats.get("l3_tb"))
    else:
        last10 = _avg_label(stats.get("l10_k_avg"))
        last5 = _avg_label(stats.get("l5_k_avg"))
        last3 = "--"

    return {
        "player": play.player_name,
        "team": play.team,
        "market": play.category,
        "line": play.line,
        "score": round(play.score, 1),
        "tier": play.tier,
        "confidence": play.confidence,
        "last10": last10,
        "last5": last5,
        "last3": last3,
        "status": "Probable starter" if play.category == "K" else "Confirmed lineup",
        "why": play.reason,
        "sort_score": play.score,
    }


def _build_mlb_games(results: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows_by_game: Dict[str, List[Dict[str, Any]]] = defaultdict(list)

    for pick in results.get("hr_picks", []) or []:
        row = _mlb_row_from_pick(pick, "HR")
        if row:
            rows_by_game[str(pick.get("game") or "")].append(row)

    for pick in results.get("tb_picks", []) or []:
        row = _mlb_row_from_pick(pick, "TB")
        if row:
            rows_by_game[str(pick.get("game") or "")].append(row)

        hit_row = _mlb_row_from_pick(pick, "HIT")
        if hit_row:
            rows_by_game[str(pick.get("game") or "")].append(hit_row)

    for pick in results.get("k_picks", []) or []:
        row = _mlb_row_from_pick(pick, "K")
        if row:
            rows_by_game[str(pick.get("game") or "")].append(row)

    board = build_game_board_from_results(results)
    game_lookup = _mlb_game_lookup(results)
    games: List[Dict[str, Any]] = []

    # IMPORTANT:
    # Build cards from the full slate, not only rows_by_game.
    # rows_by_game only contains games with playable picks.
    # game_lookup contains the slate games returned by the pipeline.
    for title, lookup in game_lookup.items():
        rows = rows_by_game.get(title, [])
        rows_sorted = sorted(rows, key=lambda row: row["sort_score"], reverse=True)
        top_board = board.get(title, [])

        top_picks = [
            {
                "name": play.player_name,
                "market": play.category,
                "why": play.reason,
                "tier": play.tier.title(),
                "confidence": play.confidence,
                "line": play.line,
            }
            for play in top_board[:4]
        ] or [
            {
                "name": row["player"],
                "market": row["market"],
                "why": row["why"],
                "tier": str(row["tier"]).title(),
                "confidence": row["confidence"],
                "line": row["line"],
            }
            for row in rows_sorted[:4]
        ]

        avg_score = (
            round(sum(row["sort_score"] for row in rows_sorted) / len(rows_sorted), 1)
            if rows_sorted
            else 0.0
        )
        core_count = sum(1 for row in rows_sorted if str(row["tier"]).upper() == "CORE")
        top_markets = ", ".join(dict.fromkeys(row["market"] for row in rows_sorted[:3]))

        away_pitcher = lookup.get("awayPitcherName") or "TBD"
        home_pitcher = lookup.get("homePitcherName") or "TBD"
        pitcher_confirmed = away_pitcher != "TBD" and home_pitcher != "TBD"

        if rows_sorted:
            status = "Confirmed lineups"
            lineup_status = "Confirmed lineup data loaded"
            attack_note = f"Best signal lane: {top_markets}. Click through for the full tracked board."
        elif pitcher_confirmed:
            status = "Pitchers confirmed"
            lineup_status = "Pitchers locked, lineup pending"
            attack_note = "Early form board active. Signals upgrade when batting orders confirm."
        else:
            status = "Early form board"
            lineup_status = "Awaiting pitchers and lineups"
            attack_note = "Early form board active. Signals upgrade when pitchers and batting orders confirm."

        games.append(
            {
                "id": str(lookup.get("gamePk") or title),
                "title": title,
                "start": _format_game_time_utc(lookup.get("gameTimeUTC")),
                "status": status,
                "meta": f"{away_pitcher} vs {home_pitcher}",
                "attackNote": attack_note,
                "lineupStatus": lineup_status,
                "summary": {
                    "plays": len(rows_sorted),
                    "core": core_count,
                    "avgScore": f"{avg_score:.1f}",
                    "signal": _score_signal(avg_score),
                },
                "topPicks": top_picks,
                "roster": [
                    {
                        key: value
                        for key, value in row.items()
                        if key != "sort_score"
                    }
                    for row in rows_sorted
                ],
            }
        )

    games.sort(
        key=lambda game: (
            len(game.get("roster", [])) == 0,
            game.get("start", "TBD"),
        )
    )
    return games


def _build_mlb_sport(game_date: Optional[str]) -> Dict[str, Any]:
    try:
        results = run_mlb_pipeline(game_date=game_date, screenshot_path=None, verbose=False)
    except Exception as exc:
        return {
            "label": "MLB",
            "note": f"MLB pipeline error: {exc}",
            "launches": [],
            "notes": ["The MLB pipeline failed while building website data."],
            "pickOfDay": None,
            "filters": ["all", "hr", "tb", "hit", "k"],
            "games": [],
        }

    if not results:
        return {
            "label": "MLB",
            "note": "No playable MLB slate yet. Check again after lineups start confirming.",
            "launches": [],
            "notes": ["The MLB website feed stays empty until the validated slate has something real to show."],
            "pickOfDay": None,
            "filters": ["all", "hr", "tb", "hit", "k"],
            "games": [],
        }

    games = _build_mlb_games(results)
    pick_of_day = None
    if games and games[0]["topPicks"]:
        top_game = games[0]
        top_pick = top_game["topPicks"][0]
        pick_of_day = {
            "player": top_pick["name"],
            "team": top_game["title"],
            "market": top_pick["market"],
            "line": top_pick["line"],
            "score": f"{max((row['score'] for row in top_game['roster'] if row['player'] == top_pick['name'] and row['market'] == top_pick['market']), default=0):.1f}/50",
            "confidence": f"{top_pick['confidence']}%",
            "rate": next(
                (
                    f"L10 {row['last10']} | L5 {row['last5']} | L3 {row['last3']}"
                    for row in top_game["roster"]
                    if row["player"] == top_pick["name"] and row["market"] == top_pick["market"]
                ),
                "--",
            ),
            "environment": top_game["meta"],
            "summary": top_game["attackNote"],
        }

    return {
        "label": "MLB",
        "note": "Live MLB board from the validated model pipeline. Click a game for the full tracked slate.",
        "launches": [
            {"title": "Live API", "copy": "This board is now fed by the live MLB pipeline instead of sample bootstrap data."},
            {"title": "Game clustering", "copy": "Each matchup keeps a compressed top layer plus a deeper slate behind the click."},
            {"title": "Recent form", "copy": "Hit-rate columns use live MLB recent-form fields, including L3 when available."},
        ],
        "notes": [
            "If no lineups are confirmed yet, the board will stay sparse instead of inventing plays.",
            "Scores stay on the 0-50 scale from the tuned board logic.",
        ],
        "pickOfDay": pick_of_day,
        "filters": ["all", "hr", "tb", "hit", "k"],
        "games": games,
    }


def _nba_game_index(games: Iterable[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    lookup: Dict[str, Dict[str, Any]] = {}
    for game in games:
        away = str(game.get("away_team") or "")
        home = str(game.get("home_team") or "")
        if away:
            lookup[away] = game
        if home:
            lookup[home] = game
    return lookup


def _nba_recent_fields(pick: Dict[str, Any]) -> tuple[str, str, str]:
    recent_line = str(pick.get("recent_line") or "").strip()
    if recent_line:
        parts = [part.strip() for part in recent_line.split("|")]
        mapping: Dict[str, str] = {}
        for part in parts:
            if " " in part:
                key, value = part.split(" ", 1)
                mapping[key.strip().upper()] = value.strip()
        return (
            mapping.get("L10", "--"),
            mapping.get("L5", "--"),
            mapping.get("L3", "--"),
        )

    l10 = pick.get("l10")
    l5 = pick.get("l5")
    l1 = pick.get("l1")
    return (
        _avg_label(l10) if l10 not in (None, "") else "--",
        _avg_label(l5) if l5 not in (None, "") else "--",
        _avg_label(l1) if l1 not in (None, "") else "--",
    )


def _build_nba_games(results: Dict[str, Any]) -> List[Dict[str, Any]]:
    games = results.get("games") or []
    game_lookup = _nba_game_index(games)
    rows_by_game: Dict[str, List[Dict[str, Any]]] = defaultdict(list)

    pick_groups = [
        ("pts_picks", "PTS"),
        ("ast_picks", "AST"),
        ("reb_picks", "REB"),
        ("three_picks", "3PM"),
    ]

    for group_key, market in pick_groups:
        for pick in results.get(group_key, []) or []:
            team = str(pick.get("team") or "").upper()
            game = game_lookup.get(team)
            if not game:
                continue
            last10, last5, last3 = _nba_recent_fields(pick)
            title = f"{game.get('away_team', 'AWAY')} @ {game.get('home_team', 'HOME')}"
            rows_by_game[title].append(
                {
                    "player": str(pick.get("name") or "Unknown"),
                    "team": team,
                    "market": market,
                    "line": _extract_line_from_rec(str(pick.get("rec") or ""), f"{market} play"),
                    "score": round(_safe_float(pick.get("score")), 1),
                    "tier": "Core" if _safe_float(pick.get("score")) >= 72 else "Value" if _safe_float(pick.get("score")) >= 58 else "Longshot",
                    "confidence": _safe_int(pick.get("conf")),
                    "last10": last10,
                    "last5": last5,
                    "last3": last3,
                    "status": "Available pool",
                    "why": _extract_reason_from_rec(str(pick.get("rec") or ""), str(pick.get("matchup") or "Model read")),
                    "sort_score": _safe_float(pick.get("score")),
                }
            )

    site_games: List[Dict[str, Any]] = []
    for game in games:
        title = f"{game.get('away_team', 'AWAY')} @ {game.get('home_team', 'HOME')}"
        rows = sorted(rows_by_game.get(title, []), key=lambda row: row["sort_score"], reverse=True)
        if not rows:
            continue
        avg_score = round(sum(row["sort_score"] for row in rows) / len(rows), 1)
        site_games.append(
            {
                "id": str(game.get("game_id") or title),
                "title": title,
                "start": str(game.get("status") or "Today"),
                "status": "Live board",
                "meta": str(game.get("status") or "Game on slate"),
                "attackNote": "Grouped by matchup so you can scan ladders and stable lanes from one screen.",
                "lineupStatus": "Availability filter applied",
                "summary": {
                    "plays": len(rows),
                    "core": sum(1 for row in rows if str(row["tier"]).lower() == "core"),
                    "avgScore": f"{avg_score:.1f}",
                    "signal": _score_signal(avg_score),
                },
                "topPicks": [
                    {
                        "name": row["player"],
                        "market": row["market"],
                        "why": row["why"],
                        "tier": str(row["tier"]).title(),
                        "confidence": row["confidence"],
                        "line": row["line"],
                    }
                    for row in rows[:4]
                ],
                "roster": [
                    {
                        key: value
                        for key, value in row.items()
                        if key != "sort_score"
                    }
                    for row in rows
                ],
            }
        )

    site_games.sort(key=lambda game: max((pick["confidence"] for pick in game["topPicks"]), default=0), reverse=True)
    return site_games


def _build_nba_sport(game_date: Optional[str]) -> Dict[str, Any]:
    try:
        results = run_nba_model(game_date=game_date, league="nba")
    except Exception as exc:
        return {
            "label": "NBA",
            "note": f"NBA pipeline error: {exc}",
            "launches": [],
            "notes": ["The NBA pipeline failed while building website data."],
            "pickOfDay": None,
            "filters": ["all", "pts", "ast", "reb", "3pm"],
            "games": [],
        }

    if not isinstance(results, dict) or results.get("error"):
        return {
            "label": "NBA",
            "note": str((results or {}).get("message") or "NBA slate is not ready yet."),
            "launches": [],
            "notes": ["NBA feed falls back safely when upstream data is thin."],
            "pickOfDay": None,
            "filters": ["all", "pts", "ast", "reb", "3pm"],
            "games": [],
        }

    games = _build_nba_games(results)
    pick_of_day = None
    if games and games[0]["topPicks"]:
        top_game = games[0]
        top_pick = top_game["topPicks"][0]
        pick_of_day = {
            "player": top_pick["name"],
            "team": top_game["title"],
            "market": top_pick["market"],
            "line": top_pick["line"],
            "score": f"{max((row['score'] for row in top_game['roster'] if row['player'] == top_pick['name'] and row['market'] == top_pick['market']), default=0):.1f}/100",
            "confidence": f"{top_pick['confidence']}%",
            "rate": next(
                (
                    f"L10 {row['last10']} | L5 {row['last5']} | L3 {row['last3']}"
                    for row in top_game["roster"]
                    if row["player"] == top_pick["name"] and row["market"] == top_pick["market"]
                ),
                "--",
            ),
            "environment": top_game["meta"],
            "summary": top_game["attackNote"],
        }

    return {
        "label": "NBA",
        "note": "Live NBA board grouped by game with availability filtering applied.",
        "launches": [
            {"title": "Live slate grouping", "copy": "NBA picks are grouped into the same clickable game view as MLB."},
            {"title": "Availability aware", "copy": "Inactive and out-of-pool players are filtered before the site payload is built."},
            {"title": "Best available recent form", "copy": "If recent hit-rate lines exist, they show. Otherwise the site falls back to recent averages."},
        ],
        "notes": [
            "This worktree still uses the existing NBA model output shape, so recent columns can vary by source quality.",
        ],
        "pickOfDay": pick_of_day,
        "filters": ["all", "pts", "ast", "reb", "3pm"],
        "games": games,
    }


def build_site_payload(game_date: Optional[str] = None) -> Dict[str, Any]:
    return {
        "updatedAt": _now_label(),
        "sourceMode": "Live website API",
        "sports": {
            "mlb": _build_mlb_sport(game_date),
            "nba": _build_nba_sport(game_date),
            "wnba": {
                "label": "WNBA",
                "note": "WNBA board will fill in here when the backend is ready.",
                "launches": [],
                "notes": [],
                "pickOfDay": None,
                "filters": ["all"],
                "games": [],
            },
            "soccer": {
                "label": "Soccer",
                "note": "Soccer props will plug into the same site payload once those feeds are wired.",
                "launches": [],
                "notes": [],
                "pickOfDay": None,
                "filters": ["all"],
                "games": [],
            },
            "highlights": {
                "label": "Highlights",
                "note": "Highlights stay separated from the board so the research surface stays clean.",
                "launches": [],
                "notes": [],
                "pickOfDay": None,
                "filters": ["all"],
                "games": [],
                "highlights": [
                    {
                        "sport": "nba",
                        "title": "NBA playoff highlights",
                        "source": "YouTube search feed",
                        "url": "https://www.youtube.com/embed?listType=search&q=NBA+playoff+highlights+2026",
                    },
                    {
                        "sport": "mlb",
                        "title": "MLB daily home run reel",
                        "source": "YouTube search feed",
                        "url": "https://www.youtube.com/embed?listType=search&q=MLB+home+run+highlights+2026",
                    },
                ],
            },
        },
    }
