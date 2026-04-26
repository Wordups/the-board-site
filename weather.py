# validators.py
"""
Pre-scoring validation gates. Enforces session rules 1-3:
  - Game state (skip Final/Live/Postponed)
  - Confirmed starters (drop TBD pitchers)
  - Confirmed lineups (9-man batting order posted)
  - Injury scrub (drop IL / Day-to-Day)
  - Team sanity (catches the Peralta-as-CHC bug)

Every gate fails loud with a reason. No silent drops.
"""
import requests
from datetime import datetime
from zoneinfo import ZoneInfo

MLB_API      = "https://statsapi.mlb.com/api/v1"
MLB_API_LIVE = "https://statsapi.mlb.com/api/v1.1"

DEAD_STATUSES = {"Final", "Game Over", "Completed Early", "Postponed",
                 "Cancelled", "Suspended", "Delayed Start"}
LIVE_STATUSES = {"In Progress", "Manager Challenge", "Review", "Warmup"}
SCRATCH_STATUSES = {"Out", "Day-To-Day", "10-Day IL", "15-Day IL", "60-Day IL",
                    "7-Day IL", "Bereavement List", "Paternity List",
                    "Restricted List", "Suspended"}


# ── Game state ────────────────────────────────────────────────────────────────

def is_game_bettable(game):
    status = game.get("status", {}).get("detailedState", "")
    if status in DEAD_STATUSES:
        return False, f"game_dead:{status}"
    if status in LIVE_STATUSES:
        return False, f"game_live:{status}"
    abstract = game.get("status", {}).get("abstractGameState", "")
    if abstract in {"Final", "Live"}:
        return False, f"game_{abstract.lower()}"
    return True, "ok"


# ── Confirmed starter (Rule 2 — deGrom vs Leiter) ─────────────────────────────

def _fetch_pitcher_hand(pid):
    """Schedule hydrate often omits pitchHand. Fetch from /people endpoint."""
    try:
        resp = requests.get(f"{MLB_API}/people/{pid}", timeout=10)
        resp.raise_for_status()
        people = resp.json().get("people", [])
        if people:
            return people[0].get("pitchHand", {}).get("code")
    except Exception as e:
        print(f"[WARN] Could not fetch hand for pitcher {pid}: {e}")
    return None


def pitcher_is_confirmed(game, side):
    """Returns (ok, pid, name, hand, reason). TBD/missing = fail the game."""
    team = game.get("teams", {}).get(side, {})
    p = team.get("probablePitcher", {})
    pid = p.get("id")
    name = p.get("fullName")
    if not pid or not name or name == "TBD":
        return False, None, None, None, f"{side}_pitcher_unconfirmed"
    hand = p.get("pitchHand", {}).get("code") or _fetch_pitcher_hand(pid) or "R"
    return True, pid, name, hand, "ok"


# ── Confirmed lineup (Rule 2b — no projected lineups allowed) ────────────────

def get_confirmed_lineup(game_pk, side):
    """Returns (lineup_list, is_confirmed, reason). Requires 9 posted."""
    try:
        resp = requests.get(f"{MLB_API_LIVE}/game/{game_pk}/feed/live", timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        return [], False, f"fetch_failed:{e}"

    detailed = data.get("gameData", {}).get("status", {}).get("detailedState", "")
    box = data.get("liveData", {}).get("boxscore", {})
    team = box.get("teams", {}).get(side, {})
    batting_order = team.get("battingOrder", [])
    players = team.get("players", {})

    if len(batting_order) < 9:
        return [], False, f"lineup_not_posted:{detailed}"

    lineup = []
    for order, pid in enumerate(batting_order, 1):
        p = players.get(f"ID{pid}", {})
        person = p.get("person", {})
        bat_side = p.get("batSide", {}).get("code", "R")
        status_code = p.get("status", {}).get("code", "A")
        lineup.append({
            "playerId": pid,
            "name": person.get("fullName", "Unknown"),
            "battingOrder": order,
            "batSide": bat_side,
            "status_code": status_code,
        })
    return lineup, True, "ok"


# ── Injury scrub (Rule 3 — Rutschman void) ───────────────────────────────────

def get_team_injuries(team_id):
    """Return set of playerIds currently IL / DTD / unavailable."""
    injured_ids = set()
    try:
        url = f"{MLB_API}/teams/{team_id}/roster?rosterType=fullRoster"
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        for entry in resp.json().get("roster", []):
            status = entry.get("status", {}).get("description", "")
            if status in SCRATCH_STATUSES:
                injured_ids.add(entry.get("person", {}).get("id"))
    except Exception as e:
        print(f"[WARN] Injury pull failed for team {team_id}: {e}")
    return injured_ids


def scrub_injuries(lineup, injured_ids):
    """Drop injured / inactive players. Returns (clean, dropped_names)."""
    clean, dropped = [], []
    for p in lineup:
        if p["playerId"] in injured_ids or p.get("status_code") != "A":
            dropped.append(p["name"])
        else:
            clean.append(p)
    return clean, dropped


# ── Team-assignment sanity check ──────────────────────────────────────────────

def assert_team_assignment(pick, game):
    valid = {game["homeTeam"], game["awayTeam"]}
    if pick.get("team") not in valid:
        return False, f"team_mismatch:{pick.get('team')}_not_in_{valid}"
    return True, "ok"


# ── Bettable-games fetcher ────────────────────────────────────────────────────

def fetch_bettable_games(game_date=None):
    """Pull slate, drop dead/live games, drop games w/o confirmed pitchers."""
    if game_date is None:
        game_date = datetime.now(ZoneInfo("America/New_York")).strftime("%Y-%m-%d")

    url = (f"{MLB_API}/schedule?sportId=1&date={game_date}"
           f"&hydrate=probablePitcher,team,venue,linescore")
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    bettable, drops = [], []
    for date_entry in data.get("dates", []):
        for g in date_entry.get("games", []):
            ok, reason = is_game_bettable(g)
            if not ok:
                drops.append({"game": g.get("gamePk"), "reason": reason})
                continue
            h_ok, h_pid, h_name, h_hand, h_reason = pitcher_is_confirmed(g, "home")
            a_ok, a_pid, a_name, a_hand, a_reason = pitcher_is_confirmed(g, "away")
            if not h_ok or not a_ok:
                drops.append({"game": g.get("gamePk"),
                              "reason": f"pitcher_unconfirmed:{h_reason}|{a_reason}"})
                continue

            home = g["teams"]["home"]
            away = g["teams"]["away"]
            bettable.append({
                "gamePk":          g["gamePk"],
                "homeTeam":        home["team"].get("abbreviation", "???"),
                "awayTeam":        away["team"].get("abbreviation", "???"),
                "homeTeamId":      home["team"]["id"],
                "awayTeamId":      away["team"]["id"],
                "homeTeamName":    home["team"].get("name", ""),
                "awayTeamName":    away["team"].get("name", ""),
                "gameTimeUTC":     g.get("gameDate", ""),
                "venueName":       g.get("venue", {}).get("name", ""),
                "venueId":         g.get("venue", {}).get("id"),
                "homePitcherId":   h_pid,
                "homePitcherName": h_name,
                "homePitcherHand": h_hand,
                "awayPitcherId":   a_pid,
                "awayPitcherName": a_name,
                "awayPitcherHand": a_hand,
            })
    return bettable, drops
