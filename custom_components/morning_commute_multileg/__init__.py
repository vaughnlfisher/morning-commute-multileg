"""Morning Commute Multileg integration."""
from __future__ import annotations

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

    # Schedule HSP leg2 history fetch independently — runs hourly
    # First fetch is delayed 30 seconds to let HA fully settle after startup
    async def _fetch_hsp_now(_now=None) -> None:
        """Fetch HSP leg2 history and store in coordinator."""
        try:
            result = await coordinator._fetch_leg2_history()
            if result:
                _LOGGER.warning(
                    "HSP leg2 scheduled fetch: 7-day %.1f%%, 30-day %.1f%%",
                    result.get("on_time_pct_7day") or 0,
                    result.get("on_time_pct_30day") or 0,
                )
                coordinator._leg2_history = result
                coordinator.async_set_updated_data(coordinator.data)
        except Exception as err:
            _LOGGER.warning("HSP scheduled fetch error: %s", err)

    # Fire once after 30s, then every hour
    async def _delayed_first_fetch(event=None) -> None:
        await _fetch_hsp_now()

    hass.loop.call_later(30, hass.async_create_task, _delayed_first_fetch())

    cancel_interval = async_track_time_interval(hass, _fetch_hsp_now, HSP_INTERVAL)
    entry.async_on_unload(cancel_interval)

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
