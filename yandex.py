"""Яндекс.Недвижимость.

CONFIDENCE: переменная. Отдаёт данные через встроенный в страницу JSON
(initialState), но капча с datacenter-IP прилетает регулярно. Парсер ищет
JSON-блок состояния; если его нет или стоит SmartCaptcha — BLOCKED.
"""
from __future__ import annotations

import json
import re

import requests

from .base import BaseSource, Listing, SourceResult, SourceStatus

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

# Каталог участков, ЛО. rgid/параметры геофильтра уточнить под регион.
SEARCH_URL = "https://realty.yandex.ru/sankt-peterburg_i_leningradskaya_oblast/kupit/uchastok/"

_STATE_RE = re.compile(r'<script[^>]*>\s*window\.__INITIAL_STATE__\s*=\s*(\{.*?\})\s*</script>',
                       re.DOTALL)


class Source(BaseSource):
    name = "yandex"

    def fetch(self) -> SourceResult:
        session = requests.Session()
        session.headers.update({"User-Agent": UA, "Accept-Language": "ru-RU,ru"})
        try:
            resp = session.get(
                SEARCH_URL,
                params={"priceMax": self.cfg["hard"]["max_price_rub"],
                        "sort": "PRICE"},
                timeout=25,
            )
            if "captcha" in resp.text.lower() or resp.status_code in (403, 429):
                return SourceResult(self.name, SourceStatus.BLOCKED,
                                    message="SmartCaptcha / 403")
            m = _STATE_RE.search(resp.text)
            if not m:
                return SourceResult(self.name, SourceStatus.BLOCKED,
                                    message="no initial state (likely captcha wall)")
            listings = self._parse_state(m.group(1))
        except Exception as e:  # noqa: BLE001
            return SourceResult(self.name, SourceStatus.ERROR, message=str(e))
        return SourceResult(self.name, SourceStatus.OK, listings=listings)

    def _parse_state(self, raw: str) -> list[Listing]:
        out: list[Listing] = []
        try:
            state = json.loads(raw)
        except json.JSONDecodeError:
            return out
        # Структура initialState у Яндекса вложенная и меняется — ищем
        # любые объекты с признаками оффера рекурсивно.
        for offer in _walk_offers(state):
            price = offer.get("price", {}).get("value") if isinstance(offer.get("price"), dict) else None
            loc = offer.get("location", {}) or {}
            out.append(Listing(
                source=self.name,
                url="https://realty.yandex.ru/offer/" + str(offer.get("offerId", "")),
                title=offer.get("description", "")[:120],
                price_rub=price,
                area_sot=_area_to_sot(offer.get("area")),
                address=loc.get("address", ""),
                lat=loc.get("point", {}).get("latitude"),
                lon=loc.get("point", {}).get("longitude"),
                description=offer.get("description", "")[:800],
            ))
        return out


def _walk_offers(node, depth=0):
    if depth > 8:
        return
    if isinstance(node, dict):
        if "offerId" in node and ("price" in node or "location" in node):
            yield node
        for v in node.values():
            yield from _walk_offers(v, depth + 1)
    elif isinstance(node, list):
        for v in node:
            yield from _walk_offers(v, depth + 1)


def _area_to_sot(area):
    if isinstance(area, dict) and area.get("value"):
        unit = (area.get("unit") or "").upper()
        val = area["value"]
        if unit in ("SOTKA", "СОТ"):
            return float(val)
        if unit in ("HECTARE", "ГА"):
            return float(val) * 100
    return None
