"""Базовый интерфейс источника и нормализованная модель лота.

Каждый источник (mirkvartir, yandex, ...) наследует BaseSource и реализует
fetch() -> SourceResult. Никакой источник НЕ кидает исключения наружу:
сетевые/анти-бот проблемы упаковываются в SourceResult.status, чтобы
оркестратор мог честно отчитаться в Telegram, какие площадки отвалились.
"""
from __future__ import annotations

import dataclasses
import hashlib
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class SourceStatus(str, Enum):
    OK = "ok"            # отработал, лоты (возможно 0) получены
    BLOCKED = "blocked"  # капча / 403 / бан — данные недостоверны
    ERROR = "error"      # сеть/парсинг упали
    SKIPPED = "skipped"  # выключен в конфиге


@dataclass
class Listing:
    """Нормализованный лот. Все источники приводят данные к этому виду."""
    source: str
    url: str
    title: str = ""
    price_rub: Optional[int] = None
    area_sot: Optional[float] = None
    address: str = ""
    lat: Optional[float] = None
    lon: Optional[float] = None
    land_status: str = ""          # ИЖС / СНТ / ДНП / ЛПХ / ...
    description: str = ""
    published: str = ""            # ISO-строка, если известна
    has_house: Optional[bool] = None

    # --- заполняется на этапах обогащения, не источником ---
    distance_km: Optional[float] = None
    has_pine: Optional[bool] = None
    has_water: Optional[bool] = None
    water_name: str = ""
    has_power: Optional[bool] = None
    score: int = 0
    notes: list = field(default_factory=list)

    @property
    def uid(self) -> str:
        """Стабильный ID для дедупа. URL без query обычно стабилен."""
        base = re.sub(r"[?#].*$", "", self.url) or self.title
        return f"{self.source}:{hashlib.sha1(base.encode()).hexdigest()[:16]}"

    def to_dict(self) -> dict:
        d = dataclasses.asdict(self)
        d["uid"] = self.uid
        return d


@dataclass
class SourceResult:
    source: str
    status: SourceStatus
    listings: list = field(default_factory=list)
    message: str = ""   # для BLOCKED/ERROR — что именно случилось


class BaseSource:
    name: str = "base"

    def __init__(self, cfg: dict):
        self.cfg = cfg

    def fetch(self) -> SourceResult:  # pragma: no cover - переопределяется
        raise NotImplementedError

    # --- сеть с поддержкой общего прокси ---

    @staticmethod
    def get_proxies(source_specific_env: str = None) -> Optional[dict]:
        """Единый прокси для всех источников.

        Приоритет: source-specific env (AVITO_PROXY_URL и т.п.) → общий PROXY_URL.
        Возвращает dict для requests или None если прокси не задан.
        """
        import os
        url = None
        if source_specific_env:
            url = os.environ.get(source_specific_env)
        if not url:
            url = os.environ.get("PROXY_URL")
        if not url:
            return None
        return {"http": url, "https": url}

    def session(self, ua: str = None) -> "requests.Session":
        """requests.Session с UA и общим прокси (если задан PROXY_URL)."""
        import requests
        s = requests.Session()
        s.headers.update({
            "User-Agent": ua or (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
            ),
            "Accept-Language": "ru-RU,ru",
        })
        proxies = self.get_proxies()
        if proxies:
            s.proxies.update(proxies)
        return s

    # --- общие хелперы для парсеров ---

    @staticmethod
    def parse_price(text: str) -> Optional[int]:
        """'3 950 000 ₽' / '3.95 млн' -> int рублей.

        Цена привязывается к валютному маркеру (₽/руб/р.), иначе в карточке
        с площадью/датами склеились бы все цифры. Если в тексте несколько
        цен — берётся первая (для агрегатов лучше парсить цену на странице
        самой карточки)."""
        if not text:
            return None
        t = text.lower().replace("\xa0", " ")
        # 'N млн' / 'N.N млн'
        m = re.search(r"([\d\s.,]+?)\s*млн", t)
        if m:
            num = m.group(1).replace(" ", "").replace(",", ".")
            try:
                return int(float(num) * 1_000_000)
            except ValueError:
                pass
        # число прямо перед валютой
        m = re.search(r"(\d[\d\s.]*\d|\d)\s*(?:₽|руб|р\.|rub)", t)
        if m:
            digits = re.sub(r"[^\d]", "", m.group(1))
            return int(digits) if digits else None
        return None

    @staticmethod
    def parse_area_sot(text: str) -> Optional[float]:
        """'6 сот' / '0.06 га' -> сотки."""
        if not text:
            return None
        t = text.lower().replace(",", ".")
        m = re.search(r"([\d.]+)\s*га", t)
        if m:
            try:
                return float(m.group(1)) * 100
            except ValueError:
                pass
        m = re.search(r"([\d.]+)\s*сот", t)
        if m:
            try:
                return float(m.group(1))
            except ValueError:
                pass
        return None

    @staticmethod
    def detect_land_status(text: str) -> str:
        t = (text or "").upper()
        for tag in ("ИЖС", "ЛПХ", "ДНП", "ДНТ", "СНТ", "КП"):
            if tag in t:
                return tag
        return ""

    @staticmethod
    def debug_dump(name: str, text: str) -> None:
        """При DACHA_DEBUG=1 сохраняет сырой ответ в debug/<name>.html.
        Нужен, чтобы чинить селекторы по живой разметке с Actions-IP."""
        import os
        if not os.environ.get("DACHA_DEBUG"):
            return
        from pathlib import Path
        d = Path(__file__).resolve().parent / "debug"
        d.mkdir(exist_ok=True)
        (d / f"{name}.html").write_text((text or "")[:800_000], encoding="utf-8")
