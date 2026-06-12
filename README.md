# threads-leadgen

Локальный скрапер Threads + SQLite + MCP-сервер для генерации лидов из публичных постов. Подробности — в [спеке](docs/superpowers/specs/2026-06-12-threads-leadgenerator-design.md).

## Setup

```bash
uv sync
cp .env.example .env
# отредактируй .env
```

## Запуск

```bash
# Скрапер (запускать вручную или через Task Scheduler)
uv run python scripts/run_scraper.py

# MCP-сервер — обычно поднимается автоматически Claude Code из .mcp.json
uv run python scripts/run_mcp.py
```

## Тесты

```bash
uv run pytest
```
