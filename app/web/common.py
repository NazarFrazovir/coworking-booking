"""Shared helpers for server-rendered pages."""

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from pathlib import Path
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from fastapi import Request, status
from fastapi.responses import RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.config import settings
from app.models.booking import Booking, BookingStatus
from app.models.space import Space
from app.models.user import User

templates = Jinja2Templates(directory=Path(__file__).parent.parent / "templates")
# Lets every page show which environment it is served from.
templates.env.globals["app_env"] = settings.app_env

LOCAL_TZ = ZoneInfo(settings.display_timezone)


def local_dt(value: datetime | None, fmt: str = "%d.%m.%Y %H:%M") -> str:
    """Show a stored (UTC) datetime in the coworking's local time zone."""
    if value is None:
        return ""
    if value.tzinfo is None:  # SQLite returns naive UTC values
        value = value.replace(tzinfo=ZoneInfo("UTC"))
    return value.astimezone(LOCAL_TZ).strftime(fmt)


templates.env.filters["local"] = local_dt

SPACE_KINDS = {
    "meeting": "Переговорна",
    "desk": "Робоче місце",
    "office": "Кабінет",
    "hall": "Зала",
}


def space_kind(value: str) -> str:
    return SPACE_KINDS.get(value, value)


def seats(n: int) -> str:
    if n % 10 == 1 and n % 100 != 11:
        word = "місце"
    elif 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        word = "місця"
    else:
        word = "місць"
    return f"{n} {word}"


MONTHS_SHORT_UA = [
    "січ", "лют", "бер", "квіт", "трав", "черв",
    "лип", "серп", "вер", "жовт", "лист", "груд",
]  # fmt: skip


def month_short(value: datetime) -> str:
    return MONTHS_SHORT_UA[int(local_dt(value, "%m")) - 1]


def when(value: datetime) -> str:
    """'Сьогодні' / 'Завтра' / 'середа, 21 жовтня' for a stored datetime."""
    d = date.fromisoformat(local_dt(value, "%Y-%m-%d"))
    today = datetime.now(LOCAL_TZ).date()
    if d == today:
        return "Сьогодні"
    if d == today + timedelta(days=1):
        return "Завтра"
    return human_day(d).capitalize()


templates.env.filters["month_short"] = month_short
templates.env.filters["when"] = when
templates.env.filters["kind"] = space_kind
templates.env.filters["seats"] = seats


def combine_local(day: date, at: time) -> datetime:
    """Date + time typed in a form are local time → aware datetime."""
    return datetime.combine(day, at, tzinfo=LOCAL_TZ)


def home_url(user: User) -> str:
    return "/admin" if user.is_admin else "/home"


def redirect(
    url: str,
    *,
    msg: str | None = None,
    err: str | None = None,
    day: date | None = None,
) -> Response:
    """302 redirect (Post/Redirect/Get) with an optional flash message."""
    params = {
        k: v
        for k, v in {
            "day": day.isoformat() if day else None,
            "msg": msg,
            "err": err,
        }.items()
        if v
    }
    if params:
        url = f"{url}?{urlencode(params)}"
    return RedirectResponse(url, status_code=status.HTTP_302_FOUND)


def forbidden(request: Request, user: User | None) -> Response:
    return templates.TemplateResponse(
        request, "forbidden.html", {"user": user}, status_code=403
    )


def flash(request: Request) -> dict[str, str | None]:
    return {
        "msg": request.query_params.get("msg"),
        "err": request.query_params.get("err"),
    }


# ---------- day schedule (the "booking board") ----------

DAY_START_HOUR = 8
DAY_END_HOUR = 22
WEEKDAYS_UA = [
    "понеділок",
    "вівторок",
    "середа",
    "четвер",
    "пʼятниця",
    "субота",
    "неділя",
]
MONTHS_UA = [
    "січня", "лютого", "березня", "квітня", "травня", "червня",
    "липня", "серпня", "вересня", "жовтня", "листопада", "грудня",
]  # fmt: skip


def local_now() -> datetime:
    return datetime.now(LOCAL_TZ)


def human_day(day: date) -> str:
    """'вівторок, 20 жовтня' — how people say a date in Ukrainian."""
    return f"{WEEKDAYS_UA[day.weekday()]}, {day.day} {MONTHS_UA[day.month - 1]}"


def parse_day(raw: str | None) -> date:
    try:
        return date.fromisoformat(raw) if raw else local_now().date()
    except ValueError:
        return local_now().date()


@dataclass
class Block:
    left: float  # % from the start of the visible day
    width: float  # % of the visible day
    time: str
    label: str
    mine: bool
    booking_id: int


@dataclass
class Hour:
    hour: int
    past: bool


@dataclass
class ScheduleRow:
    space: Space
    blocks: list[Block] = field(default_factory=list)


def build_schedule(
    db: Session, day: date, spaces: list[Space], viewer: User
) -> tuple[list[ScheduleRow], list[Hour], float | None]:
    """Rows of confirmed bookings positioned on a DAY_START..DAY_END axis.

    Returns rows, hour cells and the "now" marker position (% or None).
    """
    start = combine_local(day, time(DAY_START_HOUR))
    end = combine_local(day, time(DAY_END_HOUR))
    total = (end - start).total_seconds()

    rows = {s.id: ScheduleRow(space=s) for s in spaces}
    bookings = db.scalars(
        select(Booking)
        .options(joinedload(Booking.user))
        .where(
            Booking.space_id.in_(rows.keys()),
            Booking.status == BookingStatus.CONFIRMED,
            Booking.start_time < end,
            Booking.end_time > start,
        )
        .order_by(Booking.start_time)
    ).all()
    for b in bookings:
        b_start = _aware(b.start_time).astimezone(LOCAL_TZ)
        b_end = _aware(b.end_time).astimezone(LOCAL_TZ)
        left = (max(b_start, start) - start).total_seconds() / total * 100
        right = (min(b_end, end) - start).total_seconds() / total * 100
        mine = b.user_id == viewer.id
        rows[b.space_id].blocks.append(
            Block(
                left=round(left, 3),
                width=round(right - left, 3),
                time=f"{b_start:%H:%M}–{b_end:%H:%M}",
                label=(
                    "Ви" if mine else (b.user.email if viewer.is_admin else "Зайнято")
                ),
                mine=mine,
                booking_id=b.id,
            )
        )

    now = local_now()
    hours = [
        Hour(hour=h, past=combine_local(day, time(h)) + timedelta(hours=1) <= now)
        for h in range(DAY_START_HOUR, DAY_END_HOUR)
    ]
    now_pos = None
    if start <= now <= end:
        now_pos = round((now - start).total_seconds() / total * 100, 3)
    return list(rows.values()), hours, now_pos


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=ZoneInfo("UTC"))


def schedule_context(db: Session, day: date, viewer: User) -> dict:
    spaces = list(
        db.scalars(select(Space).where(Space.is_active.is_(True)).order_by(Space.id))
    )
    rows, hours, now_pos = build_schedule(db, day, spaces, viewer)
    today = local_now().date()
    return {
        "day": day,
        "day_label": human_day(day),
        "is_today": day == today,
        "prev_day": day - timedelta(days=1),
        "next_day": day + timedelta(days=1),
        "today": today,
        "rows": rows,
        "hours": hours,
        "now_pos": now_pos,
        "spaces": spaces,
        "first_hour": DAY_START_HOUR,
        "last_hour": DAY_END_HOUR,
    }
