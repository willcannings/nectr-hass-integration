"""Constants for the Nectr integration."""

from datetime import timedelta

DOMAIN = "nectr"

# Config entry keys.
CONF_EMAIL = "email"
CONF_PASSWORD = "password"
CONF_ACCOUNT_NUMBER = "account_number"
CONF_ACCOUNT_STATE = "account_state"
CONF_ACCOUNT_ADDRESS = "account_address"
CONF_DAYS_TO_LOAD = "days_to_load"
CONF_PEAK_RATE = "peak_rate"
CONF_OFFPEAK_RATE = "offpeak_rate"
CONF_PEAK_START_HOUR = "peak_start_hour"
CONF_PEAK_END_HOUR = "peak_end_hour"

DEFAULT_DAYS_TO_LOAD = 14
MIN_DAYS_TO_LOAD = 1
MAX_DAYS_TO_LOAD = 365

# Tariff defaults. Rates are entered in cents/kWh (matching the user's bill); the
# imported cost statistic is stored in dollars so the Energy dashboard renders it with
# the configured currency.
DEFAULT_PEAK_START_HOUR = 15
DEFAULT_PEAK_END_HOUR = 21
MIN_HOUR = 0
MAX_HOUR = 23

# Poll hourly so newly-available usage data appears within roughly an hour.
UPDATE_INTERVAL = timedelta(hours=1)

# Unit of the imported energy statistic.
ENERGY_UNIT = "kWh"
# Recorder unit_class for the energy unit converter (HA 2025.11+ statistics API).
ENERGY_UNIT_CLASS = "energy"

# Persisted (non-authoritative) diagnostic state.
STORAGE_VERSION = 1

# Coordinator data keys.
DATA_LAST_IMPORTED_DATE = "last_imported_date"
DATA_LAST_DAY_TOTAL = "last_day_total_kwh"
DATA_LAST_DAY_COST = "last_day_cost_dollars"
