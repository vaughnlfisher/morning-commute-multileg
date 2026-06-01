"""Coordinator for Morning Commute Multileg - uses Huxley2/Darwin for 2-hour leg 2 window."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    SOUTHBOUND_TERMINI,
    DOMAIN,
    LEG1_PREFIX,
    LEG2_STATION,
    LEG2_WALK_MINS,
    NUM_TRAINS,
    SCAN_INTERVAL_PEAK,
    SCAN_INTERVAL_OFFPEAK,
    SCAN_INTERVAL_NIGHT,
    DARWIN_TOKEN,
)

_LOGGER = logging.getLogger(__name__)

HUXLEY_URL = (
    "https://huxley2.azurewebsites.net/departures/CTK/{rows}"
    "?timeWindow=120&accessToken={token}"
)
HUXLEY_ROWS = 50

# Whitelist of genuine southbound termini from City Thameslink
# Trains going south through Blackfriars → Elephant & Castle → beyond
SOUTHBOUND_TERMINI = {
    "sutton", "wimbledon", "brighton", "horsham", "gatwick",
    "gatwick airport", "three bridges", "rainham",
    "elephant", "elephant & castle", "blackfriars",
    "tulse hill", "crystal palace", "norwood junction",
    "east croydon", "purley", "redhill", "reigate",
    "epsom", "dorking", "crawley", "littlehampton",
    "worthing", "shoreham", "hove", "haywards heath",
}


def _get_scan_interval() -> timedelta:
    hour = datetime.now().hour
    if 6 <= hour < 10 or 16 <= hour < 20:
        return timedelta(seconds=SCAN_INTERVAL_PEAK)
    if 23 <= hour or hour < 5:
        return timedelta(seconds=SCAN_INTERVAL_NIGHT)
    return timedelta(seconds=SCAN_INTERVAL_OFFPEAK)


def _attr(hass: HomeAssistant, entity_id: str, attr: str):
    state = hass.states.get(entity_id)
    return state.attributes.get(attr) if state else None


def _state(hass: HomeAssistant, entity_id: str) -> str | None:
    state = hass.states.get(entity_id)
    return state.state if state else None


def _svc_dest(svc: dict) -> str:
    dest = svc.get("destination") or []
    if isinstance(dest, list) and dest:
        return dest[0].get("locationName", "")
    return str(dest)


def _is_southbound(svc: dict) -> bool:
    dest = _svc_dest(svc).lower()
    return any(kw in dest for kw in SOUTHBOUND_TERMINI)


def _svc_time(svc: dict) -> datetime | None:
    """Return best departure datetime from a Huxley service."""
    now = datetime.now().astimezone()
    # etd is expected, std is scheduled
    for key in ("etd", "std"):
        val = (svc.get(key) or "").strip()
        if val in ("", "Delayed", "Cancelled"):
            continue
        if val == "On time":
            # fall through to std
            continue
        try:
            h, m = map(int, val.split(":"))
            dt = now.replace(hour=h, minute=m, second=0, microsecond=0)
            if (dt - now).total_seconds() < -3600:
                dt += timedelta(days=1)
            return dt
        except (ValueError, TypeError):
            continue
    # etd = "On time" → use std
    std = (svc.get("std") or "").strip()
    if std:
        try:
            h, m = map(int, std.split(":"))
            dt = now.replace(hour=h, minute=m, second=0, microsecond=0)
            if (dt - now).total_seconds() < -3600:
                dt += timedelta(days=1)
            return dt
        except (ValueError, TypeError):
            pass
    return None


def _parse_hhmm(hhmm: str, ref: datetime) -> datetime | None:
    try:
        h, m = map(int, hhmm.split(":"))
        dt = ref.replace(hour=h, minute=m, second=0, microsecond=0)
        if (ref - dt).total_seconds() > 6 * 3600:
            dt += timedelta(days=1)
        return dt
    except (ValueError, TypeError, AttributeError):
        return None


def _build_leg2(southbound: list[dict], scheduled_arrival_str: str | None) -> dict:
    """Build leg2 attributes for one train using its scheduled Farringdon arrival."""
    result = {
        "leg2_station": LEG2_STATION,
        "leg2_walk_mins": LEG2_WALK_MINS,
        "leg2_next_southbound_departure": None,
        "leg2_next_southbound_destination": None,
        "leg2_southbound_departures": [],
        "leg2_earliest_after_arrival": None,
        "leg2_earliest_destination": None,
        "leg2_connection_mins": None,
    }

    if not southbound:
        return result

    now = datetime.now().astimezone()

    # Upcoming southbound list
    upcoming = []
    for svc in southbound:
        dt = _svc_time(svc)
        if dt and dt >= now:
            upcoming.append((dt, _svc_dest(svc), svc))

    if upcoming:
        first_dt, first_dest, _ = upcoming[0]
        result["leg2_next_southbound_departure"] = first_dt.strftime("%H:%M")
        result["leg2_next_southbound_destination"] = first_dest
        result["leg2_southbound_departures"] = [
            f"{dt.strftime('%H:%M')} → {dest}" for dt, dest, _ in upcoming[:5]
        ]

    # Per-train connection
    if not scheduled_arrival_str:
        return result

    arr_dt = _parse_hhmm(scheduled_arrival_str, now)
    if not arr_dt:
        return result

    earliest_board = arr_dt + timedelta(minutes=LEG2_WALK_MINS)

    for dep_dt, dest, svc in upcoming:
        if dep_dt >= earliest_board:
            wait = max(0, round((dep_dt - arr_dt).total_seconds() / 60) - LEG2_WALK_MINS)
            result["leg2_earliest_after_arrival"] = f"{dep_dt.strftime('%H:%M')} → {dest}"
            result["leg2_earliest_destination"] = dest
            result["leg2_connection_mins"] = wait
            return result

    _LOGGER.warning(
        "No southbound CTK service found for Farringdon arrival %s (board %s) — "
        "Huxley returned %d southbound services",
        scheduled_arrival_str,
        earliest_board.strftime("%H:%M"),
        len(upcoming),
    )
    return result


class MorningCommuteCoordinator(DataUpdateCoordinator):
    """Reads leg 1 from my_rail_commute sensors; leg 2 from Huxley2/Darwin (2-hour window)."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass, _LOGGER, name=DOMAIN, update_interval=_get_scan_interval()
        )
        self.entry = entry

    async def _fetch_southbound(self) -> list[dict]:
        """Fetch CTK departures from Huxley2, return southbound only."""
        url = HUXLEY_URL.format(rows=HUXLEY_ROWS, token=DARWIN_TOKEN)
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url, timeout=aiohttp.ClientTimeout(total=12)
                ) as resp:
                    if resp.status != 200:
                        _LOGGER.warning("Huxley HTTP %s for %s", resp.status, url)
                        return []
                    data = await resp.json(content_type=None)
                    services = data.get("trainServices") or []
                    sb = [s for s in services if _is_southbound(s)]
                    _LOGGER.debug(
                        "Huxley CTK: %d total, %d southbound", len(services), len(sb)
                    )
                    return sb
        except Exception as err:
            _LOGGER.warning("Huxley fetch error: %s", err)
            return []

    async def _async_update_data(self) -> dict:
        self.update_interval = _get_scan_interval()

        try:
            southbound = await self._fetch_southbound()
            data = {}

            s_id  = f"sensor.{LEG1_PREFIX}_summary"
            st_id = f"sensor.{LEG1_PREFIX}_status"
            nt_id = f"sensor.{LEG1_PREFIX}_next_train"
            hr_id = f"sensor.{LEG1_PREFIX}_historical_reliability"
            hd_id = f"sensor.{LEG1_PREFIX}_historical_delays"
            dis_id = f"binary_sensor.{LEG1_PREFIX}_has_disruption"

            next_arr = _attr(self.hass, nt_id, "scheduled_arrival")

            # Summary
            data["summary"] = {
                "state": _state(self.hass, s_id),
                "origin": _attr(self.hass, s_id, "origin"),
                "origin_name": _attr(self.hass, s_id, "origin_name"),
                "destination": _attr(self.hass, s_id, "destination"),
                "destination_name": _attr(self.hass, s_id, "destination_name"),
                "time_window": _attr(self.hass, s_id, "time_window"),
                "services_requested": _attr(self.hass, s_id, "services_requested"),
                "services_tracked": _attr(self.hass, s_id, "services_tracked"),
                "total_services_found": _attr(self.hass, s_id, "total_services_found"),
                "on_time_count": _attr(self.hass, s_id, "on_time_count"),
                "delayed_count": _attr(self.hass, s_id, "delayed_count"),
                "cancelled_count": _attr(self.hass, s_id, "cancelled_count"),
                "last_updated": _attr(self.hass, s_id, "last_updated"),
                "next_update": _attr(self.hass, s_id, "next_update"),
                "all_trains": _attr(self.hass, s_id, "all_trains"),
                "on_time_pct_today": _attr(self.hass, s_id, "on_time_pct_today"),
                "on_time_pct_7day": _attr(self.hass, s_id, "on_time_pct_7day"),
                "on_time_pct_30day": _attr(self.hass, s_id, "on_time_pct_30day"),
                "avg_delay_7day": _attr(self.hass, s_id, "avg_delay_7day"),
                "worst_day": _attr(self.hass, s_id, "worst_day"),
                "best_day": _attr(self.hass, s_id, "best_day"),
                "reverse_on_time_pct_today": _attr(self.hass, s_id, "reverse_on_time_pct_today"),
                "reverse_on_time_pct_7day": _attr(self.hass, s_id, "reverse_on_time_pct_7day"),
                "reverse_on_time_pct_30day": _attr(self.hass, s_id, "reverse_on_time_pct_30day"),
                "reverse_avg_delay_7day": _attr(self.hass, s_id, "reverse_avg_delay_7day"),
                "reverse_worst_day": _attr(self.hass, s_id, "reverse_worst_day"),
                "reverse_best_day": _attr(self.hass, s_id, "reverse_best_day"),
            }
            data["summary"].update(_build_leg2(southbound, next_arr))

            # Status
            data["status"] = {
                "state": _state(self.hass, st_id),
                "total_trains": _attr(self.hass, st_id, "total_trains"),
                "on_time_count": _attr(self.hass, st_id, "on_time_count"),
                "minor_delays_count": _attr(self.hass, st_id, "minor_delays_count"),
                "major_delays_count": _attr(self.hass, st_id, "major_delays_count"),
                "cancelled_count": _attr(self.hass, st_id, "cancelled_count"),
                "max_delay_minutes": _attr(self.hass, st_id, "max_delay_minutes"),
                "disruption_threshold_met": _attr(self.hass, st_id, "disruption_threshold_met"),
                "origin": _attr(self.hass, st_id, "origin"),
                "origin_name": _attr(self.hass, st_id, "origin_name"),
                "destination": _attr(self.hass, st_id, "destination"),
                "destination_name": _attr(self.hass, st_id, "destination_name"),
                "last_updated": _attr(self.hass, st_id, "last_updated"),
            }
            data["status"].update(_build_leg2(southbound, next_arr))

            # Trains 1–10
            for i in range(1, NUM_TRAINS + 1):
                t_id = f"sensor.{LEG1_PREFIX}_train_{i}"
                t_arr = _attr(self.hass, t_id, "scheduled_arrival")
                entry = {
                    "state": _state(self.hass, t_id),
                    "train_number": i,
                    "total_trains": _attr(self.hass, t_id, "total_trains"),
                    "departure_time": _attr(self.hass, t_id, "departure_time"),
                    "scheduled_departure": _attr(self.hass, t_id, "scheduled_departure"),
                    "expected_departure": _attr(self.hass, t_id, "expected_departure"),
                    "platform": _attr(self.hass, t_id, "platform"),
                    "platform_changed": _attr(self.hass, t_id, "platform_changed"),
                    "previous_platform": _attr(self.hass, t_id, "previous_platform"),
                    "operator": _attr(self.hass, t_id, "operator"),
                    "service_id": _attr(self.hass, t_id, "service_id"),
                    "status": _attr(self.hass, t_id, "status"),
                    "delay_minutes": _attr(self.hass, t_id, "delay_minutes"),
                    "is_cancelled": _attr(self.hass, t_id, "is_cancelled"),
                    "calling_points": _attr(self.hass, t_id, "calling_points"),
                    "scheduled_arrival": t_arr,
                    "estimated_arrival": _attr(self.hass, t_id, "estimated_arrival"),
                    "last_updated": _attr(self.hass, t_id, "last_updated"),
                    "cancellation_reason": _attr(self.hass, t_id, "cancellation_reason"),
                    "delay_reason": _attr(self.hass, t_id, "delay_reason"),
                }
                entry.update(_build_leg2(southbound, t_arr))
                data[f"train_{i}"] = entry

            data["next_train"] = dict(data["train_1"])

            # Historical
            data["historical_reliability"] = {
                "state": _state(self.hass, hr_id),
                "on_time_pct_today": _attr(self.hass, hr_id, "on_time_pct_today"),
                "on_time_pct_7day": _attr(self.hass, hr_id, "on_time_pct_7day"),
                "on_time_pct_30day": _attr(self.hass, hr_id, "on_time_pct_30day"),
                "on_time_count_today": _attr(self.hass, hr_id, "on_time_count_today"),
                "delayed_count_today": _attr(self.hass, hr_id, "delayed_count_today"),
                "cancelled_count_today": _attr(self.hass, hr_id, "cancelled_count_today"),
                "total_observations_today": _attr(self.hass, hr_id, "total_observations_today"),
                "days_with_data_7day": _attr(self.hass, hr_id, "days_with_data_7day"),
                "days_with_data_30day": _attr(self.hass, hr_id, "days_with_data_30day"),
                "daily_breakdown": _attr(self.hass, hr_id, "daily_breakdown"),
            }
            data["historical_delays"] = {
                "state": _state(self.hass, hd_id),
                "avg_delay_today": _attr(self.hass, hd_id, "avg_delay_today"),
                "avg_delay_7day": _attr(self.hass, hd_id, "avg_delay_7day"),
                "worst_day": _attr(self.hass, hd_id, "worst_day"),
                "best_day": _attr(self.hass, hd_id, "best_day"),
                "days_with_data_7day": _attr(self.hass, hd_id, "days_with_data_7day"),
            }
            data["has_disruption"] = {
                "state": _state(self.hass, dis_id),
                "current_status": _attr(self.hass, dis_id, "current_status"),
                "cancelled_count": _attr(self.hass, dis_id, "cancelled_count"),
                "delayed_count": _attr(self.hass, dis_id, "delayed_count"),
                "max_delay_minutes": _attr(self.hass, dis_id, "max_delay_minutes"),
                "disruption_reasons": _attr(self.hass, dis_id, "disruption_reasons"),
                "last_checked": _attr(self.hass, dis_id, "last_checked"),
            }

            return data

        except Exception as err:
            raise UpdateFailed(f"Error updating commute data: {err}") from err
