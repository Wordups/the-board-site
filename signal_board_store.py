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


def normalize_sport_key(sport: str) -> str:
    token = str(sport or "").strip().lower()
    if token not in SUPPORTED_SPORTS:
        raise ValueError(f"Unsupported sport '{sport}'. Expected one of {sorted(SUPPORTED_SPORTS)}")
    return token


def ensure_storage_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)


def _json_path(sport: str) -> Path:
    return DATA_DIR / f"{sport}-signal-board.json"


def _image_path(sport: str) -> Path:
    return IMAGE_DIR / f"{sport}-signal-board.png"


def _stamp_payload(payload: Dict[str, Any], sport: str) -> Dict[str, Any]:
    copy = dict(payload)
    copy.setdefault("sport", sport.upper())
    copy.setdefault("board_type", "signal-board")
    copy.setdefault("generated_at", datetime.now().astimezone().isoformat(timespec="seconds"))
    copy.setdefault("image", f"/images/{sport}-signal-board.png")
    return copy


def save_signal_board_json(sport: str, payload: Dict[str, Any]) -> Path:
    sport = normalize_sport_key(sport)
    ensure_storage_dirs()
    target = _json_path(sport)
    stamped = _stamp_payload(payload, sport)
    target.write_text(json.dumps(stamped, indent=2), encoding="utf-8")
    return target


def save_signal_board_image(
    sport: str,
    *,
    image_bytes: Optional[bytes] = None,
    image_path: Optional[str | Path] = None,
) -> Path:
    sport = normalize_sport_key(sport)
    ensure_storage_dirs()
    target = _image_path(sport)
    if image_bytes is not None:
      target.write_bytes(image_bytes)
      return target
    if image_path is not None:
        shutil.copyfile(Path(image_path), target)
        return target
    raise ValueError("Provide either image_bytes or image_path")


def publish_signal_board(
    sport: str,
    *,
    payload: Dict[str, Any],
    image_bytes: Optional[bytes] = None,
    image_path: Optional[str | Path] = None,
) -> Dict[str, Path]:
    paths = {"json": save_signal_board_json(sport, payload)}
    if image_bytes is not None or image_path is not None:
        paths["image"] = save_signal_board_image(sport, image_bytes=image_bytes, image_path=image_path)
    return paths


def load_signal_board(sport: str) -> Optional[Dict[str, Any]]:
    sport = normalize_sport_key(sport)
    path = _json_path(sport)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))
