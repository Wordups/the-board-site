from pathlib import Path

path = Path("site_payload.py")
text = path.read_text(encoding="utf-8")

fallback_func = r'''
def _build_fallback_hr_top10(results: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Fallback HR pool when no model HR picks exist.
    Uses any hitter/roster data already returned by run_mlb_pipeline().
    """
    if not results or not results.get("games"):
        return []

    hitters = []

    for game in results.get("games", []) or []:
        home_team = game.get("homeTeam") or game.get("home") or "TBD"
        away_team = game.get("awayTeam") or game.get("away") or "TBD"

        roster_sources = [
            (home_team, game.get("homeRoster") or []),
            (away_team, game.get("awayRoster") or []),
            (home_team, game.get("homeHitters") or []),
            (away_team, game.get("awayHitters") or []),
            ("TBD", game.get("roster") or []),
            ("TBD", game.get("hitters") or []),
        ]

        for team, roster in roster_sources:
            for hitter in roster:
                position = str(hitter.get("position") or hitter.get("pos") or "").upper()

                if position and position in {"P", "SP", "RP"}:
                    continue

                player = hitter.get("name") or hitter.get("player") or hitter.get("fullName")
                if not player:
                    continue

                home_runs = _safe_int(
                    hitter.get("homeRuns")
                    or hitter.get("hr")
                    or hitter.get("HR")
                    or 0
                )

                slugging = _safe_float(
                    hitter.get("slugging")
                    or hitter.get("slg")
                    or hitter.get("SLG")
                    or 0
                )

                hitters.append({
                    "player": player,
                    "team": hitter.get("team") or team,
                    "homeRuns": home_runs,
                    "slugging": slugging,
                    "last10": hitter.get("last10") or hitter.get("l10") or "--",
                    "last5": hitter.get("last5") or hitter.get("l5") or "--",
                    "last3": hitter.get("last3") or hitter.get("l3") or "--",
                })

    hitters.sort(key=lambda x: (x["homeRuns"], x["slugging"]), reverse=True)

    top_10 = hitters[:10]

    for i, row in enumerate(top_10, start=1):
        row["rank"] = i

    print(f"[MLB] Fallback HR pool hitters: {len(hitters)}")
    print(f"[MLB] Fallback Daily HR Top 10: {len(top_10)}")

    return top_10

'''

if "_build_fallback_hr_top10" not in text:
    marker = "def _build_mlb_sport(game_date: Optional[str]) -> Dict[str, Any]:"
    text = text.replace(marker, fallback_func + "\n" + marker)

old_return = '''        "pickOfDay": pick_of_day,
        "filters": ["all", "hr", "tb", "hit", "k"],
        "games": games,
    }'''

new_return = '''        "pickOfDay": pick_of_day,
        "filters": ["all", "hr", "tb", "hit", "k"],
        "games": games,
        "daily_hr_top_10": _build_fallback_hr_top10(results),
    }'''

if old_return not in text:
    raise SystemExit("Could not find MLB return block. Patch not applied.")

text = text.replace(old_return, new_return, 1)

path.write_text(text, encoding="utf-8")
print("Patched site_payload.py with MLB fallback Daily HR Top 10")
