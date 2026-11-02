# CoWork Booking

[![CI](https://github.com/NazarFrazovir/coworking-booking/actions/workflows/ci.yml/badge.svg)](https://github.com/NazarFrazovir/coworking-booking/actions/workflows/ci.yml)

Платформа бронювання коворкінгів та конференц-залів.
Навчальний проєкт: лабораторні роботи з курсу проєктування та розробки
високонавантажених систем.

## Предметна область

Користувачі бронюють робочі місця/переговорні кімнати (Space) на певний
часовий слот. Ключовий виклик домену — конкурентний доступ до одного й того
самого слоту (наприклад, о 9:00 в понеділок, коли відкривається новий
тиждень бронювань). Перетин бронювань заборонено, а запис простору
блокується (`SELECT … FOR UPDATE`) на час перевірки.

## Стек

- **Backend:** FastAPI (Python 3.11+)
- **БД:** PostgreSQL 16, SQLAlchemy 2.0 (ORM), Alembic (міграції)
- **Автентифікація:** JWT (PyJWT), bcrypt, ролі `user` / `admin`
- **Сторінки:** Jinja2 (вхід, реєстрація, кабінет, адмін-панель)
- **Конфігурація:** pydantic-settings, окремі `.env.sandbox` / `.env.production`
- **Тести:** pytest (unit + integration)
- **CI:** GitHub Actions (ruff, black, pytest на SQLite і PostgreSQL)
- **Якість коду:** ruff, black, pre-commit

## Середовища

| | Sandbox (тестове) | Production (робоче) |
|---|---|---|
| Файл конфігурації | `.env.sandbox` | `.env.production` |
| База даних | `coworking_sandbox`, порт 5435 | `coworking_production`, порт 5436 |
| `DEBUG` | `true` — трейсбеки у браузері | `false` — сторінка «Щось пішло не так» з кодом помилки |
| Swagger `/docs` | увімкнено | вимкнено |
| Логи | `DEBUG` | `INFO` |
| Демо-дані (`seed-demo`) | дозволено | заборонено |
| Позначка в інтерфейсі | жовтий бейдж «Sandbox» | немає |

Середовище обирається змінною **`APP_ENV`**. Застосунок читає
`.env.<APP_ENV>`; справжні змінні оточення мають пріоритет над файлом (так
працюють CI і хмарний хостинг). Файли `.env.*` містять секрети і **не
комітяться** — у репозиторії лише шаблони в `config/*.example`.

Production не запуститься, якщо:
- `DEBUG=true`;
- `JWT_SECRET_KEY` коротший за 32 символи або схожий на заглушку (`change-me`);
- назва БД містить `sandbox`/`test`/`dev` (а sandbox — `prod`).

## Підготовка (один раз)

Потрібні Python 3.11+ і Docker.

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt

cp config/.env.sandbox.example    .env.sandbox
cp config/.env.production.example .env.production
```

Відкрийте обидва файли й замініть значення `change-me…` на свої. Для
production згенеруйте ключ:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

## Запуск sandbox

```bash
make setup-sandbox    # БД у Docker + міграції + демо-дані
make run-sandbox      # http://127.0.0.1:8000 з авто-перезавантаженням
```

Без `make` — ті самі команди:

```bash
docker compose --env-file .env.sandbox -p cowork-sandbox up -d --wait
APP_ENV=sandbox alembic upgrade head
APP_ENV=sandbox python -m app.cli seed-demo
APP_ENV=sandbox uvicorn app.main:app --reload
```

Демо-користувачі: `olena@example.com`, `taras@example.com`, пароль
`sandbox-demo-1`. Адміністратора створіть так:

```bash
APP_ENV=sandbox python -m app.cli create-admin --email admin@example.com --name "Admin"
```

## Запуск production

```bash
make setup-production   # окрема БД у Docker + міграції (без демо-даних)
APP_ENV=production python -m app.cli create-admin --email you@company.com --name "Адміністратор"
make run-production     # http://127.0.0.1:8080, 2 воркери, без reload і DEBUG
```

Без `make`:

```bash
docker compose --env-file .env.production -p cowork-production up -d --wait
APP_ENV=production alembic upgrade head
APP_ENV=production uvicorn app.main:app --host 0.0.0.0 --port 8080 --workers 2
```

Обидва середовища можуть працювати одночасно: у них різні контейнери,
томи даних, порти БД і порти застосунку. Перевірити, яке середовище
відповідає: `curl localhost:8000/health` → `{"environment": "sandbox"}`.

Подивитися поточну конфігурацію (паролі приховано):

```bash
APP_ENV=production python -m app.cli show-config
```

На Windows замість `APP_ENV=… команда` використовуйте
`$env:APP_ENV="production"; команда` (PowerShell).

## Структура проєкту

```
coworking-booking/
├── app/
│   ├── main.py          # create_app(settings): роутери, обробка помилок
│   ├── config.py        # Settings, вибір .env.<APP_ENV>, перевірки безпеки
│   ├── database.py      # engine/session SQLAlchemy
│   ├── cli.py           # create-admin, promote, seed-demo, show-config
│   ├── core/            # security, deps (доступ), errors (500/404), logging
│   ├── models/          # ORM-моделі (User, Space, Booking)
│   ├── schemas/         # Pydantic-схеми запитів/відповідей
│   ├── services/        # бізнес-логіка
│   ├── routers/         # JSON API
│   ├── web/             # HTML-сторінки
│   └── templates/       # Jinja2-шаблони
├── migrations/          # Alembic
├── config/              # шаблони .env.sandbox.example / .env.production.example
├── docs/                # architecture.md, lab2-auth.md, lab3-environments.md
├── tests/               # unit/ + integration/
├── loadtest/            # Locust-сценарії, монітор ресурсів, аналіз, результати
├── .github/workflows/   # ci.yml
├── docker-compose.yml   # PostgreSQL на одне середовище (запускається двічі)
├── Makefile             # make setup-sandbox, make run-production, …
├── requirements.txt     # залежності застосунку (для production)
└── requirements-dev.txt # + лінтери й тести
```

## Сторінки та API

Сторінки: `/login`, `/register`, `/home` (кабінет: розклад, бронювання,
профіль), `/admin` (адмін-панель: простори, користувачі, ролі, усі
бронювання). У sandbox доступний Swagger: `/docs`.

| Метод | Шлях (`/api/v1`) | Доступ |
|---|---|---|
| POST | `/auth/register`, `/auth/login`, `/auth/token` | усі |
| GET/PATCH | `/users/me` | авторизований |
| GET/PATCH | `/users/{id}` | власник або admin |
| GET | `/spaces/`, `/spaces/{id}`, `/spaces/{id}/availability?day=` | усі |
| POST/PATCH/DELETE | `/spaces/…` | admin |
| GET/POST | `/bookings/` | авторизований (тільки свої) |
| GET/PATCH | `/bookings/{id}`, POST `/bookings/{id}/cancel` | власник або admin |
| GET/PATCH | `/admin/…` | admin |

## Тести і CI

```bash
make lint     # ruff + black
make test     # pytest (SQLite у пам'яті)
```

Тести примусово працюють у середовищі `test` з власною базою, тож навіть
з `APP_ENV=production` в оболонці вони не торкаються sandbox чи
production. Той самий набір на PostgreSQL:

```bash
TEST_DATABASE_URL=postgresql+psycopg2://user:password@localhost:5435/coworking_test pytest
```

GitHub Actions (`.github/workflows/ci.yml`) запускається на кожен push у
`main` і на кожен pull request: лінтери, перевірка, що жоден `.env`-файл не
закомічено, pytest на Python 3.12 і 3.13, міграції та pytest на
PostgreSQL 16.

## Навантажувальне тестування

Сценарії Locust — у `loadtest/`. Профілі `smoke`, `baseline` (50 VUsers) і
`stress` (50 → 300 VUsers):

```bash
pip install -r requirements-loadtest.txt
make loadtest-seed        # 300 тестових користувачів у sandbox
make loadtest-baseline    # сервер має бути запущений, див. Makefile
make loadtest-stress
make loadtest-report      # таблиці й графіки в loadtest/results/
```

Рішення лабораторних: [ЛР2 — ролі та доступ](docs/lab2-auth.md),
[ЛР3 — середовища та CI](docs/lab3-environments.md),
[ЛР4 — навантажувальне тестування](docs/lab4-load-testing.md).
