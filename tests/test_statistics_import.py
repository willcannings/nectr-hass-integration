import sys
import unittest
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(
    0, str(Path(__file__).resolve().parent.parent / "custom_components" / "nectr")
)

import statistics_import as si  # noqa: E402

SYDNEY = ZoneInfo("Australia/Sydney")
ADELAIDE = ZoneInfo("Australia/Adelaide")


def utc(year, month, day, hour):
    return datetime(year, month, day, hour, tzinfo=timezone.utc)


class HourlyUtcStartsTests(unittest.TestCase):
    def test_normal_day_has_24_hours(self):
        starts = si.hourly_utc_starts(date(2026, 6, 15), SYDNEY)

        self.assertEqual(len(starts), 24)
        self.assertEqual(starts[0], utc(2026, 6, 14, 14))
        self.assertEqual(starts[-1], utc(2026, 6, 15, 13))

    def test_fall_back_day_has_25_hours(self):
        # 5 Apr 2026 is the first Sunday of April: DST ends, clocks go 03:00 -> 02:00.
        starts = si.hourly_utc_starts(date(2026, 4, 5), SYDNEY)

        self.assertEqual(len(starts), 25)
        self.assertEqual(starts[0], utc(2026, 4, 4, 13))
        self.assertEqual(starts[-1], utc(2026, 4, 5, 13))
        # Strictly increasing, one-hour spacing throughout the overlap.
        deltas = {(b - a).total_seconds() for a, b in zip(starts, starts[1:])}
        self.assertEqual(deltas, {3600})

    def test_spring_forward_day_has_23_hours(self):
        # 4 Oct 2026 is the first Sunday of October: DST starts, clocks go 02:00 -> 03:00.
        starts = si.hourly_utc_starts(date(2026, 10, 4), SYDNEY)

        self.assertEqual(len(starts), 23)
        self.assertEqual(starts[0], utc(2026, 10, 3, 14))
        self.assertEqual(starts[-1], utc(2026, 10, 4, 12))


class HalfHourOffsetTests(unittest.TestCase):
    """SA/NT are UTC+9:30/+10:30; local hour boundaries fall on UTC HH:30."""

    def test_adelaide_starts_are_hour_aligned(self):
        starts = si.hourly_utc_starts(date(2026, 6, 15), ADELAIDE)

        self.assertEqual(len(starts), 24)
        self.assertTrue(all(s.minute == 0 and s.second == 0 for s in starts))
        self.assertEqual(starts[0], utc(2026, 6, 14, 14))
        self.assertEqual(starts[-1], utc(2026, 6, 15, 13))
        deltas = {(b - a).total_seconds() for a, b in zip(starts, starts[1:])}
        self.assertEqual(deltas, {3600})

    def test_adelaide_fall_back_stays_aligned_distinct_and_25_hours(self):
        starts = si.hourly_utc_starts(date(2026, 4, 5), ADELAIDE)

        self.assertEqual(len(starts), 25)
        self.assertTrue(all(s.minute == 0 for s in starts))
        self.assertEqual(len(set(starts)), 25)


class BaselineRowTests(unittest.TestCase):
    def test_baseline_is_zero_one_hour_before_first(self):
        row = si.baseline_row(utc(2026, 6, 14, 14))

        self.assertEqual(
            row, {"start": utc(2026, 6, 14, 13), "state": 0.0, "sum": 0.0}
        )


class LatestEligibleDayTests(unittest.TestCase):
    def test_before_3am_excludes_yesterday(self):
        now = datetime(2026, 6, 15, 2, 30, tzinfo=SYDNEY)

        self.assertEqual(si.latest_eligible_day(now), date(2026, 6, 13))

    def test_at_3am_includes_yesterday(self):
        now = datetime(2026, 6, 15, 3, 0, tzinfo=SYDNEY)

        self.assertEqual(si.latest_eligible_day(now), date(2026, 6, 14))


class PairUsageTests(unittest.TestCase):
    def test_reverses_descending_usage_into_chronological_order(self):
        starts = si.hourly_utc_starts(date(2026, 6, 15), SYDNEY)
        usage_descending = [float(hour) for hour in range(23, -1, -1)]

        pairs = si.pair_usage(starts, usage_descending)

        self.assertEqual(len(pairs), 24)
        self.assertEqual(pairs[0], (starts[0], 0.0))
        self.assertEqual(pairs[-1], (starts[-1], 23.0))

    def test_none_values_become_zero(self):
        starts = si.hourly_utc_starts(date(2026, 6, 15), SYDNEY)
        usage = [None] * 24

        pairs = si.pair_usage(starts, usage)

        self.assertTrue(all(value == 0.0 for _, value in pairs))

    def test_count_mismatch_raises(self):
        starts = si.hourly_utc_starts(date(2026, 6, 15), SYDNEY)

        with self.assertRaises(ValueError):
            si.pair_usage(starts, [1.0] * 23)

    def test_fall_back_daily_total_is_exact(self):
        starts = si.hourly_utc_starts(date(2026, 4, 5), SYDNEY)
        usage_descending = [round(0.1 * i, 2) for i in range(25)]

        pairs = si.pair_usage(starts, usage_descending)
        _, _, day_total = si.build_statistic_rows(pairs, 0.0)

        self.assertEqual(day_total, round(sum(usage_descending), 6))


class BuildStatisticRowsTests(unittest.TestCase):
    def test_cumulative_sum_continues_from_starting_sum(self):
        starts = si.hourly_utc_starts(date(2026, 6, 15), SYDNEY)
        pairs = [(starts[0], 1.0), (starts[1], 2.0), (starts[2], 0.5)]

        rows, ending_sum, day_total = si.build_statistic_rows(pairs, 10.0)

        self.assertEqual([row["sum"] for row in rows], [11.0, 13.0, 13.5])
        self.assertEqual([row["state"] for row in rows], [11.0, 13.0, 13.5])
        self.assertEqual(rows[0]["start"], starts[0])
        self.assertEqual(ending_sum, 13.5)
        self.assertEqual(day_total, 3.5)


class CursorTests(unittest.TestCase):
    def test_next_day_after_uses_local_date(self):
        # 2026-06-15 13:00Z == 2026-06-15 23:00 in Sydney -> next local day is the 16th.
        last_start = utc(2026, 6, 15, 13)

        self.assertEqual(si.next_day_after(last_start, SYDNEY), date(2026, 6, 16))


class TimezoneForStateTests(unittest.TestCase):
    def test_known_states_map_case_insensitively(self):
        self.assertEqual(
            si.timezone_name_for_state("NSW", "UTC"), "Australia/Sydney"
        )
        self.assertEqual(
            si.timezone_name_for_state("qld", "UTC"), "Australia/Brisbane"
        )

    def test_unknown_or_missing_state_falls_back(self):
        self.assertEqual(si.timezone_name_for_state("ZZ", "Australia/Perth"), "Australia/Perth")
        self.assertEqual(si.timezone_name_for_state(None, "Australia/Perth"), "Australia/Perth")


if __name__ == "__main__":
    unittest.main()
