# Morning Commute Multileg

A Home Assistant custom integration that combines two commute legs into a unified set of 16 sensors, all carrying both leg 1 and leg 2 connection data.

## Route

| Leg | From | To | Mode | Source |
|-----|------|----|------|--------|
| 1 | Twyford | Farringdon | Elizabeth line | `my_rail_commute` integration |
| Walk | Farringdon | City Thameslink | 5 min walk | — |
| 2 | City Thameslink | Cambridge / Bedford / Luton | Thameslink | `london_tfl` (910GCTMSLNK) sensor |

## Entities produced

Mirrors all 16 entities from `my_rail_commute` (Twyford→Farringdon route) but prefixed `morning_commute_` instead of `twyford_to_farringdon_`. Every entity carries the same attributes as the source **plus** leg 2 Thameslink data:

| Extra attribute | Description |
|----------------|-------------|
| `leg2_station` | `City Thameslink` |
| `leg2_walk_mins` | `5` |
| `leg2_next_departure` | HH:MM of the next Thameslink departure |
| `leg2_next_destination` | Destination of that train |
| `leg2_northbound_departures` | List of up to 5 northbound departures |
| `leg2_earliest_after_arrival` | First Thameslink reachable after arriving Farringdon + 5 min walk |

### Full entity list

- `sensor.morning_commute_summary`
- `sensor.morning_commute_status`
- `sensor.morning_commute_next_train`
- `sensor.morning_commute_train_1` … `sensor.morning_commute_train_10`
- `sensor.morning_commute_historical_reliability`
- `sensor.morning_commute_historical_delays`
- `binary_sensor.morning_commute_has_disruption`

## Prerequisites

- [`my_rail_commute`](https://github.com/adamf83/my-rail-commute) installed and configured for **Twyford → Farringdon**
- `london_tfl` integration configured for stop **910GCTMSLNK** (City Thameslink)

## Installation

### Via HACS (custom repository)

1. HACS → Integrations → ⋮ → Custom repositories
2. Add `https://github.com/VaughnFisher/morning-commute-multileg` → Integration
3. Download → Restart HA
4. Settings → Devices & Services → Add Integration → **Morning Commute Multileg**

### Manual

1. Copy `custom_components/morning_commute_multileg/` to `/config/custom_components/`
2. Restart HA
3. Settings → Devices & Services → Add Integration → **Morning Commute Multileg**

## Update interval

Mirrors `my_rail_commute` timing automatically:
- **Peak** (06:00–10:00, 16:00–20:00): every 2 minutes
- **Off-peak**: every 5 minutes  
- **Night** (23:00–05:00): every 15 minutes
