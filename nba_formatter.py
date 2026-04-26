# nba_formatter.py
import discord
from datetime import datetime
from zoneinfo import ZoneInfo


COLOR_MAIN = 0x1ABC9C


def _fmt_pick(pick, emoji="🏀"):
    name = pick.get("name", "Unknown")
    team = pick.get("team", "?")
    rec = pick.get("rec", "")
    conf = pick.get("conf", 0)
    matchup = pick.get("matchup", "Neutral")

    return (
        f"{emoji} **{name}** `{team}`\n"
        f"🧠 {rec}\n"
        f"📈 {conf}% · {matchup}"
    )


def _fmt_sleepers(sleepers):
    lines = []
    for s in sleepers[:5]:
        lines.append(
            f"🔥 **{s.get('name', 'Unknown')}** `{s.get('team', '?')}`\n"
            f"📊 {s.get('category', '?')} ladder: {s.get('ladder', '')}\n"
            f"📈 Avg: {s.get('avg', 0)}"
        )
    return "\n\n".join(lines) if lines else "No sleepers available."


def _split_two_columns(picks, emoji):
    left = []
    right = []

    for i, pick in enumerate(picks[:6]):
        block = _fmt_pick(pick, emoji=emoji)
        if i % 2 == 0:
            left.append(block)
        else:
            right.append(block)

    left_text = "\n\n".join(left) if left else "—"
    right_text = "\n\n".join(right) if right else "—"
    return left_text, right_text


def _pick_of_day(results):
    buckets = [
        ("Assists", results.get("ast_picks", []), "🅰️"),
        ("Rebounds", results.get("reb_picks", []), "📦"),
        ("3PM", results.get("three_picks", []), "🎯"),
        ("Points", results.get("pts_picks", []), "🏀"),
    ]

    best = None
    best_label = None
    best_emoji = None

    for label, picks, emoji in buckets:
        if not picks:
            continue
        top = picks[0]
        if not best or top.get("score", 0) > best.get("score", 0):
            best = top
            best_label = label
            best_emoji = emoji

    if not best:
        return "No pick available."

    return (
        f"{best_emoji} **{best.get('name', 'Unknown')}** `{best.get('team', '?')}`\n"
        f"**{best_label} Pick of the Day**\n"
        f"🧠 {best.get('rec', '')}\n"
        f"📈 {best.get('conf', 0)}% confidence · {best.get('matchup', 'Neutral')}"
    )


def build_nba_board(results):
    if not results or results.get("error"):
        return None

    league = results.get("league", "NBA")
    now_et = datetime.now(ZoneInfo("America/New_York"))
    title_date = now_et.strftime("%B %-d, %Y") if "%" in "%-d" else now_et.strftime("%B %d, %Y")

    embed = discord.Embed(
        title=f"🏀 {league} Board — {title_date}",
        color=COLOR_MAIN,
    )

    games = results.get("games", [])
    if games:
        matchups = []
        for g in games[:6]:
            away = g.get("away_team", "?")
            home = g.get("home_team", "?")
            matchups.append(f"{away} @ {home}")
        embed.description = " | ".join(matchups)

    embed.add_field(
        name="🏆 Pick of the Day",
        value=_pick_of_day(results),
        inline=False,
    )

    # Assists
    ast_left, ast_right = _split_two_columns(results.get("ast_picks", []), "🅰️")
    embed.add_field(name="🅰️ Assist Plays", value=ast_left, inline=True)
    embed.add_field(name="\u200b", value=ast_right, inline=True)
    embed.add_field(name="\u200b", value="\u200b", inline=False)

    # Rebounds
    reb_left, reb_right = _split_two_columns(results.get("reb_picks", []), "📦")
    embed.add_field(name="📦 Rebound Plays", value=reb_left, inline=True)
    embed.add_field(name="\u200b", value=reb_right, inline=True)
    embed.add_field(name="\u200b", value="\u200b", inline=False)

    # 3PM
    three_left, three_right = _split_two_columns(results.get("three_picks", []), "🎯")
    embed.add_field(name="🎯 3PT Plays", value=three_left, inline=True)
    embed.add_field(name="\u200b", value=three_right, inline=True)
    embed.add_field(name="\u200b", value="\u200b", inline=False)

    # Sleepers
    embed.add_field(
        name="🔥 Sleepers",
        value=_fmt_sleepers(results.get("sleepers", [])),
        inline=False,
    )

    embed.set_footer(
        text="Confidence = model score | Strong / Good / Neutral / Thin"
    )

    return embed