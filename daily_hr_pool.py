import json
import sys
import requests
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path

BOARD_FILE = Path("board-data.json")
WEB_BOARD_FILE = Path("web/board-data.json")
SEASON = datetime.now().year
TODAY = datetime.now(ZoneInfo("America/New_York")).strftime("%Y-%m-%d")

MLB_API = "https://statsapi.mlb.com/api/v1"
TOP_N = 10

def get_today_games():
    url = f"{MLB_API}/schedule"
    params = {
        "sportId": 1,
        "date": TODAY,
        "hydrate": "team"
    }

    r = requests.get(url, params=params, timeout=20)
    r.raise_for_status()
    data = r.json()

    games = []
    for date_block in data.get("dates", []):
        for g in date_block.get("games", []):
            status = g.get("status", {}).get("detailedState", "")
            if "Final" in status:
                continue

            away = g["teams"]["away"]["team"]
            home = g["teams"]["home"]["team"]

            games.append({
                "gamePk": g.get("gamePk"),
                "away_id": away.get("id"),
                "away": away.get("abbreviation"),
                "home_id": home.get("id"),
                "home": home.get("abbreviation"),
                "matchup": f"{away.get('abbreviation')} @ {home.get('abbreviation')}",
                "status": status
            })

    return games

def get_active_roster(team_id):
    url = f"{MLB_API}/teams/{team_id}/roster"
    params = {"rosterType": "active"}

    r = requests.get(url, params=params, timeout=20)
    r.raise_for_status()

    players = []
    for row in r.json().get("roster", []):
        person = row.get("person", {})
        position = row.get("position", {}).get("abbreviation", "")

        if position == "P":
            continue

        players.append({
            "id": person.get("id"),
            "name": person.get("fullName")
        })

    return players

def get_hitting_stats(player_id):
    url = f"{MLB_API}/people/{player_id}/stats"
    params = {
        "stats": "season",
        "group": "hitting",
        "season": SEASON
    }

    try:
        r = requests.get(url, params=params, timeout=15)
        r.raise_for_status()
        splits = r.json().get("stats", [{}])[0].get("splits", [])
        if not splits:
            return {}

        return splits[0].get("stat", {})
    except Exception:
        return {}

def build_daily_hr_pool():
    games = get_today_games()

    if not games:
        print("ERROR: No active/scheduled MLB games found today. Aborting.")
        sys.exit(1)

    candidates = []

    for game in games:
        for side, team_id, team_abbr, opp_abbr in [
            ("away", game["away_id"], game["away"], game["home"]),
            ("home", game["home_id"], game["home"], game["away"]),
        ]:
            roster = get_active_roster(team_id)

            for p in roster:
                stats = get_hitting_stats(p["id"])

                hrs = int(stats.get("homeRuns", 0) or 0)
                slg = float(stats.get("slg", 0) or 0)
                ops = float(stats.get("ops", 0) or 0)
                at_bats = int(stats.get("atBats", 0) or 0)

                if at_bats < 20:
                    continue

                score = (hrs * 5) + (slg * 25) + (ops * 10)

                candidates.append({
                    "player": p["name"],
                    "team": team_abbr,
                    "opponent": opp_abbr,
                    "matchup": game["matchup"],
                    "line": "HR 1+",
                    "season_hr": hrs,
                    "slg": slg,
                    "ops": ops,
                    "hr_edge_score": round(score, 1),
                    "status": game["status"],
                    "why": f"{hrs} HR this season | {game['matchup']}"
                })

    ranked = sorted(
        candidates,
        key=lambda x: (x["season_hr"], x["hr_edge_score"]),
        reverse=True
    )

    top_10 = ranked[:TOP_N]

    for i, p in enumerate(top_10, start=1):
        p["rank"] = i

    return top_10

def main():
    if not BOARD_FILE.exists():
        print("ERROR: board-data.json not found.")
        sys.exit(1)

    with open(BOARD_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    top_10 = build_daily_hr_pool()

    if not top_10:
        print("ERROR: Daily HR pool came back empty. Existing board not overwritten.")
        sys.exit(1)

    data.setdefault("sports", {}).setdefault("mlb", {})["daily_hr_top_10"] = top_10
    data.pop("daily_hr_top_10", None)

    with open(BOARD_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    if WEB_BOARD_FILE.parent.exists():
        with open(WEB_BOARD_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    print(f"SUCCESS: MLB Daily HR Top 10 built from today's slate: {TODAY}")
    for p in top_10:
        print(f"{p['rank']}. {p['player']} {p['team']} - {p['season_hr']} HR")

if __name__ == "__main__":
    main()
