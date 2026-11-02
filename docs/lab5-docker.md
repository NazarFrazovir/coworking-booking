# Лабораторна робота №5 — контейнеризація (Docker)

Уся система (FastAPI + PostgreSQL) запускається однією командою:

```bash
cp config/.env.docker.example .env      # один раз
docker compose up --build
```

## Що зроблено

| Завдання | Де | Як |
|---|---|---|
| Базовий образ | `Dockerfile` | `python:3.12-slim`, версія задана через `ARG PYTHON_IMAGE` |
| Робоча директорія | `Dockerfile` | `WORKDIR /app` |
| `.dockerignore` | `.dockerignore` | виключено `.git`, `__pycache__`, `.venv`, усі `.env*`, логи, тести, документацію |
| Команда запуску | `Dockerfile` | `uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2` |
| Офіційний образ БД | `docker-compose.yml` | `postgres:16-alpine` |
| Збереження даних | `docker-compose.yml` | іменований том `pgdata` → `/var/lib/postgresql/data` |
| Один файл оркестрації | `docker-compose.yml` | сервіси `app` і `db` |
| Змінні з `.env` | `docker-compose.yml` | Compose сам читає `.env`, у контейнер передається лише явний список змінних |
| Внутрішня мережа | `docker-compose.yml` | `backend` (`internal: true`) для app↔db, `frontend` — лише для порту застосунку |
| Черговість запуску | `docker-compose.yml` | `healthcheck` у БД (`pg_isready`) + `depends_on: condition: service_healthy` |
| Міграції | `docker/entrypoint.sh` | `alembic upgrade head` перед стартом сервера |
| **Дод. 1:** multi-stage | `Dockerfile` | `builder` (компілятори, pip) → `runtime` (лише venv і код) |
| **Дод. 2:** hot-reload | `docker-compose.dev.yml` | bind mount `./app:/app/app` + `uvicorn --reload` |

## Як влаштовано

```
                 ┌──────────── мережа frontend ────────────┐
  браузер ──► localhost:8000 ──► app (FastAPI, 2 воркери) │
                 └───────────────────┬─────────────────────┘
                     мережа backend  │  internal: true — без інтернету
                     і без портів на │  хост-машину
                                     ▼
                               db (PostgreSQL 16) ──► том pgdata
```

**Порядок старту:**
1. Стартує `db`. Healthcheck щокілька секунд виконує `pg_isready`.
2. Лише коли БД *реально приймає з'єднання* (`healthy`), стартує `app`.
   Без `condition: service_healthy` застосунок запустився б раніше за базу й
   упав з помилкою підключення.
3. `entrypoint.sh` застосовує міграції (`alembic upgrade head`), у sandbox
   додає демо-дані й передає керування uvicorn.
4. У `app` теж є healthcheck (`GET /health`), тож `docker compose ps`
   показує `healthy`, коли сервер справді відповідає.

## Рішення і чому так

**Multi-stage build.** У стадії `builder` встановлюються `build-essential`
(gcc) і `libpq-dev`: вони потрібні, якщо якусь залежність доведеться
компілювати. Там же створюється віртуальне оточення `/opt/venv` з усіма
пакетами. Фінальна стадія `runtime` бере чистий `python:3.12-slim` і копіює
**лише** `/opt/venv` і код. Компілятори, заголовні файли, кеш apt і pip
залишаються в `builder` і в образ не потрапляють. Порівняння розмірів
`builder` і `runtime` друкує крок «Image report» у CI.

**Шари кешуються.** Спершу копіюється лише `requirements.txt` і
встановлюються залежності, а код — потім. Тому при зміні коду Docker не
перевстановлює пакети, і перезбирання займає секунди.

**Безпека образу:**
- застосунок працює від непривілейованого користувача `app`, не root;
- у образ не потрапляють `.env`-файли: секрети приходять лише змінними
  оточення під час запуску;
- немає тестів, документації, `.git`, кешів;
- БД сидить у мережі `internal: true`: до неї не можна достукатися ні з
  інтернету, ні з хост-машини, лише з контейнера застосунку.

**Змінні оточення.** Compose автоматично читає `.env` з папки проєкту й
підставляє `${ЗМІННІ}` у `docker-compose.yml`. Сервісу `app` передається
явний список змінних (білий список), а `POSTGRES_HOST` примусово `db`, тобто
ім'я сервісу всередині мережі compose. Обов'язкові змінні позначені
`${VAR:?повідомлення}`: якщо їх немає, compose відмовиться стартувати й
пояснить, чого бракує. Шаблон — `config/.env.docker.example`.

**Збереження даних.** PostgreSQL зберігає файли в іменованому томі
`pgdata`. `docker compose down` видаляє контейнери, але не томи, тож після
`up` усі користувачі й бронювання на місці. Дані видаляє лише
`docker compose down -v`.

**Режим розробки** (`docker-compose.dev.yml` накладається поверх основного):
- образ збирається зі стадії `dev` (додатково pytest, ruff тощо);
- папки `app/`, `migrations/`, `tests/` монтуються з диска (bind mount):
  контейнер бачить зміни коду одразу;
- uvicorn працює з `--reload`: зберіг файл — сервер перезапустився, без
  перезбирання образу. На macOS увімкнено `WATCHFILES_FORCE_POLLING`, бо
  події файлової системи через bind mount у Docker Desktop доходять не завжди;
- БД додатково публікується на `127.0.0.1:5435` для DB-клієнтів і для
  запуску застосунку поза Docker (ЛР3).

## Перевірка

Перевірено вживу:

| Перевірка | Результат |
|---|---|
| `docker compose up --build` | обидва контейнери `healthy`, app стартує лише після db |
| Міграції | у лозі `Running upgrade -> 0001`, у таблиці `alembic_version` — `0001` |
| API | `/health` → 200, реєстрація користувача, каталог просторів з демо-даними |
| Збереження даних | користувач є після `docker compose down` + `up` |
| Ізоляція | у `db` немає опублікованого порту, мережа `backend` має `internal=true` |
| Hot-reload | зміна `app/main.py` на диску → `WatchFiles detected changes… Reloading` → нова відповідь |
| Образ | користувач `app`, у `/app` лише `app/`, `migrations/`, `alembic.ini` |
| Лінтери | `hadolint Dockerfile` — без зауважень, `docker compose config` — валідна |

Те саме на офіційних образах Docker Hub автоматично перевіряє job **Docker
image + compose** у GitHub Actions (`.github/workflows/ci.yml`).

## Корисні команди

```bash
docker compose up --build -d          # у фоні
docker compose ps                     # стан і healthcheck
docker compose logs -f app            # логи застосунку
docker compose exec app python -m app.cli create-admin --email admin@example.com
docker compose exec db psql -U cowork_sandbox -d coworking_sandbox   # консоль БД
docker compose down                   # зупинити (дані зберігаються)
docker compose down -v                # зупинити й видалити дані
make docker-dev                       # режим розробки з hot-reload
```
