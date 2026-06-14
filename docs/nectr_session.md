# NectrSession Quick Reference

`NectrSession` is an asynchronous Python client for Nectr's private GraphQL API.
It authenticates with an email/password, discovers the user's Nectr accounts,
and retrieves one day of hourly electricity usage for an account.

```python
from datetime import date

from nectr_session import NectrSession


async def fetch_usage():
    session = NectrSession()

    if not await session.login("user@example.com", "password"):
        raise RuntimeError("Nectr login failed")

    accounts = await session.get_accounts()
    if not accounts:
        raise RuntimeError("No Nectr accounts found")

    account = accounts[0]
    result = await session.get_hourly_data(account.number, date(2026, 5, 12))
    if not result.success:
        raise RuntimeError(result.message)

    for hour, usage_kwh in zip(result.hours, result.usage):
        print(f"{hour:02d}:00: {usage_kwh} kWh")
```

## API

- `NectrSession()` creates a client.
- `await login(email, password) -> bool` authenticates and stores the bearer
  token internally.
- `await get_accounts() -> list[Account]` returns the authenticated user's
  accounts. Each `Account` has `number`, `status`, `address`, and `state`.
- `await get_hourly_data(account_number, day) -> HourlyDataResponse` retrieves
  hourly grid consumption for an account and date.

Call `login()` first, then `get_accounts()`, then request usage with an account's
`number`. `get_accounts()` returns an empty list if unavailable or unsuccessful.

`HourlyDataResponse` contains:

- `success`: whether the request and response processing succeeded.
- `message`: API or request error text when unsuccessful.
- `day`: the requested date.
- `hours`: hour numbers, usually returned in descending order (`23` to `0`).
- `usage`: corresponding grid usage values in kWh; values may be `None`.
- `is_complete`: `True` when 24 hourly entries were returned.

The client uses `httpx.AsyncClient`, catches HTTP/response errors, and reports
them through `False`, an empty account list, or `HourlyDataResponse` rather than
raising them.
