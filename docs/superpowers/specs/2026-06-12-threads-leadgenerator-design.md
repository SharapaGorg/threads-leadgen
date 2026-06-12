# Threads Lead Generator — Design

**Дата:** 2026-06-12
**Статус:** утверждён к имплементации

## Цель

Собирать публичные посты Threads, где люди формулируют боль/запрос, релевантный продуктам для SMM-специалистов и блогеров (примеры тем на старте: «поиск идей для контента», «AI-разбор reels»). Полуручной режим: фон собирает, владелец раз в день из Claude Code прогоняет накопленное через LLM-фильтрацию и отмечает релевантные посты для ручного ответа.

Нецели MVP:
- автоответы / автокомментирование;
- многопользовательский режим;
- веб-интерфейс или дашборд;
- интеграция с CRM.

## Архитектура

Три независимых процесса, общаются исключительно через SQLite-файл.

### Скрапер
Отдельный Python-процесс. Запускается вручную или через Windows Task Scheduler.

Цикл:
1. Берёт из БД активные `keywords` (где `enabled=true` и тема не на паузе).
2. По одному ключевику: ходит в Threads через клиентскую обёртку, получает свежие посты, дедуплицирует по `post_id`, вставляет в `posts` со статусом `unreviewed`.
3. Спит рандомные 30–180 сек между запросами.
4. После прохода по всем ключевикам — спит 15–60 минут.
5. Активен только 09:00–23:00 по локальному времени машины.
6. Лимит ~40 HTTP-запросов в час суммарно.
7. При ошибке логина / капче — пишет лог и завершается. Автоматических ретраев нет (палится).

Сессия (cookies) кешируется на диск, чтобы не релогиниться каждый цикл.

### База
SQLite-файл `data/leads.db`. Один файл — легко переезжает на VPS.

### MCP-сервер
Отдельный Python-процесс, поднимается Claude Code'ом при старте сессии (конфиг в `~/.claude/...` или в проектном `.mcp.json`). Через него владелец из чата управляет темами и просматривает лиды.

## Модель данных

```sql
CREATE TABLE topics (
    id            INTEGER PRIMARY KEY,
    description   TEXT NOT NULL,
    paused        INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT NOT NULL
);

CREATE TABLE keywords (
    id                  INTEGER PRIMARY KEY,
    topic_id            INTEGER NOT NULL REFERENCES topics(id),
    text                TEXT NOT NULL,
    probed_volume_7d    INTEGER,
    last_scraped_at     TEXT,
    enabled             INTEGER NOT NULL DEFAULT 1,
    UNIQUE(topic_id, text)
);

CREATE TABLE posts (
    id                  TEXT PRIMARY KEY,          -- threads post id
    keyword_id          INTEGER NOT NULL REFERENCES keywords(id),
    author_username     TEXT NOT NULL,
    author_followers    INTEGER,
    text                TEXT NOT NULL,
    url                 TEXT NOT NULL,
    posted_at           TEXT NOT NULL,
    likes_count         INTEGER,
    replies_count       INTEGER,
    fetched_at          TEXT NOT NULL,
    status              TEXT NOT NULL DEFAULT 'unreviewed',
    llm_notes           TEXT,
    marked_at           TEXT
);

CREATE INDEX posts_status_idx ON posts(status);
CREATE INDEX posts_keyword_idx ON posts(keyword_id);
```

`status` ∈ `{unreviewed, relevant, irrelevant, replied, skipped}`.

Если один и тот же post_id найден по нескольким ключевикам — оставляем первую запись, остальные `keyword_id` теряем (для MVP достаточно).

## MCP-тулы

### Управление темами
- `list_topics()` — все темы + счётчики `keywords`, `posts_unreviewed`, `posts_relevant`.
- `add_topic(description: str) -> topic_id` — создаёт тему. Ключевики НЕ генерит — это делает Claude Code в чате через `probe_keywords` + `commit_keywords`.
- `probe_keywords(keywords: list[str]) -> list[{keyword, volume_7d, samples: list[str]}]` — для каждого ключевика: число постов за 7 дней + 3 примера текстов. Чтобы LLM мог отсеять мёртвые/шумные фразы. Сами посты в БД при probe НЕ сохраняются.
- `commit_keywords(topic_id: int, keywords: list[str])` — привязывает ключевики к теме. Скрапер подхватит со следующего цикла.
- `pause_topic(topic_id)` / `resume_topic(topic_id)` — выставляет `paused`.

### Работа с лидами
- `list_unreviewed(topic_id?: int, limit: int = 30) -> list[Post]` — пачка непроверенных постов.
- `get_post(post_id: str) -> Post` — полные детали + URL.
- `mark_post(post_id: str, status: str, why?: str)` — пометка с опциональной заметкой LLM.
- `search_leads(status?, topic_id?, since?, query?: str)` — поиск по уже размеченным.
- `stats(since?: str)` — собрано / релевантных / конверсия по темам.

Все тулы возвращают JSON-совместимый dict. Ошибки — `ToolError` с человеческим сообщением.

## Антибан-стратегия

- Один аккаунт-донор (основной аккаунт владельца). Креды в `.env`.
- Рандомные задержки 30–180 сек между запросами.
- Максимум ~40 запросов в час.
- Активен 09:00–23:00 локального времени.
- При капче/ошибке логина — скрапер завершается с понятным логом, не пытается переподключиться.
- Cookies/сессия кешируется на диск, релогин — только когда сессия протухла.
- Никаких автолайков/реплаев/follow — только чтение.

## Доступ к Threads

Используем питон-либу для реверс-API. Кандидаты: `threadspy`, `threads-net`. Финальный выбор — на этапе имплементации после короткого спайка (см. план). Если обе мертвы — fallback на Playwright с прогретым профилем браузера.

Обёртка `threads_client.py` — тонкий фасад, чтобы при смене либы менять одно место. Интерфейс минимальный:
```python
class ThreadsClient:
    def login(self) -> None: ...
    def search_recent(self, keyword: str, limit: int = 30) -> list[RawPost]: ...
    def get_post(self, post_id: str) -> RawPost: ...
```

Официальный Meta Threads API в MVP НЕ используем — keyword-поиск там в закрытой бете и не покрывает кейс лидгена по чужим публичным постам.

## Стек

- Python 3.11+
- `uv` для управления зависимостями
- `mcp` (официальный Python SDK для MCP)
- `httpx` (если либа не закрывает HTTP)
- `pydantic` для типов
- `python-dotenv` для `.env`
- SQLite через `sqlite3` из стандартной библиотеки (без ORM — слишком маленькая модель)

## Структура проекта

```
threads-leadgenerator/
├── pyproject.toml
├── .env.example
├── .gitignore
├── README.md
├── data/
│   └── leads.db                    # gitignored
├── src/threads_leadgen/
│   ├── __init__.py
│   ├── config.py                   # загрузка .env, пути
│   ├── db.py                       # schema, миграции, запросы
│   ├── threads_client.py           # обёртка над реверс-либой
│   ├── scraper.py                  # цикл скрапинга
│   └── mcp_server.py               # FastMCP с тулами
├── scripts/
│   ├── run_scraper.py
│   └── run_mcp.py
└── docs/superpowers/specs/
    └── 2026-06-12-threads-leadgenerator-design.md
```

`.env`:
```
THREADS_USERNAME=...
THREADS_PASSWORD=...
DB_PATH=./data/leads.db
SESSION_PATH=./data/session.json
SCRAPER_ACTIVE_HOURS=09-23
```

## Конфигурация MCP в Claude Code

В `.mcp.json` проекта:
```json
{
  "mcpServers": {
    "threads-leadgen": {
      "command": "uv",
      "args": ["run", "python", "scripts/run_mcp.py"],
      "cwd": "C:/Dev/Dev_2025/threads-leadgenerator"
    }
  }
}
```

## Запуск скрапера

Вариант 1 — вручную, когда садишься работать: `uv run python scripts/run_scraper.py`.
Вариант 2 — Windows Task Scheduler, дневной триггер 09:00, скрипт сам завершится в 23:00.

VPS — будущее. SQLite-файл переедет копированием.

## Риски и митигации

| Риск | Митигация |
|---|---|
| Реверс-либа ломается при обновлении Threads | Тонкая обёртка `threads_client.py`. При смене либы — правка одного файла. |
| Бан аккаунта-донора | Мягкие лимиты, активность в человеческие часы, ручное завершение при капче. Запасной план — отдельный донор (вне MVP). |
| Шум в выдаче по ключевикам (реклама, боты) | LLM-фильтрация на стадии ручного review через Claude Code. |
| Дублирование постов между ключевиками одной темы | PK по `post_id` — первая запись побеждает. |
| Probe бьёт по тому же rate-limit, что и скрапер | Probe идёт через тот же `threads_client`, считается в общий лимит. При большом probe — рискуем. Митигация: probe-запросы маленькие (limit=5), редкие, инициируются вручную. |

## Что НЕ входит в MVP

- Автоответы / автокомментирование.
- Анализ родительского треда и реплаев под постом.
- Поиск по хештегам и аккаунтам (только keyword-search).
- UI/дашборд.
- Несколько донор-аккаунтов в ротации.
- Алерты при появлении горячих лидов.

Эти пункты — после того, как MVP докажет, что в нём вообще есть смысл.
