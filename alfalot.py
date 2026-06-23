"""Alfalot — alfalot.ru (агрегатор банкротных торгов).

CONFIDENCE: низко-средняя (scaffold). Агрегатор лотов, обычно серверный HTML
с пагинацией. Селекторы — каркас, фейлится безопасно. Чинится по
debug/alfalot.html (DACHA_DEBUG=1).
"""
from __future__ import annotations

import requests
from bs4 import BeautifulSoup

from base import BaseSource, Listing, SourceResult, SourceStatus

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

SEARCH_URL = "https://alfalot.ru/lots/"   # каркас; реальный путь/параметры по дампу

_JUNK = {"подробнее", "показать", "найти", "сбросить", "ещё", "еще",
         "далее", "назад", "войти", "регистрация", "участок", "лот", "все лоты"}


class Source(BaseSource):
    name = "alfalot"

    def fetch(self) -> SourceResult:
        s = self.session(UA)
        try:
            resp = s.get(SEARCH_URL,
                         params={"q": "земельный участок",
                                 "region": "Ленинградская область",
                                 "price_to": self.cfg["hard"]["max_price_rub"]},
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
        for c in soup.select("[class*='lot'], [class*='card'], [class*='offer'], article"):
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
                url = "https://alfalot.ru" + url
            if url in seen:
                continue
            seen.add(url)
            out.append(Listing(
                source=self.name, url=url, title=anchor[:120], price_rub=price,
                area_sot=self.parse_area_sot(text),
                land_status=self.detect_land_status(text), description=text[:800],
            ))
        return out
