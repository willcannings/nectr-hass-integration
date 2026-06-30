# Repository Guide

## Purpose

This repository is a Home Assistant integration for Nectr electricity usage, packaged
under `custom_components/nectr/`. The API layer is
`custom_components/nectr/nectr_session.py`; it is kept independent of Home Assistant so
it can be exercised by `bin/day-usage.py` and the tests. The integration imports hourly
usage and cost into the recorder as long-term external statistics for the Energy
dashboard.

Two statistics are written per import:

- **Consumption** (`nectr:<account>`) — cumulative kWh, unit `kWh`.
- **Cost** (`nectr:<account>_cost`) — cumulative dollars, no unit (matches Home
  Assistant's `opower` convention so the Energy dashboard renders it with the configured
  currency). A zero baseline is seeded on a fresh import so the first hour's cost is not
  swallowed as the dashboard baseline.

Cost is calculated from tariff rates stored in the config entry. Rates are entered in
cents/kWh (fractional cents allowed, matching how they appear on a Nectr statement) and
stored in `const.py` config keys; the statistic value is divided by 100 to produce
dollars.

The tariff config keys are:
- `CONF_PEAK_RATE` / `CONF_OFFPEAK_RATE` — rate in cents/kWh.
- `CONF_PEAK_START_HOUR` / `CONF_PEAK_END_HOUR` — local clock hours 0–23 defining a
  half-open `[start, end)` peak window. Supports windows that wrap past midnight.
  Defaults are 15–21.

## API Reference

- Read `api-docs/API.md` for the API overview.
- Treat `api-docs/emailAuthenticate.har`, `api-docs/getUserBrief.har`, and
  `api-docs/getUsageInfo.har` as the source of truth for GraphQL operation
  names, variables, fields, headers, and date formats.
- The API endpoint is `https://mobile.nectr.com.au/graphql`.
- Authenticate before requesting accounts or usage. Send the returned access
  token as `Authorization: bearer <token>`.
- Discover account numbers with `get_accounts()` rather than requiring users
  to provide them during session construction.
- Hourly usage requests use `DD/MM/YYYY` dates and an exclusive next-day
  `toDate`.
- Usage entries are returned in descending hour order.
- The upstream schema spells its granularity enum type `GRANUALRITY`. Preserve
  that spelling unless the captured API behavior changes.

## Development

- Use asynchronous I/O and `httpx.AsyncClient`.
- Do not log credentials, tokens, authorization headers, or full login
  payloads.
- Keep the API interface independent of Home Assistant where practical so it
  can be tested in isolation.
- Prefer typed response objects and explicit handling of malformed or partial
  API responses.
- Tests use the standard-library `unittest` framework and must not call the
  live Nectr API.
- `bin/day-usage.py` is the manual API runner. It accepts an optional date in
  `YYYY-MM-DD` format and defaults to yesterday in Australia/Sydney.
- Run tests with:

  ```sh
  venv/bin/python -m unittest discover -s tests -v
  ```

### Cost calculation

The cost helpers in `custom_components/nectr/statistics_import.py` are HA-independent
and unit-tested:

- `local_hours_for_day(day, tz)` — returns the local clock hour of each hour boundary
  in a calendar day, positionally aligned with `hourly_utc_starts`. Reads the true local
  hour (not the floored UTC start) so half-hour-offset states (SA, NT) classify boundary
  hours correctly.
- `is_peak_hour(hour, peak_start, peak_end)` — half-open `[start, end)` test with
  midnight-wrap support.
- `cost_pairs(pairs, local_hours, peak_start, peak_end, peak_cents, offpeak_cents)` —
  converts `(utc_start, kWh)` pairs to `(utc_start, dollars)` pairs.

### Config flow

The config flow (`config_flow.py`) collects tariff rates in the `account` step and
stores them in the config entry. A `reconfigure` step lets users update credentials
(email/password) and tariff rates without removing the integration. If email or password
changes, the new credentials are validated against the Nectr API before saving.

### Strings

`strings.json` and `translations/en.json` are manually kept in sync — there is no
generation script (unlike main hass-core). Edit both files together whenever adding or
changing UI text.

### Integration setup

`async_setup_entry` backgrounds the initial refresh with
`hass.async_create_task(coordinator.async_refresh())` so the config dialog closes
immediately. Do not revert to `async_config_entry_first_refresh()` — it blocks the UI
for the full backfill duration.

### Coordinator data

The coordinator returns `DATA_LAST_IMPORTED_DATE`, `DATA_LAST_DAY_TOTAL`, and
`DATA_LAST_DAY_COST` in its `data` dict and persists them to storage. Sensors handle
`None` data (before the first refresh completes). Cost backfill runs automatically on
the first refresh when consumption stats exist but cost stats do not.

### Sensor units

`SensorDeviceClass.MONETARY` requires a runtime currency unit that can't be set
statically in `SensorEntityDescription`. Override `native_unit_of_measurement` as a
property on the entity class returning `self.hass.config.currency`.

## Credentials

The local CLI reads `NECTR_EMAIL` and `NECTR_PASSWORD` from the environment.
`bin/run-day-usage.sh` is a local-only credential wrapper and is ignored by
Git. Never add it, live credentials, or newly captured bearer tokens to source
files, fixtures, test output, or commits.
