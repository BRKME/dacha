"""Авито Недвижимость — приоритетный источник.

Статус: антибот пройден (РФ-прокси + curl_cffi TLS-имитация — соединение
устанавливается, путь доходит до Авито). Осталось нащупать рабочий внутренний
эндпоинт каталога: прежний /web/1/main/items отдаёт 502.

Этот модуль ПЕРЕБИРАЕТ несколько кандидатов-эндпоинтов и сохраняет сырой
ответ каждого в debug/avito_<tag>.html. Первый, отдавший валидный JSON со
списком, используется как источник лотов; остальные — для разбора по дампам.
"""
from __future__ import annotations

import json
import os

from base import BaseSource, Listing, SourceResult, SourceStatus

PRICE_PARAM = "priceMax"

# Кандидаты внутренних API каталога Авито. Параметры подставляются ниже.
# tag нужен для имени дамп-файла. Перебор идёт сверху вниз до первого JSON.
CANDIDATES = [
    ("web9_js", "https://www.avito.ru/web/9/js/items"),
    ("web1_js", "https://www.avito.ru/web/1/js/items"),
    ("m_api9",  "https://m.avito.ru/api/9/items"),
    ("m_api11", "https://m.avito.ru/api/11/items"),
    ("web1_main", "https://www.avito.ru/web/1/main/items"),
]
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
            PRICE_PARAM: self.cfg["hard"]["max_price_rub"],
            "sort": "date",
            "limit": 50,
        }

        tried = []
        for tag, url in CANDIDATES:
            try:
                resp = creq.get(
                    url, params=params,
                    headers={"Accept": "application/json",
                             "Accept-Language": "ru-RU,ru"},
                    impersonate="chrome", proxies=proxies, timeout=30,
                )
            except Exception as e:  # noqa: BLE001
                tried.append(f"{tag}:err")
                self.debug_dump(f"{self.name}_{tag}", f"EXC {e}")
                continue

            body = resp.text or ""
            self.debug_dump(f"{self.name}_{tag}", body)
            tried.append(f"{tag}:{resp.status_code}")

            # пытаемся распарсить JSON
            try:
                data = json.loads(body)
            except json.JSONDecodeError:
                continue  # не JSON (502/HTML) — пробуем следующий

            lots = self._parse(data)
            return SourceResult(
                self.name, SourceStatus.OK, listings=lots,
                message=f"JSON от {tag} ({len(lots)} лотов); перебор: {', '.join(tried)}",
            )

        # ни один кандидат не отдал JSON — снимем ещё и HTML страницы
        self._dump_html_page(creq, proxies)
        return SourceResult(
            self.name, SourceStatus.BLOCKED,
            message=f"ни один эндпоинт не дал JSON: {', '.join(tried)} "
                    "(см. debug/avito_*.html)",
        )

    def _dump_html_page(self, creq, proxies) -> None:
        try:
            r = creq.get(SEARCH_URL, impersonate="chrome",
                         proxies=proxies, timeout=30)
            self.debug_dump(self.name + "_page", r.text)
        except Exception:  # noqa: BLE001
            pass

    def _parse(self, data: dict) -> list[Listing]:
        """Разбор JSON-каталога. Точные поля выверить по рабочему дампу."""
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
