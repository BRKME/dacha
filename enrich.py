"""Обогащение описаний через LLM — reason-then-number стиль, как в Polymarket.

LLM достаёт из свободного текста объявления: статус земли, наличие
сосен/воды (включая имя водоёма), электричество, дом, возможность
регистрации. Заполняет поля Listing только если они ещё пустые
(источник/OSM имеют приоритет над догадками модели).

Провайдер выбирается в config.enrich.provider. Ключи берутся из env:
  grok   -> XAI_API_KEY
  claude -> ANTHROPIC_API_KEY
  openai -> OPENAI_API_KEY
"""
from __future__ import annotations

import json
import os

import requests

from base import Listing

_PROMPT = """Ты разбираешь объявление о продаже земельного участка под Петербургом.
Верни СТРОГО JSON без markdown, по схеме:
{{"land_status": "ИЖС|СНТ|ДНП|ЛПХ|КП|"", "has_pine": bool, "has_water": bool,
"water_name": "" , "has_power": bool, "has_house": bool, "registration": bool,
"reason": "одно короткое предложение"}}

Объявление:
Заголовок: {title}
Адрес: {address}
Описание: {desc}
"""


def _call_grok(prompt: str, model: str) -> str:
    r = requests.post(
        "https://api.x.ai/v1/chat/completions",
        headers={"Authorization": f"Bearer {os.environ['XAI_API_KEY']}"},
        json={"model": model, "temperature": 0,
              "messages": [{"role": "user", "content": prompt}]},
        timeout=40,
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


def _call_claude(prompt: str, model: str) -> str:
    r = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={"x-api-key": os.environ["ANTHROPIC_API_KEY"],
                 "anthropic-version": "2023-06-01"},
        json={"model": model, "max_tokens": 400,
              "messages": [{"role": "user", "content": prompt}]},
        timeout=40,
    )
    r.raise_for_status()
    return r.json()["content"][0]["text"]


def _call_openai(prompt: str, model: str) -> str:
    r = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"},
        json={"model": model, "temperature": 0,
              "messages": [{"role": "user", "content": prompt}]},
        timeout=40,
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


_DISPATCH = {"grok": _call_grok, "claude": _call_claude, "openai": _call_openai}


def _parse_json(raw: str) -> dict:
    raw = raw.strip().replace("```json", "").replace("```", "").strip()
    return json.loads(raw)


def enrich(listings: list[Listing], cfg: dict) -> None:
    """Мутирует listings на месте. Тихо пропускает при ошибке провайдера."""
    ec = cfg["enrich"]
    if not ec.get("enabled"):
        return
    provider = ec.get("provider", "grok")
    caller = _DISPATCH.get(provider)
    if caller is None:
        return
    limit = ec.get("max_listings_per_run", 25)

    for lst in listings[:limit]:
        if not (lst.description or lst.title):
            continue
        prompt = _PROMPT.format(
            title=lst.title, address=lst.address, desc=lst.description[:1500]
        )
        try:
            data = _parse_json(caller(prompt, ec["model"]))
        except Exception as e:  # noqa: BLE001 — обогащение не должно ронять прогон
            lst.notes.append(f"enrich error: {type(e).__name__}")
            continue

        if not lst.land_status and data.get("land_status"):
            lst.land_status = data["land_status"]
        if lst.has_pine is None:
            lst.has_pine = bool(data.get("has_pine"))
        if lst.has_water is None:
            lst.has_water = bool(data.get("has_water"))
        if not lst.water_name and data.get("water_name"):
            lst.water_name = data["water_name"]
        if lst.has_power is None:
            lst.has_power = bool(data.get("has_power"))
        if lst.has_house is None and "has_house" in data:
            lst.has_house = bool(data["has_house"])
        if data.get("registration") is False:
            lst.notes.append("регистрация под вопросом")
        if data.get("reason"):
            lst.notes.append(f"LLM: {data['reason']}")
