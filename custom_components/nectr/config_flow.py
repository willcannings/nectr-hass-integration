"""Config flow for the Nectr integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers import selector
from homeassistant.helpers.httpx_client import get_async_client

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
    DEFAULT_DAYS_TO_LOAD,
    DEFAULT_PEAK_END_HOUR,
    DEFAULT_PEAK_START_HOUR,
    DOMAIN,
    MAX_DAYS_TO_LOAD,
    MAX_HOUR,
    MIN_DAYS_TO_LOAD,
    MIN_HOUR,
)
from .nectr_session import Account, NectrSession

_LOGGER = logging.getLogger(__name__)


# A tariff rate in cents/kWh. Allows fractional cents and is entered as a plain number
# box; the coordinator converts cents to dollars when building the cost statistic.
def _rate_selector() -> selector.NumberSelector:
    return selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=0,
            step=0.01,
            mode=selector.NumberSelectorMode.BOX,
            unit_of_measurement="cents/kWh",
        )
    )


# An hour-of-day (0-23) used to delimit the peak tariff window.
def _hour_selector() -> selector.NumberSelector:
    return selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=MIN_HOUR,
            max=MAX_HOUR,
            step=1,
            mode=selector.NumberSelectorMode.BOX,
            unit_of_measurement="h",
        )
    )


USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_EMAIL): selector.TextSelector(
            selector.TextSelectorConfig(type=selector.TextSelectorType.EMAIL)
        ),
        vol.Required(CONF_PASSWORD): selector.TextSelector(
            selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
        ),
    }
)


class NectrConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the Nectr config flow."""

    VERSION = 1

    def __init__(self) -> None:
        self._email: str = ""
        self._password: str = ""
        self._accounts: list[Account] = []

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Collect credentials, validate them, and load the user's accounts."""
        errors: dict[str, str] = {}

        if user_input is not None:
            email = user_input[CONF_EMAIL]
            password = user_input[CONF_PASSWORD]
            session = NectrSession(get_async_client(self.hass))

            try:
                logged_in = await session.login(email, password)
            except Exception:  # noqa: BLE001 - any failure here is a connection problem
                _LOGGER.exception("Error connecting to Nectr during setup")
                errors["base"] = "cannot_connect"
            else:
                if not logged_in:
                    errors["base"] = "invalid_auth"
                else:
                    accounts = await session.get_accounts()
                    if not accounts:
                        errors["base"] = "no_accounts"
                    else:
                        self._email = email
                        self._password = password
                        self._accounts = accounts
                        return await self.async_step_account()

        return self.async_show_form(
            step_id="user", data_schema=USER_SCHEMA, errors=errors
        )

    async def async_step_account(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Let the user pick an account and how many days of history to backfill."""
        if user_input is not None:
            account = next(
                acc
                for acc in self._accounts
                if acc.number == user_input[CONF_ACCOUNT_NUMBER]
            )

            await self.async_set_unique_id(account.number)
            self._abort_if_unique_id_configured()

            return self.async_create_entry(
                title=f"Nectr ({account.address})",
                data={
                    CONF_EMAIL: self._email,
                    CONF_PASSWORD: self._password,
                    CONF_ACCOUNT_NUMBER: account.number,
                    CONF_ACCOUNT_STATE: account.state,
                    CONF_ACCOUNT_ADDRESS: account.address,
                    CONF_DAYS_TO_LOAD: user_input[CONF_DAYS_TO_LOAD],
                    CONF_PEAK_RATE: user_input[CONF_PEAK_RATE],
                    CONF_OFFPEAK_RATE: user_input[CONF_OFFPEAK_RATE],
                    CONF_PEAK_START_HOUR: user_input[CONF_PEAK_START_HOUR],
                    CONF_PEAK_END_HOUR: user_input[CONF_PEAK_END_HOUR],
                },
            )

        account_options = [
            selector.SelectOptionDict(
                value=acc.number,
                label=f"{acc.number} — {acc.address} ({acc.state})",
            )
            for acc in self._accounts
        ]
        schema = vol.Schema(
            {
                vol.Required(CONF_ACCOUNT_NUMBER): selector.SelectSelector(
                    selector.SelectSelectorConfig(options=account_options)
                ),
                vol.Required(
                    CONF_DAYS_TO_LOAD, default=DEFAULT_DAYS_TO_LOAD
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=MIN_DAYS_TO_LOAD,
                        max=MAX_DAYS_TO_LOAD,
                        step=1,
                        mode=selector.NumberSelectorMode.BOX,
                        unit_of_measurement="days",
                    )
                ),
                vol.Required(CONF_PEAK_RATE): _rate_selector(),
                vol.Required(CONF_OFFPEAK_RATE): _rate_selector(),
                vol.Required(
                    CONF_PEAK_START_HOUR, default=DEFAULT_PEAK_START_HOUR
                ): _hour_selector(),
                vol.Required(
                    CONF_PEAK_END_HOUR, default=DEFAULT_PEAK_END_HOUR
                ): _hour_selector(),
            }
        )
        return self.async_show_form(step_id="account", data_schema=schema)

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Let an existing entry update credentials and/or tariff rates.

        Email is pre-filled with the current value; password is blank (leave empty to
        keep the existing password). If either credential field changes, the new
        credentials are validated against the Nectr API before saving.
        """
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}

        if user_input is not None:
            new_email = user_input[CONF_EMAIL]
            new_password = user_input.get(CONF_PASSWORD, "")
            current_email = entry.data[CONF_EMAIL]
            current_password = entry.data[CONF_PASSWORD]

            # Use the new password if provided, otherwise keep the existing one.
            final_password = new_password if new_password else current_password
            credentials_changed = new_email != current_email or bool(new_password)

            if credentials_changed:
                session = NectrSession(get_async_client(self.hass))
                try:
                    logged_in = await session.login(new_email, final_password)
                except Exception:  # noqa: BLE001
                    _LOGGER.exception("Error connecting to Nectr during reconfigure")
                    errors["base"] = "cannot_connect"
                else:
                    if not logged_in:
                        errors["base"] = "invalid_auth"

            if not errors:
                return self.async_update_reload_and_abort(
                    entry,
                    data_updates={
                        CONF_EMAIL: new_email,
                        CONF_PASSWORD: final_password,
                        CONF_PEAK_RATE: user_input[CONF_PEAK_RATE],
                        CONF_OFFPEAK_RATE: user_input[CONF_OFFPEAK_RATE],
                        CONF_PEAK_START_HOUR: user_input[CONF_PEAK_START_HOUR],
                        CONF_PEAK_END_HOUR: user_input[CONF_PEAK_END_HOUR],
                    },
                )

        # Pre-fill email with current value; password is always left blank for security.
        data = entry.data
        schema = vol.Schema(
            {
                vol.Required(CONF_EMAIL, default=data[CONF_EMAIL]): selector.TextSelector(
                    selector.TextSelectorConfig(type=selector.TextSelectorType.EMAIL)
                ),
                vol.Optional(CONF_PASSWORD): selector.TextSelector(
                    selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
                ),
                vol.Required(
                    CONF_PEAK_RATE, default=data.get(CONF_PEAK_RATE)
                ): _rate_selector(),
                vol.Required(
                    CONF_OFFPEAK_RATE, default=data.get(CONF_OFFPEAK_RATE)
                ): _rate_selector(),
                vol.Required(
                    CONF_PEAK_START_HOUR,
                    default=data.get(CONF_PEAK_START_HOUR, DEFAULT_PEAK_START_HOUR),
                ): _hour_selector(),
                vol.Required(
                    CONF_PEAK_END_HOUR,
                    default=data.get(CONF_PEAK_END_HOUR, DEFAULT_PEAK_END_HOUR),
                ): _hour_selector(),
            }
        )
        return self.async_show_form(
            step_id="reconfigure", data_schema=schema, errors=errors
        )
