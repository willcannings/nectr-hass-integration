# Nectr Energy for Home Assistant

A Home Assistant custom integration that imports your [Nectr](https://nectr.com.au/)
electricity consumption data every day and makes it available on the Energy dashboard.

## What it does

- Imports hourly **grid consumption** as a cumulative `kWh` statistic
  (`nectr:<account>_consumption`) suitable for the Energy dashboard.
- Backfills a configurable number of past days **once** at setup (default 14).

Because Nectr only provides historical electricity consumption data rather than live
readings, this integration writes long-term external statistics directly into Home
Assistant's recorder instead of exposing a live sensor entity.

As a result, the Nectr "device" in Home Assistant won't have any entities or live data,
only two diagnostic sensors: the last successfully imported date and the total
electricity consumption for that day.

To view the imported data, check the Energy Dashboard, where "Nectr Consumption" will
appear as an option for grid connections.

Nectr releases a full day’s data after midnight, typically between 3–5am the following
day. This integration checks for new data every 3 hours, so the previous day’s
consumption should be available by the time you wake up.


## Installation (HACS)

1. In HACS, add this repository as a custom repository:
   `https://github.com/willcannings/nectr-hass-integration` (category: *Integration*).
2. Install **Nectr Energy** and restart Home Assistant.
3. Go to **Settings → Devices & services → Add integration** and search for **Nectr**.

Requires Home Assistant **2025.11** or newer.

## Setup

1. Enter your Nectr login **email** and **password**.
2. Pick the account (connection) to add (you'll probably only have one) and the number of
   days of history to backfill.
3. Finish. The backfill runs immediately; new days are picked up automatically.

## Add to the Energy dashboard

1. Go to **Settings → Energy**.
2. Under **Electricity grid → Grid connections**, choose the
   **Nectr consumption (<your address>)** statistic.

You can confirm the imported data under **Developer Tools → Statistics**.

## Development

The Nectr API client (`custom_components/nectr/nectr_session.py`) is kept independent of
Home Assistant to be split off into another repo later if needed. Run the test suite with:

```sh
venv/bin/python -m unittest discover -s tests -v
```
