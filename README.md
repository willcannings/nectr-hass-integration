# Nectr Energy for Home Assistant

A Home Assistant custom integration that imports your [Nectr](https://nectr.com.au/)
electricity consumption data every day and makes it available on the Energy dashboard.

## What it does

- Imports hourly **grid consumption** as a cumulative `kWh` statistic
  (`nectr:<account>_consumption`) suitable for the Energy dashboard.
- Imports the matching hourly **usage cost** as a cumulative statistic
  (`nectr:<account>_consumption_cost`) for the Energy dashboard's cost tracking, using
  the peak/off-peak rates you enter at setup.
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
2. Pick the account (connection) to add (you'll probably only have one), the number of
   days of history to backfill, and your tariff:
   - **Peak rate** and **off-peak rate** in **cents/kWh** (enter them as they appear on
     your bill, e.g. `20` for 20c/kWh).
   - **Peak start hour** and **peak end hour** as local clock hours, `0`–`23`. The peak
     window is `[start, end)`, so the defaults `15` and `21` mean peak runs 3pm–9pm and
     the 9pm hour onward is off-peak.
3. Finish. The backfill runs immediately; new days are picked up automatically.

Each hour's cost is its usage multiplied by the peak or off-peak rate, depending on
whether the hour falls inside the peak window (in the account's local time). Although you
enter rates in **cents**, the cost statistic is stored in **dollars**, so the Energy
dashboard shows it with your configured currency (e.g. 2 kWh at 20c/kWh appears as
`$0.40`).

## Add to the Energy dashboard

1. Go to **Settings → Energy**.
2. Under **Electricity grid → Grid connections**, choose the
   **Nectr consumption (<your address>)** statistic.
3. To track cost, expand that grid connection's **Cost tracking**, choose **Use an entity
   tracking the total costs**, and select **Nectr consumption cost (<your address>)** as
   the entity with the total costs.

You can confirm the imported data under **Developer Tools → Statistics**.

> **Already running an older version?** The tariff questions are only asked when you
> first add the integration, so an entry created before this version has no rates and its
> cost statistic records **$0**. Enter your rates via **Settings → Devices & services →
> Nectr → Reconfigure**. New rates apply to the next import onward; costs already imported
> at $0 are not recalculated. To get a fully-costed history, remove and re-add the
> integration (which re-runs the backfill with your rates).

## Development

The Nectr API client (`custom_components/nectr/nectr_session.py`) is kept independent of
Home Assistant to be split off into another repo later if needed. Run the test suite with:

```sh
venv/bin/python -m unittest discover -s tests -v
```
