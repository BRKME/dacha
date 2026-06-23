"""Формирование и отправка Telegram-сообщения (HTML parse_mode).

Сообщение содержит: новые лоты, снижения цены и строку статусов
источников (какие площадки отдали данные, какие заблокированы).
"""
from __future__ import annotations

import html
import os

import requests

from base import Listing, SourceResult, SourceStatus

TG_API = "https://api.telegram.org/bot{token}/sendMessage"

_STATUS_EMOJI = {
    SourceStatus.OK: "🟢",
    SourceStatus.BLOCKED: "🔴",
    SourceStatus.ERROR: "🟠",
    SourceStatus.SKIPPED: "⚪",
}


def _fmt_listing(lst: Listing) -> str:
    price = f"{lst.price_rub:,}₽".replace(",", " ") if lst.price_rub else "цена н/д"
    area = f"{lst.area_sot:g} сот" if lst.area_sot else "площадь н/д"
    dist = f"{lst.distance_km:.1f} км" if lst.distance_km is not None else "? км"
    pine = "🌲" if lst.has_pine else ""
    water = "💧" if lst.has_water else ""
    status = f" · {lst.land_status}" if lst.land_status else ""
    title = html.escape(lst.title or lst.address or "участок")[:80]

    line = (f"<b>{price}</b> · {area} · {dist}{status} {pine}{water}\n"
            f"<a href=\"{html.escape(lst.url)}\">{title}</a> "
            f"<i>[{lst.source}, score {lst.score}]</i>")
    if lst.water_name:
        line += f"\n   💧 {html.escape(lst.water_name)}"
    if lst.notes:
        line += "\n   ⚠️ " + "; ".join(html.escape(n) for n in lst.notes)
    return line


def build_message(new: list[Listing], drops: list[Listing],
                  results: list[SourceResult]) -> str:
    parts = ["🏞 <b>land_radar — участки под Белоостровом</b>"]

    if new:
        parts.append(f"\n<b>🆕 Новые ({len(new)})</b>")
        for lst in sorted(new, key=lambda x: -x.score)[:15]:
            parts.append(_fmt_listing(lst))
    if drops:
        parts.append(f"\n<b>📉 Подешевели ({len(drops)})</b>")
        for lst in sorted(drops, key=lambda x: -x.score)[:10]:
            parts.append(_fmt_listing(lst))
    if not new and not drops:
        parts.append("\nНовых лотов нет.")

    statuses = " ".join(
        f"{_STATUS_EMOJI.get(r.status, '?')}{r.source}" for r in results
    )
    parts.append(f"\n<i>{statuses}</i>")
    blocked = [r for r in results if r.status == SourceStatus.BLOCKED]
    if blocked:
        parts.append("<i>⚠️ заблокированы: "
                     + ", ".join(r.source for r in blocked) + "</i>")
    return "\n".join(parts)


def send(text: str):
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("[notify] нет TELEGRAM_BOT_TOKEN/CHAT_ID — печатаю в stdout:\n")
        print(text)
        return
    # Telegram лимит 4096 символов
    for chunk_start in range(0, len(text), 4000):
        chunk = text[chunk_start:chunk_start + 4000]
        requests.post(
            TG_API.format(token=token),
            json={"chat_id": chat_id, "text": chunk,
                  "parse_mode": "HTML", "disable_web_page_preview": True},
            timeout=20,
        )
