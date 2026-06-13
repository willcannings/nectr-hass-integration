#!/bin/sh
# Example shell script showing how to run the day-usage.py script, setting the necessary
# environment variables and passing along any provided date
set -eu

export NECTR_ACCOUNT_NUMBER="A-********"
export NECTR_EMAIL="EMAIL"
export NECTR_PASSWORD="PASSWORD"

repository_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
exec "$repository_root/venv/bin/python" "$repository_root/bin/day-usage.py" "$@"
