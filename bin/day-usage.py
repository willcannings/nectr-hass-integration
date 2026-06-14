#!/usr/bin/env python3

import argparse
import asyncio
from datetime import date, datetime, timedelta
import os
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPOSITORY_ROOT))

from nectr_session import NectrSession  # noqa: E402


def parse_date(value: str) -> date:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as error:
        raise argparse.ArgumentTypeError(
            f"invalid date {value!r}; expected YYYY-MM-DD"
        ) from error


def default_usage_date(now: datetime | None = None) -> date:
    if now is None:
        now = datetime.now(ZoneInfo("Australia/Sydney"))
    return now.date() - timedelta(days=1)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fetch hourly Nectr electricity usage for a day."
    )
    parser.add_argument(
        "date",
        type=parse_date,
        nargs="?",
        default=None,
        help="date to fetch in YYYY-MM-DD format (default: yesterday in Sydney)",
    )
    return parser


async def fetch_and_print_usage(day: date) -> int:
    session = NectrSession()

    if not await session.login(
        os.environ["NECTR_EMAIL"],
        os.environ["NECTR_PASSWORD"],
    ):
        print("Login failed", file=sys.stderr)
        return 1

    accounts = await session.get_accounts()
    if not accounts:
        print("No Nectr accounts found", file=sys.stderr)
        return 1

    data = await session.get_hourly_data(accounts[0].number, day)
    if not data.success:
        print(f"Failed to retrieve data: {data.message}", file=sys.stderr)
        return 1

    print(f"Data retrieved for {data.day}")
    print(f"  Complete: {data.is_complete}")
    print(f"  Hours: {len(data.hours)}")
    print(f"  Total usage: {sum(u for u in data.usage if u is not None):.2f} kWh")

    for hour, kwh in zip(data.hours, data.usage):
        print(f"  {hour:02d}:00 - {kwh if kwh is not None else 'N/A'} kWh")

    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    required_variables = (
        "NECTR_EMAIL",
        "NECTR_PASSWORD",
    )
    missing_variables = [name for name in required_variables if not os.getenv(name)]
    if missing_variables:
        parser.error(
            "missing required environment variables: "
            + ", ".join(missing_variables)
        )

    day = args.date if args.date is not None else default_usage_date()
    return asyncio.run(fetch_and_print_usage(day))


if __name__ == "__main__":
    raise SystemExit(main())
