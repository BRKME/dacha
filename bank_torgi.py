"""Залоговые торги банков и агрегаторы залогового имущества.

CONFIDENCE: средняя. Тут часто бывают открытые реестры/поиск, поэтому
с Actions-IP реальнее, чем Авито/Циан. Но площадок много и у каждой свой
формат. Каркас рассчитан на один источник (РАД / lot-online), остальные
добавляются по аналогии.

Полезные точки входа (проверить вручную, форматы меняются):
  • lot-online.ru (РАД)        — поиск по «земельные участки» + регион
  • portal-da.ru / Сбербанк-АСТ — реестр залогового имущества
  • torgi.gov.ru               — гос/банкротные торги, есть выгрузки
"""
from __future__ import annotations

import re
import requests

from base import BaseSource, Listing, SourceResult, SourceStatus

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

# Реальная категория «Земельные участки» на lot-online = category_id=2
# (вытащено из живого каталога). CS-Cart, серверный рендер.
SEARCH_URL = "https://catalog.lot-online.ru/index.php"
CATEGORY_ID = 2


class Source(BaseSource):
    name = "bank_torgi"

    def fetch(self) -> SourceResult:
        session = requests.Session()
        session.headers.update({"User-Agent": UA, "Accept-Language": "ru-RU,ru"})
        listings: list[Listing] = []
        try:
            resp = session.get(
                SEARCH_URL,
                params={"dispatch": "categories.view",
                        "category_id": CATEGORY_ID,
                        "items_per_page": 100},
                timeout=25,
            )
            self.debug_dump(self.name, resp.text)
            if resp.status_code in (403, 429):
                return SourceResult(self.name, SourceStatus.BLOCKED,
                                    message=f"HTTP {resp.status_code}")
            listings = self._parse(resp.text)
        except Exception as e:  # noqa: BLE001
            return SourceResult(self.name, SourceStatus.ERROR, message=str(e))
        return SourceResult(self.name, SourceStatus.OK, listings=listings)

    # лоты банкротные, по всей РФ и без координат — оставляем только наш регион
    _REGION = ("ленинград", "ленобл", "санкт-петербург", "спб", "всеволож",
               "выборг", "белоостров", "сертолово", "курортн", "приозерск",
               "юкки", "осиновая роща", "песочн", "солнечн")

    @staticmethod
    def _price_from_el(el) -> int | None:
        # .ty-price-num содержит чистое число без «руб» — берём цифры напрямую
        if el is None:
            return None
        digits = re.sub(r"[^\d]", "", el.get_text(strip=True))
        return int(digits) if len(digits) >= 5 else None

    def _parse(self, html_text: str) -> list[Listing]:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html_text, "html.parser")
        out: list[Listing] = []
        seen: set[str] = set()
        for it in soup.select(".ty-grid-list__item"):
            a = it.select_one("a.product-title")
            if not a or not a.get("href"):
                continue
            title = a.get_text(strip=True)
            url = a["href"]
            if not title or url in seen:
                continue
            seen.add(url)
            # без координат фильтруем по упоминанию региона в названии
            if not any(k in title.lower() for k in self._REGION):
                continue
            price_el = it.select_one(".ty-price-num") or it.select_one(".ty-price")
            out.append(Listing(
                source=self.name,
                url=url,
                title=title[:120],
                price_rub=self._price_from_el(price_el),
                area_sot=self.parse_area_sot(title),
                land_status=self.detect_land_status(title),
                description=title[:800],
            ))
        return out
