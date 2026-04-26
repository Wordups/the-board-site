# The Board

Sports betting signal board — MLB, NBA, WNBA, Soccer.

Live props, ladders, daily picks, and session bankroll tracking.

## Stack

- **Frontend** — Vanilla JS SPA (`web/index.html`)
- **Backend** — Python aiohttp (`site_server.py`)
- **Data** — Bot pipeline feeds `site_payload.py` → JSON API → frontend
- **Deploy** — Render.com (free tier)

## Local Dev

```bash
pip install -r requirements.txt
cp .env.example .env
python site_server.py
# Open http://localhost:8000
```

## Deploy to Render

1. Push to GitHub
2. New Web Service on Render → connect this repo
3. Runtime: Python 3
4. Build Command: `pip install -r requirements.txt`
5. Start Command: `python site_server.py`
6. Add env vars from `.env.example`

## Features

- MLB / NBA / WNBA / Soccer tabs
- Game cards with picks, confidence tiers, why notes
- Explorer view — dense table for parlay scanning
- Click-through game modal with full roster breakdown
- Highlights tab — YouTube embeds
- Session Bankroll tracker — cookie-persistent, per-session
  - Enter FanDuel balance → track deployed / remaining
  - Add tickets with wager + payout
  - Settle as Win / Loss / Cash Out
  - P&L tracking
  - 25% max bet rule enforced

## Sports Coming Soon

- WNBA (when season tips)
- Soccer (EPL, MLS, Champions League)
