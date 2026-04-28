import json

INPUT_FILE = "board-data.json"
OUTPUT_FILE = "board-data.json"

MAX_PLAYERS_PER_GAME = 4
MAX_PLAYERS_PER_TEAM = 3
TOP_N = 10

def collect_hr_candidates(data):
    candidates = []
    mlb = data.get("sports", {}).get("mlb", {})
    games = mlb.get("games", [])

    for game in games:
        game_title = game.get("title", "")
        game_id = game.get("id", game_title)

        for p in game.get("roster", []):
            if str(p.get("market", "")).upper() != "HR":
                continue

            candidates.append({
                "player": p.get("player"),
                "team": p.get("team"),
                "opponent": game_title,
                "game_key": game_id,
                "line": p.get("line", "HR 1+"),
                "score": float(p.get("score", 0) or 0),
                "confidence": p.get("confidence"),
                "tier": p.get("tier"),
                "status": p.get("status"),
                "why": p.get("why"),
                "last10": p.get("last10"),
                "last5": p.get("last5")
            })

    return candidates

def build_daily_hr_top_10(candidates):
    ranked = sorted(candidates, key=lambda x: x["score"], reverse=True)

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
            "rank": len(board) + 1,
            "player": p.get("player"),
            "team": team,
            "opponent": p.get("opponent"),
            "line": p.get("line"),
            "hr_edge_score": round(p.get("score", 0), 1),
            "confidence": p.get("confidence"),
            "tier": p.get("tier"),
            "status": p.get("status"),
            "why": p.get("why"),
            "last10": p.get("last10"),
            "last5": p.get("last5")
        })

        game_counts[game] = game_counts.get(game, 0) + 1
        team_counts[team] = team_counts.get(team, 0) + 1

        if len(board) == TOP_N:
            break

    return board

def main():
    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    candidates = collect_hr_candidates(data)
    data["daily_hr_top_10"] = build_daily_hr_top_10(candidates)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    print(f"Daily HR Top 10 injected into board-data.json ({len(data['daily_hr_top_10'])} plays)")

if __name__ == "__main__":
    main()
