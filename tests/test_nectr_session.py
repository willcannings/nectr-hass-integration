import unittest
from datetime import date
from unittest.mock import patch

from nectr_session import NectrSession


class FakeResponse:
    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict:
        return {
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
    async def test_get_hourly_data_sends_har_compatible_graphql_request(self):
        session = NectrSession(account_number="A-TEST")
        session._token = "access-token"

        with patch("nectr_session.httpx.AsyncClient", FakeAsyncClient):
            result = await session.get_hourly_data(date(2026, 5, 12))

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
