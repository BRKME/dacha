"""Жёсткие фильтры (отсев) и мягкий скоринг (ранжирование).

passes_hard() — лот должен пройти ВСЕ жёсткие условия из config.hard.
score_listing() — начисляет баллы 0..100 по мягким критериям. Заполняет
has_pine / has_water / has_power / water_name по тексту, если они ещё
не выставлены источником или OSM-проверкой.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sources.base import Listing


def _has_any(text: str, keywords) -> bool:
    t = (text or "").lower()
    return any(k in t for k in keywords)


def passes_hard(lst: Listing, hard: dict) -> tuple[bool, str]:
    """Возвращает (прошёл, причина_отказа)."""
    if lst.price_rub is not None and lst.price_rub > hard["max_price_rub"]:
        return False, f"цена {lst.price_rub:,}₽ > лимита"
    if lst.area_sot is not None and lst.area_sot < hard["min_area_sot"]:
        return False, f"площадь {lst.area_sot} сот < минимума"
    if lst.distance_km is not None and lst.distance_km > hard["max_distance_km"]:
        return False, f"{lst.distance_km:.1f} км > радиуса"
    if lst.published and hard.get("max_age_days"):
        try:
            pub = datetime.fromisoformat(lst.published.replace("Z", "+00:00"))
            age = (datetime.now(timezone.utc) - pub).days
            if age > hard["max_age_days"]:
                return False, f"объявлению {age} дн"
        except ValueError:
            pass
    return True, ""


def score_listing(lst: Listing, soft: dict) -> int:
    """Скоринг по мягким критериям. Мутирует lst (флаги + notes)."""
    w = soft["weights"]
    blob = f"{lst.title} {lst.description} {lst.address}".lower()
    score = 0

    # сосны/лес — текст или OSM
    if lst.has_pine is None:
        lst.has_pine = _has_any(blob, soft["pine_keywords"])
    if lst.has_pine:
        score += w["pine"]

    # вода — текст или OSM
    if lst.has_water is None:
        lst.has_water = _has_any(blob, soft["water_keywords"])
    if lst.has_water:
        score += w["water"]

    # именованные водоёмы — бонус
    for nm in soft["named_water"]:
        if nm in blob:
            score += w["named_water_bonus"]
            if not lst.water_name:
                lst.water_name = nm
            break

    # электричество
    if lst.has_power is None:
        lst.has_power = _has_any(blob, soft["power_keywords"])
    if lst.has_power:
        score += w["power"]

    # дорога
    if _has_any(blob, ["асфальт", "круглогодичн", "проезд", "грунтов"]):
        score += w["road"]

    lst.score = min(score, 100)
    return lst.score
