# formatter.py
"""
Discord formatter for the MLB per-game board.

The model pipeline produces one board. This layer turns it into compact,
market-first Discord sheets without rebuilding or rescoring anything.
"""
from collections import defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo

import discord

from board_logic import (
    build_game_board_from_results,
    filter_board_by_team,
)

DISCORD_EMBED_LIMIT = 6000
SAFE_EMBED_LIMIT = 5000
DISCORD_FIELD_LIMIT = 1024
DISCORD_FIELD_COUNT_LIMIT = 25
PICK_OF_DAY_COLOR = 0xF2C94C

MARKETS = (
    {
        "title": "HR Attack Board",
        "categories": {"HR"},
        "color": 0xD64545,
        "min_score": 34.0,
        "max_plays": 18,
        "value_label": "VALUE (34-36.9)",
        "suffix": "",
    },
    {
        "title": "Hits Floor Board",
        "categories": {"HIT"},
        "color": 0xF2C94C,
        "min_score": 30.0,
        "max_plays": 8,
        "value_label": "VALUE (30-36.9)",
        "suffix": " HIT",
    },
    {
        "title": "TB Stability Board",
        "categories": {"TB"},
        "color": 0x2D9CDB,
        "min_score": 30.0,
        "max_plays": 6,
        "value_label": "VALUE (30-36.9)",
        "suffix": " TB",
    },
    {
        "title": "K Strikeout Board",
        "categories": {"K"},
        "color": 0x6FCF97,
        "min_score": 34.0,
        "max_plays": 4,
        "value_label": "VALUE (34-36.9)",
        "suffix": " K",
    },
)

FOOTER_TEXT = "Scores 0-50 | Hidden below display cut | One line per player"
PICK_PRIORITY = {"HR": 4, "HIT": 3, "TB": 2, "K": 1}


def _discord_len(text):
    return len(str(text or "").encode("utf-16-le")) // 2


def _game_order(results, board):
    ordered = [
        f"{game.get('awayTeam')} @ {game.get('homeTeam')}"
        for game in results.get("games", []) or []
        if game.get("awayTeam") and game.get("homeTeam")
    ]
    seen = set()
    final = []
    for game_id in ordered + list(board):
        if game_id in board and game_id not in seen:
            final.append(game_id)
            seen.add(game_id)
    return final


def _embed_size(embed, footer_text=""):
    total = _discord_len(embed.title) + _discord_len(embed.description)
    total += _discord_len(footer_text)
    for field in embed.fields:
        total += _discord_len(field.name) + _discord_len(field.value)
    return total


def _display_bucket(play, market):
    score = play.score
    if score >= 40:
        return "CORE (40+)"
    if score >= 37:
        return "STRONG (37-39.9)"
    if score >= market["min_score"]:
        return market["value_label"]
    return None


def _market_plays(board, market):
    plays = [
        play
        for game_plays in board.values()
        for play in game_plays
        if play.category in market["categories"] and play.score >= market["min_score"]
    ]
    plays.sort(key=lambda play: play.score, reverse=True)
    return plays[: market["max_plays"]], len(plays)


def _top_signal_games(plays):
    by_game = defaultdict(list)
    for play in plays:
        by_game[play.game_id].append(play)

    ranked = sorted(
        by_game.items(),
        key=lambda item: (len(item[1]), max(play.score for play in item[1])),
        reverse=True,
    )
    return [game_id for game_id, _ in ranked[:3]]


def _description(plays):
    top = plays[0]
    games = _top_signal_games(plays)
    signal = "\n".join(f"{idx}. {game_id}" for idx, game_id in enumerate(games, start=1))
    return (
        f"Top play: **{top.player_name}** `{top.team}` - {top.score:.1f}\n\n"
        f"Top Signal Games:\n{signal}"
    )


def _stat_int(stats, *keys):
    for key in keys:
        value = stats.get(key)
        if value in (None, ""):
            continue
        try:
            return int(round(float(value)))
        except (TypeError, ValueError):
            continue
    return None


def _recent_form(play):
    stats = play.stats or {}
    category_keys = {
        "HR": ("HR", ("l1_hr",), ("l5_hr",), ("l10_hr",)),
        "TB": ("TB", ("l1_tb",), ("l5_tb",), ("l10_tb",)),
        "HIT": ("HIT", ("l1_hits",), ("l5_hits",), ("l10_hits",)),
        "K": ("K", ("l1_k",), ("l5_k", "l5_k_avg"), ("l10_k", "l10_k_avg")),
    }
    config = category_keys.get(play.category)
    if not config:
        return ""

    label, l1_keys, l5_keys, l10_keys = config
    values = [
        _stat_int(stats, *l1_keys),
        _stat_int(stats, *l5_keys),
        _stat_int(stats, *l10_keys),
    ]
    if all(value is None for value in values):
        return ""

    display = "/".join("--" if value is None else str(value) for value in values)
    return f" | L1/L5/L10 {label} {display}"


def _play_line(play, suffix):
    return (
        f"- **{play.player_name}** `{play.team}` - "
        f"{play.score:.1f}{suffix}{_recent_form(play)}"
    )


def _market_for_category(category):
    for market in MARKETS:
        if category in market["categories"]:
            return market
    return None


def _pick_candidates(board):
    candidates = []
    for market in MARKETS:
        plays, _ = _market_plays(board, market)
        candidates.extend(plays)
    return candidates


def _headshot_url(play):
    player_id = (play.stats or {}).get("mlbam_id") or (play.stats or {}).get("playerId")
    if not player_id:
        return None
    return f"https://img.mlbstatic.com/mlb-photos/image/upload/w_180/v1/people/{player_id}/headshot/67/current"


def _compact_reason(play):
    parts = [part.strip() for part in str(play.reason or "").split("|") if part.strip()]
    parts = [part for part in parts if "L1/L5/L10" not in part]
    return " | ".join(parts[:2])


def _build_pick_of_day_embed(base_title, board):
    candidates = _pick_candidates(board)
    if not candidates:
        return None

    pick = max(candidates, key=lambda play: (play.score, PICK_PRIORITY.get(play.category, 0)))
    market = _market_for_category(pick.category) or {}
    suffix = market.get("suffix", "")
    lane = market.get("title", pick.category)
    recent = _recent_form(pick).lstrip(" |")

    lines = [
        f"**{pick.player_name}** `{pick.team}` - {pick.line} - **{pick.score:.1f}{suffix}**",
        f"{pick.game_id} | vs `{pick.opponent}`",
        f"Lane: {lane}",
    ]
    if recent:
        lines.append(recent)
    reason = _compact_reason(pick)
    if reason:
        lines.append(reason)

    embed = discord.Embed(
        title=f"{base_title} - Pick of the Day",
        description="\n".join(lines),
        color=PICK_OF_DAY_COLOR,
    )
    headshot = _headshot_url(pick)
    if headshot:
        embed.set_thumbnail(url=headshot)
    embed.set_footer(text="Gold anchor | Board still split by market below")
    return embed


def _field_value(bucket_plays, game_order, suffix):
    by_game = defaultdict(list)
    for play in bucket_plays:
        by_game[play.game_id].append(play)

    parts = []
    for game_id in game_order:
        plays = by_game.get(game_id, [])
        if not plays:
            continue

        lines = [f"**{game_id}**"]
        lines.extend(_play_line(play, suffix) for play in plays)
        parts.append("\n".join(lines))

    return "\n\n".join(parts)


def _trim_field_value(value):
    if _discord_len(value) <= DISCORD_FIELD_LIMIT:
        return value, False

    lines = value.splitlines()
    kept = []
    trimmed = False
    for line in lines:
        candidate = "\n".join(kept + [line])
        if _discord_len(candidate) > DISCORD_FIELD_LIMIT - 24:
            trimmed = True
            break
        kept.append(line)

    if not kept:
        return "*Trimmed for Discord size.*", True
    return "\n".join(kept) + "\n*More hidden.*", trimmed


def _build_market_embed(results, board, base_title, market):
    plays, total_available = _market_plays(board, market)
    if not plays:
        return None

    embed = discord.Embed(
        title=f"{base_title} - {market['title']}",
        description=_description(plays),
        color=market["color"],
    )

    game_order = _game_order(results, board)
    ordered_plays = sorted(plays, key=lambda play: play.score, reverse=True)

    buckets = defaultdict(list)
    for play in ordered_plays:
        bucket = _display_bucket(play, market)
        if bucket:
            buckets[bucket].append(play)

    shown_plays = 0
    trimmed = total_available > len(plays)

    for bucket in ("CORE (40+)", "STRONG (37-39.9)", market["value_label"]):
        bucket_plays = buckets.get(bucket, [])
        if not bucket_plays:
            continue
        if len(embed.fields) >= DISCORD_FIELD_COUNT_LIMIT:
            trimmed = True
            break

        value, was_trimmed = _trim_field_value(
            _field_value(bucket_plays, game_order, market["suffix"])
        )
        trimmed = trimmed or was_trimmed
        projected_size = _embed_size(embed, FOOTER_TEXT) + _discord_len(bucket) + _discord_len(value)
        if projected_size > SAFE_EMBED_LIMIT:
            trimmed = True
            break

        shown_plays += len(bucket_plays)
        embed.add_field(name=bucket, value=value, inline=False)

    footer = FOOTER_TEXT
    if trimmed or shown_plays < total_available:
        footer = f"{footer} | Showing {shown_plays}/{total_available}"
    if _embed_size(embed, footer) > DISCORD_EMBED_LIMIT:
        footer = f"Scores 0-50 | Showing {shown_plays}/{total_available}"

    embed.set_footer(text=footer)
    return embed


def build_board_embeds(results, team_filter=None):
    today = datetime.now(ZoneInfo("America/New_York")).strftime("%B %d, %Y")
    board = build_game_board_from_results(results)
    if team_filter:
        board = filter_board_by_team(board, team_filter)

    base_title = f"MLB Per-Game Board - {today}"
    if team_filter:
        base_title = f"{base_title} - {str(team_filter).lstrip('/').title()}"

    all_plays = [play for plays in board.values() for play in plays]
    if not all_plays:
        embed = discord.Embed(title=base_title, color=0x00D26A)
        embed.description = "No playable MLB props matched this board."
        return [embed]

    embeds = []
    pick_embed = _build_pick_of_day_embed(base_title, board)
    if pick_embed:
        embeds.append(pick_embed)

    for market in MARKETS:
        embed = _build_market_embed(results, board, base_title, market)
        if embed:
            embeds.append(embed)

    return embeds or [
        discord.Embed(
            title=base_title,
            description="No visible plays met the display cut.",
            color=0x00D26A,
        )
    ]


def build_full_board(results, team_filter=None):
    return build_board_embeds(results, team_filter=team_filter)[0]
