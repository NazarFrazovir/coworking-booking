"""Load test scenario for CoWork Booking (lab #4).

Two kinds of virtual users imitate real traffic:

* ``Visitor``  (1 of 5) — not logged in: opens the login page and browses
  the public catalogue of spaces and their free slots.
* ``Member``   (4 of 5) — logs in once (POST /api/v1/auth/login), then
  works in the cabinet: opens /home with the day schedule, checks spaces
  and availability, looks at own bookings, sometimes books a slot and
  sometimes cancels it. Now and then logs in again (session expiry).

Think time between actions: 1–3 s, like a person clicking around.

Load profile is chosen with LOAD_PROFILE:

* ``smoke``               — 10 users for 30 s, a quick sanity check;
* ``baseline`` (default) — ramp-up 0→50 users in 60 s, hold 3 min (4 min);
* ``stress``             — +50 users every 60 s: 50 → 300 (6 min),
  to find where latency starts to grow.

    APP_ENV=sandbox python -m loadtest.seed_users --users 300
    LOAD_PROFILE=baseline locust -f loadtest/locustfile.py \
        --host http://127.0.0.1:8000 --headless --csv loadtest/results/baseline \
        --csv-full-history --html loadtest/results/baseline.html
"""

import os
import random
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from locust import HttpUser, LoadTestShape, between, task

API = "/api/v1"
PASSWORD = "loadtest-pass-1"
USERS_IN_POOL = int(os.getenv("LOADTEST_USERS", "300"))
KYIV = ZoneInfo("Europe/Kyiv")

_next_user = 0


def _next_email() -> str:
    """Each virtual user takes its own account from the seeded pool."""
    global _next_user
    _next_user = _next_user % USERS_IN_POOL + 1
    return f"loaduser{_next_user:04d}@example.com"


def _load_space_ids(client) -> list[int]:
    """Ids of bookable spaces. If the server is overloaded right now, fall
    back to the seeded ids instead of crashing the virtual user."""
    r = client.get(f"{API}/spaces/", name="GET /api/v1/spaces/")
    if r.status_code == 200 and r.json():
        return [s["id"] for s in r.json()]
    return [1, 2, 3, 4]


def _random_day() -> str:
    return (
        datetime.now(KYIV).date() + timedelta(days=random.randint(0, 6))
    ).isoformat()


class Visitor(HttpUser):
    """Anonymous visitor looking at what can be booked."""

    weight = 1
    wait_time = between(1, 3)

    def on_start(self) -> None:
        self.space_ids = _load_space_ids(self.client)

    @task(3)
    def catalogue(self) -> None:
        self.client.get(f"{API}/spaces/", name="GET /api/v1/spaces/")

    @task(3)
    def availability(self) -> None:
        self.client.get(
            f"{API}/spaces/{random.choice(self.space_ids)}/availability",
            params={"day": _random_day()},
            name="GET /api/v1/spaces/[id]/availability",
        )

    @task(2)
    def login_page(self) -> None:
        self.client.get("/login", name="GET /login")

    @task(1)
    def health(self) -> None:
        self.client.get("/health", name="GET /health")


class Member(HttpUser):
    """Registered user working with bookings."""

    weight = 4
    wait_time = between(1, 3)

    def on_start(self) -> None:
        self.email = _next_email()
        self.my_bookings: list[int] = []
        self.login()
        self.space_ids = _load_space_ids(self.client)

    # ---------- actions ----------

    def login(self) -> None:
        r = self.client.post(
            f"{API}/auth/login",
            json={"email": self.email, "password": PASSWORD},
            name="POST /api/v1/auth/login",
        )
        if r.status_code == 200:
            token = r.json()["access_token"]
            self.client.headers["Authorization"] = f"Bearer {token}"
            # the same JWT as a cookie, so the HTML cabinet works too
            self.client.cookies.set("access_token", token)

    @task(1)
    def relogin(self) -> None:
        self.login()

    @task(4)
    def home_page(self) -> None:
        self.client.get("/home", params={"day": _random_day()}, name="GET /home")

    @task(3)
    def catalogue(self) -> None:
        self.client.get(f"{API}/spaces/", name="GET /api/v1/spaces/")

    @task(3)
    def availability(self) -> None:
        self.client.get(
            f"{API}/spaces/{random.choice(self.space_ids)}/availability",
            params={"day": _random_day()},
            name="GET /api/v1/spaces/[id]/availability",
        )

    @task(2)
    def my_bookings_list(self) -> None:
        self.client.get(f"{API}/bookings/", name="GET /api/v1/bookings/")

    @task(1)
    def profile(self) -> None:
        self.client.get(f"{API}/users/me", name="GET /api/v1/users/me")

    @task(2)
    def book(self) -> None:
        """Book a random 1-hour slot. 409 'already booked' is a normal
        business answer when two users want the same slot, not an error."""
        day = datetime.now(KYIV).date() + timedelta(days=random.randint(1, 30))
        start = datetime.combine(day, time(random.randint(8, 20)), tzinfo=KYIV)
        with self.client.post(
            f"{API}/bookings/",
            json={
                "space_id": random.choice(self.space_ids),
                "start_time": start.isoformat(),
                "end_time": (start + timedelta(hours=1)).isoformat(),
            },
            name="POST /api/v1/bookings/",
            catch_response=True,
        ) as r:
            if r.status_code == 201:
                self.my_bookings.append(r.json()["id"])
                r.success()
            elif r.status_code == 409:
                r.success()
            else:
                r.failure(f"unexpected {r.status_code}")

    @task(1)
    def cancel(self) -> None:
        if not self.my_bookings:
            return
        booking_id = self.my_bookings.pop(random.randrange(len(self.my_bookings)))
        self.client.post(
            f"{API}/bookings/{booking_id}/cancel",
            name="POST /api/v1/bookings/[id]/cancel",
        )


# ---------- load profiles ----------

PROFILES = {
    # (end of stage in seconds, users, spawn rate per second)
    "smoke": [(30, 10, 5)],  # quick check that the scenario works
    "baseline": [(60, 50, 1), (240, 50, 1)],
    "stress": [(60, 50, 5), (120, 100, 5), (180, 150, 5),
               (240, 200, 5), (300, 250, 5), (360, 300, 5)],  # fmt: skip
}


class Profile(LoadTestShape):
    """Stages from PROFILES[LOAD_PROFILE]; the test stops after the last."""

    stages = PROFILES[os.getenv("LOAD_PROFILE", "baseline")]

    def tick(self):
        run_time = self.get_run_time()
        for end, users, rate in self.stages:
            if run_time < end:
                return users, rate
        return None
