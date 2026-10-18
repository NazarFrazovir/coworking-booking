# CoWork Booking

Платформа бронювання коворкінгів та конференц-залів.
Навчальний проєкт: лабораторні роботи з курсу проєктування та розробки
високонавантажених систем.

## Предметна область

Користувачі бронюють робочі місця/переговорні кімнати (Space) на певний
часовий слот. Ключовий виклик домену — конкурентний доступ до одного й того
самого слоту (наприклад, о 9:00 в понеділок, коли відкривається новий
тиждень бронювань). Це навмисно закладено в схему БД через
`UNIQUE(space_id, start_time)`, щоб надалі досліджувати кешування,
блокування та масштабування без переписування домену.

## Стек

- **Backend:** FastAPI (Python 3.11+)
- **БД:** PostgreSQL, SQLAlchemy 2.0 (ORM), Alembic (міграції)
- **Автентифікація:** JWT (PyJWT), bcrypt, ролі `user` / `admin`
- **Сторінки:** Jinja2 (вхід, реєстрація, домашні сторінки ролей)
- **Тести:** pytest (unit + integration)
- **Якість коду:** ruff (лінтер), black (форматер), pre-commit (git-хуки)

## Структура проєкту

```
coworking-booking/
├── app/
│   ├── main.py          # точка входу FastAPI
│   ├── config.py        # налаштування (env)
│   ├── database.py      # engine/session SQLAlchemy
│   ├── cli.py           # створення адміністратора
│   ├── core/            # security (bcrypt, JWT), deps (контроль доступу)
│   ├── models/          # ORM-моделі (User, Space, Booking)
│   ├── schemas/         # Pydantic-схеми запитів/відповідей
│   ├── services/        # бізнес-логіка (реєстрація, вхід, бронювання)
│   ├── routers/         # ендпоінти API (auth, users, spaces, bookings, admin)
│   ├── web/             # HTML-сторінки (cookie-автентифікація)
│   └── templates/       # Jinja2-шаблони
├── migrations/          # Alembic
├── docs/
│   ├── architecture.md  # опис архітектури + діаграма
│   └── lab2-auth.md     # ЛР2: ролі, доступ, обґрунтування рішень
├── config/
│   └── .env.example
├── tests/               # unit/ + integration/
├── requirements.txt
├── pyproject.toml       # конфіг ruff/black
└── .pre-commit-config.yaml
```

## Запуск локально

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp config/.env.example .env
# відредагуйте .env під свою БД і задайте JWT_SECRET_KEY

alembic upgrade head                      # створити таблиці
python -m app.cli create-admin --email admin@example.com --name "Admin"

uvicorn app.main:app --reload
```

> Якщо база вже існує з ЛР1 (таблиці без колонки `role`), видаліть і
> створіть її заново перед `alembic upgrade head`.

Сторінки: `/login`, `/register`, `/home` (користувач), `/admin`
(адміністратор). У Swagger (`/docs`) натисніть **Authorize** і введіть email
у полі `username`.

## Основні ендпоінти (`/api/v1`)

| Метод | Шлях | Доступ |
|---|---|---|
| POST | `/auth/register`, `/auth/login`, `/auth/token` | усі |
| GET/PATCH | `/users/me` | авторизований |
| GET/PATCH | `/users/{id}` | власник або admin |
| GET | `/spaces/`, `/spaces/{id}`, `/spaces/{id}/availability?day=` | усі |
| POST/PATCH/DELETE | `/spaces/…` | admin |
| GET/POST | `/bookings/` | авторизований (тільки свої) |
| GET/PATCH | `/bookings/{id}`, POST `/bookings/{id}/cancel` | власник або admin |
| GET/PATCH | `/admin/stats`, `/admin/users`, `/admin/users/{id}/role`, `/admin/users/{id}/active`, `/admin/bookings` | admin |

Детально про рішення — [docs/lab2-auth.md](docs/lab2-auth.md).

## Тести

```bash
pytest                    # SQLite у пам'яті
TEST_DATABASE_URL=postgresql+psycopg2://postgres:postgres@localhost/coworking_test pytest
```

API буде доступне на `http://127.0.0.1:8000`, документація Swagger — на
`http://127.0.0.1:8000/docs`.

## Контроль якості коду

```bash
ruff check .        # лінт
black .             # форматування
pre-commit install  # встановити git-хуки один раз
```

Після `pre-commit install` кожен `git commit` автоматично прожене
ruff/black/базові перевірки і заблокує коміт при порушеннях стилю чи
синтаксичних помилках.
