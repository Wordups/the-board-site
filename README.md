# The Board

Website for live sports scanning plus saved bot-generated board artifacts.

## Architecture

The Discord bot is still the producer. The website is the consumer.

The site should never need Discord commands in order to render. Instead, the bot writes the latest board artifacts to disk after it generates them, and the website reads those saved files on page load.

## Board model

There are now three separate board layers:

1. `Outlook Board`
   - built the night before or early morning
   - projected plays for the next slate
   - includes uncertainty penalties when starters, injuries, or lineups are not fully confirmed

2. `Confirmed Board`
   - built day-of after verification
   - uses confirmed starters, injuries, lineup spots, and weather
   - removes the uncertainty discount when data is locked

3. `Trend Board`
   - dense verification table
   - cross-reference only
   - should not be merged into the signal rows

The website automatically prefers the Confirmed Board when it exists, and falls back to the Outlook Board when it does not.

## Saved artifact contract

For each supported sport (`mlb`, `nba`), the bot should save:

- `public/data/{sport}-outlook-board.json`
- `public/data/{sport}-confirmed-board.json`
- `public/data/{sport}-trend-board.json`
- `public/images/{sport}-outlook-board.png`
- `public/images/{sport}-confirmed-board.png`

Trend Board is table-only and does not need a PNG.

## Required signal fields

Signal board payloads should carry:

- `baseScore`
- `adjustments[]`
- `uncertaintyPenalty`
- `finalScore`
- `board_type` (`"outlook"` or `"confirmed"`)
- `confidenceLabel`
- `lastUpdated`

Trend board payloads should carry rows shaped like:

- `player`
- `market`
- `line`
- `season`
- `l10`
- `l5`
- `l3`
- `l1`

## Publishing helper

Use [signal_board_store.py](C:/Users/bword/Documents/the-board-site/signal_board_store.py) from the bot side:

```python
from signal_board_store import publish_board

publish_board(
    "mlb",
    "outlook",
    payload=mlb_outlook_payload,
    image_path="exports/mlb-outlook-board.png",
)

publish_board(
    "mlb",
    "confirmed",
    payload=mlb_confirmed_payload,
    image_path="exports/mlb-confirmed-board.png",
)

publish_board(
    "mlb",
    "trend",
    payload=mlb_trend_payload,
)
```

The same pattern works for `"nba"`.

## Website surfaces

- `Live Board`
  - compact live scoreboard
  - separate from Signal Board
  - current game status, scores, and quick notes

- `Signal Board`
  - clean model output only
  - player, market, score, tag
  - explicit `OUTLOOK` or `CONFIRMED` label
  - falls back to saved PNG if needed

- `Trend Board`
  - dense verification table
  - season and L10/L5/L3/L1 cross-reference

- `Bankroll`
  - cookie-backed session tracker

## Routes

- `/` -> website
- `/api/live-board` -> live scoreboard payload
- `/api/signal-board/{sport}` -> preferred signal board for a sport
- `/api/signal-board/{sport}?type=outlook`
- `/api/signal-board/{sport}?type=confirmed`
- `/api/trend-board/{sport}` -> trend board route alias
- `/api/trend-board/{sport}?type=trend`
- `/data/...` -> saved JSON board artifacts
- `/images/...` -> saved PNG board artifacts
- `/healthz` -> health check

## Local run

```bash
pip install -r requirements.txt
python site_server.py
```

Then open `http://localhost:8000`.

## Deploy

Render can run this directly with:

- Build command: `pip install -r requirements.txt`
- Start command: `python site_server.py`
