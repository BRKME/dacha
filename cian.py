"""Циан — PHASE 2.

CONFIDENCE: низкая с Actions-IP. Циан режет автоматический доступ
(Qrator/анти-бот), datacenter-адреса быстро ловят капчу/403.

У Циана есть JSON-API поиска (api.cian.ru/search-offers/...), который при
наличии нормального IP отдаёт структурированные офферы. Каркас под него
оставлен; включается флагом sources.cian=true + рабочий прокси.
"""
from __future__ import annotations

import os

import requests

from base import BaseSource, Listing, SourceResult, SourceStatus

API_URL = "https://api.cian.ru/search-offers/v2/search-offers-desktop/"


class Source(BaseSource):
    name = "cian"

    def fetch(self) -> SourceResult:
        proxies = self.get_proxies("CIAN_PROXY_URL")
        if not proxies:
            return SourceResult(
                self.name, SourceStatus.BLOCKED,
                message="нет прокси (CIAN_PROXY_URL/PROXY_URL); Циан недоступен с Actions-IP",
            )
        body = {
            "jsonQuery": {
                "_type": "suburbansale",
                "engine_version": {"type": "term", "value": 2},
                "object_type": {"type": "terms", "value": [1]},  # участки
                "region": {"type": "terms", "value": [4588, 1]},  # ЛО + СПб
                "price": {"type": "range",
                          "value": {"lte": self.cfg["hard"]["max_price_rub"]}},
            }
        }
        try:
            resp = requests.post(API_URL, json=body, proxies=proxies, timeout=30,
                                 headers={"Content-Type": "application/json"})
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
        offers = (data.get("data", {}) or {}).get("offersSerialized", [])
        for o in offers:
            geo = (o.get("geo", {}) or {}).get("coordinates", {}) or {}
            out.append(Listing(
                source=self.name,
                url=o.get("fullUrl", ""),
                title=(o.get("title") or o.get("description") or "")[:120],
                price_rub=(o.get("bargainTerms", {}) or {}).get("price"),
                area_sot=_to_sot(o.get("totalArea")),
                address=", ".join(g.get("fullName", "")
                                  for g in (o.get("geo", {}) or {}).get("address", [])),
                lat=geo.get("lat"),
                lon=geo.get("lng"),
                description=(o.get("description") or "")[:800],
            ))
        return out


def _to_sot(value):
    # Циан по участкам обычно отдаёт сотки в totalArea
    try:
        return float(value) if value else None
    except (TypeError, ValueError):
        return None
