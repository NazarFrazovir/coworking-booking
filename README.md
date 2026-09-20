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
- **Якість коду:** ruff (лінтер), black (форматер), pre-commit (git-хуки)

## Структура проєкту

```
coworking-booking/
├── app/
│   ├── main.py          # точка входу FastAPI
│   ├── config.py        # налаштування (env)
│   ├── database.py      # engine/session SQLAlchemy
│   ├── models/          # ORM-моделі (User, Space, Booking)
│   ├── schemas/         # Pydantic-схеми запитів/відповідей
│   └── routers/         # ендпоінти API
├── docs/
│   └── architecture.md  # опис архітектури + діаграма
├── config/
│   └── .env.example
├── tests/
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
# відредагуйте .env під свою БД

uvicorn app.main:app --reload
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
