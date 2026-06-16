"""Diagnostic sensors for the Nectr integration."""

from __future__ import annotations

from datetime import date

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.const import EntityCategory, UnitOfEnergy
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import NectrConfigEntry
from .const import DATA_LAST_DAY_TOTAL, DATA_LAST_IMPORTED_DATE, DOMAIN
from .coordinator import NectrUpdateCoordinator

# Diagnostic sensors. Neither sets a state_class: these are status read-outs, not values
# we want the recorder to turn into their own long-term statistics (the energy series is
# imported separately as an external statistic).
SENSORS: tuple[SensorEntityDescription, ...] = (
    SensorEntityDescription(
        key=DATA_LAST_IMPORTED_DATE,
        translation_key="last_imported_date",
        device_class=SensorDeviceClass.DATE,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        key=DATA_LAST_DAY_TOTAL,
        translation_key="last_day_usage",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: NectrConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the Nectr diagnostic sensors."""
    coordinator = entry.runtime_data
    async_add_entities(
        NectrDiagnosticSensor(coordinator, entry, description)
        for description in SENSORS
    )


class NectrDiagnosticSensor(CoordinatorEntity[NectrUpdateCoordinator], SensorEntity):
    """A coordinator-backed diagnostic sensor."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: NectrUpdateCoordinator,
        entry: NectrConfigEntry,
        description: SensorEntityDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="Nectr",
        )

    @property
    def native_value(self) -> date | float | None:
        """Return the current diagnostic value from coordinator data."""
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get(self.entity_description.key)
