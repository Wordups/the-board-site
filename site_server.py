from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional

from aiohttp import web

from site_payload import build_site_payload


ROOT = Path(__file__).resolve().parent
WEB_DIR = ROOT / "web"
INDEX_FILE = WEB_DIR / "index.html"
CACHE_TTL_SECONDS = int(os.getenv("SITE_CACHE_TTL_SECONDS", "300"))

_CACHE: Dict[str, Any] = {
    "payload": None,
    "game_date": None,
    "expires_at": 0.0,
}


async def _get_payload(game_date: Optional[str], refresh: bool = False) -> Dict[str, Any]:
    now = time.time()
    if (
        not refresh
        and _CACHE["payload"] is not None
        and _CACHE["game_date"] == game_date
        and now < float(_CACHE["expires_at"])
    ):
        return _CACHE["payload"]

    payload = await asyncio.to_thread(build_site_payload, game_date)
    _CACHE.update(
        {
            "payload": payload,
            "game_date": game_date,
            "expires_at": now + CACHE_TTL_SECONDS,
        }
    )
    return payload


async def index(request: web.Request) -> web.FileResponse:
    return web.FileResponse(INDEX_FILE)


async def api_site_board(request: web.Request) -> web.Response:
    game_date = request.query.get("date")
    refresh = request.query.get("refresh", "").strip().lower() in {"1", "true", "yes"}
    payload = await _get_payload(game_date, refresh=refresh)
    return web.json_response(payload)


async def healthz(request: web.Request) -> web.Response:
    return web.json_response({"ok": True})


def create_app() -> web.Application:
    app = web.Application()
    app.router.add_get("/", index)
    app.router.add_get("/index.html", index)
    app.router.add_get("/api/site-board", api_site_board)
    app.router.add_get("/board-data.json", api_site_board)
    app.router.add_get("/healthz", healthz)
    app.router.add_static("/web/", WEB_DIR)
    return app


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    web.run_app(create_app(), host="0.0.0.0", port=port)
