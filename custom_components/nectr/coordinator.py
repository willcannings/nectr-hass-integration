"""Data update coordinator for the Nectr integration.

Responsible for logging in, deciding which days to import, building cumulative energy
statistics, and writing them to the recorder as external statistics. The recorder
itself is the single source of truth for both the running cumulative sum and the cursor
(the next day to import), which makes re-runs idempotent and immune to lost local state.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
import logging
from zoneinfo import ZoneInfo

from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.models import (
    StatisticData,
    StatisticMeanType,
    StatisticMetaData,
)
from homeassistant.components.recorder.statistics import (
    async_add_external_statistics,
    get_last_statistics,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.httpx_client import get_async_client
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util, slugify

from .const import (
    CONF_ACCOUNT_ADDRESS,
    CONF_ACCOUNT_NUMBER,
    CONF_ACCOUNT_STATE,
    CONF_DAYS_TO_LOAD,
    CONF_EMAIL,
    CONF_OFFPEAK_RATE,
    CONF_PASSWORD,
    CONF_PEAK_END_HOUR,
    CONF_PEAK_RATE,
    CONF_PEAK_START_HOUR,
    DATA_LAST_DAY_COST,
    DATA_LAST_DAY_TOTAL,
    DATA_LAST_IMPORTED_DATE,
    DEFAULT_DAYS_TO_LOAD,
    DEFAULT_PEAK_END_HOUR,
    DEFAULT_PEAK_START_HOUR,
    DOMAIN,
    ENERGY_UNIT,
    ENERGY_UNIT_CLASS,
    STORAGE_VERSION,
    UPDATE_INTERVAL,
)
from .nectr_session import NectrSession
from .statistics_import import (
    baseline_row,
    build_statistic_rows,
    cost_pairs,
    hourly_utc_starts,
    latest_eligible_day,
    local_hours_for_day,
    next_day_after,
    pair_usage,
    timezone_name_for_state,
)

_LOGGER = logging.getLogger(__name__)


class NectrUpdateCoordinator(DataUpdateCoordinator[dict]):
    """Coordinates fetching Nectr usage and importing it as external statistics."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=UPDATE_INTERVAL,
        )
        self.entry = entry
        self._email: str = entry.data[CONF_EMAIL]
        self._password: str = entry.data[CONF_PASSWORD]
        self._account_number: str = entry.data[CONF_ACCOUNT_NUMBER]
        self._account_address: str = entry.data.get(CONF_ACCOUNT_ADDRESS, "")
        self._days_to_load: int = int(
            entry.data.get(CONF_DAYS_TO_LOAD, DEFAULT_DAYS_TO_LOAD)
        )

        # Tariff config (rates are cents/kWh; hours are local clock hours).
        self._peak_rate: float = float(entry.data.get(CONF_PEAK_RATE, 0.0))
        self._offpeak_rate: float = float(entry.data.get(CONF_OFFPEAK_RATE, 0.0))
        self._peak_start_hour: int = int(
            entry.data.get(CONF_PEAK_START_HOUR, DEFAULT_PEAK_START_HOUR)
        )
        self._peak_end_hour: int = int(
            entry.data.get(CONF_PEAK_END_HOUR, DEFAULT_PEAK_END_HOUR)
        )

        tz_name = timezone_name_for_state(
            entry.data.get(CONF_ACCOUNT_STATE), hass.config.time_zone
        )
        self._tz = ZoneInfo(tz_name)

        self.statistic_id = f"{DOMAIN}:{slugify(self._account_number)}_consumption"
        self._metadata: StatisticMetaData = StatisticMetaData(
            source=DOMAIN,
            statistic_id=self.statistic_id,
            name=f"Nectr consumption ({self._account_address})".strip(),
            unit_of_measurement=ENERGY_UNIT,
            unit_class=ENERGY_UNIT_CLASS,
            has_sum=True,
            mean_type=StatisticMeanType.NONE,
        )

        # Cost statistic: same id as consumption with "_cost" appended. The value is a
        # cumulative dollar sum; unit_of_measurement/unit_class are None so the Energy
        # dashboard renders it with HA's configured currency (mirrors core's opower).
        self.cost_statistic_id = f"{self.statistic_id}_cost"
        self._cost_metadata: StatisticMetaData = StatisticMetaData(
            source=DOMAIN,
            statistic_id=self.cost_statistic_id,
            name=f"Nectr consumption cost ({self._account_address})".strip(),
            unit_of_measurement=None,
            unit_class=None,
            has_sum=True,
            mean_type=StatisticMeanType.NONE,
        )

        # Non-authoritative persistence: only so diagnostic sensors show their last
        # value immediately after a restart. Import decisions never depend on it.
        self._store: Store = Store(hass, STORAGE_VERSION, f"{DOMAIN}_{entry.entry_id}")
        self._restored: dict | None = None

    async def async_load_restored(self) -> None:
        """Load persisted diagnostic state before the first refresh."""
        self._restored = await self._store.async_load()

    async def _async_update_data(self) -> dict:
        """Fetch any newly-available days and import them as statistics."""
        session = NectrSession(get_async_client(self.hass))

        try:
            logged_in = await session.login(self._email, self._password)
        except Exception as err:  # noqa: BLE001 - surface as a retryable update failure
            raise UpdateFailed(f"Error connecting to Nectr: {err}") from err
        if not logged_in:
            raise ConfigEntryAuthFailed("Nectr authentication failed")

        latest = latest_eligible_day(dt_util.now(self._tz))

        running_sum, first_day, seed_baseline = await self._resolve_cursor(latest)
        running_cost_sum, has_cost_stats = await self._resolve_cost_sum()

        # When consumption stats already exist but cost stats do not (e.g. the user
        # entered tariff rates via Reconfigure for the first time), backfill costs for
        # the historical window before continuing with new days. seed_baseline is False
        # only when consumption stats already exist.
        if not has_cost_stats and not seed_baseline:
            running_cost_sum = await self._backfill_cost_stats(
                session, latest, first_day
            )

        last_imported_date, last_day_total, last_day_cost = self._initial_diagnostics()

        day = first_day
        while day <= latest:
            response = await session.get_hourly_data(self._account_number, day)

            # success=False means Nectr hasn't processed this day yet. Stop and retry
            # next cycle without advancing, so the day is picked up once it's ready.
            if not response.success:
                _LOGGER.debug(
                    "Nectr day %s not available yet: %s", day, response.message
                )
                break

            utc_starts = hourly_utc_starts(day, self._tz)
            try:
                pairs = pair_usage(utc_starts, response.usage)
            except ValueError as err:
                # Unexpected shape on a day Nectr says is ready. A one-day gap is a
                # minor blemish; a stuck cursor would block every future day, so we
                # log loudly and advance past it.
                _LOGGER.warning("Skipping Nectr day %s: %s", day, err)
                day += timedelta(days=1)
                continue

            rows, running_sum, day_total = build_statistic_rows(pairs, running_sum)

            # Cost mirrors consumption: each hour's local clock hour selects the peak or
            # offpeak rate, and the cumulative dollar sum is built the same way.
            local_hours = local_hours_for_day(day, self._tz)
            day_cost_pairs = cost_pairs(
                pairs,
                local_hours,
                self._peak_start_hour,
                self._peak_end_hour,
                self._peak_rate,
                self._offpeak_rate,
            )
            cost_rows, running_cost_sum, cost_day_total = build_statistic_rows(
                day_cost_pairs, running_cost_sum
            )

            # On a fresh import, seed a zero point before the first ever hour so the
            # first hour's consumption/cost is not swallowed as the dashboard baseline.
            if seed_baseline and rows:
                rows = [baseline_row(rows[0]["start"]), *rows]
                cost_rows = [baseline_row(cost_rows[0]["start"]), *cost_rows]
                seed_baseline = False

            async_add_external_statistics(
                self.hass, self._metadata, [StatisticData(**row) for row in rows]
            )
            async_add_external_statistics(
                self.hass,
                self._cost_metadata,
                [StatisticData(**row) for row in cost_rows],
            )
            _LOGGER.debug(
                "Imported %s hours for %s (%.3f kWh)", len(rows), day, day_total
            )
            last_imported_date = day
            last_day_total = day_total
            last_day_cost = cost_day_total
            day += timedelta(days=1)

        data = {
            DATA_LAST_IMPORTED_DATE: last_imported_date,
            DATA_LAST_DAY_TOTAL: last_day_total,
            DATA_LAST_DAY_COST: last_day_cost,
        }
        await self._persist(data)
        return data

    async def _resolve_cursor(self, latest: date) -> tuple[float, date, bool]:
        """
        Derive the running cumulative sum and the next day to import from the recorder.

        Returns (running_sum, first_day, is_fresh). When statistics already exist,
        continue from the last imported hour. When they do not, start a fresh backfill
        window sized by `days_to_load` and flag it so the caller seeds a baseline point.
        """
        last_stat = await get_instance(self.hass).async_add_executor_job(
            get_last_statistics,
            self.hass,
            1,
            self.statistic_id,
            # convert_units=False: we read back the raw stored sum to continue from; a
            # converted value would silently break cumulative continuity.
            False,
            {"sum"},
        )

        rows = last_stat.get(self.statistic_id)
        if rows:
            row = rows[0]
            running_sum = float(row.get("sum") or 0.0)
            last_start = self._row_start_to_utc(row["start"])
            return running_sum, next_day_after(last_start, self._tz), False

        return 0.0, latest - timedelta(days=self._days_to_load - 1), True

    async def _resolve_cost_sum(self) -> tuple[float, bool]:
        """
        Return the running cumulative cost (dollars) and whether cost stats exist.

        Read from the cost statistic itself so cost stays self-consistent. Returns
        (running_sum, True) when stats exist, (0.0, False) when they do not — the
        caller uses the bool to decide whether a historical cost backfill is needed.
        """
        last_stat = await get_instance(self.hass).async_add_executor_job(
            get_last_statistics,
            self.hass,
            1,
            self.cost_statistic_id,
            False,
            {"sum"},
        )
        rows = last_stat.get(self.cost_statistic_id)
        if rows:
            return float(rows[0].get("sum") or 0.0), True
        return 0.0, False

    async def _backfill_cost_stats(
        self,
        session: NectrSession,
        latest: date,
        first_day: date,
    ) -> float:
        """
        Write cost statistics for days that already have consumption stats but no cost.

        Called once when cost stats are absent but consumption stats exist — typically
        after a user enters tariff rates via Reconfigure on an existing install. Fetches
        each day in the window [latest - days_to_load + 1, first_day - 1] from the
        Nectr API, calculates costs using the current tariff, and writes cost-only stats.
        Returns the running cost sum after the backfill so the normal refresh loop can
        continue seamlessly from first_day.
        """
        backfill_start = latest - timedelta(days=self._days_to_load - 1)
        backfill_end = first_day - timedelta(days=1)

        if backfill_start > backfill_end:
            # No historical days to backfill (e.g. days_to_load=1 or first_day is at
            # the very start of the window).
            return 0.0

        _LOGGER.debug(
            "Backfilling cost stats from %s to %s", backfill_start, backfill_end
        )

        running_cost_sum = 0.0
        seeded_baseline = False
        day = backfill_start
        while day <= backfill_end:
            response = await session.get_hourly_data(self._account_number, day)
            if not response.success:
                _LOGGER.debug(
                    "Cost backfill: Nectr day %s not available, skipping", day
                )
                day += timedelta(days=1)
                continue

            utc_starts = hourly_utc_starts(day, self._tz)
            try:
                pairs = pair_usage(utc_starts, response.usage)
            except ValueError as err:
                _LOGGER.warning("Cost backfill: skipping day %s: %s", day, err)
                day += timedelta(days=1)
                continue

            local_hours = local_hours_for_day(day, self._tz)
            day_cost_pairs = cost_pairs(
                pairs,
                local_hours,
                self._peak_start_hour,
                self._peak_end_hour,
                self._peak_rate,
                self._offpeak_rate,
            )
            cost_rows, running_cost_sum, _ = build_statistic_rows(
                day_cost_pairs, running_cost_sum
            )

            # Seed a zero baseline before the first ever cost row so the Energy
            # dashboard doesn't swallow the first hour's cost as its baseline.
            if not seeded_baseline and cost_rows:
                cost_rows = [baseline_row(cost_rows[0]["start"]), *cost_rows]
                seeded_baseline = True

            async_add_external_statistics(
                self.hass,
                self._cost_metadata,
                [StatisticData(**row) for row in cost_rows],
            )
            _LOGGER.debug("Backfilled cost for %s", day)
            day += timedelta(days=1)

        return running_cost_sum

    @staticmethod
    def _row_start_to_utc(start) -> datetime:
        """Normalise a get_last_statistics `start` (float ts or datetime) to aware UTC."""
        if isinstance(start, (int, float)):
            return dt_util.utc_from_timestamp(start)
        return dt_util.as_utc(start)

    def _initial_diagnostics(self) -> tuple[date | None, float | None, float | None]:
        """Seed diagnostics from prior in-memory data, else restored storage."""
        if self.data:
            return (
                self.data.get(DATA_LAST_IMPORTED_DATE),
                self.data.get(DATA_LAST_DAY_TOTAL),
                self.data.get(DATA_LAST_DAY_COST),
            )
        if self._restored:
            stored_date = self._restored.get(DATA_LAST_IMPORTED_DATE)
            parsed = dt_util.parse_date(stored_date) if stored_date else None
            return parsed, self._restored.get(DATA_LAST_DAY_TOTAL), self._restored.get(DATA_LAST_DAY_COST)
        return None, None, None

    async def _persist(self, data: dict) -> None:
        """Persist diagnostic state (date serialised as ISO string)."""
        imported_date = data[DATA_LAST_IMPORTED_DATE]
        await self._store.async_save(
            {
                DATA_LAST_IMPORTED_DATE: (
                    imported_date.isoformat() if imported_date else None
                ),
                DATA_LAST_DAY_TOTAL: data[DATA_LAST_DAY_TOTAL],
                DATA_LAST_DAY_COST: data[DATA_LAST_DAY_COST],
            }
        )
