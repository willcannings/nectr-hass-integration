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

    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Backfill runs in the background so the config dialog closes immediately.
    # Sensors return None until the first refresh completes, which they handle.
    hass.async_create_task(coordinator.async_refresh())
    return True


async def async_unload_entry(hass: HomeAssistant, entry: NectrConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
