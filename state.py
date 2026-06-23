"""Стейт в committed JSON (паттерн BRKME — без БД).

state/seen.json   — {uid: {price, first_seen, last_seen}} для дедупа и
                    отслеживания снижения цены.
state/listings.json — последний полный снапшот прошедших фильтр лотов
                    (для дебага/истории).

classify() делит лоты на новые / подешевевшие / уже виденные.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from sources.base import Listing

STATE_DIR = Path(__file__).resolve().parent.parent / "state"
SEEN_PATH = STATE_DIR / "seen.json"
SNAPSHOT_PATH = STATE_DIR / "listings.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_seen() -> dict:
    if SEEN_PATH.exists():
        try:
            return json.loads(SEEN_PATH.read_text("utf-8"))
        except json.JSONDecodeError:
            return {}
    return {}


def classify(listings: list[Listing], seen: dict):
    """-> (new, price_drops). Мутирует seen (обновляет last_seen/price)."""
    new, drops = [], []
    for lst in listings:
        uid = lst.uid
        rec = seen.get(uid)
        if rec is None:
            seen[uid] = {
                "price": lst.price_rub,
                "first_seen": _now(),
                "last_seen": _now(),
            }
            new.append(lst)
        else:
            old_price = rec.get("price")
            if (lst.price_rub is not None and old_price is not None
                    and lst.price_rub < old_price):
                lst.notes.append(f"цена ↓ {old_price:,}→{lst.price_rub:,}₽")
                drops.append(lst)
            rec["last_seen"] = _now()
            rec["price"] = lst.price_rub
    return new, drops


def save(seen: dict, listings: list[Listing]):
    STATE_DIR.mkdir(exist_ok=True)
    SEEN_PATH.write_text(json.dumps(seen, ensure_ascii=False, indent=2), "utf-8")
    snap = [l.to_dict() for l in sorted(listings, key=lambda x: -x.score)]
    SNAPSHOT_PATH.write_text(json.dumps(snap, ensure_ascii=False, indent=2), "utf-8")
