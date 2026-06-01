"""Sensor platform for Morning Commute Multileg."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, NUM_TRAINS
from .coordinator import MorningCommuteCoordinator

_LOGGER = logging.getLogger(__name__)

# Maps data key → (friendly name suffix, unit, icon)
SENSOR_DEFS: list[tuple[str, str, str | None, str]] = [
    ("summary",               "Summary",               None,    "mdi:train"),
    ("status",                "Status",                None,    "mdi:train"),
    ("next_train",            "Next Train",            None,    "mdi:train-car"),
    ("historical_reliability","Historical Reliability", "%",    "mdi:percent"),
    ("historical_delays",     "Historical Delays",     "min",   "mdi:clock-alert"),
] + [
    (f"train_{i}", f"Train {i}", None, "mdi:train")
    for i in range(1, NUM_TRAINS + 1)
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: MorningCommuteCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities = [
        MorningCommuteSensor(coordinator, key, name, unit, icon)
        for key, name, unit, icon in SENSOR_DEFS
    ]
    async_add_entities(entities)


class MorningCommuteSensor(CoordinatorEntity, SensorEntity):
    """A sensor that mirrors a my_rail_commute entity plus leg2 Thameslink data."""

    def __init__(
        self,
        coordinator: MorningCommuteCoordinator,
        data_key: str,
        name_suffix: str,
        unit: str | None,
        icon: str,
    ) -> None:
        super().__init__(coordinator)
        self._data_key = data_key
        self._attr_name = f"Morning Commute {name_suffix}"
        self._attr_unique_id = f"morning_commute_multileg_{data_key}"
        self._attr_native_unit_of_measurement = unit
        self._attr_icon = icon

    @property
    def _data(self) -> dict:
        return self.coordinator.data.get(self._data_key, {})

    @property
    def native_value(self) -> str | None:
        return self._data.get("state")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        # Return everything except 'state' key itself
        return {k: v for k, v in self._data.items() if k != "state"}

    @property
    def icon(self) -> str:
        """Dynamic icon matching my_rail_commute logic."""
        state = self.native_value
        if state == "Cancelled":
            return "mdi:alert-circle"
        if state in ("Delayed", "Major Delays", "Severe Disruption"):
            return "mdi:clock-alert"
        if state == "Minor Delays":
            return "mdi:train-variant"
        if self._data_key in ("historical_reliability", "historical_delays"):
            return self._attr_icon
        return self._attr_icon

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success and bool(self._data)
