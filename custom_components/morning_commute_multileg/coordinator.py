"""Coordinator for Morning Commute Multileg."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    DOMAIN,
    LEG1_PREFIX,
    LEG2_SENSOR,
    LEG2_STATION,
    LEG2_WALK_MINS,
    NUM_TRAINS,
    SCAN_INTERVAL_PEAK,
    SCAN_INTERVAL_OFFPEAK,
    SCAN_INTERVAL_NIGHT,
)

_LOGGER = logging.getLogger(__name__)


def _get_scan_interval() -> timedelta:
    """Return scan interval based on time of day, mirroring my_rail_commute logic."""
    hour = datetime.now().hour
    if 6 <= hour < 10 or 16 <= hour < 20:
        return timedelta(seconds=SCAN_INTERVAL_PEAK)
    if 23 <= hour or hour < 5:
        return timedelta(seconds=SCAN_INTERVAL_NIGHT)
    return timedelta(seconds=SCAN_INTERVAL_OFFPEAK)


def _attr(hass: HomeAssistant, entity_id: str, attr: str):
    """Safe attribute getter."""
    state = hass.states.get(entity_id)
    if state is None:
        return None
    return state.attributes.get(attr)


def _state(hass: HomeAssistant, entity_id: str) -> str | None:
    """Safe state getter."""
    state = hass.states.get(entity_id)
    return state.state if state else None


def _build_leg2(hass: HomeAssistant, scheduled_arrival_str: str | None) -> dict:
    """
    Build the leg2 dict from the TfL Thameslink sensor.

    leg2_next_departure       : HH:MM of the very next departure from City Thameslink
    leg2_next_destination     : destination of that departure
    leg2_northbound_departures: list of up to 5 northbound departures (designation '1')
    leg2_earliest_after_arrival: first northbound departure reachable after arriving at
                                 Farringdon + LEG2_WALK_MINS walk
    leg2_station              : 'City Thameslink'
    leg2_walk_mins            : walk minutes Farringdon → City Thameslink
    """
    result = {
        "leg2_station": LEG2_STATION,
        "leg2_walk_mins": LEG2_WALK_MINS,
        "leg2_next_departure": None,
        "leg2_next_destination": None,
        "leg2_northbound_departures": [],
        "leg2_earliest_after_arrival": None,
    }

    tfl_state = hass.states.get(LEG2_SENSOR)
    if tfl_state is None:
        return result

    departures = tfl_state.attributes.get("departures")
    if not departures:
        return result

    # Next departure (any direction)
    first = departures[0]
    try:
        first_dt = datetime.fromisoformat(first["expected"])
        result["leg2_next_departure"] = first_dt.astimezone().strftime("%H:%M")
        result["leg2_next_destination"] = (
            first.get("destination", "").replace(" Rail Station", "")
        )
    except (KeyError, ValueError, TypeError):
        pass

    # Northbound (designation == '1')
    northbound = []
    for dep in departures:
        try:
            if dep.get("line", {}).get("designation") == "1":
                dep_dt = datetime.fromisoformat(dep["expected"])
                dest = dep.get("destination", "").replace(" Rail Station", "")
                northbound.append(
                    f"{dep_dt.astimezone().strftime('%H:%M')} → {dest}"
                )
        except (KeyError, ValueError, TypeError):
            continue
    result["leg2_northbound_departures"] = northbound[:5]

    # Earliest reachable after arrival
    if scheduled_arrival_str:
        try:
            # scheduled_arrival is "HH:MM" – build a datetime for today
            now = datetime.now().astimezone()
            h, m = map(int, scheduled_arrival_str.split(":"))
            arr_dt = now.replace(hour=h, minute=m, second=0, microsecond=0)
            earliest = arr_dt + timedelta(minutes=LEG2_WALK_MINS)
            for dep in departures:
                try:
                    dep_dt = datetime.fromisoformat(dep["expected"]).astimezone()
                    if dep_dt >= earliest:
                        dest = dep.get("destination", "").replace(" Rail Station", "")
                        result["leg2_earliest_after_arrival"] = (
                            f"{dep_dt.strftime('%H:%M')} → {dest}"
                        )
                        break
                except (KeyError, ValueError, TypeError):
                    continue
        except (AttributeError, ValueError, TypeError):
            pass

    return result


class MorningCommuteCoordinator(DataUpdateCoordinator):
    """Coordinator: polls both legs and merges into a unified data dict."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=_get_scan_interval(),
        )
        self.entry = entry

    async def _async_update_data(self) -> dict:
        """Fetch and merge both legs. Returns the full data dict."""

        # Adjust polling interval dynamically (peak / off-peak / night)
        self.update_interval = _get_scan_interval()

        try:
            data = {}

            # ── SUMMARY ──────────────────────────────────────────────
            s_id = f"sensor.{LEG1_PREFIX}_summary"
            s_state = hass.states.get(s_id) if False else self.hass.states.get(s_id)
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
            # Inject leg2 using next_train's scheduled_arrival
            next_arr = None
            nt_id = f"sensor.{LEG1_PREFIX}_next_train"
            next_arr = _attr(self.hass, nt_id, "scheduled_arrival")
            data["summary"].update(_build_leg2(self.hass, next_arr))

            # ── STATUS ───────────────────────────────────────────────
            st_id = f"sensor.{LEG1_PREFIX}_status"
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
            data["status"].update(_build_leg2(self.hass, next_arr))

            # ── NEXT TRAIN + TRAINS 1-10 ─────────────────────────────
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
                entry.update(_build_leg2(self.hass, t_arr))
                data[f"train_{i}"] = entry

            # next_train mirrors train_1
            data["next_train"] = dict(data["train_1"])

            # ── HISTORICAL RELIABILITY ───────────────────────────────
            hr_id = f"sensor.{LEG1_PREFIX}_historical_reliability"
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
            data["historical_reliability"].update(_build_leg2(self.hass, next_arr))

            # ── HISTORICAL DELAYS ────────────────────────────────────
            hd_id = f"sensor.{LEG1_PREFIX}_historical_delays"
            data["historical_delays"] = {
                "state": _state(self.hass, hd_id),
                "avg_delay_today": _attr(self.hass, hd_id, "avg_delay_today"),
                "avg_delay_7day": _attr(self.hass, hd_id, "avg_delay_7day"),
                "worst_day": _attr(self.hass, hd_id, "worst_day"),
                "best_day": _attr(self.hass, hd_id, "best_day"),
                "days_with_data_7day": _attr(self.hass, hd_id, "days_with_data_7day"),
            }
            data["historical_delays"].update(_build_leg2(self.hass, next_arr))

            # ── DISRUPTION BINARY SENSOR ─────────────────────────────
            dis_id = f"binary_sensor.{LEG1_PREFIX}_has_disruption"
            data["has_disruption"] = {
                "state": _state(self.hass, dis_id),
                "current_status": _attr(self.hass, dis_id, "current_status"),
                "cancelled_count": _attr(self.hass, dis_id, "cancelled_count"),
                "delayed_count": _attr(self.hass, dis_id, "delayed_count"),
                "max_delay_minutes": _attr(self.hass, dis_id, "max_delay_minutes"),
                "disruption_reasons": _attr(self.hass, dis_id, "disruption_reasons"),
                "last_checked": _attr(self.hass, dis_id, "last_checked"),
            }
            data["has_disruption"].update(_build_leg2(self.hass, next_arr))

            return data

        except Exception as err:
            raise UpdateFailed(f"Error reading commute data: {err}") from err
