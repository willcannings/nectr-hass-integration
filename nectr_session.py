"""
nectr API Client for Home Assistant Integration
Provides async methods to authenticate and fetch hourly electricity usage data
"""

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional
import httpx


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
        session = NectrSession(account_number="A-EXAMPLE")
        if await session.login("email@example.com", "password"):
            data = await session.get_hourly_data(date(2025, 11, 5))
            if data.success:
                print(f"Usage: {data.usage}")
    """

    BASE_URL = "https://mobile.nectr.com.au/graphql"

    def __init__(self, account_number: str):
        """
        Initialise the nectr session.

        Args:
            account_number: Your nectr account number (e.g., "A-EXAMPLE")
        """
        self.account_number = account_number
        self._token: Optional[str] = None
        self._refresh_token: Optional[str] = None

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
            async with httpx.AsyncClient() as client:
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

    async def get_hourly_data(self, day: date) -> HourlyDataResponse:
        """
        Fetch hourly electricity usage data for a specific day.

        Args:
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
                "accountNumber": self.account_number,
                "pageNumber": 1,
                "granularity": "HOURLY",
                "toDate": to_date,
                "fromDate": from_date,
            },
            "query": query,
        }

        try:
            async with httpx.AsyncClient() as client:
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
