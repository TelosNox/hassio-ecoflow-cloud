# STREAM system history (public API)

Daily values of a STREAM system from `POST /iot-open/sign/device/quota/data`
(stream.md, "Historical data"), as sensors and as long-term statistics.
Public API (access key / secret key) only. Code: `custom_components/ecoflow_cloud/devices/public/stream_history.py`.

## Which unit carries it

stream.md: "If there are multiple devices, use the API to obtain the serial number of the
main device". Every query uses the system main SN from `MainSnCache`
(`GET /device/system/main/sn`, the lookup the system commands already use). The history is
set up once the main SN is resolved; it is never guessed from a unit's own SN.

The main role can move to another unit at any time. One statistic per system stays in
place when it does:

- **System id:** the main SN seen first, stored in `.storage/ecoflow_cloud.stream_history`.
  It does not change when the main role moves, and the statistics are named after it.
- **Entities:** every STREAM unit has its own history sensors,
  `ecoflow-api-<unit_sn>-history-<series>`. The current main unit fills them; on the other
  units they are unavailable, because 0 would read as a real daily value.
- **Move:** every update looks the main SN up again, so after an hour at the latest the new
  main unit takes over and continues the same statistic. If both units briefly claim the
  role, they write the same rows.
- A unit whose main unit is configured in no enabled public-API entry carries the history
  instead. If there are several, the first one wins.

## Time model

The API aggregates over UTC days (`beginTime`/`endTime` "in UTC timezone"). A "today" value
would restart at 00:00 UTC, which is 01:00 (CET) or 02:00 (CEST) local time.

- **Sensors** show the value of the **last completed UTC day**. Attributes: `date`
  (the UTC day), `period_start`, `period_end`, `system_main_sn`, `statistic_id`. The value
  changes once per day, shortly after 00:00 UTC, and never resets within a local day.
  No `state_class`: the recorder compiles no statistics of its own from these sensors.
- **Statistics** (`ecoflow_cloud:<system_id>_<series>`, lowercase): one row per UTC day,
  `start` = 00:00 UTC of that day, `state` = the day's value, `sum` = running total.
  In the energy dashboard the whole UTC day shows up in the hour starting 00:00 UTC; a day
  view in a UTC+x time zone shows it on the same date.

No cumulative sensor is summed from the daily values; the statistic's `sum` is the total.

## Series

| Series | Code | Unit | Statistic |
|---|---|---|---|
| `solar_energy` | `BK621-...-SOLAR-ENERGY-...` | Wh | yes |
| `home_consumption` | `BK621-...-LOAD-ENERGY-...` | Wh | yes |
| `grid_import` / `grid_export` | `BK621-...-GRID-ENERGY-...`, `extra` 1 / 2 | Wh | yes |
| `battery_charge` / `battery_discharge` | `BK621-...-SOC-ENERGY-...`, `extra` 1 / 2 | Wh | yes |
| `co2_reduction` | `BK621-...-CO2-WEIGHT-...` | g | yes |
| `solar_savings` | `BK621-...-SAVING-CURRENCY-...` | currency of the response, e.g. € | yes |
| `energy_independence` | `BK621-...-INDEPENDENCE-PERCENT-...` (lookup period: year) | % | no, a sensor for the current UTC year |

The meaning of `extra` 1/2 is not documented; it follows tolwi/hassio-ecoflow-cloud#812.
Check it against the app (see the PR's live test plan) before relying on grid/battery.

## Polling, backfill, errors

- One query per metric and UTC day. Updates every hour; a completed day is read again at
  most every 6 hours (catches late corrections), the year value likewise.
- The newest day is not written while the API returns no data for it yet; it is asked
  again at the next update. An older day without data (before the system existed) is 0.
- Backfill: option *History backfill (days)* of the unit carrying it at the first import, default 90, 1-1095.
  Only the first import goes back that far; later ones continue from the last row.
  At most 120 requests per update, one per second; while a backfill remains, the next
  update follows after 5 minutes.
- Idempotent: every update re-reads the series' last row and overwrites it; the `sum`
  continues from the row before it. Rows with the same start are replaced by the recorder,
  never duplicated. To import a longer range later, delete the statistics
  (Developer tools -> Statistics) and raise the option.
- An API error stops the update after importing what was read; the coordinator logs the
  first failure and the recovery, not every retry. An unusable response (unknown unit,
  inner error code) is logged once per metric as a warning, then at debug level.
