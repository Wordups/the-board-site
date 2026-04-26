from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path
from typing import Any, Dict

from aiohttp import web

from live_board import build_live_board_payload
from signal_board_store import load_signal_board, normalize_sport_key


ROOT = Path(__file__).resolve().parent
WEB_DIR = ROOT / "web"
PUBLIC_DIR = ROOT / "public"
DATA_DIR = PUBLIC_DIR / "data"
IMAGE_DIR = PUBLIC_DIR / "images"
INDEX_FILE = WEB_DIR / "index.html"
LIVE_CACHE_TTL_SECONDS = int(os.getenv("LIVE_BOARD_CACHE_TTL_SECONDS", "60"))

_LIVE_CACHE: Dict[str, Any] = {
    "payload": None,
    "expires_at": 0.0,
}


async def index(_: web.Request) -> web.FileResponse:
    return web.FileResponse(INDEX_FILE)


async def healthz(_: web.Request) -> web.Response:
    return web.json_response(
        {
            "ok": True,
            "data_dir": DATA_DIR.exists(),
            "image_dir": IMAGE_DIR.exists(),
        }
    )


async def api_live_board(request: web.Request) -> web.Response:
    refresh = request.query.get("refresh", "").strip().lower() in {"1", "true", "yes"}
    now = time.time()
    if not refresh and _LIVE_CACHE["payload"] is not None and now < float(_LIVE_CACHE["expires_at"]):
        return web.json_response(_LIVE_CACHE["payload"])

    payload = await asyncio.to_thread(build_live_board_payload)
    _LIVE_CACHE.update(
        {
            "payload": payload,
            "expires_at": now + LIVE_CACHE_TTL_SECONDS,
        }
    )
    return web.json_response(payload)


async def api_signal_board(request: web.Request) -> web.Response:
    sport = normalize_sport_key(request.match_info.get("sport", ""))
    payload = load_signal_board(sport)
    if payload is None:
        return web.json_response(
            {
                "sport": sport.upper(),
                "board_type": "signal-board",
                "generated_at": None,
                "title": f"{sport.upper()} Signal Board",
                "subtitle": "No saved bot board yet.",
                "pick_of_day": None,
                "sections": [],
                "games": [],
                "notes": [
                    "The website is waiting for the Discord bot to save the latest board artifacts.",
                ],
                "image": f"/images/{sport}-signal-board.png",
            }
        )
    return web.json_response(payload)


def create_app() -> web.Application:
    app = web.Application()
    app.router.add_get("/", index)
    app.router.add_get("/index.html", index)
    app.router.add_get("/healthz", healthz)
    app.router.add_get("/api/live-board", api_live_board)
    app.router.add_get("/api/signal-board/{sport}", api_signal_board)
    app.router.add_static("/data/", DATA_DIR)
    app.router.add_static("/images/", IMAGE_DIR)
    app.router.add_static("/web/", WEB_DIR)
    return app


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    web.run_app(create_app(), host="0.0.0.0", port=port)
