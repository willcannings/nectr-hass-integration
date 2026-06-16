"""The Nectr electricity usage integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .coordinator import NectrUpdateCoordinator

PLATFORMS: list[Platform] = [Platform.SENSOR]

type NectrConfigEntry = ConfigEntry[NectrUpdateCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: NectrConfigEntry) -> bool:
    """Set up Nectr from a config entry."""
    coordinator = NectrUpdateCoordinator(hass, entry)
    await coordinator.async_load_restored()

    # The first refresh performs the immediate one-time backfill of prior days; every
    # subsequent (3-hourly) refresh just imports newly-available days.
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: NectrConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
