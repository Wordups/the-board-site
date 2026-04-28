# run_daily.py
"""
Main runner. Enforces the full verification checklist top to bottom.

Usage:
    python run_daily.py                           # today
    python run_daily.py --date 2026-04-18         # specific date
    python run_daily.py --screenshot lines.json   # book override
"""
import argparse
import json
import os
import sys
from datetime import date, timedelta

from config import PARK_FACTORS, PARK_NAMES
from validators import (
    fetch_bettable_games, get_confirmed_lineup,
    get_team_injuries, scrub_injuries, assert_team_assignment,
)
from weather import fetch_game_weather, weather_multiplier
from calibration import (
    calibrate_hr_prob, calibrate_tb_prob, calibrate_k_prob,
    parlay_prob, confidence_label, prob_to_american_odds,
)

sys.path.insert(0, ".")
try:
    from hr_model import (
        get_pitcher_stats, get_batter_stats, get_recent_batter_stats,
        score_hr, score_tb, score_k, has_platoon_advantage,
        recommend_hr, recommend_tb, recommend_k,
    )
    MODEL_AVAILABLE = True
except Exception as e:
    print(f"[WARN] hr_model imports failed: {e}")
    MODEL_AVAILABLE = False


# ── Screenshot override (Rule #5: book > research) ────────────────────────────

def load_screenshot_override(path):
    if not path or not os.path.exists(path):
        if path: print(f"[WARN] Screenshot file not found: {path}")
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except Exception as e:
        print(f"[WARN] Screenshot load failed: {e}")
        return None


def apply_screenshot_override(games, override):
    if not override:
        return games, []
    conflicts = []
    for g in games:
        key = f"{g['awayTeam']}@{g['homeTeam']}"
        if override.get("game") != key:
            continue
        book = override.get("pitchers", {})
        for side in ("home", "away"):
            bn = book.get(side)
            mn = g[f"{side}PitcherName"]
            if bn and bn.lower() not in mn.lower() and mn.lower() not in bn.lower():
                conflicts.append({"game": key, "side": side, "model": mn, "book": bn})
    return games, conflicts


# ── Pipeline ──────────────────────────────────────────────────────────────────

def enrich_recent_form_lines(recent, game_date=None):
    """
    Adds hitter L1/L5/L10 HR, TB, and hits from recent Statcast game logs.
    This only feeds display context; scoring still uses the existing model.
    """
    try:
        from pybaseball import statcast

        end = date.fromisoformat(game_date) if game_date else date.today()
        start = end - timedelta(days=14)
        df = statcast(start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"))
        required = {"batter", "game_date", "events"}
        if df.empty or not required.issubset(df.columns):
            return recent

        hit_events = {"single", "double", "triple", "home_run"}
        tb_values = {"single": 1, "double": 2, "triple": 3, "home_run": 4}
        df["recent_hit"] = df["events"].isin(hit_events).astype(int)
        df["recent_hr"] = (df["events"] == "home_run").astype(int)
        df["recent_tb"] = df["events"].map(tb_values).fillna(0).astype(int)

        game_logs = (
            df.groupby(["batter", "game_date"], as_index=False)
            .agg(
                recent_hits=("recent_hit", "sum"),
                recent_hr=("recent_hr", "sum"),
                recent_tb=("recent_tb", "sum"),
            )
            .sort_values(["batter", "game_date"], ascending=[True, False])
        )

        enriched = dict(recent or {})
        for batter, games in game_logs.groupby("batter"):
            stats = dict(enriched.get(int(batter), {}))
            stats.update(
                {
                    "l1_hits": int(games["recent_hits"].head(1).sum()),
                    "l5_hits": int(games["recent_hits"].head(5).sum()),
                    "l10_hits": int(games["recent_hits"].head(10).sum()),
                    "l1_hr": int(games["recent_hr"].head(1).sum()),
                    "l5_hr": int(games["recent_hr"].head(5).sum()),
                    "l10_hr": int(games["recent_hr"].head(10).sum()),
                    "l1_tb": int(games["recent_tb"].head(1).sum()),
                    "l5_tb": int(games["recent_tb"].head(5).sum()),
                    "l10_tb": int(games["recent_tb"].head(10).sum()),
                }
            )
            enriched[int(batter)] = stats

        print(f"[recent] L1/L5/L10 form loaded for {len(game_logs['batter'].unique())} batters.")
        return enriched
    except Exception as e:
        print(f"[WARN] Recent L1/L5/L10 form failed: {e}")
        return recent

def run(game_date=None, screenshot_path=None, verbose=True):
    if game_date is None:
        game_date = date.today().strftime("%Y-%m-%d")

    year = int(game_date[:4])

    def note(m):
        if verbose:
            print(m)

    print("[MLB] Requesting schedule for:", game_date)
    print("\n==============================================================")
    print("  MLB MODEL RUN -", game_date)
    print("==============================================================")

    note("\n[1] Pulling slate + confirming probable starters...")
    games, drops = fetch_bettable_games(game_date)
    note(f"    Bettable games: {len(games)} | Dropped: {len(drops)}")
    for d in drops:
        note(f"      ✗ gamePk {d['game']}: {d['reason']}")

    if not games:
        note("\n[!] No bettable games. Exiting.")
        return None

    override = load_screenshot_override(screenshot_path)
    if override:
        note(f"\n[5] Screenshot override for: {override.get('game')}")
        _, conflicts = apply_screenshot_override(games, override)
        for c in conflicts:
            note(f"    ⚠ BOOK/MODEL MISMATCH game {c['game']} {c['side']}: "
                 f"model={c['model']} book={c['book']} → book wins")

    if not MODEL_AVAILABLE:
        note("\n[!] Scoring unavailable — fix hr_model imports and rerun.")
        return {"games": games, "drops": drops}

    note("\n[stat] Loading season + L14 stat tables...")
    pitcher_df = get_pitcher_stats(year)
    batter_df  = get_batter_stats(year)
    recent     = get_recent_batter_stats(year)
    recent     = enrich_recent_form_lines(recent, game_date)

    all_hr, all_tb, all_k = [], [], []

    for g in games:
        note(f"\n[game] {g['awayTeamName']} @ {g['homeTeamName']}")
        note(f"        {g['awayPitcherName']} ({g['awayPitcherHand']}) vs "
             f"{g['homePitcherName']} ({g['homePitcherHand']})")

        home_pr = away_pr = {}
        m = pitcher_df[pitcher_df["mlbam_id"] == g["homePitcherId"]]
        if not m.empty: home_pr = m.iloc[0].to_dict()
        m = pitcher_df[pitcher_df["mlbam_id"] == g["awayPitcherId"]]
        if not m.empty: away_pr = m.iloc[0].to_dict()

        # Rule 4: Weather
        wx = fetch_game_weather(g["venueName"], g["gameTimeUTC"])
        hr_mult, wx_flags = weather_multiplier(wx, "hr")
        tb_mult, _        = weather_multiplier(wx, "tb")
        k_mult, _         = weather_multiplier(wx, "k")
        note(f"        wx: {wx.get('temp_f','?')}°F, {wx.get('wind_mph','?')}mph, "
             f"{wx.get('precip_prob','?')}% | HR×{hr_mult} K×{k_mult} {wx_flags}")

        park_factor = PARK_FACTORS.get(g["homeTeam"], 1.00)

        # Rule 2b + 3: Lineups + injury scrub
        for side, opp_pr, opp_hand, team_id, own_team, pitcher_team in [
            ("home", away_pr, g["awayPitcherHand"], g["homeTeamId"],
             g["homeTeam"], g["awayTeam"]),
            ("away", home_pr, g["homePitcherHand"], g["awayTeamId"],
             g["awayTeam"], g["homeTeam"]),
        ]:
            lineup, confirmed, reason = get_confirmed_lineup(g["gamePk"], side)
            if not confirmed:
                note(f"        ⏸ {own_team} lineup not confirmed ({reason})")
                continue

            injured = get_team_injuries(team_id)
            lineup, dropped = scrub_injuries(lineup, injured)
            if dropped:
                note(f"        ✗ scrubbed ({own_team}): {', '.join(dropped)}")

            for b in lineup:
                bs = batter_df[batter_df["mlbam_id"] == b["playerId"]]
                if bs.empty:
                    continue
                brow = bs.iloc[0].to_dict()
                brow.update({"batSide": b["batSide"], "name": b["name"],
                             "mlbam_id": b["playerId"]})
                p_hand = opp_hand or "R"
                recent_line = recent.get(b["playerId"], {}) or {}

                raw_hr = score_hr(brow, opp_pr, park_factor, p_hand, recent)
                raw_tb = score_tb(brow, opp_pr, park_factor, p_hand, b["battingOrder"])
                adj_hr = raw_hr * hr_mult
                adj_tb = raw_tb * tb_mult

                slg_raw = (brow.get("SLG_vsR") if p_hand == "R"
                           else brow.get("SLG_vsL"))
                if slg_raw is None:
                    slg_raw = brow.get("SLG") or 0
                slg = float(slg_raw or 0)

                pick = {
                    "name": b["name"],
                    "team": own_team,
                    "opp_team": pitcher_team,
                    "bat_side": b["batSide"],
                    "pitcher_hand": p_hand,
                    "pitcher_name": (g["awayPitcherName"] if side == "home"
                                     else g["homePitcherName"]),
                    "mlbam_id": b["playerId"],
                    "batting_order": b["battingOrder"],
                    "game": f"{g['awayTeam']} @ {g['homeTeam']}",
                    "gamePk": g["gamePk"],
                    "slg": round(slg, 3),
                    "barrel_pct": round(float(brow.get("barrel_pct") or 0), 1),
                    "l1_hr": int(recent_line.get("l1_hr") or 0),
                    "l5_hr": int(recent_line.get("l5_hr") or 0),
                    "l10_hr": int(recent_line.get("l10_hr") or 0),
                    "l1_tb": int(recent_line.get("l1_tb") or 0),
                    "l5_tb": int(recent_line.get("l5_tb") or 0),
                    "l10_tb": int(recent_line.get("l10_tb") or 0),
                    "l1_hits": int(recent_line.get("l1_hits") or 0),
                    "l5_hits": int(recent_line.get("l5_hits") or 0),
                    "l10_hits": int(recent_line.get("l10_hits") or 0),
                    "score": round(adj_hr, 2),
                    "tb_score": round(adj_tb, 2),
                    "p_hr": calibrate_hr_prob(adj_hr),
                    "p_tb": calibrate_tb_prob(adj_tb),
                    "platoon_advantage": has_platoon_advantage(b["batSide"], p_hand),
                    "weather_flags": wx_flags,
                }

                ok, why = assert_team_assignment(pick, g)
                if not ok:
                    note(f"        ✗ team mismatch: {pick['name']} {why}")
                    continue

                pick["hr_rec"] = recommend_hr(pick)
                pick["tb_rec"] = recommend_tb(pick)
                all_hr.append(pick)
                all_tb.append(pick)

        # K picks — pitcher's own team tagged correctly
        for pr, pname, pid_, own_team, opp_team in [
            (away_pr, g["awayPitcherName"], g["awayPitcherId"],
             g["awayTeam"], g["homeTeam"]),
            (home_pr, g["homePitcherName"], g["homePitcherId"],
             g["homeTeam"], g["awayTeam"]),
        ]:
            if not pr:
                continue
            raw_k = score_k(pr)
            adj_k = raw_k * k_mult
            k_pick = {
                "name": pname,
                "team": own_team,
                "pitcher_team": own_team,
                "opp_team": opp_team,
                "mlbam_id": pid_,
                "k9": round(float(pr.get("k9") or 0), 1),
                "k_pct": round(float(pr.get("k_pct") or 0), 1),
                "swstr_pct": round(float(pr.get("swstr_pct") or 0), 1),
                "k_score": round(adj_k, 2),
                "p_k_45": calibrate_k_prob(adj_k, 4.5),
                "p_k_55": calibrate_k_prob(adj_k, 5.5),
                "p_k_65": calibrate_k_prob(adj_k, 6.5),
                "game": f"{g['awayTeam']} @ {g['homeTeam']}",
                "gamePk": g["gamePk"],
                "weather_flags": wx_flags,
            }
            k_pick["k_rec"] = recommend_k(k_pick)
            all_k.append(k_pick)

    all_hr.sort(key=lambda x: x["p_hr"], reverse=True)
    all_tb.sort(key=lambda x: x["p_tb"], reverse=True)
    all_k.sort(key=lambda x: x["p_k_55"], reverse=True)

    return {
        "date": game_date,
        "games": games,
        "drops": drops,
        "hr_picks": all_hr,
        "tb_picks": all_tb,
        "k_picks": all_k,
        "override_active": override is not None,
    }


# ── Parlay builder ────────────────────────────────────────────────────────────

def build_parlays(results):
    if not results:
        return {}
    hr, tb, k = results["hr_picks"], results["tb_picks"], results["k_picks"]

    def pick_hr(pool, require_platoon):
        out, used = [], {}
        for p in pool:
            if require_platoon and not p["platoon_advantage"]: continue
            if p["batting_order"] > 6: continue
            gp, team = p["gamePk"], p["team"]
            if used.get(gp) and used[gp] != team: continue
            out.append(p); used[gp] = team
            if len(out) >= 3: break
        return out

    hr_parlay = pick_hr(hr, True)
    if len(hr_parlay) < 2:
        hr_parlay = pick_hr(hr, False)

    tb_parlay, used = [], {}
    for p in tb:
        if p["batting_order"] > 7: continue
        gp, team = p["gamePk"], p["team"]
        if used.get(gp) and used[gp] != team: continue
        tb_parlay.append(p); used[gp] = team
        if len(tb_parlay) >= 3: break

    k_parlay = []
    against = {(x["gamePk"], x["pitcher_name"]) for x in hr_parlay + tb_parlay}
    for p in k[:6]:
        if (p["gamePk"], p["name"]) in against: continue
        k_parlay.append(p)
        if len(k_parlay) >= 3: break

    return {"hr": hr_parlay, "tb": tb_parlay, "k": k_parlay}


# ── Output ────────────────────────────────────────────────────────────────────

def render_gambly(results, parlays):
    if not results:
        return "No playable slate."
    out = [f"\n{'='*62}", f"📋 MLB BOARD — {results['date']}",
           "   Verified: pitchers confirmed, lineups posted, injuries scrubbed, weather gated", ""]

    out.append("💣 HR PARLAY")
    probs = []
    for p in parlays.get("hr", []):
        out.append(f"   {p['name']} ({p['team']}) vs {p['pitcher_name']} "
                   f"· HR 1+ · {int(p['p_hr']*100)}% · "
                   f"{confidence_label(p['p_hr'], 'hr')}")
        probs.append(p["p_hr"])
    if probs:
        c = parlay_prob(probs)
        out.append(f"   → Parlay: {int(c*100)}%  fair odds {prob_to_american_odds(c):+d}")
    out.append("")

    out.append("🎯 TB PARLAY")
    probs = []
    for p in parlays.get("tb", []):
        out.append(f"   {p['name']} ({p['team']}) vs {p['pitcher_name']} "
                   f"· Over 1.5 TB · {int(p['p_tb']*100)}% · "
                   f"{confidence_label(p['p_tb'], 'tb')}")
        probs.append(p["p_tb"])
    if probs:
        c = parlay_prob(probs)
        out.append(f"   → Parlay: {int(c*100)}%  fair odds {prob_to_american_odds(c):+d}")
    out.append("")

    out.append("⚾ K PARLAY")
    probs = []
    for p in parlays.get("k", []):
        out.append(f"   {p['name']} ({p['team']}) · Over 5.5 Ks · "
                   f"{int(p['p_k_55']*100)}% · {confidence_label(p['p_k_55'], 'k')}")
        probs.append(p["p_k_55"])
    if probs:
        c = parlay_prob(probs)
        out.append(f"   → Parlay: {int(c*100)}%  fair odds {prob_to_american_odds(c):+d}")
    out.append("")

    if not results.get("override_active"):
        out.append("⚠ No FanDuel screenshot loaded — pass --screenshot lines.json "
                   "to lock lines (book > model).")
    return "\n".join(out)


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=None, help="YYYY-MM-DD")
    ap.add_argument("--screenshot", default=None, help="Path to FD JSON")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    results = run(args.date, args.screenshot, verbose=not args.quiet)
    if results and results.get("hr_picks") is not None:
        parlays = build_parlays(results)
        print(render_gambly(results, parlays))
