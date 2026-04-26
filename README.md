# The Board

Website for live sports scanning plus saved bot-generated signal boards.

## Architecture

The Discord bot is the producer.

- `/hrimage` and daily MLB output should publish:
  - `public/data/mlb-signal-board.json`
  - `public/images/mlb-signal-board.png`
- `/nbaimage` and daily NBA output should publish:
  - `public/data/nba-signal-board.json`
  - `public/images/nba-signal-board.png`

The website is the consumer.

- `Signal Board` reads the latest saved JSON files on page load
- if JSON render is thin or unavailable, the page falls back to the latest PNG
- `Live Board` is a separate API surface for today’s schedule and live scores
- `Bankroll` is local browser session state only

## Bot-to-site publishing helper

Use [signal_board_store.py](C:/Users/bword/Documents/the-board-site/signal_board_store.py) from the bot side:

```python
from signal_board_store import publish_signal_board

publish_signal_board(
    "mlb",
    payload=mlb_board_payload,
    image_path="exports/mlb-signal-board.png",
)
```

The same pattern works for `"nba"`.

## Routes

- `/` -> website
- `/api/live-board` -> live scoreboard payload
- `/api/signal-board/mlb` -> latest MLB saved board
- `/api/signal-board/nba` -> latest NBA saved board
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

## Current shape

- `Live Board`: compact scoreboard and status view
- `Signal Board`: latest bot-generated MLB/NBA board
- `Bankroll`: cookie-backed session tracker
