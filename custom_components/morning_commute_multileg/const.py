"""Constants for morning_commute_multileg."""

DOMAIN = "morning_commute_multileg"

LEG1_PREFIX = "twyford_to_farringdon"
LEG2_SENSOR = "sensor.london_tfl_thameslink_910gctmslnk"
LEG2_STATION = "City Thameslink"
LEG2_WALK_MINS = 5  # walk Farringdon → City Thameslink

COMMUTE_PREFIX = "morning_commute"
NUM_TRAINS = 10

SCAN_INTERVAL_PEAK    = 120   # 2 min  06-10, 16-20
SCAN_INTERVAL_OFFPEAK = 300   # 5 min
SCAN_INTERVAL_NIGHT   = 900   # 15 min 23-05
