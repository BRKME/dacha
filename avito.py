"""Авито Недвижимость — приоритетный источник.

Статус: антибот пройден (РФ-прокси + curl_cffi TLS — соединение доходит).
Идёт поиск рабочего внутреннего эндпоинта каталога. Модуль перебирает
кандидатов (web + мобильный API), КАЖДЫЙ ответ сохраняет в debug/avito_<tag>.html,
и принимает эндпоинт только при HTTP 200 с непустым списком. На 404/502 — идёт
дальше. По дампам с кодом 200 выверяются точные поля и параметры.
"""
from __future__ import annotations

import json
import os

from base import BaseSource, Listing, SourceResult, SourceStatus

# Публичный ключ мобильного API Авито (используется их приложением).
MOBILE_KEY = "af0deccbgcgidddjgnvljitntccdduijhdinfgjgfjir"


def _web_params(price_max: int) -> dict:
    return {"categoryId": 24, "locationId": 643,
            "priceMax": price_max, "sort": "date", "limit": 50}


def _mobile_params(price_max: int) -> dict:
    return {"key": MOBILE_KEY, "categoryId": 24, "locationId": 643,
            "priceMax": price_max, "sort": "date", "limit": 50,
            "display": "list", "page": 1}


# (tag, url, params-builder)
def candidates(price_max: int):
    return [
        ("web1_js",   "https://www.avito.ru/web/1/js/items",  _web_params(price_max)),
        ("web1_main", "https://www.avito.ru/web/1/main/items", _web_params(price_max)),
        ("m_api9",    "https://m.avito.ru/api/9/items",  _mobile_params(price_max)),
        ("m_api11",   "https://m.avito.ru/api/11/items", _mobile_params(price_max)),
        ("m_api12",   "https://m.avito.ru/api/12/items", _mobile_params(price_max)),
    ]


SEARCH_URL = "https://www.avito.ru/leningradskaya_oblast/zemelnye_uchastki"


class Source(BaseSource):
    name = "avito"

    def fetch(self) -> SourceResult:
        try:
            from curl_cffi import requests as creq
        except ImportError:
            return SourceResult(self.name, SourceStatus.ERROR,
                                message="нет curl_cffi (добавь в requirements.txt)")

        proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY")
        proxies = {"http": proxy, "https": proxy} if proxy else None
        price_max = self.cfg["hard"]["max_price_rub"]

        trail = []
        first_ok = None  # (tag, lots)
        for tag, url, params in candidates(price_max):
            try:
                resp = creq.get(
                    url, params=params,
                    headers={"Accept": "application/json", "Accept-Language": "ru-RU,ru"},
                    impersonate="chrome", proxies=proxies, timeout=30,
                )
            except Exception as e:  # noqa: BLE001
                trail.append(f"{tag}:err")
                self.debug_dump(f"{self.name}_{tag}", f"EXC {e}")
                continue

            self.debug_dump(f"{self.name}_{tag}", resp.text or "")
            trail.append(f"{tag}:{resp.status_code}")

            # принимаем ТОЛЬКО 200 + валидный JSON со списком
            if resp.status_code == 200:
                try:
                    data = json.loads(resp.text or "")
                except json.JSONDecodeError:
                    continue
                lots = self._parse(data)
                if lots and first_ok is None:
                    first_ok = (tag, lots)
                    break  # нашли рабочий — хватит

        if first_ok:
            tag, lots = first_ok
            return SourceResult(self.name, SourceStatus.OK, listings=lots,
                                message=f"JSON от {tag} ({len(lots)}); {', '.join(trail)}")

        self._dump_html_page(creq, proxies)
        return SourceResult(
            self.name, SourceStatus.BLOCKED,
            message=f"рабочий эндпоинт не найден: {', '.join(trail)} (см. debug/avito_*.html)",
        )

    def _dump_html_page(self, creq, proxies) -> None:
        try:
            r = creq.get(SEARCH_URL, impersonate="chrome", proxies=proxies, timeout=30)
            self.debug_dump(self.name + "_page", r.text)
        except Exception:  # noqa: BLE001
            pass

    def _parse(self, data: dict) -> list[Listing]:
        out: list[Listing] = []
        items = (data.get("items")
                 or (data.get("catalog") or {}).get("items")
                 or (data.get("result") or {}).get("items")
                 or [])
        for it in items:
            if not isinstance(it, dict) or it.get("type") not in (None, "item"):
                continue
            price = it.get("priceDetailed", {}) or {}
            coords = it.get("coords") or (it.get("location") or {}).get("coords") or {}
            url = it.get("urlPath") or it.get("url") or ""
            if url.startswith("/"):
                url = "https://www.avito.ru" + url
            out.append(Listing(
                source=self.name, url=url,
                title=(it.get("title") or "")[:120],
                price_rub=_to_int(price.get("value") or it.get("price")),
                area_sot=_area(it),
                address=(it.get("address") or (it.get("geo") or {}).get("formattedAddress", "")),
                lat=_to_float(coords.get("lat")),
                lon=_to_float(coords.get("lng") or coords.get("lon")),
                description=(it.get("description") or "")[:800],
            ))
        return out


def _area(it: dict):
    for key in ("area", "landArea", "square"):
        v = it.get(key)
        if v:
            try:
                return float(str(v).replace(",", "."))
            except ValueError:
                pass
    return None


def _to_int(v):
    try:
        return int(float(v)) if v is not None else None
    except (TypeError, ValueError):
        return None


def _to_float(v):
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None
