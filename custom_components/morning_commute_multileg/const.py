"""Constants for morning_commute_multileg."""

DOMAIN = "morning_commute_multileg"

LEG1_PREFIX    = "twyford_to_farringdon"
LEG2_STATION   = "City Thameslink"
LEG2_WALK_MINS = 5

NUM_TRAINS = 10

SCAN_INTERVAL_PEAK    = 120
SCAN_INTERVAL_OFFPEAK = 300
SCAN_INTERVAL_NIGHT   = 900

# Darwin token for Huxley2 (Rail Data Marketplace)
DARWIN_TOKEN = "001105bc-e005-48d1-a443-595d23aba5aa"

# Huxley2 Darwin JSON proxy — 2-hour window for CTK (City Thameslink)
HUXLEY_URL = (
    "https://huxley2.azurewebsites.net/departures/CTK/{rows}"
    "?timeWindow=120&accessToken={token}"
)
HUXLEY_ROWS = 50

# Southbound filter — exclude destinations that go north from CTK
NORTHBOUND_KEYWORDS = {
    "bedford", "luton", "cambridge", "st albans",
    "welwyn", "stevenage", "kings cross",
}
