"""
NBA/WNBA Daily Props Model

Primary schedule source:
- NBA CDN live/static schedule feeds

Secondary stats sources:
- stats.nba.com endpoints for player/team data

Goal:
- avoid false "No NBA games today" responses
- keep output compatible with bot.py / nba formatter
"""

from datetime import datetime
from statistics import mean
from zoneinfo import ZoneInfo
import math
import os
import requests


# ── Headers / URLs ────────────────────────────────────────

NBA_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://www.nba.com/",
    "Origin": "https://www.nba.com",
    "Accept": "application/json",
    "x-nba-stats-origin": "stats",
    "x-nba-stats-token": "true",
}

BASE = "https://stats.nba.com/stats"
LIVE_SCOREBOARD_URL = "https://cdn.nba.com/static/json/liveData/scoreboard/todaysScoreboard_00.json"
SCHEDULE_URLS = (
    "https://cdn.nba.com/static/json/staticData/scheduleLeagueV2_1.json",
    "https://cdn.nba.com/static/json/staticData/scheduleLeagueV2.json",
)

CURRENT_SEASON = "2025-26"
BALLDONTLIE_API_KEY = os.getenv("BALLDONTLIE_API_KEY", "").strip()
BALLDONTLIE_API_BASE = "https://api.balldontlie.io"
NBA_REQUEST_TIMEOUT = 10
NBA_DASHBOARD_TIMEOUT = 12
BALLDONTLIE_TIMEOUT = 6
BALLDONTLIE_PLAN_HINT = (
    "BALLDONTLIE Active Players requires ALL-STAR and Season Averages requires GOAT."
)


# ── Date Helpers ──────────────────────────────────────────

def _target_game_date(game_date=None):
    if game_date is None:
        return datetime.now(ZoneInfo("America/New_York")).date()

    raw = str(game_date).strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%Y %H:%M:%S", "%m/%d/%Y %I:%M:%S %p"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def _to_mmddyyyy(game_date=None):
    target = _target_game_date(game_date)
    if target is None:
        return None
    return target.strftime("%m/%d/%Y")


def _normalize_schedule_date(value):
    if not value:
        return None

    raw = str(value).strip()
    for fmt in (
        "%Y-%m-%d",
        "%m/%d/%Y",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%m/%d/%Y %H:%M:%S",
        "%m/%d/%Y %I:%M:%S %p",
    ):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue

    if "T" in raw:
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00")).date()
        except ValueError:
            pass

    return None


# ── Generic Helpers ───────────────────────────────────────

def safe_mean(values):
    vals = [v for v in values if v is not None]
    return round(mean(vals), 1) if vals else 0.0


def confidence(score, floor=25, ceiling=80):
    normalized = (score - 50) / 15
    prob = 1 / (1 + math.exp(-normalized))
    return min(ceiling, max(floor, round(floor + prob * (ceiling - floor))))


def matchup_label(score):
    if score >= 72:
        return "Strong"
    if score >= 58:
        return "Good"
    if score >= 45:
        return "Neutral"
    return "Thin"


def _request_json(url, params=None, timeout=NBA_REQUEST_TIMEOUT):
    resp = requests.get(url, headers=NBA_HEADERS, params=params, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def _balldontlie_request(path, params=None, timeout=BALLDONTLIE_TIMEOUT):
    if not BALLDONTLIE_API_KEY:
        raise RuntimeError("BALLDONTLIE_API_KEY is not set")

    headers = {"Authorization": BALLDONTLIE_API_KEY}
    resp = requests.get(
        f"{BALLDONTLIE_API_BASE}{path}",
        headers=headers,
        params=params,
        timeout=timeout,
    )
    resp.raise_for_status()
    return resp.json()


def _season_year_for_game_date(game_date=None):
    target = _target_game_date(game_date)
    if target is None:
        target = datetime.now(ZoneInfo("America/New_York")).date()
    return target.year if target.month >= 10 else target.year - 1


# ── Schedule Sources (CDN FIRST) ──────────────────────────

def _fallback_games_from_live_scoreboard(target_date):
    try:
        data = _request_json(LIVE_SCOREBOARD_URL)
    except Exception as e:
        print(f"[NBA] Live scoreboard fallback error: {e}")
        return []

    scoreboard = data.get("scoreboard", {})
    scoreboard_date = _normalize_schedule_date(scoreboard.get("gameDate"))
    if scoreboard_date != target_date:
        return []

    games = []
    for game in scoreboard.get("games", []):
        home = game.get("homeTeam", {})
        away = game.get("awayTeam", {})
        games.append({
            "game_id": game.get("gameId"),
            "home_team": home.get("teamTricode") or home.get("teamName") or str(home.get("teamId") or ""),
            "away_team": away.get("teamTricode") or away.get("teamName") or str(away.get("teamId") or ""),
            "home_team_id": home.get("teamId"),
            "away_team_id": away.get("teamId"),
            "status": game.get("gameStatusText") or str(game.get("gameStatus") or ""),
        })
    return games


def _fallback_games_from_schedule(target_date):
    for url in SCHEDULE_URLS:
        try:
            data = _request_json(url)
        except Exception as e:
            print(f"[NBA] Schedule fallback error from {url}: {e}")
            continue

        game_dates = data.get("leagueSchedule", {}).get("gameDates", [])
        for slate in game_dates:
            if _normalize_schedule_date(slate.get("gameDate")) != target_date:
                continue

            games = []
            for game in slate.get("games", []):
                home = game.get("homeTeam", {})
                away = game.get("awayTeam", {})
                games.append({
                    "game_id": game.get("gameId"),
                    "home_team": home.get("teamTricode") or home.get("teamName") or str(home.get("teamId") or ""),
                    "away_team": away.get("teamTricode") or away.get("teamName") or str(away.get("teamId") or ""),
                    "home_team_id": home.get("teamId"),
                    "away_team_id": away.get("teamId"),
                    "status": game.get("gameStatusText") or game.get("gameLabel") or "",
                })

            if games:
                return games

    return []


def get_todays_scoreboard(game_date=None):
    """
    Backward-compatible function name, but now CDN is primary.
    """
    target_date = _target_game_date(game_date)
    if target_date is None:
        print("[NBA] Invalid game date supplied.")
        return []

    games = _fallback_games_from_live_scoreboard(target_date)
    if games:
        print(f"[NBA] CDN live scoreboard found {len(games)} games")
        return games

    games = _fallback_games_from_schedule(target_date)
    if games:
        print(f"[NBA] CDN static schedule found {len(games)} games")
        return games

    mmddyyyy = _to_mmddyyyy(game_date)
    if not mmddyyyy:
        return []

    print(f"[NBA] CDN returned 0 games. Trying stats API for {mmddyyyy}")
    url = f"{BASE}/scoreboardv2"
    params = {
        "GameDate": mmddyyyy,
        "LeagueID": "00",
        "DayOffset": "0",
    }

    try:
        data = _request_json(url, params=params)
        result_sets = data.get("resultSets", [])
        if not result_sets:
            return []

        game_header = result_sets[0]
        headers = game_header.get("headers", [])
        rows = game_header.get("rowSet", [])

        games = []
        for row in rows:
            g = dict(zip(headers, row))
            games.append({
                "game_id": g.get("GAME_ID"),
                "home_team": g.get("HOME_TEAM_ABBREVIATION") or str(g.get("HOME_TEAM_ID") or ""),
                "away_team": g.get("VISITOR_TEAM_ABBREVIATION") or str(g.get("VISITOR_TEAM_ID") or ""),
                "home_team_id": g.get("HOME_TEAM_ID"),
                "away_team_id": g.get("VISITOR_TEAM_ID"),
                "status": g.get("GAME_STATUS_TEXT", ""),
            })

        print(f"[NBA] stats API found {len(games)} games")
        return games
    except Exception as e:
        print(f"[NBA] Stats scoreboard fallback error: {e}")
        return []


# ── Stats Pulls ───────────────────────────────────────────

def get_player_game_logs(team_id, season=CURRENT_SEASON, last_n=15):
    """
    Team game logs.
    Kept for compatibility / future use.
    """
    url = f"{BASE}/teamgamelog"
    params = {
        "TeamID": team_id,
        "Season": season,
        "SeasonType": "Playoffs",
        "LeagueID": "00",
    }

    try:
        data = _request_json(url, params=params)
        result = data["resultSets"][0]
        headers = result["headers"]
        rows = result["rowSet"]
        return [dict(zip(headers, row)) for row in rows[:last_n]]
    except Exception as e:
        print(f"[NBA] Team game log error (team {team_id}): {e}")

    try:
        params["SeasonType"] = "Regular Season"
        data = _request_json(url, params=params)
        result = data["resultSets"][0]
        headers = result["headers"]
        rows = result["rowSet"]
        return [dict(zip(headers, row)) for row in rows[:last_n]]
    except Exception as e:
        print(f"[NBA] Team game log fallback error (team {team_id}): {e}")
        return []


def get_players_for_game(game_id, season=CURRENT_SEASON):
    """
    Single-game boxscore.
    Kept for compatibility / future use.
    """
    url = f"{BASE}/boxscoretraditionalv2"
    params = {
        "GameID": game_id,
        "StartPeriod": "0",
        "EndPeriod": "10",
        "StartRange": "0",
        "EndRange": "28800",
        "RangeType": "0",
    }

    try:
        data = _request_json(url, params=params)
        player_stats = data["resultSets"][0]
        headers = player_stats["headers"]
        rows = player_stats["rowSet"]
        return [dict(zip(headers, row)) for row in rows]
    except Exception as e:
        print(f"[NBA] Boxscore error (game {game_id}): {e}")
        return []


def get_player_recent_logs(player_id, season=CURRENT_SEASON, last_n=10):
    """
    Player recent logs.
    Kept for compatibility / future use.
    """
    url = f"{BASE}/playergamelogs"
    params = {
        "PlayerID": player_id,
        "Season": season,
        "SeasonType": "Playoffs",
        "LeagueID": "00",
        "LastNGames": last_n,
    }

    try:
        data = _request_json(url, params=params)
        result = data["resultSets"][0]
        headers = result["headers"]
        rows = result["rowSet"]
        logs = [dict(zip(headers, row)) for row in rows]
        if logs:
            return logs
    except Exception as e:
        print(f"[NBA] Player logs error (player {player_id}): {e}")

    try:
        params["SeasonType"] = "Regular Season"
        data = _request_json(url, params=params)
        result = data["resultSets"][0]
        headers = result["headers"]
        rows = result["rowSet"]
        return [dict(zip(headers, row)) for row in rows]
    except Exception as e:
        print(f"[NBA] Player logs fallback error (player {player_id}): {e}")
        return []


def get_todays_players(games, game_date=None):
    """
    Pull player per-game stats for the teams on today's slate.
    Playoffs first, then regular season fallback.
    """
    url = f"{BASE}/leaguedashplayerstats"
    team_ids = {g.get("home_team_id") for g in games} | {g.get("away_team_id") for g in games}
    team_ids = {tid for tid in team_ids if tid}

    params = {
        "Season": CURRENT_SEASON,
        "SeasonType": "Playoffs",
        "LeagueID": "00",
        "PerMode": "PerGame",
        "MeasureType": "Base",
        "PlusMinus": "N",
        "PaceAdjust": "N",
        "Rank": "N",
        "Outcome": "",
        "Location": "",
        "Month": "0",
        "SeasonSegment": "",
        "DateFrom": "",
        "DateTo": "",
        "OpponentTeamID": "0",
        "VsConference": "",
        "VsDivision": "",
        "GameSegment": "",
        "Period": "0",
        "LastNGames": "0",
        "GameScope": "",
        "PlayerExperience": "",
        "PlayerPosition": "",
        "StarterBench": "",
        "DraftYear": "",
        "DraftPick": "",
        "College": "",
        "Country": "",
        "Height": "",
        "Weight": "",
        "TwoWay": "0",
    }

    def _fetch(current_params):
        data = _request_json(url, params=current_params, timeout=NBA_DASHBOARD_TIMEOUT)
        result = data["resultSets"][0]
        headers = result["headers"]
        rows = result["rowSet"]
        all_players = [dict(zip(headers, row)) for row in rows]
        return [p for p in all_players if p.get("TEAM_ID") in team_ids]

    try:
        players = _fetch(params)
        if players:
            return players
        print("[NBA] Playoff dashboard returned 0 players, falling back to regular season.")
    except Exception as e:
        print(f"[NBA] League dashboard error: {e}")

    try:
        params["SeasonType"] = "Regular Season"
        players = _fetch(params)
        if players:
            return players
        print("[NBA] Regular season dashboard returned 0 players, trying BALLDONTLIE fallback.")
    except Exception as e:
        print(f"[NBA] Regular season dashboard fallback error: {e}")

    return _get_todays_players_from_balldontlie(games, game_date)


def _get_todays_players_from_balldontlie(games, game_date=None):
    if not BALLDONTLIE_API_KEY:
        print("[NBA] BALLDONTLIE_API_KEY not set, skipping BALLDONTLIE fallback.")
        return []

    team_abbreviations = {str(g.get("home_team") or "").upper() for g in games}
    team_abbreviations |= {str(g.get("away_team") or "").upper() for g in games}
    team_abbreviations.discard("")

    if not team_abbreviations:
        return []

    active_players = []
    cursor = None

    while True:
        params = {"per_page": 100}
        if cursor:
            params["cursor"] = cursor

        try:
            data = _balldontlie_request("/nba/v1/players/active", params=params)
        except Exception as e:
            print(f"[NBA] BALLDONTLIE active players error: {e}")
            return []

        page_players = data.get("data", [])
        active_players.extend(
            player for player in page_players
            if str(player.get("team", {}).get("abbreviation") or "").upper() in team_abbreviations
        )

        cursor = data.get("meta", {}).get("next_cursor")
        if not cursor:
            break

    if not active_players:
        print(
            "[NBA] BALLDONTLIE returned 0 active players for today's teams. "
            f"Expected abbreviations: {sorted(team_abbreviations)}"
        )
        return []

    season = _season_year_for_game_date(game_date)
    season_types = ("playoffs", "regular")
    players_by_id = {player["id"]: player for player in active_players if player.get("id")}

    for season_type in season_types:
        merged_players = []
        player_ids = list(players_by_id.keys())

        for idx in range(0, len(player_ids), 100):
            batch_ids = player_ids[idx:idx + 100]
            params = {
                "season": season,
                "season_type": season_type,
                "type": "base",
                "per_page": 100,
                "player_ids[]": batch_ids,
            }

            print(f"[NBA DEBUG] Fetching season averages for {len(batch_ids)} players ({season_type})")

            try:
                data = _balldontlie_request(
                    "/nba/v1/season_averages/general",
                    params=params,
                )
            except Exception as e:
                print(f"[NBA] BALLDONTLIE season averages error ({season_type}): {e}")
                merged_players = []
                break

            records = data.get("data", [])
            print(f"[NBA DEBUG] Returned {len(records)} records")

            for item in records:
                player_info = item.get("player", {})
                stats = item.get("stats", {})
                active_player = players_by_id.get(player_info.get("id"))
                if not active_player:
                    continue

                full_name = " ".join(
                    part for part in [player_info.get("first_name"), player_info.get("last_name")] if part
                ).strip() or "Unknown"
                team = active_player.get("team", {})

                merged_players.append({
                    "PLAYER_NAME": full_name,
                    "TEAM_ABBREVIATION": team.get("abbreviation", "?"),
                    "TEAM_ID": team.get("id"),
                    "PTS": float(stats.get("pts") or 0),
                    "AST": float(stats.get("ast") or 0),
                    "REB": float(stats.get("reb") or 0),
                    "FG3M": float(stats.get("fg3m") or 0),
                    "MIN": float(stats.get("min") or 0),
                })

        if merged_players:
            print(f"[NBA] BALLDONTLIE fallback returned {len(merged_players)} players ({season_type}).")
            return merged_players

    print("[NBA] BALLDONTLIE fallback returned no season averages.")
    return []


# ── Scoring ───────────────────────────────────────────────

def score_pts(p):
    pts = float(p.get("PTS") or 0)
    min_pg = float(p.get("MIN") or 0)
    return round(min(pts * 2.8 + min_pg * 0.4, 100), 2)


def score_ast(p):
    ast = float(p.get("AST") or 0)
    min_pg = float(p.get("MIN") or 0)
    return round(min(ast * 8.0 + min_pg * 0.2, 100), 2)


def score_reb(p):
    reb = float(p.get("REB") or 0)
    min_pg = float(p.get("MIN") or 0)
    return round(min(reb * 6.0 + min_pg * 0.15, 100), 2)


def score_3pm(p):
    fg3m = float(p.get("FG3M") or 0)
    min_pg = float(p.get("MIN") or 0)
    return round(min(fg3m * 18.0 + min_pg * 0.1, 100), 2)


def recommend_pts(p):
    pts = float(p.get("PTS") or 0)
    if pts >= 28:
        return "🎯 Over 27.5 PTS · Strong lean"
    if pts >= 22:
        return "🎯 Over 21.5 PTS · Good value"
    if pts >= 16:
        return "🎯 Over 15.5 PTS · Solid floor"
    return "🎯 Over 14.5 PTS · Floor play"


def recommend_ast(p):
    ast = float(p.get("AST") or 0)
    if ast >= 9:
        return "🎯 Over 8.5 AST · Strong lean"
    if ast >= 7:
        return "🎯 Over 6.5 AST · Good value"
    if ast >= 5:
        return "🎯 Over 4.5 AST · Solid"
    return "🎯 Over 3.5 AST · Floor play"


def recommend_reb(p):
    reb = float(p.get("REB") or 0)
    if reb >= 11:
        return "🎯 Over 10.5 REB · Strong lean"
    if reb >= 8:
        return "🎯 Over 7.5 REB · Good value"
    if reb >= 6:
        return "🎯 Over 5.5 REB · Solid"
    return "🎯 Over 4.5 REB · Floor play"


def recommend_3pm(p):
    fg3m = float(p.get("FG3M") or 0)
    if fg3m >= 3.5:
        return "🎯 Over 3.5 3PM · Strong lean"
    if fg3m >= 2.5:
        return "🎯 Over 2.5 3PM · Good value"
    if fg3m >= 1.5:
        return "🎯 Over 1.5 3PM · Solid"
    return "🎯 Over 0.5 3PM · Floor play"


def build_sleepers(players):
    sleepers = []
    seen = set()

    for p in players:
        ast = float(p.get("AST") or 0)
        reb = float(p.get("REB") or 0)
        fg3m = float(p.get("FG3M") or 0)
        mins = float(p.get("MIN") or 0)

        if mins < 18:
            continue

        name = p.get("PLAYER_NAME", "Unknown")
        team = p.get("TEAM_ABBREVIATION", "?")

        checks = [
            (ast >= 7, "AST", "6+ / 8+ / 10+", ast),
            (reb >= 9, "REB", "8+ / 10+ / 12+", reb),
            (fg3m >= 3, "3PM", "2+ / 4+ / 6+", fg3m),
        ]

        for condition, category, ladder, avg in checks:
            key = (name, category)
            if condition and key not in seen:
                sleepers.append({
                    "name": name,
                    "team": team,
                    "category": category,
                    "ladder": ladder,
                    "avg": round(avg, 1),
                })
                seen.add(key)

    return sleepers[:5]


# ── Main Runner ───────────────────────────────────────────

def run_nba_model(game_date=None, league="nba"):
    if league == "wnba":
        print("[WNBA] WNBA season not started yet — skipping")
        return None

    print(f"[NBA] Running model for {game_date or 'today'}...")
    games = get_todays_scoreboard(game_date)

    if not games:
        print("[NBA] ERROR: No games from any schedule source.")
        return {
            "error": "NO_GAMES",
            "message": "All NBA schedule sources returned empty",
            "league": "NBA",
            "games": [],
            "pts_picks": [],
            "ast_picks": [],
            "reb_picks": [],
            "three_picks": [],
            "sleepers": [],
        }

    print(f"[NBA] Pulling player stats for {len(games)} games...")
    players = get_todays_players(games, game_date)

    if not players:
        print("[NBA] ERROR: No player data found.")
        if BALLDONTLIE_API_KEY:
            message = (
                "NBA schedule found, but both stats.nba.com and BALLDONTLIE player data returned empty. "
                + BALLDONTLIE_PLAN_HINT
            )
        else:
            message = "NBA schedule found, but player data returned empty and BALLDONTLIE_API_KEY is not configured"
        return {
            "error": "NO_PLAYERS",
            "message": message,
            "league": "NBA",
            "games": games,
            "pts_picks": [],
            "ast_picks": [],
            "reb_picks": [],
            "three_picks": [],
            "sleepers": [],
        }

    print(f"[NBA] Found {len(players)} players.")

    pts_picks = []
    ast_picks = []
    reb_picks = []
    three_picks = []

    for p in players:
        name = p.get("PLAYER_NAME", "Unknown")
        team = p.get("TEAM_ABBREVIATION", "?")
        pts = float(p.get("PTS") or 0)
        ast = float(p.get("AST") or 0)
        reb = float(p.get("REB") or 0)
        fg3m = float(p.get("FG3M") or 0)
        mins = float(p.get("MIN") or 0)

        if mins < 15:
            continue

        pts_score = score_pts(p)
        pts_picks.append({
            "name": name,
            "team": team,
            "l1": pts,
            "l5": pts,
            "l10": pts,
            "score": pts_score,
            "conf": confidence(pts_score),
            "matchup": matchup_label(pts_score),
            "rec": recommend_pts(p),
        })

        ast_score = score_ast(p)
        ast_picks.append({
            "name": name,
            "team": team,
            "l1": ast,
            "l5": ast,
            "l10": ast,
            "score": ast_score,
            "conf": confidence(ast_score),
            "matchup": matchup_label(ast_score),
            "rec": recommend_ast(p),
        })

        reb_score = score_reb(p)
        reb_picks.append({
            "name": name,
            "team": team,
            "l1": reb,
            "l5": reb,
            "l10": reb,
            "score": reb_score,
            "conf": confidence(reb_score),
            "matchup": matchup_label(reb_score),
            "rec": recommend_reb(p),
        })

        three_score = score_3pm(p)
        three_picks.append({
            "name": name,
            "team": team,
            "l1": fg3m,
            "l5": fg3m,
            "l10": fg3m,
            "score": three_score,
            "conf": confidence(three_score),
            "matchup": matchup_label(three_score),
            "rec": recommend_3pm(p),
        })

    return {
        "league": "NBA",
        "games": games,
        "pts_picks": sorted(pts_picks, key=lambda x: x["score"], reverse=True)[:5],
        "ast_picks": sorted(ast_picks, key=lambda x: x["score"], reverse=True)[:5],
        "reb_picks": sorted(reb_picks, key=lambda x: x["score"], reverse=True)[:5],
        "three_picks": sorted(three_picks, key=lambda x: x["score"], reverse=True)[:5],
        "sleepers": build_sleepers(players),
    }
