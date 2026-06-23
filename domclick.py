"""Домклик (Сбер).

CONFIDENCE: переменная. У Домклика есть JSON-API каталога
(api.domclick.ru), который иногда отдаёт данные без жёсткой капчи, но
требует корректных заголовков и может банить datacenter-IP. Каркас бьёт
по API офферов; при 403/429 — BLOCKED.
"""
from __future__ import annotations

import requests

from .base import BaseSource, Listing, SourceResult, SourceStatus

UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
      "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile Safari/604.1")

# Каркас эндпоинта каталога. Параметры геофильтра/категории уточнить.
API_URL = "https://offers-service.domclick.ru/research/v5/offers/"


class Source(BaseSource):
    name = "domclick"

    def fetch(self) -> SourceResult:
        session = requests.Session()
        session.headers.update({
            "User-Agent": UA,
            "Accept": "application/json",
            "Accept-Language": "ru-RU,ru",
        })
        try:
            resp = session.get(
                API_URL,
                params={
                    "offer_type": "layout",
                    "category": "country",     # загородка
                    "deal_type": "sale",
                    "address": "Ленинградская область",
                    "price__lte": self.cfg["hard"]["max_price_rub"],
                    "sort": "price",
                    "sort_dir": "asc",
                    "offset": 0, "limit": 50,
                },
                timeout=25,
            )
            if resp.status_code in (403, 429):
                return SourceResult(self.name, SourceStatus.BLOCKED,
                                    message=f"HTTP {resp.status_code}")
            data = resp.json()
        except Exception as e:  # noqa: BLE001
            return SourceResult(self.name, SourceStatus.ERROR, message=str(e))
        return SourceResult(self.name, SourceStatus.OK,
                            listings=self._parse(data))

    def _parse(self, data: dict) -> list[Listing]:
        out: list[Listing] = []
        items = (data.get("result", {}) or {}).get("items") or data.get("items", [])
        for it in items:
            addr = (it.get("address", {}) or {}).get("display_name", "")
            coords = (it.get("address", {}) or {}).get("position", {}) or {}
            out.append(Listing(
                source=self.name,
                url="https://domclick.ru/card/sale__land__" + str(it.get("id", "")),
                title=(it.get("description") or addr)[:120],
                price_rub=it.get("price"),
                area_sot=_to_sot(it.get("land_area"), it.get("land_area_unit")),
                address=addr,
                lat=coords.get("lat"),
                lon=coords.get("lon"),
                description=(it.get("description") or "")[:800],
            ))
        return out


def _to_sot(value, unit):
    if not value:
        return None
    if (unit or "").lower() in ("hectare", "га"):
        return float(value) * 100
    return float(value)
