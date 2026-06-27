"""Авито Недвижимость — приоритетный источник.

Подход: внутренний JSON-API каталога Авито + curl_cffi с TLS-имитацией Chrome.
Два слоя антибана сняты: IP (РФ-прокси из окружения) + TLS-фингерпринт
(curl_cffi impersonate). Поведенческий слой не покрыт — возможна капча,
тогда источник честно отдаёт BLOCKED, а сырой ответ падает в debug/avito_api.html
для разбора (как делали с bank_torgi).

ВАЖНО: точные имена полей JSON и параметры (categoryId/locationId) выверяются
по первому дампу. Парсер рассчитан на типовую структуру items[], подтвердить
на живом ответе (DACHA_DEBUG=1 → debug/avito_api.html).
"""
from __future__ import annotations

import os

from base import BaseSource, Listing, SourceResult, SourceStatus

# Внутренний каталог Авито (web). Параметры выверить по дампу.
# categoryId=24 — «Земельные участки»; locationId 643 — Ленобласть (подтвердить).
API_URL = "https://www.avito.ru/web/1/main/items"
SEARCH_URL = "https://www.avito.ru/leningradskaya_oblast/zemelnye_uchastki"


class Source(BaseSource):
    name = "avito"

    def fetch(self) -> SourceResult:
        try:
            from curl_cffi import requests as creq
        except ImportError:
            return SourceResult(
                self.name, SourceStatus.ERROR,
                message="нет curl_cffi (добавь в requirements.txt)",
            )

        proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY")
        proxies = {"http": proxy, "https": proxy} if proxy else None

        params = {
            "categoryId": 24,
            "locationId": 643,
            "priceMax": self.cfg["hard"]["max_price_rub"],
            "sort": "date",
            "limit": 50,
            "display": "list",
        }
        try:
            resp = creq.get(
                API_URL,
                params=params,
                headers={"Accept": "application/json",
                         "X-Requested-With": "XMLHttpRequest",
                         "Accept-Language": "ru-RU,ru"},
                impersonate="chrome",
                proxies=proxies,
                timeout=30,
            )
            self.debug_dump(self.name + "_api", resp.text)
            if resp.status_code in (403, 429) or "firewall" in resp.text.lower():
                self._dump_html_page(creq, proxies)
                return SourceResult(
                    self.name, SourceStatus.BLOCKED,
                    message=f"HTTP {resp.status_code}/firewall "
                            "(поведенческий слой; см. debug/avito_api.html)",
                )
            data = resp.json()
        except Exception as e:  # noqa: BLE001
            return SourceResult(self.name, SourceStatus.ERROR, message=str(e))

        return SourceResult(self.name, SourceStatus.OK, listings=self._parse(data))

    def _dump_html_page(self, creq, proxies) -> None:
        try:
            r = creq.get(SEARCH_URL, impersonate="chrome",
                         proxies=proxies, timeout=30)
            self.debug_dump(self.name + "_page", r.text)
        except Exception:  # noqa: BLE001
            pass

    def _parse(self, data: dict) -> list[Listing]:
        """Разбор JSON-каталога. Структуру выверить по debug/avito_api.html:
        лоты обычно в data['items'] или data['catalog']['items']."""
        out: list[Listing] = []
        items = (data.get("items")
                 or (data.get("catalog") or {}).get("items")
                 or (data.get("result") or {}).get("items")
                 or [])
        for it in items:
            if not isinstance(it, dict):
                continue
            if it.get("type") not in (None, "item"):
                continue
            price = it.get("priceDetailed", {}) or {}
            coords = it.get("coords") or (it.get("location") or {}).get("coords") or {}
            url = it.get("urlPath") or it.get("url") or ""
            if url.startswith("/"):
                url = "https://www.avito.ru" + url
            out.append(Listing(
                source=self.name,
                url=url,
                title=(it.get("title") or "")[:120],
                price_rub=_to_int(price.get("value") or it.get("price")),
                area_sot=_area(it),
                address=(it.get("address")
                         or (it.get("geo") or {}).get("formattedAddress", "")),
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
