import json

INPUT_FILE = "board-data.json"
OUTPUT_FILE = "board-data.json"  # overwrite existing payload

MAX_PLAYERS_PER_GAME = 4
MAX_PLAYERS_PER_TEAM = 3
TOP_N = 10

def calc_hr_edge(p):
    return (
        p.get("power_score", 0) * 0.30 +
        p.get("barrel_score", 0) * 0.25 +
        p.get("pitcher_damage_score", 0) * 0.20 +
        p.get("park_weather_score", 0) * 0.15 +
        p.get("lineup_spot_score", 0) * 0.10
    )

def build_daily_hr_top_10(hitters):
    for p in hitters:
        p["hr_edge_score"] = round(calc_hr_edge(p), 2)

    ranked = sorted(hitters, key=lambda x: x["hr_edge_score"], reverse=True)

    board = []
    game_counts = {}
    team_counts = {}

    for p in ranked:
        game = p.get("game_key")
        team = p.get("team")

        if game_counts.get(game, 0) >= MAX_PLAYERS_PER_GAME:
            continue

        if team_counts.get(team, 0) >= MAX_PLAYERS_PER_TEAM:
            continue

        board.append({
            "player": p.get("name"),
            "team": team,
            "opponent": p.get("opponent"),
            "hr_edge_score": p["hr_edge_score"]
        })

        game_counts[game] = game_counts.get(game, 0) + 1
        team_counts[team] = team_counts.get(team, 0) + 1

        if len(board) == TOP_N:
            break

    return board

def main():
    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    hitters = data.get("hitters", [])

    data["daily_hr_top_10"] = build_daily_hr_top_10(hitters)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    print("HR Top 10 injected into board-data.json")

if __name__ == "__main__":
    main()
