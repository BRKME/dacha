"""Мир Квартир — лёгкая защита, реалистично берётся с Actions-IP.

CONFIDENCE: средне-высокая. Это HTML-парсер по CSS-классам листинга.
ВАЖНО: разметку проверить на первом прогоне — у агрегаторов классы
меняются. Если селекторы поехали, fetch() вернёт OK с 0 лотов (не BLOCKED),
поэтому при подозрительном нуле сверяйся с живой страницей.
"""
from __future__ import annotations

import time
import urllib.parse

import requests
from bs4 import BeautifulSoup

from base import BaseSource, Listing, SourceResult, SourceStatus

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

# Регион ЛО/СПб, раздел «участки». Базовый URL — каркас; параметры локации
# и цены добавляются из конфига.
SEARCH_URL = "https://www.mirkvartir.ru/Ленинградская+область/участки/"


class Source(BaseSource):
    name = "mirkvartir"

    def fetch(self) -> SourceResult:
        max_price = self.cfg["hard"]["max_price_rub"]
        listings: list[Listing] = []
        session = self.session(UA)

        queries = self.cfg["locations"]["primary"]
        try:
            for i, q in enumerate(queries):
                url = SEARCH_URL + "?" + urllib.parse.urlencode(
                    {"q": q, "pricemax": max_price}
                )
                resp = session.get(url, timeout=25)
                self.debug_dump(f"{self.name}_{i}", resp.text)
                if resp.status_code in (403, 429) or "captcha" in resp.text.lower():
                    return SourceResult(self.name, SourceStatus.BLOCKED,
                                        message=f"HTTP {resp.status_code}/captcha")
                listings.extend(self._parse(resp.text))
                time.sleep(2)  # вежливая пауза
        except Exception as e:  # noqa: BLE001
            return SourceResult(self.name, SourceStatus.ERROR, message=str(e))

        # дедуп внутри источника по url
        uniq = {l.url: l for l in listings}
        return SourceResult(self.name, SourceStatus.OK, listings=list(uniq.values()))

    def _parse(self, html_text: str) -> list[Listing]:
        soup = BeautifulSoup(html_text, "html.parser")
        out: list[Listing] = []
        # СЕЛЕКТОРЫ-КАРКАС: проверить на живой выдаче и поправить под факт.
        cards = soup.select("[class*='snippet'], [class*='card'], article")
        for c in cards:
            link = c.find("a", href=True)
            if not link:
                continue
            url = link["href"]
            if url.startswith("/"):
                url = "https://www.mirkvartir.ru" + url
            text = c.get_text(" ", strip=True)
            price = self.parse_price(text)
            if price is None:
                continue
            out.append(Listing(
                source=self.name,
                url=url,
                title=link.get_text(strip=True)[:120],
                price_rub=price,
                area_sot=self.parse_area_sot(text),
                address="",            # уточняется на странице лота при enrich
                land_status=self.detect_land_status(text),
                description=text[:800],
            ))
        return out
