"""
nectr API Client for Home Assistant Integration
Provides async methods to authenticate and fetch hourly electricity usage data
"""

from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import date, timedelta
from typing import AsyncIterator, Optional
import httpx


@dataclass
class Account:
    """Nectr account available to the authenticated user."""

    number: str
    status: str
    address: str
    state: str


@dataclass
class HourlyDataResponse:
    """Response object for hourly electricity usage data"""
    success: bool
    message: str
    is_complete: bool
    day: date
    usage: list[Optional[float]]
    hours: list[int]


class NectrSession:
    """
    Async session for interacting with the nectr GraphQL API.

    Usage:
        session = NectrSession()
        if await session.login("email@example.com", "password"):
            accounts = await session.get_accounts()
            if accounts:
                data = await session.get_hourly_data(
                    accounts[0].number,
                    date(2025, 11, 5),
                )
    """

    BASE_URL = "https://mobile.nectr.com.au/graphql"

    def __init__(self, client: Optional[httpx.AsyncClient] = None):
        """
        Create a session.

        Args:
            client: Optional shared httpx.AsyncClient (e.g. Home Assistant's). When
                provided it is reused for every request and never closed by this
                session. When omitted, a short-lived client is created per request,
                preserving the original standalone behaviour used by the CLI/tests.
        """
        self._token: Optional[str] = None
        self._refresh_token: Optional[str] = None
        self._client = client

    @asynccontextmanager
    async def _http_client(self) -> AsyncIterator[httpx.AsyncClient]:
        """Yield an httpx client, reusing the injected one or creating a transient one."""
        # Reuse an injected client without closing it (its owner manages its lifecycle).
        if self._client is not None:
            yield self._client
        else:
            async with httpx.AsyncClient() as client:
                yield client

    async def login(self, email: str, password: str) -> bool:
        """
        Authenticate with nectr and store the access tokens.

        Args:
            email: Your nectr account email
            password: Your nectr account password

        Returns:
            True if login successful, False otherwise
        """
        query = """
        mutation emailAuthenticate($email: String!, $password: String!) {
            emailAuthenticate(email: $email, password: $password) {
                token
                refreshToken
                __typename
            }
        }
        """

        headers = {
            "x-client-type": "web",
            "authorization": "bearer undefined",
            "app-version": "2.9.0",
            "Content-Type": "application/json",
        }

        payload = {
            "operationName": "emailAuthenticate",
            "variables": {
                "email": email,
                "password": password,
            },
            "query": query,
        }

        try:
            async with self._http_client() as client:
                response = await client.post(
                    self.BASE_URL,
                    json=payload,
                    headers=headers,
                    timeout=30.0,
                )
                response.raise_for_status()

                data = response.json()

                # Check if authentication was successful
                if "data" in data and "emailAuthenticate" in data["data"]:
                    auth_data = data["data"]["emailAuthenticate"]
                    self._token = auth_data.get("token")
                    self._refresh_token = auth_data.get("refreshToken")
                    return self._token is not None

                return False

        except (httpx.HTTPError, KeyError, ValueError) as e:
            # Log the error in production - for now just return False
            print(f"Login failed: {e}")
            return False

    async def get_accounts(self) -> list[Account]:
        """
        Fetch the accounts available to the authenticated user.

        Returns:
            A list of Account objects, or an empty list if the request fails.

        Note:
            Requires a successful login() call first to obtain an auth token.
        """
        if not self._token:
            return []

        query = """
        query getUserBrief {
            userBrief {
                id
                fullName
                firstName
                lastName
                email
                mobile
                dateOfBirth
                accounts {
                    lnspId
                    number
                    status
                    address
                    state
                    supplyStatus
                    __typename
                }
                message
                __typename
            }
        }
        """

        headers = {
            "x-client-type": "web",
            "authorization": f"bearer {self._token}",
            "app-version": "2.9.0",
            "Content-Type": "application/json",
        }

        payload = {
            "operationName": "getUserBrief",
            "variables": {},
            "query": query,
        }

        try:
            async with self._http_client() as client:
                response = await client.post(
                    self.BASE_URL,
                    json=payload,
                    headers=headers,
                    timeout=30.0,
                )
                response.raise_for_status()

                data = response.json()
                user_brief = data["data"]["userBrief"]
                if not user_brief or user_brief.get("message"):
                    return []

                return [
                    Account(
                        number=account["number"],
                        status=account["status"],
                        address=account["address"],
                        state=account["state"],
                    )
                    for account in user_brief.get("accounts", [])
                ]

        except (AttributeError, httpx.HTTPError, KeyError, TypeError, ValueError):
            return []

    async def get_hourly_data(
        self,
        account_number: str,
        day: date,
    ) -> HourlyDataResponse:
        """
        Fetch hourly electricity usage data for an account on a specific day.

        Args:
            account_number: The account number returned by get_accounts().
            day: The date to fetch data for

        Returns:
            HourlyDataResponse object containing the usage data

        Note:
            Requires a successful login() call first to obtain auth token.
            The response is_complete flag is True only when all 24 hours have
            data entries (even if some values are None/0).
        """
        if not self._token:
            return HourlyDataResponse(
                success=False,
                message="Not authenticated. Call login() first.",
                is_complete=False,
                day=day,
                usage=[],
                hours=[],
            )

        # Format dates as DD/MM/YYYY
        from_date = day.strftime("%d/%m/%Y")
        # toDate is the next day (exclusive range)
        to_date = (day + timedelta(days=1)).strftime("%d/%m/%Y")

        query = """
        query getUsageInfo($accountNumber: String!, $isSmartMeterUser: Boolean!, $pageNumber: Int!, $granularity: GRANUALRITY, $fromDate: String!, $toDate: String!) {
            getUsageInfo(
                accountNumber: $accountNumber
                isSmartMeterUser: $isSmartMeterUser
                pageNumber: $pageNumber
                granularity: $granularity
                fromDate: $fromDate
                toDate: $toDate
            ) {
                secondaryHeader
                primaryHeader
                pageNumber
                message
                currentEstimates {
                    cost
                    usage
                    toolTip
                    __typename
                }
                allUsage {
                    controlLoadCost
                    controlLoadUsage
                    exportCost
                    exportUsage
                    gridUsage
                    gridCost
                    fromDate
                    toDate
                    issuedDate
                    period
                    __typename
                }
                gridConsumption {
                    title
                    toolTip
                    value
                    __typename
                }
                exportGridConsumption {
                    title
                    toolTip
                    value
                    __typename
                }
                controlledLoadConsumption {
                    title
                    toolTip
                    value
                    __typename
                }
                billProjection {
                    title
                    toolTip
                    value
                    __typename
                }
                fromDate
                toDate
                unit
                hasNextPage
                __typename
            }
        }
        """

        headers = {
            "x-client-type": "web",
            "authorization": f"bearer {self._token}",
            "app-version": "2.9.0",
            "Content-Type": "application/json",
        }

        payload = {
            "operationName": "getUsageInfo",
            "variables": {
                "isSmartMeterUser": True,
                "accountNumber": account_number,
                "pageNumber": 1,
                "granularity": "HOURLY",
                "toDate": to_date,
                "fromDate": from_date,
            },
            "query": query,
        }

        try:
            async with self._http_client() as client:
                response = await client.post(
                    self.BASE_URL,
                    json=payload,
                    headers=headers,
                    timeout=30.0,
                )
                response.raise_for_status()

                data = response.json()

                if "data" not in data or "getUsageInfo" not in data["data"]:
                    return HourlyDataResponse(
                        success=False,
                        message="Invalid API response structure",
                        is_complete=False,
                        day=day,
                        usage=[],
                        hours=[],
                    )

                usage_info = data["data"]["getUsageInfo"]

                # Check for error message (indicates no data available)
                error_message = usage_info.get("message", "")
                if error_message:
                    return HourlyDataResponse(
                        success=False,
                        message=error_message,
                        is_complete=False,
                        day=day,
                        usage=[],
                        hours=[],
                    )

                # Parse the hourly usage data
                all_usage = usage_info.get("allUsage", [])

                # Extract hours and usage values
                # Note: Data comes in reverse chronological order (23:00 to 0:00)
                hours = []
                usage = []

                for item in all_usage:
                    period = item.get("period", "")
                    grid_usage = item.get("gridUsage")

                    # Parse hour from period string (e.g., "23:00" -> 23)
                    try:
                        hour = int(period.split(":")[0])
                        hours.append(hour)
                        usage.append(grid_usage)
                    except (ValueError, IndexError):
                        # Skip malformed period entries
                        continue

                # Check if we have a complete day (all 24 hours)
                is_complete = len(hours) == 24

                return HourlyDataResponse(
                    success=True,
                    message="",
                    is_complete=is_complete,
                    day=day,
                    usage=usage,
                    hours=hours,
                )

        except (httpx.HTTPError, KeyError, ValueError) as e:
            return HourlyDataResponse(
                success=False,
                message=f"Request failed: {str(e)}",
                is_complete=False,
                day=day,
                usage=[],
                hours=[],
            )
