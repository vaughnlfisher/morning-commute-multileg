"""Coordinator for Morning Commute Multileg."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

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

# Southbound = designation "2": Blackfriars, Elephant & Castle, Sutton, Brighton etc.
LEG2_DESIGNATION = "2"


def _get_scan_interval() -> timedelta:
    """Return scan interval mirroring my_rail_commute peak/off-peak logic."""
    hour = datetime.now().hour
    if 6 <= hour < 10 or 16 <= hour < 20:
        return timedelta(seconds=SCAN_INTERVAL_PEAK)
    if 23 <= hour or hour < 5:
        return timedelta(seconds=SCAN_INTERVAL_NIGHT)
    return timedelta(seconds=SCAN_INTERVAL_OFFPEAK)


def _attr(hass: HomeAssistant, entity_id: str, attr: str):
    """Safe attribute getter."""
    state = hass.states.get(entity_id)
    return state.attributes.get(attr) if state else None


def _state(hass: HomeAssistant, entity_id: str) -> str | None:
    """Safe state getter."""
    state = hass.states.get(entity_id)
    return state.state if state else None


def _parse_hhmm(hhmm: str, reference: datetime) -> datetime | None:
    """
    Parse "HH:MM" into a datetime on the same date as reference.
    Handles rollover past midnight (e.g. arrival 00:10 when reference is 23:50).
    """
    try:
        h, m = map(int, hhmm.split(":"))
        dt = reference.replace(hour=h, minute=m, second=0, microsecond=0)
        # If parsed time is more than 6 hours before reference, assume next day
        if (reference - dt).total_seconds() > 6 * 3600:
            dt += timedelta(days=1)
        return dt
    except (ValueError, TypeError, AttributeError):
        return None


def _extrapolate_southbound(
    known_southbound: list[dict],
    target_dt: datetime,
) -> str | None:
    """
    When target_dt is beyond the TfL live window, extrapolate using the pattern
    of known southbound departures (typically every 15–30 min off-peak).
    Returns "HH:MM → Destination" or None.
    """
    if not known_southbound:
        return None

    # Build list of (datetime, destination) from known departures
    parsed = []
    for dep in known_southbound:
        try:
            dep_dt = datetime.fromisoformat(dep["expected"]).astimezone()
            dest = dep.get("destination", "").replace(" Rail Station", "")
            parsed.append((dep_dt, dest))
        except (KeyError, ValueError, TypeError):
            continue

    if not parsed:
        return None

    parsed.sort(key=lambda x: x[0])
    last_dt, last_dest = parsed[-1]

    # Calculate median interval between known departures
    if len(parsed) >= 2:
        intervals = [
            (parsed[i][0] - parsed[i - 1][0]).total_seconds()
            for i in range(1, len(parsed))
            if (parsed[i][0] - parsed[i - 1][0]).total_seconds() > 0
        ]
        median_interval = sorted(intervals)[len(intervals) // 2] if intervals else 1800
        # Clamp to realistic range (8–35 min)
        interval_secs = max(480, min(2100, median_interval))
    else:
        interval_secs = 1800  # assume 30 min if only one known departure

    # Project forward until we reach or pass target_dt
    projected_dt = last_dt
    projected_dest = last_dest
    # Cycle through destinations in sequence (they usually alternate)
    dest_cycle = [d for _, d in parsed]
    step = 0
    while projected_dt < target_dt:
        step += 1
        projected_dt += timedelta(seconds=interval_secs)
        projected_dest = dest_cycle[step % len(dest_cycle)]
        if step > 20:  # safety cap
            break

    return f"~{projected_dt.strftime('%H:%M')} → {projected_dest} (est.)"


def _build_leg2_for_train(
    departures: list[dict],
    southbound: list[dict],
    scheduled_arrival_str: str | None,
) -> dict:
    """
    Build leg2 attributes for ONE specific train, given its scheduled arrival
    at Farringdon and the full TfL departures list.

    southbound  : pre-filtered list of designation=="2" departures
    Returns a dict of leg2_* keys.
    """
    result = {
        "leg2_station": LEG2_STATION,
        "leg2_walk_mins": LEG2_WALK_MINS,
        "leg2_next_southbound_departure": None,
        "leg2_next_southbound_destination": None,
        "leg2_southbound_departures": [],
        "leg2_earliest_after_arrival": None,
        "leg2_earliest_destination": None,
        "leg2_connection_mins": None,   # minutes wait at City Thameslink
    }

    # Next southbound right now (context, not per-train)
    if southbound:
        try:
            first_dt = datetime.fromisoformat(southbound[0]["expected"]).astimezone()
            result["leg2_next_southbound_departure"] = first_dt.strftime("%H:%M")
            result["leg2_next_southbound_destination"] = (
                southbound[0].get("destination", "").replace(" Rail Station", "")
            )
        except (KeyError, ValueError, TypeError):
            pass

    # All southbound departures as strings
    sb_list = []
    for dep in southbound:
        try:
            dep_dt = datetime.fromisoformat(dep["expected"]).astimezone()
            dest = dep.get("destination", "").replace(" Rail Station", "")
            sb_list.append(f"{dep_dt.strftime('%H:%M')} → {dest}")
        except (KeyError, ValueError, TypeError):
            continue
    result["leg2_southbound_departures"] = sb_list[:5]

    # Per-train: earliest southbound reachable after this train arrives at Farringdon
    if not scheduled_arrival_str:
        return result

    now = datetime.now().astimezone()
    arr_dt = _parse_hhmm(scheduled_arrival_str, now)
    if not arr_dt:
        return result

    # Earliest possible board time = arrival + walk
    earliest_board = arr_dt + timedelta(minutes=LEG2_WALK_MINS)

    # Search live data first
    found = None
    for dep in southbound:
        try:
            dep_dt = datetime.fromisoformat(dep["expected"]).astimezone()
            if dep_dt >= earliest_board:
                dest = dep.get("destination", "").replace(" Rail Station", "")
                found = (dep_dt, dest)
                break
        except (KeyError, ValueError, TypeError):
            continue

    if found:
        dep_dt, dest = found
        wait_mins = round((dep_dt - arr_dt).total_seconds() / 60 - LEG2_WALK_MINS)
        result["leg2_earliest_after_arrival"] = f"{dep_dt.strftime('%H:%M')} → {dest}"
        result["leg2_earliest_destination"] = dest
        result["leg2_connection_mins"] = max(0, wait_mins)
    else:
        # TfL data doesn't extend far enough — extrapolate
        extrapolated = _extrapolate_southbound(southbound, earliest_board)
        if extrapolated:
            result["leg2_earliest_after_arrival"] = extrapolated
            result["leg2_earliest_destination"] = extrapolated.split(" → ")[-1] if " → " in extrapolated else None
            result["leg2_connection_mins"] = None  # unknown when extrapolated

    return result


class MorningCommuteCoordinator(DataUpdateCoordinator):
    """Coordinator: reads both legs, calculates per-train Thameslink connections."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=_get_scan_interval(),
        )
        self.entry = entry

    async def _async_update_data(self) -> dict:
        """Fetch and merge both legs."""
        self.update_interval = _get_scan_interval()

        try:
            data = {}

            # ── Read TfL sensor once, build southbound list ──────────
            tfl_state = self.hass.states.get(LEG2_SENSOR)
            all_departures = []
            southbound = []
            if tfl_state:
                all_departures = tfl_state.attributes.get("departures") or []
                southbound = [
                    d for d in all_departures
                    if d.get("line", {}).get("designation") == LEG2_DESIGNATION
                ]
                _LOGGER.debug(
                    "TfL sensor: %d total departures, %d southbound",
                    len(all_departures), len(southbound),
                )

            # ── SUMMARY ──────────────────────────────────────────────
            s_id = f"sensor.{LEG1_PREFIX}_summary"
            nt_id = f"sensor.{LEG1_PREFIX}_next_train"
            next_arr = _attr(self.hass, nt_id, "scheduled_arrival")

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
            data["summary"].update(
                _build_leg2_for_train(all_departures, southbound, next_arr)
            )

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
            data["status"].update(
                _build_leg2_for_train(all_departures, southbound, next_arr)
            )

            # ── TRAINS 1-10 (each with its own per-train leg2) ───────
            for i in range(1, NUM_TRAINS + 1):
                t_id = f"sensor.{LEG1_PREFIX}_train_{i}"
                t_state = _state(self.hass, t_id)
                t_arr = _attr(self.hass, t_id, "scheduled_arrival")

                entry = {
                    "state": t_state,
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

                # Per-train leg2 — uses that train's own scheduled_arrival
                entry.update(
                    _build_leg2_for_train(all_departures, southbound, t_arr)
                )
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

            return data

        except Exception as err:
            raise UpdateFailed(f"Error reading commute data: {err}") from err
