import sys
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

sys.path.insert(
    0, str(Path(__file__).resolve().parent.parent / "custom_components" / "nectr")
)

from nectr_session import Account, NectrSession  # noqa: E402


class FakeResponse:
    response_data = {}

    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict:
        return self.response_data


class FakeAsyncClient:
    last_request = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        return None

    async def post(self, url, **kwargs):
        type(self).last_request = (url, kwargs)
        return FakeResponse()


class NectrSessionTests(unittest.IsolatedAsyncioTestCase):
    async def test_get_accounts_sends_har_compatible_request_and_maps_accounts(self):
        FakeResponse.response_data = {
            "data": {
                "userBrief": {
                    "message": "",
                    "accounts": [
                        {
                            "number": "A-FIRST",
                            "status": "ACTIVE",
                            "address": "1 Example Street",
                            "state": "NSW",
                        },
                        {
                            "number": "A-SECOND",
                            "status": "CLOSED",
                            "address": "2 Example Street",
                            "state": "VIC",
                        },
                    ],
                }
            }
        }
        session = NectrSession()
        session._token = "access-token"

        with patch("nectr_session.httpx.AsyncClient", FakeAsyncClient):
            accounts = await session.get_accounts()

        url, request = FakeAsyncClient.last_request
        payload = request["json"]

        self.assertEqual(url, "https://mobile.nectr.com.au/graphql")
        self.assertEqual(request["headers"]["authorization"], "bearer access-token")
        self.assertEqual(payload["operationName"], "getUserBrief")
        self.assertEqual(payload["variables"], {})
        self.assertIn("query getUserBrief", payload["query"])
        self.assertIn("accounts {", payload["query"])
        self.assertEqual(
            accounts,
            [
                Account(
                    number="A-FIRST",
                    status="ACTIVE",
                    address="1 Example Street",
                    state="NSW",
                ),
                Account(
                    number="A-SECOND",
                    status="CLOSED",
                    address="2 Example Street",
                    state="VIC",
                ),
            ],
        )

    async def test_get_accounts_requires_authentication(self):
        session = NectrSession()

        self.assertEqual(await session.get_accounts(), [])

    async def test_get_hourly_data_sends_har_compatible_graphql_request(self):
        FakeResponse.response_data = {
            "data": {
                "getUsageInfo": {
                    "message": "",
                    "allUsage": [
                        {"period": "23:00", "gridUsage": 0.5},
                        {"period": "0:00", "gridUsage": 0.36},
                    ],
                }
            }
        }
        session = NectrSession()
        session._token = "access-token"

        with patch("nectr_session.httpx.AsyncClient", FakeAsyncClient):
            result = await session.get_hourly_data("A-TEST", date(2026, 5, 12))

        url, request = FakeAsyncClient.last_request
        payload = request["json"]
        query = payload["query"]

        self.assertEqual(url, "https://mobile.nectr.com.au/graphql")
        self.assertEqual(request["headers"]["authorization"], "bearer access-token")
        self.assertEqual(payload["operationName"], "getUsageInfo")
        self.assertEqual(
            payload["variables"],
            {
                "isSmartMeterUser": True,
                "accountNumber": "A-TEST",
                "pageNumber": 1,
                "granularity": "HOURLY",
                "toDate": "13/05/2026",
                "fromDate": "12/05/2026",
            },
        )
        self.assertNotIn("\n                    typename", query)
        self.assertEqual(query.count("__typename"), 7)
        self.assertTrue(result.success)
        self.assertEqual(result.hours, [23, 0])
        self.assertEqual(result.usage, [0.5, 0.36])


if __name__ == "__main__":
    unittest.main()
