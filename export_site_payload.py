import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

trend_path = Path("public/data/nba-trend-board.json")

if trend_path.exists():
    source = json.loads(trend_path.read_text(encoding="utf-8"))
else:
    source = json.loads(Path("board-data.json").read_text(encoding="utf-8"))

rows = source.get("trend_rows", [])

payload = {
    "updatedAt": datetime.now(ZoneInfo("America/New_York")).isoformat(),
    "sourceMode": "Generated site payload",
    "sports": ["nba"],
    "games": [],
    "plays": [
        {
            "player": r.get("player", ""),
            "team": r.get("team", "NBA"),
            "market": r.get("market", ""),
            "line": r.get("line", ""),
            "score": 50,
            "tier": "Trend",
            "confidence": 50,
            "last10": r.get("l10", ""),
            "last5": r.get("l5", ""),
            "last3": r.get("l3", ""),
            "last1": r.get("l1", ""),
            "season": r.get("season", ""),
            "status": "Active",
            "why": "Trend board row"
        }
        for r in rows
    ],
    "highlights": [],
    "notes": source.get("notes", [])
}

Path("board-data.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
Path("web/board-data.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")

print(f"Wrote {len(payload['plays'])} plays to board-data.json and web/board-data.json")