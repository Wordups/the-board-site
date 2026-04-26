from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional


ROOT = Path(__file__).resolve().parent
PUBLIC_DIR = ROOT / "public"
DATA_DIR = PUBLIC_DIR / "data"
IMAGE_DIR = PUBLIC_DIR / "images"
SUPPORTED_SPORTS = {"mlb", "nba"}
SUPPORTED_BOARD_KINDS = {"outlook", "confirmed", "trend"}
BOARD_PRIORITY = ("confirmed", "outlook")


def normalize_sport_key(sport: str) -> str:
    token = str(sport or "").strip().lower()
    if token not in SUPPORTED_SPORTS:
        raise ValueError(f"Unsupported sport '{sport}'. Expected one of {sorted(SUPPORTED_SPORTS)}")
    return token


def normalize_board_kind(board_kind: str) -> str:
    token = str(board_kind or "").strip().lower()
    if token not in SUPPORTED_BOARD_KINDS:
        raise ValueError(
            f"Unsupported board kind '{board_kind}'. Expected one of {sorted(SUPPORTED_BOARD_KINDS)}"
        )
    return token


def ensure_storage_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)


def _json_path(sport: str, board_kind: str) -> Path:
    return DATA_DIR / f"{sport}-{board_kind}-board.json"


def _image_path(sport: str, board_kind: str) -> Path:
    return IMAGE_DIR / f"{sport}-{board_kind}-board.png"


def _default_image(board_kind: str, sport: str) -> Optional[str]:
    if board_kind == "trend":
        return None
    return f"/images/{sport}-{board_kind}-board.png"


def _stamp_payload(payload: Dict[str, Any], sport: str, board_kind: str) -> Dict[str, Any]:
    copy = dict(payload)
    copy.setdefault("sport", sport.upper())
    copy.setdefault("board_type", board_kind)
    copy.setdefault("generated_at", datetime.now().astimezone().isoformat(timespec="seconds"))
    if board_kind in {"outlook", "confirmed"}:
        copy.setdefault("image", _default_image(board_kind, sport))
    copy.setdefault("lastUpdated", copy.get("generated_at"))
    return copy


def save_board_json(sport: str, board_kind: str, payload: Dict[str, Any]) -> Path:
    sport = normalize_sport_key(sport)
    board_kind = normalize_board_kind(board_kind)
    ensure_storage_dirs()
    target = _json_path(sport, board_kind)
    stamped = _stamp_payload(payload, sport, board_kind)
    target.write_text(json.dumps(stamped, indent=2), encoding="utf-8")
    return target


def save_board_image(
    sport: str,
    board_kind: str,
    *,
    image_bytes: Optional[bytes] = None,
    image_path: Optional[str | Path] = None,
) -> Path:
    sport = normalize_sport_key(sport)
    board_kind = normalize_board_kind(board_kind)
    if board_kind == "trend":
        raise ValueError("Trend board does not support PNG image publishing")
    ensure_storage_dirs()
    target = _image_path(sport, board_kind)
    if image_bytes is not None:
        target.write_bytes(image_bytes)
        return target
    if image_path is not None:
        shutil.copyfile(Path(image_path), target)
        return target
    raise ValueError("Provide either image_bytes or image_path")


def publish_board(
    sport: str,
    board_kind: str,
    *,
    payload: Dict[str, Any],
    image_bytes: Optional[bytes] = None,
    image_path: Optional[str | Path] = None,
) -> Dict[str, Path]:
    paths = {"json": save_board_json(sport, board_kind, payload)}
    if board_kind != "trend" and (image_bytes is not None or image_path is not None):
        paths["image"] = save_board_image(
            sport,
            board_kind,
            image_bytes=image_bytes,
            image_path=image_path,
        )
    return paths


def load_board(sport: str, board_kind: str) -> Optional[Dict[str, Any]]:
    sport = normalize_sport_key(sport)
    board_kind = normalize_board_kind(board_kind)
    path = _json_path(sport, board_kind)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def load_preferred_signal_board(sport: str) -> Optional[Dict[str, Any]]:
    sport = normalize_sport_key(sport)
    for board_kind in BOARD_PRIORITY:
        payload = load_board(sport, board_kind)
        if payload is not None:
            return payload
    return None


def board_exists(sport: str, board_kind: str) -> bool:
    return _json_path(normalize_sport_key(sport), normalize_board_kind(board_kind)).exists()
