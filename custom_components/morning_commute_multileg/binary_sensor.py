"""Binary sensor platform for Morning Commute Multileg."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import MorningCommuteCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: MorningCommuteCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([MorningCommuteDisruptionSensor(coordinator)])


class MorningCommuteDisruptionSensor(CoordinatorEntity, BinarySensorEntity):
    """Binary sensor: on when leg 1 has disruption."""

    def __init__(self, coordinator: MorningCommuteCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_name = "Morning Commute Has Disruption"
        self._attr_unique_id = "morning_commute_multileg_has_disruption"

    @property
    def _data(self) -> dict:
        return self.coordinator.data.get("has_disruption", {})

    @property
    def is_on(self) -> bool:
        return self._data.get("state") == "on"

    @property
    def icon(self) -> str:
        return "mdi:alert-circle" if self.is_on else "mdi:check-circle"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {k: v for k, v in self._data.items() if k != "state"}

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success and bool(self._data)
