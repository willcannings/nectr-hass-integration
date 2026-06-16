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

DEFAULT_DAYS_TO_LOAD = 14
MIN_DAYS_TO_LOAD = 1
MAX_DAYS_TO_LOAD = 365

# Poll every 3 hours so a transient failure (HA offline, Nectr down) only delays a sync
# by one cycle rather than a full day.
UPDATE_INTERVAL = timedelta(hours=3)

# Unit of the imported energy statistic.
ENERGY_UNIT = "kWh"
# Recorder unit_class for the energy unit converter (HA 2025.11+ statistics API).
ENERGY_UNIT_CLASS = "energy"

# Persisted (non-authoritative) diagnostic state.
STORAGE_VERSION = 1

# Coordinator data keys.
DATA_LAST_IMPORTED_DATE = "last_imported_date"
DATA_LAST_DAY_TOTAL = "last_day_total_kwh"
