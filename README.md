# land_radar 🏞

Монитор объявлений о продаже земельных участков под Белоостровом (СПб / ЛО).
Паттерн BRKME: GitHub Actions cron → Python → committed JSON-стейт → Telegram.

Каждые 6 часов опрашивает площадки, фильтрует по жёстким критериям (цена,
радиус, площадь, свежесть), ранжирует по мягким (сосны, вода, статус земли,
коммуникации) и шлёт в Telegram **новые** и **подешевевшие** лоты. Дедуп —
через `state/seen.json`.

## Критерии (config.yaml)

| Тип | Условие |
|-----|---------|
| Жёсткие (отсев) | цена ≤ 4 000 000 ₽ · радиус ≤ 20 км от Белоострова · площадь ≥ 4 сот · не старше 30 дней |
| Мягкие (скоринг 0–100) | сосны/лес (30) · вода (35) · именной водоём (+15) · электричество (10) · дорога (10) |

Якорь — Белоостров (60.1656, 30.0050). Дистанция считается по haversine,
природа дополнительно проверяется по OpenStreetMap (Overpass) в радиусе 1.5 км —
страхует случаи, когда продавец не написал про лес/озеро, а они физически рядом.

## Честно про источники

С datacenter-IP GitHub Actions площадки ведут себя по-разному. Бот это
**не скрывает**: источник возвращает статус, и в Telegram приходит строка
`🟢 отдал данные / 🔴 заблокирован / 🟠 ошибка / ⚪ выключен`.

| Источник | Реалистичность с Actions-IP | Статус |
|----------|------------------------------|--------|
| `mirkvartir`   | средне-высокая | ✅ вкл |
| `bank_torgi`   | средняя (lot-online / РАД) | ✅ вкл |
| `m_ets`        | средняя (МЭТС, банкротство) — scaffold | ✅ вкл |
| `alfalot`      | средняя (агрегатор банкротных лотов) — scaffold | ✅ вкл |
| `sberbank_ast` | низкая (SPA + POST-API, robots-запрет, таймаутит с Actions) | ✅ вкл |
| `yandex`       | переменная (SmartCaptcha) | ✅ вкл |
| `domclick`     | переменная (JSON-API, баны datacenter-IP) | ✅ вкл |
| `avito`        | **основной по задаче**, но с Actions блокируется — нужен РФ-прокси/curl_cffi | ⏸ путь не выбран |
| `cian`         | низкая (Qrator) | ⏸ Phase 2, прокси |

> Парсеры площадок — рабочий каркас. При `DACHA_DEBUG=1` каждый источник
> сохраняет сырой ответ в `debug/<name>.html` и коммитит его — по этим дампам
> селекторы правятся под живую разметку. Источник 🟢 с 0 лотов = селекторы
> не совпали (смотри дамп), не ошибка инфраструктуры.

## Phase 2: Авито / Циан

Включаются флагом в `config.yaml` (`sources.avito: true`) при наличии
рабочего РФ residential-прокси в секретах `AVITO_PROXY_URL` / `CIAN_PROXY_URL`.
Без прокси оба источника честно рапортуют BLOCKED и прогон не ломают.

## Структура (плоская — всё в корне)

```
dacha/
├── scan.py               # оркестратор (CLI: --source --dry-run --no-enrich --no-osm --raw)
├── config.yaml           # все критерии и флаги источников
├── base.py               # Listing + SourceResult + парс-хелперы + debug_dump
├── geo.py                # haversine + OSM Overpass
├── filters.py            # жёсткий отсев + скоринг
├── enrich.py             # LLM-разбор описаний (Grok 4.3 / Claude / OpenAI)
├── state.py              # JSON дедуп + детект снижения цены
├── notify.py             # Telegram HTML
├── mirkvartir.py yandex.py domclick.py            # риелторские площадки
├── bank_torgi.py m_ets.py alfalot.py sberbank_ast.py   # торги/банкротство
├── avito.py cian.py      # Phase 2 (нужен РФ-прокси)
├── test_core.py          # pytest (12 тестов)
└── .github/workflows/scan.yml
```

## Секреты (Settings → Secrets → Actions)

| Секрет | Зачем |
|--------|-------|
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | отправка | 
| `XAI_API_KEY` | LLM-обогащение (Grok). Можно переключить на `claude`/`openai` в конфиге |
| `AVITO_PROXY_URL`, `CIAN_PROXY_URL` | только Phase 2 |

## Локальный запуск

```bash
pip install -r requirements.txt
export TELEGRAM_BOT_TOKEN=... TELEGRAM_CHAT_ID=... XAI_API_KEY=...
python scan.py     # без TG-секретов сообщение печатается в stdout
```
