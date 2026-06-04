"""Morning Commute Multileg integration."""
from __future__ import annotations

import asyncio
import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_track_time_interval

from .const import DOMAIN
from .coordinator import MorningCommuteCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor", "binary_sensor"]
HSP_INTERVAL = timedelta(hours=1)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Morning Commute Multileg from a config entry."""
    coordinator = MorningCommuteCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(async_update_options))

    async def _fetch_hsp(_now=None) -> None:
        """Fetch HSP leg2 history and push update."""
        try:
            result = await coordinator._fetch_leg2_history()
            if result and result.get("on_time_pct_7day") is not None:
                _LOGGER.warning(
                    "HSP leg2: 7-day %.1f%%, 30-day %.1f%%",
                    result["on_time_pct_7day"],
                    result.get("on_time_pct_30day") or 0,
                )
                coordinator._leg2_history = result
                if coordinator.data:
                    coordinator.data["leg2_historical_reliability"] = result
                    coordinator.async_set_updated_data(coordinator.data)
        except Exception as err:
            _LOGGER.warning("HSP fetch error: %s", err)

    # First fetch 30 seconds after setup completes
    async def _delayed_hsp():
        await asyncio.sleep(30)
        await _fetch_hsp()

    hass.async_create_task(_delayed_hsp())

    # Then repeat every hour
    cancel = async_track_time_interval(hass, _fetch_hsp, HSP_INTERVAL)
    entry.async_on_unload(cancel)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok


async def async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update."""
    await hass.config_entries.async_reload(entry.entry_id)
