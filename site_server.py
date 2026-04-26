from __future__ import annotations

import asyncio
import base64
import os
import time
from pathlib import Path
from typing import Any, Dict

from aiohttp import web

from live_board import build_live_board_payload
from signal_board_store import (
    publish_board,
    load_board,
    load_preferred_signal_board,
    normalize_board_kind,
    normalize_sport_key,
)


ROOT = Path(__file__).resolve().parent
WEB_DIR = ROOT / "web"
PUBLIC_DIR = ROOT / "public"
DATA_DIR = PUBLIC_DIR / "data"
IMAGE_DIR = PUBLIC_DIR / "images"
INDEX_FILE = WEB_DIR / "index.html"
LIVE_CACHE_TTL_SECONDS = int(os.getenv("LIVE_BOARD_CACHE_TTL_SECONDS", "60"))
SITE_PUBLISH_TOKEN = os.getenv("SITE_PUBLISH_TOKEN", "").strip()

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
    requested_kind = request.query.get("type", "").strip().lower()
    default_kind = "trend" if request.path.startswith("/api/trend-board/") else None
    board_kind = normalize_board_kind(requested_kind) if requested_kind else default_kind
    payload = load_board(sport, board_kind) if board_kind else load_preferred_signal_board(sport)
    if payload is None:
        fallback_kind = board_kind or "outlook"
        return web.json_response(
            {
                "sport": sport.upper(),
                "board_type": fallback_kind,
                "generated_at": None,
                "title": f"{sport.upper()} {fallback_kind.title()} Board",
                "subtitle": "No saved bot board yet.",
                "pick_of_day": None,
                "sections": [],
                "games": [],
                "trend_rows": [],
                "notes": [
                    "The website is waiting for the Discord bot to save the latest board artifacts.",
                ],
                "image": None if fallback_kind == "trend" else f"/images/{sport}-{fallback_kind}-board.png",
            }
        )
    return web.json_response(payload)


def _is_publish_authorized(request: web.Request) -> bool:
    if not SITE_PUBLISH_TOKEN:
        return True

    auth_header = request.headers.get("Authorization", "").strip()
    token_header = request.headers.get("X-Site-Publish-Token", "").strip()

    if auth_header.startswith("Bearer "):
        return auth_header.removeprefix("Bearer ").strip() == SITE_PUBLISH_TOKEN
    return token_header == SITE_PUBLISH_TOKEN


async def api_publish_board(request: web.Request) -> web.Response:
    if not _is_publish_authorized(request):
        return web.json_response({"ok": False, "error": "unauthorized"}, status=401)

    try:
        body = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "invalid-json"}, status=400)

    try:
        sport = normalize_sport_key(body.get("sport", ""))
        board_kind = normalize_board_kind(body.get("board_kind", ""))
        payload = body.get("payload")
        if not isinstance(payload, dict):
            raise ValueError("payload must be an object")

        image_bytes = None
        image_base64 = body.get("image_base64")
        if image_base64:
            image_bytes = base64.b64decode(image_base64)

        paths = publish_board(
            sport,
            board_kind,
            payload=payload,
            image_bytes=image_bytes,
        )
    except Exception as exc:
        return web.json_response({"ok": False, "error": str(exc)}, status=400)

    return web.json_response(
        {
            "ok": True,
            "sport": sport,
            "board_kind": board_kind,
            "paths": {key: str(value) for key, value in paths.items()},
        }
    )


def create_app() -> web.Application:
    app = web.Application()
    app.router.add_get("/", index)
    app.router.add_get("/index.html", index)
    app.router.add_get("/healthz", healthz)
    app.router.add_get("/api/live-board", api_live_board)
    app.router.add_get("/api/signal-board/{sport}", api_signal_board)
    app.router.add_get("/api/trend-board/{sport}", api_signal_board)
    app.router.add_post("/api/publish-board", api_publish_board)
    app.router.add_static("/data/", DATA_DIR)
    app.router.add_static("/images/", IMAGE_DIR)
    app.router.add_static("/web/", WEB_DIR)
    return app


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    web.run_app(create_app(), host="0.0.0.0", port=port)
