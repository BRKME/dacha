"""Сбербанк-АСТ — utp.sberbank-ast.ru, раздел Bankruptcy/List/BidList.

CONFIDENCE: низкая (scaffold). ВАЖНО: BidList — это SPA, данные грузятся
POST-запросом к внутреннему API, а в robots.txt площадка запрещает ботов.
Поэтому GET страницы вернёт JS-каркас без лотов (OK с 0). Реальный путь —
найти по дампу/devtools POST-эндпоинт (обычно /Bankruptcy/.../GetList или
похожий) и слать в него JSON-фильтр. Сейчас источник честно отдаёт 0/BLOCKED,
пока эндпоинт не прописан.
"""
from __future__ import annotations

import json

import requests

from base import BaseSource, Listing, SourceResult, SourceStatus

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

PAGE_URL = "https://utp.sberbank-ast.ru/Bankruptcy/List/BidList"
# Каркас под будущий POST-API (уточнить реальный путь и тело по devtools/дампу):
API_URL = "https://utp.sberbank-ast.ru/Bankruptcy/List/GetBidList"


class Source(BaseSource):
    name = "sberbank_ast"

    def fetch(self) -> SourceResult:
        s = self.session(UA)
        try:
            # 1) пробуем POST-API (если путь верный — отдаст JSON со списком лотов)
            resp = s.post(
                API_URL,
                headers={"Content-Type": "application/json",
                         "X-Requested-With": "XMLHttpRequest"},
                data=json.dumps({
                    "filter": {"text": "земельный участок Ленинградская область"},
                    "page": 1, "pageSize": 50,
                }),
                timeout=12,
            )
            self.debug_dump(self.name + "_api", resp.text)
            if resp.status_code == 200 and resp.headers.get(
                    "content-type", "").startswith("application/json"):
                return SourceResult(self.name, SourceStatus.OK,
                                    listings=self._parse_api(resp.json()))
        except Exception as e:  # noqa: BLE001
            # не падаем — пробуем хотя бы снять страницу для дампа
            self.debug_dump(self.name + "_apierr", str(e))

        # 2) фолбэк: снять HTML страницы для дампа (анализ структуры)
        try:
            page = s.get(PAGE_URL, timeout=12)
            self.debug_dump(self.name + "_page", page.text)
            if page.status_code in (403, 429):
                return SourceResult(self.name, SourceStatus.BLOCKED,
                                    message=f"HTTP {page.status_code} (robots/anti-bot)")
        except Exception as e:  # noqa: BLE001
            return SourceResult(self.name, SourceStatus.ERROR, message=str(e))

        return SourceResult(
            self.name, SourceStatus.BLOCKED,
            message="SPA: нужен реальный POST-эндпоинт (см. debug/sberbank_ast_page.html)",
        )

    def _parse_api(self, data: dict) -> list[Listing]:
        out: list[Listing] = []
        items = data.get("items") or data.get("rows") or data.get("data") or []
        for it in items:
            if not isinstance(it, dict):
                continue
            out.append(Listing(
                source=self.name,
                url=it.get("url") or PAGE_URL,
                title=(it.get("name") or it.get("title") or "")[:120],
                price_rub=_to_int(it.get("price") or it.get("startPrice")),
                description=(it.get("description") or "")[:800],
            ))
        return out


def _to_int(v):
    try:
        return int(float(v)) if v is not None else None
    except (TypeError, ValueError):
        return None
