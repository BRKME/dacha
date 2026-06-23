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

    # --- общие хелперы для парсеров ---

    @staticmethod
    def parse_price(text: str) -> Optional[int]:
        """'3 950 000 ₽' / '3.95 млн' -> int рублей."""
        if not text:
            return None
        t = text.lower().replace("\xa0", " ")
        m = re.search(r"([\d\s.,]+)\s*млн", t)
        if m:
            num = m.group(1).replace(" ", "").replace(",", ".")
            try:
                return int(float(num) * 1_000_000)
            except ValueError:
                return None
        digits = re.sub(r"[^\d]", "", t)
        return int(digits) if digits else None

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
