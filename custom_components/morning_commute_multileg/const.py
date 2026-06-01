"""Constants for morning_commute_multileg."""

DOMAIN = "morning_commute_multileg"

# Source integration entity prefixes
LEG1_PREFIX = "twyford_to_farringdon"   # my_rail_commute route
LEG2_SENSOR = "sensor.london_tfl_thameslink_910gctmslnk"  # City Thameslink TfL sensor
LEG2_STATION = "City Thameslink"
LEG2_WALK_MINS = 5  # walk from Farringdon to City Thameslink

# Commute name prefix for produced entities
COMMUTE_PREFIX = "morning_commute"

# Number of train sensors the source integration creates
NUM_TRAINS = 10

# Scan interval seconds (mirrors my_rail_commute peak/off-peak logic)
SCAN_INTERVAL_PEAK = 120     # 2 min during 06-10 and 16-20
SCAN_INTERVAL_OFFPEAK = 300  # 5 min otherwise
SCAN_INTERVAL_NIGHT = 900    # 15 min 23-05

CONF_SCAN_INTERVAL = "scan_interval"
