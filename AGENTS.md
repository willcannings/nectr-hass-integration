# Repository Guide

## Purpose

This repository is a Home Assistant integration for Nectr electricity usage, packaged
under `custom_components/nectr/`. The API layer is
`custom_components/nectr/nectr_session.py`; it is kept independent of Home Assistant so
it can be exercised by `bin/day-usage.py` and the tests. The integration imports hourly
usage into the recorder as long-term external statistics for the Energy dashboard.

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

## Credentials

The local CLI reads `NECTR_EMAIL` and `NECTR_PASSWORD` from the environment.
`bin/run-day-usage.sh` is a local-only credential wrapper and is ignored by
Git. Never add it, live credentials, or newly captured bearer tokens to source
files, fixtures, test output, or commits.
