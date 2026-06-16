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
    CONF_PASSWORD,
    DEFAULT_DAYS_TO_LOAD,
    DOMAIN,
    MAX_DAYS_TO_LOAD,
    MIN_DAYS_TO_LOAD,
)
from .nectr_session import Account, NectrSession

_LOGGER = logging.getLogger(__name__)

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
            }
        )
        return self.async_show_form(step_id="account", data_schema=schema)
