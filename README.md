# threads-leadgen

Локальный скрапер Threads + SQLite + MCP-сервер для генерации лидов из публичных постов. Подробности — в [спеке](docs/superpowers/specs/2026-06-12-threads-leadgenerator-design.md) и [плане имплементации](docs/superpowers/plans/2026-06-12-threads-leadgenerator.md).

## Setup

```bash
uv sync
cp .env.example .env
# отредактируй .env: впиши свои THREADS_USERNAME и THREADS_PASSWORD
```

Для работы скрапера нужно экспортировать cookies из логин-сессии threads.net в браузере и сложить JSON-массив в `data/session.cookies.json` (используй расширение "Cookie Editor" или аналог). Без них `ThreadsClient.login()` падает с понятной ошибкой и подсказкой пути.

## Запуск

### Скрапер
```bash
uv run python scripts/run_scraper.py
```
Активен только 09:00–23:00 локального времени (настраивается в `SCRAPER_ACTIVE_HOURS`). Можно повесить на Windows Task Scheduler с дневным триггером — сам уйдёт спать в 23:00.

### MCP-сервер
Уже подключён через `.mcp.json` — Claude Code поднимет его автоматически при старте сессии в этой папке. Проверить:

```
/mcp
```

Должна появиться запись `threads-leadgen` со статусом `connected` и списком тулов.

## Типичный флоу

```
> добавь тему "поиск идей для контента", прикинь пару фраз и проверь объёмы

(Claude думает, дёргает probe_keywords, отчитывается)

> закоммить ту, что с объёмом > 20

> покажи 30 новых лидов и отметь релевантные

(Claude перебирает list_unreviewed, для каждого mark_post)

> покажи статистику за неделю
```

## Тесты

```bash
uv run pytest
```

Smoke-тест Threads (требует креды и экспортированные cookies) — отдельно:
```bash
uv run pytest tests/test_threads_client_smoke.py -v -s
```
