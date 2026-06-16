"""
Pure, Home-Assistant-independent helpers for turning Nectr hourly usage into
recorder external statistics.

Everything here is plain stdlib so it can be unit tested without Home Assistant
installed. The coordinator wraps these helpers, builds the HA-typed metadata, and
calls the recorder.

Key correctness concern: Nectr returns 23-25 hourly rows per day because of DST
boundaries. We never parse the local "HH:00" strings into tz-aware times (which is
ambiguous on the fall-back hour). Instead we walk forward in UTC from local midnight
to the next local midnight, which yields exactly the right number of hour starts, and
pair them positionally with the usage values in chronological order.
"""

from datetime import date, datetime, timedelta, timezone, tzinfo
from typing import Optional

# Australian state/territory -> Olson timezone. The account's state defines "local"
# for the meter data, which is not necessarily Home Assistant's own timezone.
STATE_TIMEZONES = {
    "NSW": "Australia/Sydney",
    "ACT": "Australia/Sydney",
    "VIC": "Australia/Melbourne",
    "QLD": "Australia/Brisbane",
    "SA": "Australia/Adelaide",
    "WA": "Australia/Perth",
    "TAS": "Australia/Hobart",
    "NT": "Australia/Darwin",
}

# A day's data is only available from 03:00 local on the following day.
DATA_READY_HOUR = 3


def timezone_name_for_state(state: Optional[str], default: str) -> str:
    """Return the Olson timezone name for an Australian state, or `default` if unknown."""
    return STATE_TIMEZONES.get((state or "").strip().upper(), default)


def latest_eligible_day(now_local: datetime) -> date:
    """
    Return the most recent day whose usage Nectr should have processed.

    A day D becomes available around 03:00 local on D+1, so before 03:00 today only
    data up to the day before yesterday is reliably available.
    """
    today = now_local.date()
    if now_local.hour >= DATA_READY_HOUR:
        return today - timedelta(days=1)
    return today - timedelta(days=2)


def hourly_utc_starts(day: date, tz: tzinfo) -> list[datetime]:
    """
    Return the UTC start instants of every clock hour in a local calendar day.

    Walks forward one hour at a time from local midnight to the next local midnight,
    so DST days naturally yield 23 (spring forward) or 25 (fall back) entries instead
    of 24. Midnight is never inside an Australian DST transition, so the day bounds are
    unambiguous.

    Each start is floored to the top of the UTC hour. Recorder statistics are hourly
    buckets keyed to the top of the UTC hour; for whole-hour-offset states (e.g. NSW)
    this is a no-op, while for half-hour-offset states (SA, NT) it snaps the naturally
    HH:30 boundaries down to HH:00. The hour count is still driven by the true local
    day bounds (so 23/24/25 is preserved), and consecutive floored starts stay distinct
    and gap-free; only the half-hour-zone hourly view is shifted by 30 minutes.
    """
    next_day = day + timedelta(days=1)
    start_utc = datetime(day.year, day.month, day.day, tzinfo=tz).astimezone(timezone.utc)
    end_utc = datetime(
        next_day.year, next_day.month, next_day.day, tzinfo=tz
    ).astimezone(timezone.utc)

    starts: list[datetime] = []
    current = start_utc
    while current < end_utc:
        # Floor the stored start; iterate on the true boundary to keep the hour count.
        starts.append(current.replace(minute=0, second=0, microsecond=0))
        current += timedelta(hours=1)
    return starts


def pair_usage(
    utc_starts: list[datetime],
    usage_descending: list[Optional[float]],
) -> list[tuple[datetime, float]]:
    """
    Pair UTC hour starts with usage values in chronological order.

    Nectr returns hours in descending order (23:00 -> 0:00), so we reverse the usage
    list and pair positionally with the UTC starts. Positional (not hour-number) pairing
    is what makes the duplicate fall-back 02:00 and the missing spring-forward 02:00
    line up correctly.

    Raises ValueError if the value count does not match the expected number of hours for
    the day; the caller treats that as "skip this day" rather than corrupting the series.
    """
    usage_chronological = list(reversed(usage_descending))
    if len(usage_chronological) != len(utc_starts):
        raise ValueError(
            f"expected {len(utc_starts)} hourly values for the day, "
            f"got {len(usage_chronological)}"
        )
    return [
        (start, float(value) if value is not None else 0.0)
        for start, value in zip(utc_starts, usage_chronological)
    ]


def build_statistic_rows(
    pairs: list[tuple[datetime, float]],
    starting_sum: float,
) -> tuple[list[dict], float, float]:
    """
    Build cumulative statistic rows from hourly (start, kWh) pairs.

    Returns (rows, ending_sum, day_total) where each row is a dict suitable for a
    recorder StatisticData: the cumulatively increasing `sum` the Energy dashboard reads,
    plus a mirrored `state`.
    """
    rows: list[dict] = []
    running = starting_sum
    day_total = 0.0
    for start, value in pairs:
        running += value
        day_total += value
        cumulative = round(running, 6)
        rows.append({"start": start, "state": cumulative, "sum": cumulative})
    return rows, round(running, 6), round(day_total, 6)


def baseline_row(first_start_utc: datetime) -> dict:
    """
    Build a zero-sum statistic row one hour before the first imported hour.

    The Energy dashboard derives each hour's consumption from the change in `sum`
    between consecutive points, so without a prior point the very first imported hour
    is treated as the baseline and its usage would not show. Seeding a zero point one
    hour earlier makes that first hour count. Only needed for a fresh import (no existing
    statistics).
    """
    return {
        "start": first_start_utc - timedelta(hours=1),
        "state": 0.0,
        "sum": 0.0,
    }


def next_day_after(last_start_utc: datetime, tz: tzinfo) -> date:
    """Return the local calendar day after the day containing `last_start_utc`."""
    return last_start_utc.astimezone(tz).date() + timedelta(days=1)
