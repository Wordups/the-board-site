# config.py
"""
Full config. Loaded by every other module. All constants live here.
"""
import os
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

# ── Discord ───────────────────────────────────────────────────────────────────
DISCORD_TOKEN        = os.getenv("DISCORD_TOKEN", "")
DISCORD_CHANNEL_HR   = int(os.getenv("DISCORD_CHANNEL_HR",   "0"))
DISCORD_CHANNEL_NBA  = int(os.getenv("DISCORD_CHANNEL_NBA",  "0"))
DISCORD_CHANNEL_WNBA = int(os.getenv("DISCORD_CHANNEL_WNBA", "0"))

# ── Schedule (ET) ─────────────────────────────────────────────────────────────
POST_HOUR_ET       = int(os.getenv("POST_HOUR_ET",       "10"))
POST_MINUTE_ET     = int(os.getenv("POST_MINUTE_ET",     "45"))
NBA_POST_HOUR_ET   = int(os.getenv("NBA_POST_HOUR_ET",   "11"))
NBA_POST_MINUTE_ET = int(os.getenv("NBA_POST_MINUTE_ET", "0"))

# ── MLB Board sizes ───────────────────────────────────────────────────────────
TOP_HR_BOARD = int(os.getenv("TOP_HR_BOARD", "10"))
TOP_TB_BOARD = int(os.getenv("TOP_TB_BOARD", "10"))
TOP_K_BOARD  = int(os.getenv("TOP_K_BOARD",  "6"))

# ── Stat minimums ─────────────────────────────────────────────────────────────
MIN_PA  = 40
MIN_BBE = 20

# ── Legacy aliases (some older code paths read these) ─────────────────────────
TOP_PICKS_PER_GAME    = 2
TOP_TB_PICKS_PER_GAME = 2

# ── HR scoring weights ────────────────────────────────────────────────────────
WEIGHTS = {
    "barrel_matchup":  0.28,   # batter barrel% vs pitcher barrel% allowed
    "hr_fb_pct":       0.22,   # pitcher HR/FB% — heavily weighted
    "iso_platoon":     0.20,   # ISO platoon adjusted
    "slg_platoon":     0.15,   # SLG platoon adjusted
    "park_factor":     0.10,   # park HR factor
    "recent_form":     0.05,   # L14 hard hit rate bonus
}

# ── TB scoring weights ────────────────────────────────────────────────────────
TB_WEIGHTS = {
    "slg_platoon":     0.28,
    "hard_hit_matchup":0.25,
    "contact_rate":    0.20,
    "xwoba":           0.15,
    "batting_order":   0.07,
    "park_factor":     0.05,
}

# ── K scoring weights ─────────────────────────────────────────────────────────
K_WEIGHTS = {
    "k9":        0.30,
    "k_pct":     0.25,
    "swstr_pct": 0.20,
    "opp_k_pct": 0.15,
    "fb_pct":    0.10,
}

# ── Park HR factors (higher = more HR-friendly) ───────────────────────────────
PARK_FACTORS = {
    "CIN": 1.28, "COL": 1.38, "PHI": 1.15, "BAL": 1.08, "NYY": 1.07,
    "BOS": 1.06, "HOU": 1.05, "CHC": 1.04, "MIL": 1.03, "ATL": 1.02,
    "TOR": 1.01, "MIN": 1.01, "DET": 1.00, "STL": 1.00, "LAD": 0.99,
    "ARI": 0.99, "NYM": 0.98, "CLE": 0.98, "WSH": 0.97, "SDP": 0.97,
    "TEX": 0.96, "CHW": 0.96, "PIT": 0.96, "MIA": 0.95, "SFG": 0.94,
    "KCR": 0.94, "TBR": 0.93, "LAA": 0.93, "OAK": 0.92, "SEA": 0.92,
    # Alternate abbreviations MLB API sometimes returns
    "KC":  0.94, "SD":  0.97, "SF":  0.94, "TB":  0.93, "AZ":  0.99,
    "ATH": 0.92, "WAS": 0.97,
}

# ── Park display names (for weather lookups) ──────────────────────────────────
PARK_NAMES = {
    "ARI": "Chase Field",
    "ATL": "Truist Park",
    "BAL": "Oriole Park at Camden Yards",
    "BOS": "Fenway Park",
    "CHC": "Wrigley Field",
    "CWS": "Guaranteed Rate Field",
    "CHW": "Guaranteed Rate Field",

    "CIN": "Great American Ball Park",
    "CLE": "Progressive Field",
    "COL": "Coors Field",
    "DET": "Comerica Park",
    "HOU": "Daikin Park",

    "KC": "Kauffman Stadium",
    "KCR": "Kauffman Stadium",

    "LAA": "Angel Stadium",
    "LAD": "Dodger Stadium",

    "MIA": "loanDepot park",
    "MIL": "American Family Field",
    "MIN": "Target Field",

    "NYM": "Citi Field",
    "NYY": "Yankee Stadium",

    "OAK": "Sutter Health Park",
    "ATH": "Sutter Health Park",

    "PHI": "Citizens Bank Park",
    "PIT": "PNC Park",

    "SD": "Petco Park",
    "SDP": "Petco Park",

    "SEA": "T-Mobile Park",

    "SF": "Oracle Park",
    "SFG": "Oracle Park",

    "STL": "Busch Stadium",

    "TB": "Tropicana Field",
    "TBR": "Tropicana Field",

    "TEX": "Globe Life Field",
    "TOR": "Rogers Centre",

    "WSH": "Nationals Park",
    "WAS": "Nationals Park",
}