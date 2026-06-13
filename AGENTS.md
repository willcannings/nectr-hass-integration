# Repository Guide

## Purpose

This repository is being developed into a Home Assistant integration for Nectr
electricity usage. The current API layer is `nectr_session.py`.

## API Reference

- Read `api-docs/API.md` for the API overview.
- Treat `api-docs/login.har` and `api-docs/day-usage.har` as the source of truth
  for GraphQL operation names, variables, fields, headers, and date formats.
- The API endpoint is `https://mobile.nectr.com.au/graphql`.
- Authenticate before requesting usage. Send the returned access token as
  `Authorization: bearer <token>`.
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

The local CLI reads `NECTR_ACCOUNT_NUMBER`, `NECTR_EMAIL`, and `NECTR_PASSWORD`
from the environment. `bin/run-day-usage.sh` is a local-only credential wrapper
and is ignored by Git. Never add it, live credentials, or newly captured bearer
tokens to source files, fixtures, test output, or commits.
