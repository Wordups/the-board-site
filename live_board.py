from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List
from zoneinfo import ZoneInfo

import requests

from nba_model import LIVE_SCOREBOARD_URL


ET = ZoneInfo("America/New_York")
MLB_SCHEDULE_URL = "https://statsapi.mlb.com/api/v1/schedule"


def _now_label() -> str:
    return datetime.now(ET).strftime("%B %d, %Y %I:%M %p ET")


def _today_date() -> str:
    return datetime.now(ET).strftime("%Y-%m-%d")


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except Exception:
        return 0


def _format_et(value: str) -> str:
    if not value:
        return "TBD"
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(ET)
        return dt.strftime("%I:%M %p ET").lstrip("0")
    except Exception:
        return "TBD"


def _mlb_status(game: Dict[str, Any]) -> str:
    return str(game.get("status", {}).get("detailedState") or "Scheduled")


def _mlb_score(game: Dict[str, Any]) -> str:
    teams = game.get("teams", {})
    away = _safe_int(teams.get("away", {}).get("score"))
    home = _safe_int(teams.get("home", {}).get("score"))
    status = _mlb_status(game)
    if status == "Scheduled":
        return "0 - 0"
    return f"{away} - {home}"


def _build_mlb_games() -> List[Dict[str, Any]]:
    params = {
        "sportId": 1,
        "date": _today_date(),
        "hydrate": "linescore,team,venue",
    }
    response = requests.get(MLB_SCHEDULE_URL, params=params, timeout=15)
    response.raise_for_status()
    data = response.json()

    games: List[Dict[str, Any]] = []
    for date_entry in data.get("dates", []):
        for game in date_entry.get("games", []):
            away = game.get("teams", {}).get("away", {}).get("team", {})
            home = game.get("teams", {}).get("home", {}).get("team", {})
            games.append(
                {
                    "id": str(game.get("gamePk") or ""),
                    "matchup": f"{away.get('abbreviation', 'AWAY')} @ {home.get('abbreviation', 'HOME')}",
                    "sport": "MLB",
                    "status": _mlb_status(game),
                    "score": _mlb_score(game),
                    "start": _format_et(str(game.get("gameDate") or "")),
                    "detail": game.get("venue", {}).get("name") or "",
                }
            )
    return games


def _build_nba_games() -> List[Dict[str, Any]]:
    response = requests.get(LIVE_SCOREBOARD_URL, timeout=15)
    response.raise_for_status()
    data = response.json()
    scoreboard = data.get("scoreboard", {})

    games: List[Dict[str, Any]] = []
    for game in scoreboard.get("games", []):
        away = game.get("awayTeam", {})
        home = game.get("homeTeam", {})
        away_score = away.get("score") or "0"
        home_score = home.get("score") or "0"
        games.append(
            {
                "id": str(game.get("gameId") or ""),
                "matchup": f"{away.get('teamTricode', 'AWAY')} @ {home.get('teamTricode', 'HOME')}",
                "sport": "NBA",
                "status": game.get("gameStatusText") or str(game.get("gameStatus") or "Scheduled"),
                "score": f"{away_score} - {home_score}",
                "start": _format_et(str(game.get("gameEt") or "")),
                "detail": game.get("gameLabel") or "",
            }
        )
    return games


def build_live_board_payload() -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "updatedAt": _now_label(),
        "sports": {
            "mlb": {"label": "MLB", "games": [], "note": ""},
            "nba": {"label": "NBA", "games": [], "note": ""},
            "wnba": {"label": "WNBA", "games": [], "note": "WNBA live board not wired yet."},
            "soccer": {"label": "Soccer", "games": [], "note": "Soccer live board not wired yet."},
        },
    }

    try:
        payload["sports"]["mlb"]["games"] = _build_mlb_games()
    except Exception as exc:
        payload["sports"]["mlb"]["note"] = f"Unable to load MLB games: {exc}"

    try:
        payload["sports"]["nba"]["games"] = _build_nba_games()
    except Exception as exc:
        payload["sports"]["nba"]["note"] = f"Unable to load NBA games: {exc}"

    return payload
