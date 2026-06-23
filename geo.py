"""Гео-утилиты: расстояние до якоря и проверка природы по OpenStreetMap.

osm_nature() опционален — он делает запрос к Overpass API и проверяет,
есть ли рядом с координатами лота лес (natural=wood / landuse=forest) и
вода (natural=water / waterway). Это страхует случаи, когда продавец не
написал про сосны/озеро в тексте, но они физически рядом.
"""
from __future__ import annotations

import math
from typing import Optional, Tuple

import requests

OVERPASS_URL = "https://overpass-api.de/api/interpreter"


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Расстояние между двумя точками в км."""
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlam / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def osm_nature(lat: float, lon: float, radius_m: int = 1500,
               timeout: int = 25) -> Tuple[Optional[bool], Optional[bool], str]:
    """Возвращает (есть_лес, есть_вода, имя_водоёма).

    None означает «не смогли проверить» (сеть/таймаут), это не то же самое
    что False. Имя водоёма берётся из тега name ближайшего объекта воды.
    """
    query = f"""
    [out:json][timeout:{timeout}];
    (
      way["natural"="wood"](around:{radius_m},{lat},{lon});
      way["landuse"="forest"](around:{radius_m},{lat},{lon});
      way["natural"="water"](around:{radius_m},{lat},{lon});
      relation["natural"="water"](around:{radius_m},{lat},{lon});
      way["waterway"](around:{radius_m},{lat},{lon});
    );
    out tags 30;
    """
    try:
        resp = requests.post(OVERPASS_URL, data={"data": query}, timeout=timeout + 5)
        resp.raise_for_status()
        elements = resp.json().get("elements", [])
    except Exception:
        return None, None, ""

    has_forest = False
    has_water = False
    water_name = ""
    for el in elements:
        tags = el.get("tags", {})
        if tags.get("natural") == "wood" or tags.get("landuse") == "forest":
            has_forest = True
        if tags.get("natural") == "water" or "waterway" in tags:
            has_water = True
            if not water_name and tags.get("name"):
                water_name = tags["name"]
    return has_forest, has_water, water_name
