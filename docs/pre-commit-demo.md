# Демонстрація роботи pre-commit хуків

Хуки налаштовані в `.pre-commit-config.yaml`: `ruff` (лінт + автофікс),
`black` (форматування), а також базові перевірки з
`pre-commit-hooks` (trailing whitespace, EOF, YAML-синтаксис, розмір
файлів). Встановлено командою `pre-commit install`.

## Крок 1. "Брудний" файл блокує коміт

У файл було навмисно додано невикористану змінну та недбале
форматування:

```python
import os
def broken_function(   x,y ):
    unused_var = 5
    result=x+y
    return result
```

Спроба `git commit` дала результат:

```
ruff.....................................................................Failed
- hook id: ruff
- exit code: 1
- files were modified by this hook

app/bad_example.py:2:5: F841 Local variable `unused_var` is assigned to but never used
  |
1 | def broken_function(   x,y ):
2 |     unused_var = 5
  |     ^^^^^^^^^^ F841
3 |     result=x+y
4 |     return result
  |
  = help: Remove assignment to unused variable `unused_var`

Found 2 errors (1 fixed, 1 remaining).

black....................................................................Failed
- hook id: black
- files were modified by this hook

reformatted app/bad_example.py
```

Коміт **не відбувся** — `git log` після цього все ще показував
попередній коміт як останній. `ruff` автоматично прибрав частину
проблем (невикористаний імпорт `os`), але помилку `F841`
(невикористана змінна) не можна виправити автоматично — вона вимагає
рішення розробника, тож хук завершився з ненульовим кодом і заблокував
коміт.

## Крок 2. Чистий код проходить успішно

Після виправлення файлу до:

```python
"""Scratch file used to demonstrate pre-commit hooks in lab #1."""


def add(x: int, y: int) -> int:
    """Return the sum of two integers."""
    return x + y
```

`git commit` пройшов без перешкод:

```
ruff.....................................................................Passed
black....................................................................Passed
trim trailing whitespace.................................................Passed
fix end of files.........................................................Passed
check yaml...........................................(no files to check)Skipped
check for added large files..............................................Passed
[master 32b46f6] test: demonstrate a clean commit passing pre-commit
 1 file changed, 6 insertions(+)
```

Тестовий файл після демонстрації видалено окремим комітом, щоб не
засмічувати кодову базу.
