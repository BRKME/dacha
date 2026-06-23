"""Тесты ядра land_radar. Запуск: PYTHONPATH=. pytest -q

Покрывают платформо-независимую логику: парсинг, гео-дистанцию, жёсткий
фильтр, скоринг, дедуп/снижение цены, поведение заблокированных источников
и сборку Telegram-сообщения. Сетевые вызовы здесь не делаются.
"""
import importlib
from pathlib import Path

import yaml

from base import BaseSource, Listing, SourceResult, SourceStatus
import filters, geo, notify, state

CFG = yaml.safe_load((Path(__file__).resolve().parent / "config.yaml").read_text("utf-8"))


# ── парс-хелперы ──────────────────────────────────────────────
def test_parse_price():
    assert BaseSource.parse_price("3 950 000 ₽") == 3_950_000
    assert BaseSource.parse_price("3.95 млн") == 3_950_000
    assert BaseSource.parse_price("") is None
    # не склеивать цифры из площади/прочего — брать число у валюты
    assert BaseSource.parse_price("Участок 12 сот, 2 500 000 руб, 12 сот") == 2_500_000
    # без валютного маркера цена не угадывается (лучше None, чем мусор)
    assert BaseSource.parse_price("Участок 12 сот ИЖС") is None


def test_parse_area():
    assert BaseSource.parse_area_sot("6 сот") == 6.0
    assert BaseSource.parse_area_sot("0.06 га") == 6.0
    assert BaseSource.parse_area_sot("нет") is None


def test_land_status():
    assert BaseSource.detect_land_status("участок ИЖС") == "ИЖС"
    assert BaseSource.detect_land_status("садоводство СНТ") == "СНТ"
    assert BaseSource.detect_land_status("просто поле") == ""


# ── гео ───────────────────────────────────────────────────────
def test_distance_sertolovo():
    a = CFG["anchor"]
    d = geo.haversine_km(a["lat"], a["lon"], 60.1447, 30.2034)
    assert 8 < d < 14


# ── жёсткий фильтр ────────────────────────────────────────────
def test_hard_filter():
    h = CFG["hard"]
    assert filters.passes_hard(
        Listing("t", "u", price_rub=3_500_000, area_sot=8, distance_km=12), h)[0]
    assert not filters.passes_hard(
        Listing("t", "u", price_rub=6_000_000, area_sot=8, distance_km=12), h)[0]
    assert not filters.passes_hard(
        Listing("t", "u", price_rub=3_000_000, area_sot=8, distance_km=25), h)[0]
    assert not filters.passes_hard(
        Listing("t", "u", price_rub=3_000_000, area_sot=2, distance_km=5), h)[0]


# ── скоринг ───────────────────────────────────────────────────
def test_scoring_full():
    lst = Listing("t", "u", title="Белоостров",
                  description="ИЖС в сосновом лесу, озеро Витриярви, электричество, асфальт")
    s = filters.score_listing(lst, CFG["soft"])
    assert s >= 90
    assert lst.has_pine and lst.has_water and lst.has_power
    assert lst.water_name == "витриярви"


def test_scoring_empty():
    lst = Listing("t", "u", description="голое поле без ничего")
    assert filters.score_listing(lst, CFG["soft"]) == 0


# ── стейт: дедуп + снижение цены ──────────────────────────────
def test_dedup_and_price_drop():
    seen = {}
    new, drops = state.classify([Listing("t", "https://x.ru/1", price_rub=4_000_000)], seen)
    assert len(new) == 1 and not drops
    new2, drops2 = state.classify([Listing("t", "https://x.ru/1", price_rub=3_700_000)], seen)
    assert not new2 and len(drops2) == 1
    assert "↓" in drops2[0].notes[0]


# ── источники: импорт + честный BLOCKED без прокси ────────────
def test_all_sources_import():
    for name in CFG["sources"]:
        mod = importlib.import_module(name)
        assert mod.Source(CFG).name == name


def test_avito_cian_blocked_without_proxy(monkeypatch):
    monkeypatch.delenv("AVITO_PROXY_URL", raising=False)
    monkeypatch.delenv("CIAN_PROXY_URL", raising=False)
    for name in ("avito", "cian"):
        res = importlib.import_module(name).Source(CFG).fetch()
        assert res.status == SourceStatus.BLOCKED


# ── notify ────────────────────────────────────────────────────
def test_message_shows_source_status():
    lst = Listing("mirkvartir", "https://m.ru/1", title="Белоостров",
                  price_rub=3_500_000, area_sot=8, distance_km=0.6,
                  has_pine=True, has_water=True, score=100)
    msg = notify.build_message(
        [lst], [],
        [SourceResult("mirkvartir", SourceStatus.OK, [lst]),
         SourceResult("avito", SourceStatus.BLOCKED, message="no proxy")],
    )
    assert "Белоостров" in msg
    assert "🔴avito" in msg
    assert "заблокированы" in msg
