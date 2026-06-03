"""Coordinator for Morning Commute Multileg - Huxley2 for live leg2, HSP for leg2 history."""
from __future__ import annotations

import base64
import logging
from datetime import datetime, timedelta

import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    DOMAIN,
    LEG1_PREFIX,
    LEG2_STATION,
    LEG2_WALK_MINS,
    NUM_TRAINS,
    SCAN_INTERVAL_PEAK,
    SCAN_INTERVAL_OFFPEAK,
    SCAN_INTERVAL_NIGHT,
    DARWIN_TOKEN,
    SOUTHBOUND_TERMINI,
)

_LOGGER = logging.getLogger(__name__)

HUXLEY_URL = (
    "https://huxley2.azurewebsites.net/departures/CTK/{rows}"
    "?timeWindow=120&accessToken={token}"
)
HUXLEY_ROWS = 50

# HSP — Historic Service Performance API
HSP_URL      = "https://hsp-prod.rockshore.net/api/v1/serviceMetrics"
HSP_USERNAME = "YOUR_NRE_USERNAME"
HSP_PASSWORD = "YOUR_NRE_PASSWORD"
# CTK → primary southbound termini (CRS codes)
HSP_FROM     = "CTK"
HSP_TO_LOCS  = ["EPH"]  # Elephant & Castle — confirmed 32 services, southbound from CTK
HSP_OPERATOR = "TL"   # Thameslink
# Fetch HSP once per hour (it's historical, no need to poll constantly)
HSP_REFRESH_INTERVAL = timedelta(hours=1)


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
    now = datetime.now().astimezone()
    for key in ("etd", "std"):
        val = (svc.get(key) or "").strip()
        if val in ("", "Delayed", "Cancelled", "On time"):
            continue
        try:
            h, m = map(int, val.split(":"))
            dt = now.replace(hour=h, minute=m, second=0, microsecond=0)
            if (dt - now).total_seconds() < -3600:
                dt += timedelta(days=1)
            return dt
        except (ValueError, TypeError):
            continue
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

    if not scheduled_arrival_str:
        return result

    arr_dt = _parse_hhmm(scheduled_arrival_str, now)
    if not arr_dt:
        return result

    earliest_board = arr_dt + timedelta(minutes=LEG2_WALK_MINS)
    for dep_dt, dest, _ in upcoming:
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
    """Reads leg 1 from my_rail_commute; leg 2 live from Huxley2; leg 2 history from HSP."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass, _LOGGER, name=DOMAIN, update_interval=_get_scan_interval()
        )
        self.entry = entry
        self._leg2_history: dict = {}
        self._leg2_history_last_fetch: datetime | None = None

    async def _fetch_southbound(self) -> list[dict]:
        url = HUXLEY_URL.format(rows=HUXLEY_ROWS, token=DARWIN_TOKEN)
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=12)) as resp:
                    if resp.status != 200:
                        _LOGGER.warning("Huxley HTTP %s", resp.status)
                        return []
                    data = await resp.json(content_type=None)
                    services = data.get("trainServices") or []
                    sb = [s for s in services if _is_southbound(s)]
                    _LOGGER.debug("Huxley CTK: %d total, %d southbound", len(services), len(sb))
                    return sb
        except Exception as err:
            _LOGGER.warning("Huxley fetch error: %s", err)
            return []

    async def _fetch_leg2_history(self) -> dict:
        """Fetch HSP reliability for CTK southbound routes, last 30 days.
        
        Returns dict with daily_breakdown, on_time_pct_today, on_time_pct_7day,
        on_time_pct_30day, avg_delay_7day, best_day, worst_day — same schema as leg 1.
        """
        now = datetime.now()
        # Only fetch once per hour
        if (
            self._leg2_history_last_fetch is not None
            and (now - self._leg2_history_last_fetch) < HSP_REFRESH_INTERVAL
            and self._leg2_history
        ):
            return self._leg2_history

        today = now.date()
        from_date = (today - timedelta(days=30)).strftime("%Y-%m-%d")
        to_date = today.strftime("%Y-%m-%d")

        auth = base64.b64encode(
            f"{HSP_USERNAME}:{HSP_PASSWORD}".encode()
        ).decode()
        headers = {
            "Authorization": f"Basic {auth}",
            "Content-Type": "application/json",
        }

        # Aggregate results across multiple southbound termini
        all_services: list[dict] = []
        try:
            connector = aiohttp.TCPConnector(ssl=False)
            async with aiohttp.ClientSession(connector=connector) as session:
                for to_loc in HSP_TO_LOCS:
                    payload = {
                        "from_loc": HSP_FROM,
                        "to_loc": to_loc,
                        "from_time": "0600",
                        "to_time": "1000",
                        "from_date": from_date,
                        "to_date": to_date,
                        "days": "WEEKDAY",
                        "tolerance": [3, 5, 10, 15, 30],
                    }
                    if HSP_OPERATOR:
                        payload["toc_filter"] = [HSP_OPERATOR]
                    try:
                        async with session.post(
                            HSP_URL,
                            json=payload,
                            headers=headers,
                            timeout=aiohttp.ClientTimeout(total=45),
                        ) as resp:
                            if resp.status == 200:
                                data = await resp.json(content_type=None)
                                services = data.get("Services", [])
                                all_services.extend(services)
                                _LOGGER.debug(
                                    "HSP CTK→%s: %d services", to_loc, len(services)
                                )
                            else:
                                body = await resp.text()
                                _LOGGER.warning(
                                    "HSP HTTP %s for CTK→%s: %s",
                                    resp.status, to_loc, body[:200]
                                )
                    except Exception as err:
                        _LOGGER.warning("HSP fetch error CTK→%s: %s (%s)", to_loc, type(err).__name__, err)
        except Exception as err:
            _LOGGER.warning("HSP session error: %s", err)

        if not all_services:
            return self._leg2_history  # return cached if available

        # Aggregate by date
        # HSP structure: Services[].serviceAttributesMetrics[].Metrics[].{tolerance_value,num_tolerance,percent_tolerance}
        by_date: dict[str, dict] = {}
        for svc in all_services:
            if not isinstance(svc, dict):
                continue
            for loc_data in svc.get("serviceAttributesMetrics", []):
                if not isinstance(loc_data, dict):
                    continue
                date_str = loc_data.get("date", "")
                if not date_str:
                    continue
                if date_str not in by_date:
                    by_date[date_str] = {"pct_sum": 0.0, "pct_count": 0}
                # Find 5-min tolerance metric
                metrics = loc_data.get("Metrics", [])
                if not isinstance(metrics, list):
                    continue
                for m in metrics:
                    if not isinstance(m, dict):
                        continue
                    if m.get("tolerance_value") == 5:
                        pct = m.get("percent_tolerance")
                        if pct is not None:
                            by_date[date_str]["pct_sum"] += float(pct)
                            by_date[date_str]["pct_count"] += 1
                        break

        # Build daily breakdown
        daily_breakdown = []
        for date_str in sorted(by_date.keys())[-30:]:
            d = by_date[date_str]
            pct = round(d["pct_sum"] / d["pct_count"], 2) if d["pct_count"] > 0 else None
            daily_breakdown.append({
                "date": date_str,
                "on_time_pct": pct,
                "avg_delay_minutes": None,
                "total_observations": d["pct_count"],
            })

        # Calculate summary stats
        days_with_data = [d for d in daily_breakdown if d["on_time_pct"] is not None]
        last_7 = [d for d in days_with_data if d["date"] >= (today - timedelta(days=7)).strftime("%Y-%m-%d")]
        last_30 = days_with_data

        def avg_pct(days):
            vals = [d["on_time_pct"] for d in days if d["on_time_pct"] is not None]
            return round(sum(vals) / len(vals), 1) if vals else None

        def avg_delay(days):
            vals = [d["avg_delay_minutes"] for d in days if d["avg_delay_minutes"] is not None]
            return round(sum(vals) / len(vals), 1) if vals else None

        today_str = today.strftime("%Y-%m-%d")
        today_data = next((d for d in daily_breakdown if d["date"] == today_str), None)

        best = max(days_with_data, key=lambda d: d["on_time_pct"] or 0) if days_with_data else None
        worst = min(days_with_data, key=lambda d: d["on_time_pct"] if d["on_time_pct"] is not None else 100) if days_with_data else None

        result = {
            "state": str(avg_pct(last_7) or ""),
            "on_time_pct_today": today_data["on_time_pct"] if today_data else None,
            "on_time_pct_7day": avg_pct(last_7),
            "on_time_pct_30day": avg_pct(last_30),
            "avg_delay_7day": avg_delay(last_7),
            "daily_breakdown": daily_breakdown,
            "best_day": best,
            "worst_day": worst,
            "days_with_data_7day": len(last_7),
            "days_with_data_30day": len(last_30),
        }

        self._leg2_history = result
        self._leg2_history_last_fetch = now
        _LOGGER.info(
            "HSP leg2: 7-day on-time %.1f%%, 30-day %.1f%%",
            result["on_time_pct_7day"] or 0,
            result["on_time_pct_30day"] or 0,
        )
        return result

    async def _async_update_data(self) -> dict:
        self.update_interval = _get_scan_interval()

        try:
            southbound = await self._fetch_southbound()
            leg2_history = await self._fetch_leg2_history()
            data = {}

            s_id   = f"sensor.{LEG1_PREFIX}_summary"
            st_id  = f"sensor.{LEG1_PREFIX}_status"
            nt_id  = f"sensor.{LEG1_PREFIX}_next_train"
            hr_id  = f"sensor.{LEG1_PREFIX}_historical_reliability"
            hd_id  = f"sensor.{LEG1_PREFIX}_historical_delays"
            dis_id = f"binary_sensor.{LEG1_PREFIX}_has_disruption"

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
            data["summary"].update(_build_leg2(southbound, next_arr))

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

            # Leg 2 historical reliability from HSP
            data["leg2_historical_reliability"] = leg2_history

            return data

        except Exception as err:
            raise UpdateFailed(f"Error updating commute data: {err}") from err
