#!/usr/bin/env python3
"""land_radar — оркестратор прогона.

Поток: источники → нормализация → гео-дистанция → OSM-природа → LLM-обогащение
→ жёсткий фильтр → скоринг → дедуп/снижение цены → Telegram → сохранение стейта.

Запуск: python scan.py   (читает config.yaml рядом)
Секреты через env: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, XAI_API_KEY (и т.д.)
"""
from __future__ import annotations

import importlib
import time
from pathlib import Path

import yaml

import enrich, filters, geo, notify, state
from base import SourceResult, SourceStatus

CFG_PATH = Path(__file__).resolve().parent / "config.yaml"


def load_sources(cfg: dict, only: str | None = None):
    """Инстанцирует включённые источники. only=NAME — форсит один источник
    (даже если он выключен в конфиге), удобно для отладки селекторов."""
    active = []
    for name, enabled in cfg["sources"].items():
        if only:
            if name != only:
                continue
        elif not enabled:
            continue
        mod = importlib.import_module(name)
        active.append(mod.Source(cfg))
    if only and not active:
        raise SystemExit(f"источник '{only}' не найден в config.sources")
    return active


def collect(sources, cfg) -> tuple[list, list[SourceResult]]:
    listings, results = [], []
    for src in sources:
        print(f"[scan] fetch {src.name} ...")
        try:
            res = src.fetch()
        except Exception as e:  # noqa: BLE001 — один источник не должен ронять прогон
            res = SourceResult(src.name, SourceStatus.ERROR,
                               message=f"{type(e).__name__}: {e}")
        results.append(res)
        print(f"       {res.status.value} ({len(res.listings)}) {res.message}")
        if res.status == SourceStatus.OK:
            listings.extend(res.listings)
    return listings, results


def geo_enrich(listings, cfg):
    a = cfg["anchor"]
    osm = cfg.get("osm_nature", {})
    for lst in listings:
        if lst.lat is not None and lst.lon is not None:
            lst.distance_km = round(
                geo.haversine_km(a["lat"], a["lon"], lst.lat, lst.lon), 1)
            if osm.get("enabled"):
                forest, water, wname = geo.osm_nature(
                    lst.lat, lst.lon, osm.get("radius_m", 1500))
                if forest is not None:
                    lst.has_pine = lst.has_pine or forest
                if water is not None:
                    lst.has_water = lst.has_water or water
                if wname and not lst.water_name:
                    lst.water_name = wname
                    lst.notes.append(f"OSM: вода рядом — {wname}")
                time.sleep(1)  # вежливо к Overpass


def parse_args():
    import argparse
    p = argparse.ArgumentParser(description="land_radar — монитор участков")
    p.add_argument("--source", metavar="NAME",
                   help="прогнать только один источник (для отладки селекторов)")
    p.add_argument("--dry-run", action="store_true",
                   help="не слать в Telegram и не писать стейт")
    p.add_argument("--no-enrich", action="store_true", help="без LLM-обогащения")
    p.add_argument("--no-osm", action="store_true", help="без проверки OSM-природы")
    p.add_argument("--raw", action="store_true",
                   help="печатать все собранные лоты ДО жёсткого фильтра")
    return p.parse_args()


def preflight(cfg: dict) -> None:
    """Проверяет, что все модули свежие, и за ОДИН раз выводит список
    устаревших/битых файлов. Спасает от починки по одному файлу за прогон."""
    problems: list[str] = []
    checks = {
        "geo": ["haversine_km", "osm_nature"],
        "filters": ["passes_hard", "score_listing"],
        "enrich": ["enrich"],
        "state": ["load_seen", "classify", "save"],
        "notify": ["build_message", "send"],
    }
    for mod_name, attrs in checks.items():
        try:
            mod = importlib.import_module(mod_name)
        except Exception as e:  # noqa: BLE001
            problems.append(f"{mod_name}.py — не импортируется ({type(e).__name__})")
            continue
        for a in attrs:
            if not hasattr(mod, a):
                problems.append(f"{mod_name}.py — устарел: нет '{a}'")
    try:
        import base
        for a in ("BaseSource", "Listing", "SourceResult", "SourceStatus"):
            if not hasattr(base, a):
                problems.append(f"base.py — нет '{a}'")
        if hasattr(base, "BaseSource") and not hasattr(base.BaseSource, "debug_dump"):
            problems.append("base.py — устарел: BaseSource без 'debug_dump'")
    except Exception as e:  # noqa: BLE001
        problems.append(f"base.py — не импортируется ({type(e).__name__})")
    for name in cfg["sources"]:
        try:
            m = importlib.import_module(name)
            if not hasattr(m, "Source"):
                problems.append(f"{name}.py — нет класса Source")
        except Exception as e:  # noqa: BLE001
            problems.append(f"{name}.py — не импортируется ({type(e).__name__})")

    if problems:
        print("\n‼️  PREFLIGHT: эти файлы устарели/битые — перезалей их свежими:")
        for p in problems:
            print("   -", p)
        print("(проверка остановила прогон до сетевых запросов)\n")
        raise SystemExit(1)
    print("[preflight] все модули на месте ✅")


def main():
    args = parse_args()
    cfg = yaml.safe_load(CFG_PATH.read_text("utf-8"))
    preflight(cfg)
    if args.no_enrich:
        cfg["enrich"]["enabled"] = False
    if args.no_osm:
        cfg["osm_nature"]["enabled"] = False

    sources = load_sources(cfg, only=args.source)
    raw, results = collect(sources, cfg)
    print(f"[scan] собрано лотов до фильтра: {len(raw)}")
    if args.raw:
        for l in raw:
            print(f"   · {l.source} {l.price_rub} {l.area_sot} {l.title[:60]} {l.url}")

    geo_enrich(raw, cfg)
    enrich.enrich(raw, cfg)

    kept = []
    for lst in raw:
        ok, reason = filters.passes_hard(lst, cfg["hard"])
        if not ok:
            continue
        filters.score_listing(lst, cfg["soft"])
        kept.append(lst)
    print(f"[scan] прошло жёсткий фильтр: {len(kept)}")

    seen = state.load_seen()
    new, drops = state.classify(kept, seen)
    print(f"[scan] новых: {len(new)}, подешевело: {len(drops)}")

    msg = notify.build_message(new, drops, results)
    if args.dry_run:
        print("\n[dry-run] сообщение НЕ отправлено, стейт НЕ записан:\n")
        print(msg)
    else:
        notify.send(msg)
        state.save(seen, kept)
    print("[scan] done.")


if __name__ == "__main__":
    main()
