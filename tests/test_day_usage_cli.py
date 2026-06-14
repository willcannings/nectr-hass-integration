import argparse
from contextlib import redirect_stderr, redirect_stdout
from datetime import date, datetime
import importlib.util
import io
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

from nectr_session import HourlyDataResponse


SCRIPT_PATH = Path(__file__).resolve().parent.parent / "bin" / "day-usage.py"
SPEC = importlib.util.spec_from_file_location("day_usage_cli", SCRIPT_PATH)
day_usage_cli = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(day_usage_cli)


class DayUsageCliTests(unittest.TestCase):
    def test_parse_date_accepts_iso_date(self):
        self.assertEqual(day_usage_cli.parse_date("2026-05-12"), date(2026, 5, 12))

    def test_parse_date_rejects_non_iso_date(self):
        with self.assertRaises(argparse.ArgumentTypeError):
            day_usage_cli.parse_date("12/05/2026")

    def test_parse_date_rejects_compact_iso_date(self):
        with self.assertRaises(argparse.ArgumentTypeError):
            day_usage_cli.parse_date("20260512")

    def test_default_usage_date_is_previous_calendar_day(self):
        now = datetime(2026, 6, 13, 0, 30)

        self.assertEqual(
            day_usage_cli.default_usage_date(now),
            date(2026, 6, 12),
        )

    def test_main_forwards_explicit_date(self):
        fetch_usage = AsyncMock(return_value=0)

        with (
            patch.dict(os.environ, self.required_environment(), clear=True),
            patch.object(day_usage_cli, "fetch_and_print_usage", fetch_usage),
        ):
            exit_code = day_usage_cli.main(["2026-05-12"])

        self.assertEqual(exit_code, 0)
        fetch_usage.assert_awaited_once_with(date(2026, 5, 12))

    def test_main_defaults_to_yesterday(self):
        fetch_usage = AsyncMock(return_value=0)

        with (
            patch.dict(os.environ, self.required_environment(), clear=True),
            patch.object(
                day_usage_cli,
                "default_usage_date",
                return_value=date(2026, 6, 12),
            ),
            patch.object(day_usage_cli, "fetch_and_print_usage", fetch_usage),
        ):
            exit_code = day_usage_cli.main([])

        self.assertEqual(exit_code, 0)
        fetch_usage.assert_awaited_once_with(date(2026, 6, 12))

    @staticmethod
    def required_environment():
        return {
            "NECTR_EMAIL": "test@example.com",
            "NECTR_PASSWORD": "password",
        }


class DayUsageFetchTests(unittest.IsolatedAsyncioTestCase):
    async def test_fetch_uses_first_discovered_account(self):
        session = Mock()
        session.login = AsyncMock(return_value=True)
        session.get_accounts = AsyncMock(
            return_value=[
                SimpleNamespace(number="A-FIRST"),
                SimpleNamespace(number="A-SECOND"),
            ]
        )
        session.get_hourly_data = AsyncMock(
            return_value=HourlyDataResponse(
                success=True,
                message="",
                is_complete=False,
                day=date(2026, 5, 12),
                usage=[0.5],
                hours=[23],
            )
        )

        with (
            patch.dict(os.environ, DayUsageCliTests.required_environment(), clear=True),
            patch.object(day_usage_cli, "NectrSession", return_value=session),
            redirect_stdout(io.StringIO()),
        ):
            exit_code = await day_usage_cli.fetch_and_print_usage(date(2026, 5, 12))

        self.assertEqual(exit_code, 0)
        session.get_accounts.assert_awaited_once_with()
        session.get_hourly_data.assert_awaited_once_with(
            "A-FIRST",
            date(2026, 5, 12),
        )

    async def test_fetch_fails_when_no_accounts_are_returned(self):
        session = Mock()
        session.login = AsyncMock(return_value=True)
        session.get_accounts = AsyncMock(return_value=[])

        with (
            patch.dict(os.environ, DayUsageCliTests.required_environment(), clear=True),
            patch.object(day_usage_cli, "NectrSession", return_value=session),
            redirect_stderr(io.StringIO()),
        ):
            exit_code = await day_usage_cli.fetch_and_print_usage(date(2026, 5, 12))

        self.assertEqual(exit_code, 1)


if __name__ == "__main__":
    unittest.main()
