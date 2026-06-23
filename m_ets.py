"""МЭТС — m-ets.ru (Межрегиональная электронная торговая система).

CONFIDENCE: низко-средняя (scaffold). Банкротная ЭТП с поиском по лотам.
Селекторы — каркас, фейлится безопасно (0 лотов при несовпадении, не мусор).
Чинится по debug/m_ets.html (DACHA_DEBUG=1).
"""
from __future__ import annotations

import requests
from bs4 import BeautifulSoup

from base import BaseSource, Listing, SourceResult, SourceStatus

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

SEARCH_URL = "https://m-ets.ru/trade/"   # каркас; реальный путь поиска уточнить по дампу

_JUNK = {"подробнее", "показать", "найти", "сбросить", "ещё", "еще",
         "далее", "назад", "войти", "регистрация", "участок", "лот"}


class Source(BaseSource):
    name = "m_ets"

    def fetch(self) -> SourceResult:
        s = self.session(UA)
        try:
            resp = s.get(SEARCH_URL,
                         params={"q": "земельный участок Ленинградская область",
                                 "category": "land"},
                         timeout=25)
            self.debug_dump(self.name, resp.text)
            if resp.status_code in (403, 429):
                return SourceResult(self.name, SourceStatus.BLOCKED,
                                    message=f"HTTP {resp.status_code}")
            return SourceResult(self.name, SourceStatus.OK,
                                listings=self._parse(resp.text))
        except Exception as e:  # noqa: BLE001
            return SourceResult(self.name, SourceStatus.ERROR, message=str(e))

    def _parse(self, html_text: str) -> list[Listing]:
        soup = BeautifulSoup(html_text, "html.parser")
        out, seen = [], set()
        for c in soup.select("[class*='lot'], [class*='card'], [class*='item'], article"):
            link = c.find("a", href=True)
            if not link:
                continue
            url, anchor = link["href"], link.get_text(strip=True)
            if anchor.lower() in _JUNK or url in ("/", "#"):
                continue
            text = c.get_text(" ", strip=True)
            price = self.parse_price(text)
            if price is None:
                continue
            if url.startswith("/"):
                url = "https://m-ets.ru" + url
            if url in seen:
                continue
            seen.add(url)
            out.append(Listing(
                source=self.name, url=url, title=anchor[:120], price_rub=price,
                area_sot=self.parse_area_sot(text),
                land_status=self.detect_land_status(text), description=text[:800],
            ))
        return out
