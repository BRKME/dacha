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

import requests

from base import BaseSource, Listing, SourceResult, SourceStatus

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

# Каркас. Подставить реальный поисковый эндпоинт выбранной площадки.
SEARCH_URL = "https://catalog.lot-online.ru/index.php"


class Source(BaseSource):
    name = "bank_torgi"

    def fetch(self) -> SourceResult:
        session = requests.Session()
        session.headers.update({"User-Agent": UA, "Accept-Language": "ru-RU,ru"})
        listings: list[Listing] = []
        try:
            resp = session.get(
                SEARCH_URL,
                params={"dispatch": "products.search",
                        "q": "земельный участок Ленинградская область",
                        "price_to": self.cfg["hard"]["max_price_rub"]},
                timeout=25,
            )
            if resp.status_code in (403, 429):
                return SourceResult(self.name, SourceStatus.BLOCKED,
                                    message=f"HTTP {resp.status_code}")
            listings = self._parse(resp.text)
        except Exception as e:  # noqa: BLE001
            return SourceResult(self.name, SourceStatus.ERROR, message=str(e))
        return SourceResult(self.name, SourceStatus.OK, listings=listings)

    def _parse(self, html_text: str) -> list[Listing]:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html_text, "html.parser")
        out: list[Listing] = []
        for c in soup.select("[class*='product'], [class*='lot'], article"):
            link = c.find("a", href=True)
            if not link:
                continue
            text = c.get_text(" ", strip=True)
            price = self.parse_price(text)
            if price is None:
                continue
            url = link["href"]
            if url.startswith("/"):
                url = "https://catalog.lot-online.ru" + url
            out.append(Listing(
                source=self.name,
                url=url,
                title=link.get_text(strip=True)[:120],
                price_rub=price,
                area_sot=self.parse_area_sot(text),
                land_status=self.detect_land_status(text),
                description=text[:800],
            ))
        return out
