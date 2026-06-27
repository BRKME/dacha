"""Авито Недвижимость — через Playwright (реальный Chromium).

Зачем браузер: curl_cffi проходит TLS, но Firewall Авито режет по IP/поведению.
Реальный Chromium исполняет JS-челлендж — если Firewall «мягкий», проходит и
рендерит выдачу. Если требуется настоящая капча — упрёмся в неё (видно в дампе).

Трафик идёт через прокси из окружения (DACHA_PROXY_URL/HTTPS_PROXY), чтобы у
Авито был РФ-IP. Карточки парсятся по СТАБИЛЬНЫМ data-marker атрибутам.
"""
from __future__ import annotations

import os
import re
from urllib.parse import urlparse

from base import BaseSource, Listing, SourceResult, SourceStatus

SEARCH_URL = ("https://www.avito.ru/leningradskaya_oblast/zemelnye_uchastki"
              "?pmax={pmax}&s=104")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")


def _proxy_for_playwright():
    """Разбирает DACHA_PROXY_URL/HTTPS_PROXY в формат Playwright."""
    url = os.environ.get("DACHA_PROXY_URL") or os.environ.get("HTTPS_PROXY") \
        or os.environ.get("HTTP_PROXY")
    if not url:
        return None
    p = urlparse(url)
    server = f"{p.scheme}://{p.hostname}:{p.port}"
    cfg = {"server": server}
    if p.username:
        cfg["username"] = p.username
    if p.password:
        cfg["password"] = p.password
    return cfg


class Source(BaseSource):
    name = "avito"

    def fetch(self) -> SourceResult:
        try:
            from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
        except ImportError:
            return SourceResult(self.name, SourceStatus.ERROR,
                                message="нет playwright (добавь в requirements + установи браузер)")

        pmax = self.cfg["hard"]["max_price_rub"]
        url = SEARCH_URL.format(pmax=pmax)
        proxy = _proxy_for_playwright()

        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch(
                    headless=True,
                    proxy=proxy,
                    args=["--no-sandbox", "--disable-blink-features=AutomationControlled"],
                )
                ctx = browser.new_context(
                    user_agent=UA, locale="ru-RU",
                    viewport={"width": 1366, "height": 900},
                )
                page = ctx.new_page()
                page.goto(url, timeout=45000, wait_until="domcontentloaded")

                # ждём ЛИБО карточки, ЛИБО признак Firewall
                try:
                    page.wait_for_selector('[data-marker="item"]', timeout=20000)
                except PWTimeout:
                    pass

                html = page.content()
                self.debug_dump(self.name + "_page", html)

                low = html.lower()
                if "проблема с ip" in low or "firewall" in low or "доступ ограничен" in low:
                    browser.close()
                    return SourceResult(self.name, SourceStatus.BLOCKED,
                                        message="Firewall Авито (см. debug/avito_page.html)")

                lots = self._parse_dom(page)
                browser.close()
                return SourceResult(self.name, SourceStatus.OK, listings=lots)
        except Exception as e:  # noqa: BLE001
            return SourceResult(self.name, SourceStatus.ERROR, message=str(e))

    def _parse_dom(self, page) -> list[Listing]:
        """Извлекает карточки по стабильным data-marker атрибутам."""
        out: list[Listing] = []
        items = page.query_selector_all('[data-marker="item"]')
        for it in items:
            link = it.query_selector('[data-marker="item-title"]') \
                or it.query_selector('a[itemprop="url"]') \
                or it.query_selector("a[href]")
            if not link:
                continue
            href = link.get_attribute("href") or ""
            if href.startswith("/"):
                href = "https://www.avito.ru" + href
            title = (link.inner_text() or "").strip()

            price = None
            pel = it.query_selector('[data-marker="item-price"]') \
                or it.query_selector('meta[itemprop="price"]')
            if pel:
                ptxt = pel.get_attribute("content") or pel.inner_text() or ""
                digits = re.sub(r"[^\d]", "", ptxt)
                price = int(digits) if len(digits) >= 5 else None

            text = (it.inner_text() or "")
            out.append(Listing(
                source=self.name, url=href, title=title[:120], price_rub=price,
                area_sot=self.parse_area_sot(text),
                land_status=self.detect_land_status(text),
                description=re.sub(r"\s+", " ", text)[:800],
            ))
        return out
