"""Авито Недвижимость — PHASE 2.

CONFIDENCE: низкая с Actions-IP. У Авито агрессивный анти-бот (TLS-fingerprint,
поведенческие проверки, Firewall). С datacenter-адреса GitHub Actions
ожидаемый исход — 403/429/Firewall practически на первых запросах.

Каркас оставлен, чтобы при появлении РФ residential-прокси (или решения
вроде curl_cffi с TLS-имперсонацией) источник включался флагом в конфиге.
Сейчас по умолчанию sources.avito=false и fetch() честно сообщает BLOCKED.
"""
from __future__ import annotations

import os

import requests

from base import BaseSource, Listing, SourceResult, SourceStatus

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

SEARCH_URL = "https://www.avito.ru/leningradskaya_oblast/zemelnye_uchastki"


class Source(BaseSource):
    name = "avito"

    def fetch(self) -> SourceResult:
        # Прокси: source-specific или общий PROXY_URL. Без него — честный BLOCKED.
        proxies = self.get_proxies("AVITO_PROXY_URL")
        if not proxies:
            return SourceResult(
                self.name, SourceStatus.BLOCKED,
                message="нет прокси (AVITO_PROXY_URL/PROXY_URL); Авито недоступен с Actions-IP",
            )
        try:
            resp = requests.get(
                SEARCH_URL,
                headers={"User-Agent": UA, "Accept-Language": "ru-RU,ru"},
                params={"pmax": self.cfg["hard"]["max_price_rub"], "s": "104"},
                proxies=proxies, timeout=30,
            )
            if resp.status_code in (403, 429) or "firewall" in resp.text.lower():
                return SourceResult(self.name, SourceStatus.BLOCKED,
                                    message=f"HTTP {resp.status_code}/firewall")
        except Exception as e:  # noqa: BLE001
            return SourceResult(self.name, SourceStatus.ERROR, message=str(e))
        # TODO: парсинг initial state Авито при наличии рабочего прокси
        return SourceResult(self.name, SourceStatus.OK, listings=[])
