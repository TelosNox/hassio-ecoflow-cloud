# Triage: open tolwi issues for non-STREAM devices

Snapshot: `TelosNox/ecoflow-research` `issues/tolwi.jsonl` (2026-10-25), 232 open issues. This report covers the
189 that are not about STREAM or the Smart Meter: Delta/River families, PowerStream, PowerOcean / Ocean Pro, Smart Home
Panels, Wave, Glacier, Power Kit, Smart Plug, generators and new-device requests. It also lists the issues that belong to
the shared core (MQTT delivery, login, app-gating) so the api-core session can pick them up. The 43 STREAM / Smart Meter
issues are only listed at the end.

Every verdict was checked against the fork's code on `main` (b228f12) and, where one exists, the EcoFlow doc in
`api-docs/`. Upstream PR heads were fetched from `refs/pull/*/head` of `tolwi/hassio-ecoflow-cloud`. This session had no
GitHub API access to the upstream repo, so a PR's open/closed state is taken from the task brief and not re-checked.

## Summary

| Category | Count |
|---|---|
| fixed in this PR | 7 |
| fixed in fork (already on `main`) | 43 |
| bug confirmed in fork code, not fixed here | 6 |
| needs device data | 13 |
| new device / feature request | 25 |
| duplicate | 10 |
| not a bug / user setup | 34 |
| stale / unclear | 24 |
| core (api-core session) | 27 |
| STREAM / Smart Meter session (listed only) | 43 |

## Fixed in this PR

| Issue | Device | Change | Evidence |
|---|---|---|---|
| #911 | Power Kit (public) | `pv1InWatts`/`pv2InWatts` no longer divided by 10 | V x I = 271 W vs sensor 27.1 W, total 271.985 W; `power_kits.md`: "PV1/PV2 input power (W)" |
| #900 | DELTA 2 Max (private) | X-Boost sends the full `acOutCfg` payload | Reporter confirmed it switches the device; `delta_2_max.md` acOutCfg example |
| #455 | DELTA Pro (public) | `mppt.carOutWatts` scaled by 1/10 | App 6 W vs HA 60 W (2 users); internal DELTA Pro already scales this key by 1/10 |
| #339 | DELTA 2, DELTA 2 Max, DELTA Pro | Enabling backup reserve keeps the configured level instead of 50 % | Switch sent `bpPowerSoc = value * 50`; three reporters |
| #869 | DELTA 3 (private) | Type-C (2) output power sensor added | `ef_delta3.proto` field 12 `pow_get_typec2` |
| #924 | DELTA Pro 3 (private) | JSON frames skip the protobuf decoder (port of upstream #925, SeoFood) | Reproduction in the issue; regression test added |
| #872 (+#936) | RIVER 3 / RIVER 3 Max | Undecodable protobuf frames no longer go to the JSON parser (partial port of upstream #949, PsycoStea) | WARNING+ERROR pair every ~10 s in both issues; regression test added |

No unique_id or entity key changed. The River 2 / River 2 Max / River 2 Pro / DELTA 3 1500 backup-reserve switches
use the same `value * 50` pattern, but nobody has reported it on those devices, so they are unchanged.

## Bugs confirmed but not fixed here

These change which key an entity reads, which means a unique_id migration, or they need one device capture to choose
between two fields. Several of them are in Delta/River files, which belong to the Delta/River doc session.

- **#324 DELTA 2 Max timeouts swapped** (`devices/internal/delta2_max.py:419-444`). Per `delta_2_max.md`:
  `standbyTime` with moduleType 1 sets the *device* standby and is read back as `pd.standbyMin`; moduleType 3 sets the
  *AC* standby (`inv.standbyMin`); moduleType 5 sets the *car/12 V* standby (`mppt.carStandbyMin`, key `standbyMin`, not
  `standbyMins`). The code's "Unit timeout" reads `inv.standbyMin` but writes moduleType 1, and its "AC timeout"
  reads and writes the car port. Proposed fix: keep both keys, rename the `mppt.carStandbyMin` entity to a DC
  (12 V) timeout, make `inv.standbyMin` the AC timeout with moduleType 3, and add `pd.standbyMin` as the unit timeout.
  That changes what two existing entity_ids mean, so the maintainer has to decide.
- **#472 / #719 DELTA 2 Max DC output** (`delta2_max.py:66-68`). "DC Out Power" reads `mppt.outWatts`, which the doc
  calls "PV output power, amplified 10 times", unscaled, which fits the constant 4-10 W in #472. Car output is
  `pd.carWatts` (W) or `mppt.carOutWatts` (x10). Needs one dump with a 12 V load before choosing a field.
- **#920 DELTA 2 charging state inverted** (`delta2.py:48`). `bms_emsStatus.chgState` is a charge *phase* (0 off, 1 CC,
  2 CV, 3 UPS, 4 PARA) in the DELTA 2 / 2 Max docs, not a direction, yet `ChargingStateSensorEntity` maps 1 = charging,
  2 = discharging. The direction field `pd.chgDsgState` uses 1 = discharging, 2 = charging. Needs one dump while
  charging and one while discharging.
- **#918 base RIVER 2 key variant**: some units report `bmsMaster.*`/`inv.*`/`pd.carSwitch`. Upstream #919 fixes it
  (see ranking).
- **#536 PowerStream daily energy jumps** (`devices/internal/powerstream.py:386-395`): the last day report to arrive
  wins, including yesterday's or last week's. Upstream #945 filters by UTC-midnight timestamps (see ranking).
- **DELTA Pro 3 private set commands** (#837 AC/12 V switches, #615 max charge level): the JSON/TCP envelope is
  ignored for some settings. #906's author verified on a DP3 that a protobuf cmdFunc 254 / cmdId 17 frame works for
  energy backup. Needs a DP3 owner to test the other fields the same way.

## Upstream PRs ranked as port candidates

| Rank | PR | Scope | Verdict |
|---|---|---|---|
| ported | #925 (SeoFood) DELTA Pro 3 JSON frames | +6 | Small, correct, reproduction in #924. Ported with a regression test. |
| ported (partial) | #949 (PsycoStea) RIVER 3 | +26 | Ported the JSON-routing part with one correction: the PR checks `raw_data.lstrip().startswith(b"{")`, which reintroduces the 0x0a pitfall #925 fixed; the port checks the first byte only. Left out the `cms_batt_soh` -> `bms_batt_soh` fallback (no open issue shows it). |
| 1 | #919 (PsycoStea) base RIVER 2 key variants | +135/-39, one file | Fixes #918, running on the author's unit since September. Registers a second entity per field with `auto_enable`. Port next after one review pass; it touches every RIVER 2 entity's enabled default. |
| 2 | #953 (rolandwunderlich) SHP3 grid status / reserve / mode | +128 | Feature for #950, read-only, field meanings from rabits/ha-ef-ble. Good quality, needs an SHP3 owner. |
| 3 | #929 (Dima Afanasiev) Smart Generator | +114 device file | New device (#698, #42). Clean, internal API only. Also bumps `uv.lock`, so drop that hunk when porting. |
| 4 | #904 (SeoFood) DP3 charging power via protobuf | +56/-7 | Plausible root cause for the DP3 set-command family (#615, #837), but the PR shows no device test and changes the range to 400-2900. Port together with #906 once a DP3 owner confirms. |
| 5 | #906 (Vince Stratful) DP3 backup reserve number | +146, proto change | Tested on a DP3 (2026-08-27). Regenerates `ef_dp3_iobroker_pb2.py`, so check the protoc version against mise's `protoc = 32.0` before porting. |
| 6 | #937 (volkovskiyda) SHP1 battery-port direction + timeTask slots | +79/-19 | Evidence in the PR (3 days of history), no open issue. Renames an attribute, which breaks templates. Medium priority. |
| 7 | #944 (SeoFood) DP3 DC port power not /10 | +5/-6 | Reasoned from the proto (float watts, like DELTA 3 / RIVER 3), but no user report. Wait for a DP3 value comparison. |
| 8 | #927 (Claude) DELTA Pro Ultra per-battery | +330 | Large; belongs to the Delta doc session. |
| 9 | #926 (ampersandru) DELTA 3 Plus / RIVER 3 Plus | +46, hand-spliced pb2 | The RIVER_3_PLUS -> River3 alias is backed by users (#588, #833). The DELTA 3 Plus part edits the serialized descriptor by hand and was only checked against a synthetic payload. Port the River alias only, or take jtbrough's branch. |
| 10 | #945 (Mattanja D. Heck) PowerStream daily energy | +16 | Fixes #536 for UTC+x zones, but assumes the device stamps day reports at UTC midnight. If that is wrong for a timezone, today's value is dropped. Needs validation; picking the newest report by timestamp is safer. |
| - | #940 / #941 / #914 Ocean Pro follow-ups | small / +1255 / conflicts | PowerOcean session. #914 conflicts with the fork's `ocean_pro.py`. |
| - | #943 PowerStream mode bootstrap, #946 status topic | `api/` | Core; handed to the api-core session. |
| - | #954 DP3 empty-pdata log level | +9/-4 | Correct, but no issue. Optional. |
| already in fork | #899 Wave 2 temperature unit, #882 DPU X per-phase AC | - | Upstream merged them (70a682e etc.); the PR refs are stale. |

## New-device / feature requests with available data

| Device | Issues | Data available |
|---|---|---|
| DELTA 3 Max | #738, #683 | `api-docs/delta_3_max.md`; keys are a subset of `delta_3_max_plus.md` (no AC2/PV2), so the public `Delta3MaxPlus` class probably fits. Missing: the productName EcoFlow returns. |
| Glacier (public API) | #366 | `api-docs/glacier.md`; no public Glacier class yet. |
| RIVER 3 Plus | #588, #444, #833 | jtbrough/river3-plus-support (several owners confirmed), upstream #926. |
| DELTA 3 Plus | #557, #465, #395 | Only #926's synthetic-payload mapping; one comment says it works as RIVER_3. Needs a real dump. |
| Smart Generator (Dual Fuel) | #698, #42 | Upstream #929; diagnostics in #42. |
| DELTA 3 1000/2000 Air | #831, #873 | #873 has an app-API diagnostics dump with DELTA 3-style snake_case keys. Try the DELTA_3 class. |
| SHP3 panel state | #950 | Upstream #953. |
| PowerOcean EV charger / sysBatDsgDownLimit | #795, #765 | `evPwr`/`chargingStatus` are GET-quota fields in `power_ocean.md`; `sysBatDsgDownLimit` is undocumented. |
| RAPID Pro X, Smart Gateway 200, Blade, Solar Tracker, Shelly x EcoFlow plug | #730, #697, #47, #452/#127, #550 | No usable captures. |

## Core findings for the api-core session

- **App-gating / freezes** (#283, #289, #361, #469, #560, #704, #746, #758, #782, #830, #916): the largest cluster.
  The stall-reconnect from #909 is in the fork, but reports continue.
- **Public MQTT "Not authorized" after hours/days** (#876, #901); fixed only by regenerating keys.
- **DP3 public updates only every 5 min** (#772, #764): diagnostics show only the quota/all poll moving, no MQTT push.
- **PowerStream `supplyPriority` unknown after restart** (#942), with upstream #943 as the candidate (touches
  `api/ecoflow_mqtt.py`).
- **AC output turned OFF after an MQTT reconnect with null context** (#819): check whether any reconnect path
  publishes a set message or replays an optimistic state.
- **Base JSON fallback log noise** (#210, `devices/__init__.py:168-181`): every non-JSON frame on a device class
  without its own decoder logs a WARNING plus an ERROR. Fixed here for RIVER 3 and DELTA Pro 3 only.
- **`fetch_all_available_devices` KeyError 'data'** (#598, #474, #791): the API's error message should reach the
  user instead of a KeyError.
- **"current device is not allowed to get device info"** (#724 Power Kit v2, #541, #685): EcoFlow-side (1006); could
  get a clearer config-flow error.
- **Backoff/cooldown** (#684), DNS lookups (#886), client-id handling (#355).

## Full table

Categories: fixed in this PR · fixed in fork · bug confirmed · duplicate · needs device data · new device / feature ·
not a bug / user setup · stale / unclear · core (api-core session). Code locations refer to the fork's
`custom_components/ecoflow_cloud/`.

| Issue | Device | Category | Verdict | Evidence / location | Action |
|---|---|---|---|---|---|
| [#950](https://github.com/tolwi/hassio-ecoflow-cloud/issues/950) | Smart Home Panel 3 | new device / feature | Feature: grid status (619), backup reserve (461), mode (1245), charge limit (1244). | Upstream PR #953 implements it (+128, read-only). | Port candidate #953 (feature, needs SHP3 owner). |
| [#947](https://github.com/tolwi/hassio-ecoflow-cloud/issues/947) | all | fixed in fork | Credentials in logs. | Fork commit 3e82225. | Close upstream when merged. |
| [#942](https://github.com/tolwi/hassio-ecoflow-cloud/issues/942) | PowerStream (private) | core (api-core session) | supplyPriority stays unknown after restart until app opens; a get after SUBACK fixes it. | Reporter's instrumented trace; upstream PR #943 touches api/ecoflow_mqtt.py. | Hand to api-core session; #943 is the candidate. |
| [#935](https://github.com/tolwi/hassio-ecoflow-cloud/issues/935) | PowerOcean 15 kW (OCEAN_PRO) | needs device data | Public API returns only BMS-pack params; power/phase fields missing. | Diag in issue: only accu_*/bms_* keys. | Ask for app-API test as OCEAN_PRO (HR51) + OCEAN_SMART_PANEL (HR61) and a diagnostics dump; PowerOcean doc check is the PowerOcean session's. |
| [#932](https://github.com/tolwi/hassio-ecoflow-cloud/issues/932) | all | fixed in fork | protobuf==6.32.0 pin vs HA 2026.10. | Fork manifest protobuf>=6.32.0,<8 (38986e6). | Duplicate of #928. |
| [#930](https://github.com/tolwi/hassio-ecoflow-cloud/issues/930) | all | fixed in fork | Same as #928. | 38986e6. | Duplicate of #928. |
| [#928](https://github.com/tolwi/hassio-ecoflow-cloud/issues/928) | all | fixed in fork | protobuf pin. | 38986e6. | Close. |
| [#924](https://github.com/tolwi/hassio-ecoflow-cloud/issues/924) | DELTA Pro 3 (private) | fixed in this PR | JSON status frames first went through the protobuf decoder and logged two errors. | Reproduction in issue; delta_pro_3.py _prepare_data. | Ported upstream PR #925 (SeoFood) + regression test. |
| [#920](https://github.com/tolwi/hassio-ecoflow-cloud/issues/920) | DELTA 2 (public) | bug confirmed | Charging state inverted. | Sensor reads bms_emsStatus.chgState (delta2.py:48) through ChargingStateSensorEntity (1=charging, 2=discharging). The DELTA 2/2 Max docs define that field as a charge phase (0 off, 1 CC, 2 CV, 3 UPS, 4 PARA), while pd.chgDsgState is the direction field with 1 = discharging, 2 = charging, the opposite of the entity's mapping. | Fix belongs to the Delta/River doc session (key change needs _migrate_entity_unique_id); needs one diagnostics dump while charging and while discharging to pick the field. |
| [#918](https://github.com/tolwi/hassio-ecoflow-cloud/issues/918) | RIVER 2 (private) | bug confirmed | Battery/switch/number/select entities unknown on some base RIVER 2 units. | Reporter's diagnostics: bmsMaster.soc/cycles/temp, inv.cfgAcEnabled, pd.carSwitch instead of bms_bmsStatus.*/mppt.*; running for weeks on their unit. | Port candidate upstream PR #919 (+135/-39, dual-key auto_enable). |
| [#917](https://github.com/tolwi/hassio-ecoflow-cloud/issues/917) | RIVER 2 Max (public) | not a bug / user setup | Not selectable under the developer API. | registry.py: 'RIVER 2 Max' public entry was commented out by the maintainer (6f65bf9); the research repo has no River 2 / River 2 Max public doc. | Use the app API (RIVER_2_MAX) or provide a public quota dump. |
| [#916](https://github.com/tolwi/hassio-ecoflow-cloud/issues/916) | DELTA 2 Max (private) | core (api-core session) | Device stays offline, no telemetry, while app works. | No log/diag. | api-core session (private MQTT delivery). |
| [#912](https://github.com/tolwi/hassio-ecoflow-cloud/issues/912) | all (River 2 Pro) | not a bug / user setup | jsonpath-ng could not be installed (DNS). | Comments: DNS fix solved it. | Close. |
| [#911](https://github.com/tolwi/hassio-ecoflow-cloud/issues/911) | Power Kit (public) | fixed in this PR | pv1InWatts/pv2InWatts 10x too low. | 15.455 V x 17534 mA = 271 W vs sensor 27.1 W; power_kits.md: 'PV1/PV2 input power (W)'. | Fixed: InRawWattsSolarSensorEntity (powerkit.py:290/319). |
| [#905](https://github.com/tolwi/hassio-ecoflow-cloud/issues/905) | RIVER 3 Max | needs device data | AC In Volts = 0. | river3.py:215 reads plug_in_info_ac_in_vol; no frame data in issue. | Need a diagnostics dump while on AC input. |
| [#903](https://github.com/tolwi/hassio-ecoflow-cloud/issues/903) | PowerStream (private) | needs device data | Custom load power resets to 0 after a few seconds (battery on PV input). | internal/powerstream.py:318-330 sends PERMANENT_WATTS_PACK; no set_reply in issue. | Need diagnostics with set/set_reply entries (fork records them). |
| [#901](https://github.com/tolwi/hassio-ecoflow-cloud/issues/901) | STREAM | core (api-core session) | MQTT 'Not authorized' after <2 days. |  | api-core session (dup #876). |
| [#900](https://github.com/tolwi/hassio-ecoflow-cloud/issues/900) | DELTA 2 Max (private) | fixed in this PR | X-Boost switch did not switch the device. | Reporter confirmed full acOutCfg payload works; delta_2_max.md acOutCfg uses the same 4 fields. | Fixed: delta2_max.py X-Boost payload. |
| [#886](https://github.com/tolwi/hassio-ecoflow-cloud/issues/886) | STREAM Microinverter | core (api-core session) | Many DNS lookups. |  | api-core session. |
| [#885](https://github.com/tolwi/hassio-ecoflow-cloud/issues/885) | WAVE 3 | needs device data | Consumption shows on AC Out Power, AC In 0. | wave3.py:243-244 map pow_get_ac -> AC Out, pow_get_ac_in -> AC In. | Need raw pow_get_ac / pow_get_ac_in values while running on AC. |
| [#883](https://github.com/tolwi/hassio-ecoflow-cloud/issues/883) | all | fixed in fork | jsonpath re-parsed per update (CPU). | Fixed upstream v1.6.0 (7cbf214), in fork (entities/__init__.py:133 parses once). | Close. |
| [#878](https://github.com/tolwi/hassio-ecoflow-cloud/issues/878) | Power Kit (public) | fixed in fork | Only the Power Hub entity, no sub-devices. | Flat quota/all sub-device discovery fixed in 0ff3635 (v1.6.0), config_flow.py:121-140; report was on v1.5.0. | Ask reporter to re-add on >=1.6.0. |
| [#877](https://github.com/tolwi/hassio-ecoflow-cloud/issues/877) | PowerStream | not a bug / user setup | getaddrinfo failure at MQTT connect. | DNS/network. | Close (user network). |
| [#876](https://github.com/tolwi/hassio-ecoflow-cloud/issues/876) | STREAM | core (api-core session) | Public MQTT credentials rejected. |  | api-core session. |
| [#874](https://github.com/tolwi/hassio-ecoflow-cloud/issues/874) | DELTA Pro / PowerStream | not a bug / user setup | HA 2025.1 cannot install protobuf==6.32.0/paho 2.1. | Very old HA core. | Update HA. |
| [#873](https://github.com/tolwi/hassio-ecoflow-cloud/issues/873) | DELTA 3 2000 Air | new device / feature | New device. | Diagnostics in issue: snake_case BMS/cms keys like DELTA 3 (bms_batt_soc, cms_*), via app API. | Candidate: try DELTA_3 class; needs full dump incl. pow_* fields. |
| [#872](https://github.com/tolwi/hassio-ecoflow-cloud/issues/872) | RIVER 3 Max / RIVER 2 | fixed in this PR | 'Expecting value ... Trying to load json' every ~10 s; IntegrationSensor TypeError on 1.5.0. | river3.py fed undecodable protobuf to the JSON parser; IntegrationSensor init is HA-version-aware in fork (sensor.py:888). | River 3 part fixed (partial port of #949); IntegrationSensor part fixed in fork. The RIVER 2 'no sensors' comment is #918. |
| [#871](https://github.com/tolwi/hassio-ecoflow-cloud/issues/871) | DELTA Pro Ultra X (private) | needs device data | PV ports report nothing, total input works. | delta_pro_ultra_x.py:119-120 only has pv_vin_ref/pv2_vin_ref (voltages, disabled); no PV power field mapped. | Need a dump with PV input active to find the PV power fields. |
| [#870](https://github.com/tolwi/hassio-ecoflow-cloud/issues/870) | several | not a bug / user setup | Battery level shows 2 decimals since 1.5.0. | Intentional: LevelSensorEntity suggested_display_precision=2 (a532989, upstream #801); per-entity display precision is configurable. | Close or change by maintainer decision. |
| [#869](https://github.com/tolwi/hassio-ecoflow-cloud/issues/869) | DELTA 3 (private) | fixed in this PR | Type-C (2) output missing. | ef_delta3.proto field 12 pow_get_typec2; delta3.py already reads flow_info_typec2. | Added sensor (delta3.py). |
| [#856](https://github.com/tolwi/hassio-ecoflow-cloud/issues/856) | STREAM Ultra X | not a bug / user setup | Newcomer, no devices after login. |  | Support question. |
| [#847](https://github.com/tolwi/hassio-ecoflow-cloud/issues/847) | RIVER 3 UPS | needs device data | Found but no entities. | Screenshots only. | Need diagnostics; may be a RIVER_3 variant (see #949). |
| [#837](https://github.com/tolwi/hassio-ecoflow-cloud/issues/837) | DELTA Pro 3 (private) | needs device data | AC HV / 12V DC switches unknown and without effect. | delta_pro_3.py:209-237 sends JSON id 66/81; upstream #906 author reports the DP3 ignores the JSON/TCP envelope for some configs and needs protobuf cmdFunc 254/cmdId 17. | Needs DP3 owner to test a protobuf set (pattern of #904/#906); pepijn's branch only changes the public DP3. |
| [#835](https://github.com/tolwi/hassio-ecoflow-cloud/issues/835) | DELTA Pro | not a bug / user setup | jsonpath-ng install failure after OS update. | Environment; others on same stack fine. | Close. |
| [#833](https://github.com/tolwi/hassio-ecoflow-cloud/issues/833) | RIVER 3 Plus | new device / feature | Light mode control. | jtbrough/river3-plus-support branch (tested by 3 users), upstream PR #926 registers RIVER_3_PLUS -> River3. | New-device work, see #588. |
| [#832](https://github.com/tolwi/hassio-ecoflow-cloud/issues/832) | PowerStream | new device / feature | Switch power demand mode (smart plug vs smart meter). | No documented command in power_stream_micro_inverter.md. | Feature; needs captured app command. |
| [#831](https://github.com/tolwi/hassio-ecoflow-cloud/issues/831) | DELTA 3 1000 Air | new device / feature | Is it supported? | No data. | Needs diagnostics (see #873). |
| [#830](https://github.com/tolwi/hassio-ecoflow-cloud/issues/830) | STREAM AC Pro / WAVE 3 | core (api-core session) | Values stop updating until app opened. | Comment: periodic get keeps stream alive. | api-core session (app-gating). |
| [#825](https://github.com/tolwi/hassio-ecoflow-cloud/issues/825) | PowerStream | not a bug / user setup | Wants lower max output. | 'Custom load power' number already exists (internal/public powerstream.py). | Close. |
| [#819](https://github.com/tolwi/hassio-ecoflow-cloud/issues/819) | Delta (UPS) | core (api-core session) | AC output switched OFF with null context after MQTT reconnect. | switch state change without user context; no set log provided. | api-core session: check whether any code path publishes a set on reconnect; ask for diagnostics 'set' list. |
| [#816](https://github.com/tolwi/hassio-ecoflow-cloud/issues/816) | DELTA 3 (private) | needs device data | Backup reserve switch/level read off/0 after opening the app. | delta3.py:425-448/518 read energy_backup_*; app-triggered frame probably lacks/zeros the fields. | Need the raw frame received when the app opens. |
| [#814](https://github.com/tolwi/hassio-ecoflow-cloud/issues/814) | DELTA 2 Max (public) | duplicate | Solar input drops to 0. |  | Duplicate of #811 (STREAM/core). |
| [#813](https://github.com/tolwi/hassio-ecoflow-cloud/issues/813) | DELTA Pro 3 | not a bug / user setup | DNS timeout at login. | Ad-blocker / IPv6 per comments. | Close. |
| [#804](https://github.com/tolwi/hassio-ecoflow-cloud/issues/804) | PowerStream | stale / unclear | API host not saved (1.5.0-beta3). | Reconfigure pre-fills CONF_API_HOST from entry data (config_flow.py:265-296); options save fixed in fork (f630d1d). | Ask to retest. |
| [#798](https://github.com/tolwi/hassio-ecoflow-cloud/issues/798) | BK01 microinverter (added as PowerStream) | not a bug / user setup | cmd_func 254/cmd_id 21 ignored by the PowerStream decoder. | Serial prefix BK01 is the STREAM microinverter family, not PowerStream (HW51); fork has STREAM_MICROINVERTER. | Re-add as STREAM_MICROINVERTER; STREAM session. |
| [#795](https://github.com/tolwi/hassio-ecoflow-cloud/issues/795) | PowerOcean (public) | fixed in fork | sysGridPwr/sysLoadPwr/bpPwr requested. | powerocean.py:87-89 (since 1.5.0). evPwr/chargingStatus are only GET-quota fields in power_ocean.md. | Remaining EV fields = feature for PowerOcean session. |
| [#791](https://github.com/tolwi/hassio-ecoflow-cloud/issues/791) | STREAM | not a bug / user setup | KeyError 'data' at public login. | Developer account/email mismatch per comments. | Close. |
| [#783](https://github.com/tolwi/hassio-ecoflow-cloud/issues/783) | WAVE 2 | needs device data | Main Remain Capacity frozen after firmware 1.0.11.11. | No dump. | Need diagnostics from a 1.0.11.11 unit. |
| [#782](https://github.com/tolwi/hassio-ecoflow-cloud/issues/782) | PowerStream | core (api-core session) | Freezing/junk data. |  | api-core (app-gating). |
| [#779](https://github.com/tolwi/hassio-ecoflow-cloud/issues/779) | PowerStream | not a bug / user setup | Question: is permanentWatts written to flash? | Unknown to EcoFlow docs. | Close as question. |
| [#778](https://github.com/tolwi/hassio-ecoflow-cloud/issues/778) | DELTA 2 Max (private) | new device / feature | AC charging max hardcoded 2400 W. | delta2_max.py ChargingPowerEntity max; proposed inv.acChgRatedPower not verified in the cloud data. | Needs a dump showing a rated-power field. |
| [#773](https://github.com/tolwi/hassio-ecoflow-cloud/issues/773) | DELTA 2 Max (private) | core (api-core session) | Slow/frozen updates. |  | api-core. |
| [#772](https://github.com/tolwi/hassio-ecoflow-cloud/issues/772) | DELTA Pro 3 (public) | core (api-core session) | Updates only every ~5 min. | Diagnostics show quota_cloud_ts moving every 5 min (= quota/all poll), MQTT pushes missing. | api-core session (public MQTT delivery). |
| [#765](https://github.com/tolwi/hassio-ecoflow-cloud/issues/765) | PowerOcean | new device / feature | Expose sysBatDsgDownLimit. | Field not in power_ocean.md. | Needs dump showing the field. |
| [#764](https://github.com/tolwi/hassio-ecoflow-cloud/issues/764) | DELTA Pro 3 (public) | duplicate | Updates only every 15 min. |  | Duplicate of #772. |
| [#758](https://github.com/tolwi/hassio-ecoflow-cloud/issues/758) | PowerStream | core (api-core session) | Still freezing. | Stall reconnect is in fork (#909), app-gating remains. | api-core. |
| [#750](https://github.com/tolwi/hassio-ecoflow-cloud/issues/750) | PowerStream | not a bug / user setup | Custom load power step 100 W. | Step comes from the per-device 'power step' option (default 100, devices/__init__.py:83-90); doc unit is 0.1 W, so 1 W works. Options save fixed in fork (f630d1d). | Tell users to set the step option; maintainer may lower PowerStream default. |
| [#746](https://github.com/tolwi/hassio-ecoflow-cloud/issues/746) | PowerStream | core (api-core session) | Freeze / 0. |  | api-core (dup #704). |
| [#738](https://github.com/tolwi/hassio-ecoflow-cloud/issues/738) | DELTA 3 Max | new device / feature | Support request. | api-docs/delta_3_max.md exists; keys are a subset of delta_3_max_plus.md (no AC2/PV2), so public Delta3MaxPlus likely fits; DELTA_3 (private) limits AC charging to 1500. | New-device candidate: needs the productName EcoFlow returns. |
| [#735](https://github.com/tolwi/hassio-ecoflow-cloud/issues/735) | PowerStream (public) | core (api-core session) | 'Failed to set up' after MQTT connect. |  | api-core. |
| [#732](https://github.com/tolwi/hassio-ecoflow-cloud/issues/732) | DELTA 3 + Delta 2 extra battery | needs device data | Slave battery entities missing. | Diagnostics attached upstream (not in research snapshot). | Needs the attached dump to map bms slave fields. |
| [#730](https://github.com/tolwi/hassio-ecoflow-cloud/issues/730) | RAPID Pro X (P51) | new device / feature | New device. | No data. | Needs diagnostics. |
| [#724](https://github.com/tolwi/hassio-ecoflow-cloud/issues/724) | Power Kit v2 (5 kVA) | core (api-core session) | 'current device is not allowed to get device info' (1006). | EcoFlow refuses quota for this product. | EcoFlow-side / api-core; nothing in device code. |
| [#719](https://github.com/tolwi/hassio-ecoflow-cloud/issues/719) | DELTA 2 Max | bug confirmed | No DC car output power sensor. | delta2_max.py:66-68: DC_OUT_POWER reads mppt.outWatts, which delta_2_max.md defines as 'PV output power, amplified 10 times'; car output is pd.carWatts (W) / mppt.carOutWatts (x10). Related #472. | Needs one dump with a 12 V load before changing keys; Delta/River session. |
| [#704](https://github.com/tolwi/hassio-ecoflow-cloud/issues/704) | PowerStream | core (api-core session) | Updates only after app opened. |  | api-core (app-gating). |
| [#698](https://github.com/tolwi/hassio-ecoflow-cloud/issues/698) | Smart Generator (Dual Fuel) | new device / feature | New device. | Upstream PR #929 adds SMART_GENERATOR (+114 device file). | Port candidate #929 (new device). |
| [#697](https://github.com/tolwi/hassio-ecoflow-cloud/issues/697) | Smart Gateway 200 | new device / feature | New device. | External protobuf reference only. | Needs captures. |
| [#685](https://github.com/tolwi/hassio-ecoflow-cloud/issues/685) | Ocean Pro (US) | fixed in fork | Support request. | Read-only OCEAN_PRO + OCEAN_SMART_PANEL in fork (devices/internal/ocean_pro.py, upstream #892/#894). | Follow-ups #914/#941 are PowerOcean-session candidates. |
| [#684](https://github.com/tolwi/hassio-ecoflow-cloud/issues/684) | STREAM | core (api-core session) | Retry/backoff. |  | api-core. |
| [#683](https://github.com/tolwi/hassio-ecoflow-cloud/issues/683) | DELTA 3 Max (private, as DELTA_3) | needs device data | AC charging power cannot be set. | delta3.py:411-420 range 100-1500 and the DELTA 3 command; no DELTA 3 Max type. | Part of #738; needs a DELTA 3 Max set capture. |
| [#678](https://github.com/tolwi/hassio-ecoflow-cloud/issues/678) | RIVER 2 Max | fixed in fork | Refresh period option ignored. | Options save fixed in fork (f630d1d). | Ask to retest. |
| [#651](https://github.com/tolwi/hassio-ecoflow-cloud/issues/651) | STREAM Micro | fixed in fork | Last value held when offline. | Fork 4286bc8 + reset-on-offline. | Close. |
| [#615](https://github.com/tolwi/hassio-ecoflow-cloud/issues/615) | DELTA Pro 3 (private) | needs device data | Max charge level not saved, reverts. | Same JSON-vs-protobuf set path as #837; #906 shows protobuf works for energy backup on DP3. | Needs DP3 tester for a protobuf cms_max_chg_soc set. |
| [#606](https://github.com/tolwi/hassio-ecoflow-cloud/issues/606) | PowerOcean (private, 1.3.0) | stale / unclear | Corrupt unscaled values after re-add. | Old version; no current repro. | Ask for diagnostics on current fork. |
| [#598](https://github.com/tolwi/hassio-ecoflow-cloud/issues/598) | DELTA Pro (public) | not a bug / user setup | KeyError 'data' during device fetch. | Device bound to another account; core could show a clearer error. | Core note: public_api fetch should report the API message. |
| [#597](https://github.com/tolwi/hassio-ecoflow-cloud/issues/597) | DELTA Pro | fixed in fork | Net total power sensor. | Added upstream #628 (e1e3fec). | Close. |
| [#596](https://github.com/tolwi/hassio-ecoflow-cloud/issues/596) | SHP2 + DPU (public) | fixed in fork | Values only on startup. | QuotaScheduledStatusSensorEntity every 60 s (smart_home_panel_2.py:67). | Close (dup #546). |
| [#592](https://github.com/tolwi/hassio-ecoflow-cloud/issues/592) | PowerStream | fixed in fork | Last value held when offline. | 4286bc8, reset-on-offline option. | Close. |
| [#588](https://github.com/tolwi/hassio-ecoflow-cloud/issues/588) | RIVER 3 Plus | new device / feature | Support request. | jtbrough branch confirmed by several owners; upstream #926 registers RIVER_3_PLUS -> River3. | New-device port candidate (#926 River part). |
| [#586](https://github.com/tolwi/hassio-ecoflow-cloud/issues/586) | Glacier (private) | fixed in fork | Setpoint only in Celsius while temps show Fahrenheit. | SetTempEntity now has device_class TEMPERATURE (number.py:166, upstream 70a682e), so HA converts the setpoint to the user's unit like the sensors. | Ask reporter to confirm. |
| [#575](https://github.com/tolwi/hassio-ecoflow-cloud/issues/575) | RIVER 2 Max (public) | duplicate | Zeros/unavailable. |  | Duplicate of #917. |
| [#566](https://github.com/tolwi/hassio-ecoflow-cloud/issues/566) | - | not a bug / user setup | Missing from HACS default list. |  | Close. |
| [#565](https://github.com/tolwi/hassio-ecoflow-cloud/issues/565) | PowerStream #2 (private) | stale / unclear | Second unit only zeros. | No data. | Ask for diagnostics. |
| [#562](https://github.com/tolwi/hassio-ecoflow-cloud/issues/562) | PowerStream | fixed in fork | Values not zeroed offline. | Reset-on-offline. | Close (dup #592). |
| [#561](https://github.com/tolwi/hassio-ecoflow-cloud/issues/561) | PowerStream (public) | not a bug / user setup | 'accessKey is invalid'. | Regenerating key solved it. | Close. |
| [#560](https://github.com/tolwi/hassio-ecoflow-cloud/issues/560) | several | core (api-core session) | Updates freeze. |  | api-core (app-gating). |
| [#558](https://github.com/tolwi/hassio-ecoflow-cloud/issues/558) | - | not a bug / user setup | jsonpath-ng download error. | Network. | Close. |
| [#557](https://github.com/tolwi/hassio-ecoflow-cloud/issues/557) | DELTA 3 Plus | new device / feature | Support request. | Upstream #926 adds DELTA_3_PLUS with hand-spliced pb2, verified only with a synthetic payload. | Not ready; needs a real dump. |
| [#554](https://github.com/tolwi/hassio-ecoflow-cloud/issues/554) | - | stale / unclear | HA update broke an old YAML MQTT package. | Not this integration's YAML. | Close. |
| [#550](https://github.com/tolwi/hassio-ecoflow-cloud/issues/550) | EcoFlow x Shelly plug | new device / feature | Shelly-branded plug not switchable. | Not the EcoFlow Smart Plug. | Needs data. |
| [#546](https://github.com/tolwi/hassio-ecoflow-cloud/issues/546) | SHP2 (public) | fixed in fork | Battery level only on startup. | QuotaScheduled every 60 s (smart_home_panel_2.py:67). | Close. |
| [#542](https://github.com/tolwi/hassio-ecoflow-cloud/issues/542) | Alternator Charger via DELTA 2 Max | new device / feature | Alternator input missing on D2M. | Fork has a standalone ALTERNATOR device; D2M slave port fields unknown. | Needs D2M dump with the charger running (see #472 slave power). |
| [#541](https://github.com/tolwi/hassio-ecoflow-cloud/issues/541) | RIVER 2 Pro | duplicate | 'not allowed to get device info'. |  | Duplicate of #540 (STREAM/core). |
| [#536](https://github.com/tolwi/hassio-ecoflow-cloud/issues/536) | PowerStream (private) | bug confirmed | Daily PV energy jumps to yesterday's value at sunset; always online. | internal/powerstream.py:386-395 stores sum(watth) of whatever day report arrives last. | Candidate #945 (+16) assumes UTC-midnight timestamps; #946 (status topic) is core. Not ported, see PR ranking. |
| [#532](https://github.com/tolwi/hassio-ecoflow-cloud/issues/532) | Power Kit | duplicate | No entities. |  | Duplicate of #878 (fixed v1.6.0). |
| [#522](https://github.com/tolwi/hassio-ecoflow-cloud/issues/522) | RIVER 2 Pro | stale / unclear | HA lags/crashes after setup (1.3.0/1.4.0). | Likely the jsonpath CPU bug #883, fixed v1.6.0. | Ask to retest. |
| [#499](https://github.com/tolwi/hassio-ecoflow-cloud/issues/499) | PowerStream | fixed in fork | Values not zeroed when cloud down. | Reset-on-offline. | Close. |
| [#493](https://github.com/tolwi/hassio-ecoflow-cloud/issues/493) | - | core (api-core session) | Lag / setup DNS error. | Probably #883 + DNS. | Close / api-core. |
| [#474](https://github.com/tolwi/hassio-ecoflow-cloud/issues/474) | RIVER 2 (public) | not a bug / user setup | KeyError 'data'. | Same as #598. | Duplicate of #598. |
| [#473](https://github.com/tolwi/hassio-ecoflow-cloud/issues/473) | PowerStream #2 (public) | not a bug / user setup | Not updating. | Key regeneration fixed it. | Close. |
| [#472](https://github.com/tolwi/hassio-ecoflow-cloud/issues/472) | DELTA 2 Max | bug confirmed | DC out power shows 4-10 W constantly; slave in/out empty. | delta2_max.py:68 DC_OUT_POWER = mppt.outWatts, documented as PV output power x10, read unscaled. | Needs dump with DC load to choose pd.carWatts vs mppt.carOutWatts (unique_id migration); Delta/River session. |
| [#471](https://github.com/tolwi/hassio-ecoflow-cloud/issues/471) | - | stale / unclear | 500 error on v1.2.0. | Old version. | Close. |
| [#470](https://github.com/tolwi/hassio-ecoflow-cloud/issues/470) | RIVER 2 Max | not a bug / user setup | Question about MQTT commands. |  | Close. |
| [#469](https://github.com/tolwi/hassio-ecoflow-cloud/issues/469) | PowerStream + DELTA 3 Plus | core (api-core session) | Stops until app opened. |  | api-core (app-gating). |
| [#465](https://github.com/tolwi/hassio-ecoflow-cloud/issues/465) | DELTA 3 Plus / gen 3 | new device / feature | Support request. | Fork has DELTA_3, RIVER_3; Plus see #557. | Duplicate of #557/#588. |
| [#460](https://github.com/tolwi/hassio-ecoflow-cloud/issues/460) | - | not a bug / user setup | 'signature is wrong'. | Old/invalid key. | Close. |
| [#455](https://github.com/tolwi/hassio-ecoflow-cloud/issues/455) | DELTA Pro (public) | fixed in this PR | DC car out power 10x too high. | App 6 W vs HA 60 W (2 users); internal delta_pro.py:70 scales the same key by 1/10. | Fixed: public delta_pro.py uses OutWattsDcSensorEntity. |
| [#452](https://github.com/tolwi/hassio-ecoflow-cloud/issues/452) | Single Axis Solar Tracker | new device / feature | Support request. | EcoFlow refuses docs; MITM shows no control cmds. | Not feasible now. |
| [#445](https://github.com/tolwi/hassio-ecoflow-cloud/issues/445) | - | not a bug / user setup | Energy device_class request. | Energy sensors use device_class energy (sensor.py). | Close. |
| [#444](https://github.com/tolwi/hassio-ecoflow-cloud/issues/444) | RIVER 3 Plus | duplicate | Request support for new device River 3 Plus |  | Duplicate of #588. |
| [#431](https://github.com/tolwi/hassio-ecoflow-cloud/issues/431) | Power Kit | duplicate | No devices after setup. |  | Duplicate of #878. |
| [#428](https://github.com/tolwi/hassio-ecoflow-cloud/issues/428) | DELTA Pro 3 (public) | not a bug / user setup | Added as 'DELTA Pro' / signature errors. | Wrong device type per comments. | Close. |
| [#418](https://github.com/tolwi/hassio-ecoflow-cloud/issues/418) | DELTA Pro 3 (public) | fixed in fork | AC HV/LV switch request; refresh. | public delta_pro_3.py:202-226 has both switches; refresh = #772. | Close switch part. |
| [#415](https://github.com/tolwi/hassio-ecoflow-cloud/issues/415) | - | fixed in fork | High CPU. | #883 fix. | Close. |
| [#407](https://github.com/tolwi/hassio-ecoflow-cloud/issues/407) | - | stale / unclear | Old version. |  | Close. |
| [#406](https://github.com/tolwi/hassio-ecoflow-cloud/issues/406) | DELTA 2 Max (public) | not a bug / user setup | 'signature is wrong', goes offline. | Regenerating the key fixed it (several users). | Close. |
| [#405](https://github.com/tolwi/hassio-ecoflow-cloud/issues/405) | - | not a bug / user setup | Data once after load, signature wrong. | Key regeneration. | Duplicate of #406. |
| [#404](https://github.com/tolwi/hassio-ecoflow-cloud/issues/404) | PowerStream | fixed in fork | Values stuck overnight. | Reset-on-offline. | Close. |
| [#403](https://github.com/tolwi/hassio-ecoflow-cloud/issues/403) | PowerStream | not a bug / user setup | Question internal vs public module. | Chosen by login type. | Close. |
| [#402](https://github.com/tolwi/hassio-ecoflow-cloud/issues/402) | WAVE 2 | fixed in fork | Setpoint limited to 0-40 C on a Fahrenheit device. | Fork has upstream #899 (70a682e): Wave2SetTempEntity follows pd.tempSys, 16-30 C / 60-86 F, per wave_air_conditioner.md. | Close. |
| [#401](https://github.com/tolwi/hassio-ecoflow-cloud/issues/401) | RIVER Pro (public) | new device / feature | Public API selection. | No public RIVER Pro doc in research repo. | Feature; needs public quota dump. |
| [#400](https://github.com/tolwi/hassio-ecoflow-cloud/issues/400) | - | not a bug / user setup | Docs request. |  | Close. |
| [#396](https://github.com/tolwi/hassio-ecoflow-cloud/issues/396) | - | fixed in fork | KeyError 'productName' with DELTA 3 / RIVER 3 on account. | public_api.py:51 uses .get('productName','undefined'). | Close. |
| [#395](https://github.com/tolwi/hassio-ecoflow-cloud/issues/395) | DELTA 3 Plus | duplicate | Add support for Delta 3 Plus units |  | Duplicate of #557. |
| [#393](https://github.com/tolwi/hassio-ecoflow-cloud/issues/393) | RIVER 3 | fixed in fork | Support request. | RIVER_3 (internal) in fork. | Close. |
| [#392](https://github.com/tolwi/hassio-ecoflow-cloud/issues/392) | DELTA Max | fixed in fork | AC charging slider unknown. | internal delta_max.py:186-190 uses inv.cfgSlowChgWatts + id 69 (the fix from #159). | Close. |
| [#389](https://github.com/tolwi/hassio-ecoflow-cloud/issues/389) | PowerStream | stale / unclear | v1.1.0. |  | Close. |
| [#385](https://github.com/tolwi/hassio-ecoflow-cloud/issues/385) | RIVER 2 | fixed in fork | Solar V/A zero. | river2.py:59-60 reads mppt.inAmp/inVol. | Close. |
| [#384](https://github.com/tolwi/hassio-ecoflow-cloud/issues/384) | PowerStream | fixed in fork | Permanent power control. | Custom load power number. | Close. |
| [#381](https://github.com/tolwi/hassio-ecoflow-cloud/issues/381) | RIVER 3 | not a bug / user setup | Question. |  | Close. |
| [#379](https://github.com/tolwi/hassio-ecoflow-cloud/issues/379) | RIVER 2 Pro | stale / unclear | 1.2.0. |  | Close. |
| [#377](https://github.com/tolwi/hassio-ecoflow-cloud/issues/377) | DELTA 2 | not a bug / user setup | Remaining time shown as minutes (HA frontend). |  | Close. |
| [#371](https://github.com/tolwi/hassio-ecoflow-cloud/issues/371) | DELTA Max | needs device data | Solar in off by 10 (1.2.0). | delta_max.py:66 mppt.inWatts via InWattsSolarSensorEntity (/10); direction not stated. | Need app vs HA values on current version. |
| [#366](https://github.com/tolwi/hassio-ecoflow-cloud/issues/366) | Glacier (public) | new device / feature | Public API option. | api-docs/glacier.md exists; no public Glacier class. | New-device candidate with doc. |
| [#364](https://github.com/tolwi/hassio-ecoflow-cloud/issues/364) | RIVER 2 Pro | stale / unclear | 1.2.0. |  | Close. |
| [#362](https://github.com/tolwi/hassio-ecoflow-cloud/issues/362) | - | stale / unclear | Old version KeyError 'type'. |  | Close. |
| [#361](https://github.com/tolwi/hassio-ecoflow-cloud/issues/361) | several | core (api-core session) | Only syncing with app open. |  | api-core. |
| [#359](https://github.com/tolwi/hassio-ecoflow-cloud/issues/359) | PowerStream | new device / feature | Energy sensor from device totals. | Fork has watth daily sums (internal powerstream). | Partly done; see #536. |
| [#355](https://github.com/tolwi/hassio-ecoflow-cloud/issues/355) | - | core (api-core session) | Data stops after reboots (client ids). |  | api-core. |
| [#352](https://github.com/tolwi/hassio-ecoflow-cloud/issues/352) | PowerStream | fixed in fork | Power demand control. | Custom load power. | Close. |
| [#350](https://github.com/tolwi/hassio-ecoflow-cloud/issues/350) | RIVER 2 Pro | fixed in fork | Fewer entities, min discharge missing. | river2_pro.py:92-136 has max/min/backup levels. | Close. |
| [#346](https://github.com/tolwi/hassio-ecoflow-cloud/issues/346) | PowerStream | fixed in fork | Battery values not reset offline. | Reset-on-offline. | Close. |
| [#340](https://github.com/tolwi/hassio-ecoflow-cloud/issues/340) | - | stale / unclear | No values. |  | Close. |
| [#339](https://github.com/tolwi/hassio-ecoflow-cloud/issues/339) | DELTA 2 Max / DELTA 2 / DELTA Pro | fixed in this PR | Enabling backup reserve resets the level to 50 %. | Switch sent bpPowerSoc = value * 50. | Fixed: send the current level (delta2.py, delta2_max.py, delta_pro.py internal+public). |
| [#335](https://github.com/tolwi/hassio-ecoflow-cloud/issues/335) | Glacier | stale / unclear | Device deleted on restart (2024). |  | Close. |
| [#334](https://github.com/tolwi/hassio-ecoflow-cloud/issues/334) | - | core (api-core session) | Public API freeze. |  | api-core. |
| [#331](https://github.com/tolwi/hassio-ecoflow-cloud/issues/331) | PowerStream | stale / unclear | v1.1.0. |  | Close. |
| [#329](https://github.com/tolwi/hassio-ecoflow-cloud/issues/329) | DELTA 2 | core (api-core session) | Only with app open. |  | api-core. |
| [#328](https://github.com/tolwi/hassio-ecoflow-cloud/issues/328) | Smart Plug (public) | stale / unclear | Values not updating (2024). | Rebind fixed per comments. | Close. |
| [#326](https://github.com/tolwi/hassio-ecoflow-cloud/issues/326) | DELTA Max | fixed in fork | AC charging power not working. | Same fix as #392. | Close. |
| [#325](https://github.com/tolwi/hassio-ecoflow-cloud/issues/325) | PowerStream / RIVER | stale / unclear | 2024 update. |  | Close. |
| [#324](https://github.com/tolwi/hassio-ecoflow-cloud/issues/324) | DELTA 2 Max | bug confirmed | Timeout selects swapped. | delta2_max.py:419-444: 'Unit timeout' reads inv.standbyMin (doc: AC standby) but writes moduleType 1 (doc: device standby, read back as pd.standbyMin); 'AC timeout' reads/writes mppt.carStandbyMin (doc: car/12 V standby, moduleType 5). Confirmed by a second user 2025-11. | Fix needs a decision on entity identity (unique_id = key); proposal in report. Delta/River session. |
| [#323](https://github.com/tolwi/hassio-ecoflow-cloud/issues/323) | DELTA 2 + extra battery | new device / feature | AC charge max 1200 vs 1500 with extra battery. | Static max in delta2.py. | Feature: dynamic max. |
| [#320](https://github.com/tolwi/hassio-ecoflow-cloud/issues/320) | DELTA Max | fixed in fork | Set commands 'invalid parameter'. | Commands moved to TCP/id style (id 66/34/69) as in delta_max.py. | Close. |
| [#307](https://github.com/tolwi/hassio-ecoflow-cloud/issues/307) | DELTA Pro / PowerStream | core (api-core session) | 2024 data stop. |  | Close / api-core. |
| [#289](https://github.com/tolwi/hassio-ecoflow-cloud/issues/289) | several | core (api-core session) | Data freeze (2024). |  | api-core. |
| [#283](https://github.com/tolwi/hassio-ecoflow-cloud/issues/283) | DELTA Pro and others | core (api-core session) | Only populates with app open. |  | api-core. |
| [#279](https://github.com/tolwi/hassio-ecoflow-cloud/issues/279) | PowerStream | stale / unclear | Smart plug loads spike to 7 MW at 01:00 (2024). | No data. | Close unless reproduced. |
| [#268](https://github.com/tolwi/hassio-ecoflow-cloud/issues/268) | DELTA Pro | new device / feature | Show error codes. |  | Feature. |
| [#264](https://github.com/tolwi/hassio-ecoflow-cloud/issues/264) | RIVER Max | not a bug / user setup | Battery level lower than app with extra battery. | Main vs combined SoC. | Close. |
| [#262](https://github.com/tolwi/hassio-ecoflow-cloud/issues/262) | PowerStream | not a bug / user setup | Energy dashboard. | Use integration helper / energy sensors. | Close. |
| [#261](https://github.com/tolwi/hassio-ecoflow-cloud/issues/261) | - | not a bug / user setup | Local MQTT question. |  | Close. |
| [#258](https://github.com/tolwi/hassio-ecoflow-cloud/issues/258) | DELTA 2 | new device / feature | Battery energy sensors for Energy view. |  | Feature. |
| [#256](https://github.com/tolwi/hassio-ecoflow-cloud/issues/256) | RIVER 2 Pro | stale / unclear | 2024. |  | Close. |
| [#255](https://github.com/tolwi/hassio-ecoflow-cloud/issues/255) | DELTA 2 + extra battery | duplicate | Delta 2 Extra battery |  | Duplicate of #323. |
| [#247](https://github.com/tolwi/hassio-ecoflow-cloud/issues/247) | DELTA Pro | stale / unclear | 0.13.1. |  | Close. |
| [#244](https://github.com/tolwi/hassio-ecoflow-cloud/issues/244) | unknown | stale / unclear | Solar in x10, device unknown. |  | Close. |
| [#239](https://github.com/tolwi/hassio-ecoflow-cloud/issues/239) | PowerStream | fixed in fork | Relay status / temps. | llcTemp, invTemp, espTemp sensors exist (internal powerstream.py:158-202); EcoFlow sends 0 for invTemp. | Close. |
| [#225](https://github.com/tolwi/hassio-ecoflow-cloud/issues/225) | - | stale / unclear | Old MQTT log error. |  | Close. |
| [#220](https://github.com/tolwi/hassio-ecoflow-cloud/issues/220) | PowerStream | fixed in fork | Reset output when offline. | Reset-on-offline. | Close. |
| [#216](https://github.com/tolwi/hassio-ecoflow-cloud/issues/216) | - | not a bug / user setup | HACS default. |  | Close. |
| [#214](https://github.com/tolwi/hassio-ecoflow-cloud/issues/214) | DELTA Pro | fixed in fork | mAh with device_class current warning. | CapacitySensorEntity has no device_class (sensor.py:554). | Close. |
| [#210](https://github.com/tolwi/hassio-ecoflow-cloud/issues/210) | several | core (api-core session) | utf-8 decode / 'Trying to load json' log noise. | devices/__init__.py:168-181 logs WARNING+ERROR for every non-JSON frame; River 3 path fixed here. | api-core: base JSON fallback noise. |
| [#209](https://github.com/tolwi/hassio-ecoflow-cloud/issues/209) | RIVER Max | fixed in fork | maxChargeSoc command. | river_max.py:134-138 uses id 49 maxChgSoc. | Close. |
| [#206](https://github.com/tolwi/hassio-ecoflow-cloud/issues/206) | - | fixed in fork | Failed to set up without internet. | ConfigEntryNotReady (#631) + aiohttp errors caught. | Close. |
| [#174](https://github.com/tolwi/hassio-ecoflow-cloud/issues/174) | PowerStream | fixed in fork | Dynamic power adjustment. | Custom load power number. | Close. |
| [#169](https://github.com/tolwi/hassio-ecoflow-cloud/issues/169) | PowerStream | fixed in fork | Spikes after offline. | Reset-on-offline. | Close. |
| [#165](https://github.com/tolwi/hassio-ecoflow-cloud/issues/165) | PowerStream | stale / unclear | 2023. |  | Close. |
| [#159](https://github.com/tolwi/hassio-ecoflow-cloud/issues/159) | DELTA Max | fixed in fork | AC charging power. | delta_max.py:186-190. | Close. |
| [#157](https://github.com/tolwi/hassio-ecoflow-cloud/issues/157) | PowerStream | fixed in fork | Values stuck offline. | Reset-on-offline. | Close. |
| [#141](https://github.com/tolwi/hassio-ecoflow-cloud/issues/141) | PowerStream | fixed in fork | Inverter temps. | See #239. | Close. |
| [#136](https://github.com/tolwi/hassio-ecoflow-cloud/issues/136) | - | not a bug / user setup | Info. |  | Close. |
| [#128](https://github.com/tolwi/hassio-ecoflow-cloud/issues/128) | DELTA Pro | stale / unclear | Extra battery (2023). |  | Close. |
| [#127](https://github.com/tolwi/hassio-ecoflow-cloud/issues/127) | Solar Tracker | duplicate | Miss new Single Axis Solar Tracker |  | Duplicate of #452. |
| [#55](https://github.com/tolwi/hassio-ecoflow-cloud/issues/55) | RIVER Max | stale / unclear | Input voltage 0 (2023). | river_max.py:75 inv.acInVol exists. | Ask to retest. |
| [#54](https://github.com/tolwi/hassio-ecoflow-cloud/issues/54) | PowerStream | fixed in fork | PowerStream support. | Internal + public PowerStream. | Close. |
| [#49](https://github.com/tolwi/hassio-ecoflow-cloud/issues/49) | RIVER 2 Max | fixed in fork | Solar V/A sensors. | river2_max.py:59-60. | Close. |
| [#47](https://github.com/tolwi/hassio-ecoflow-cloud/issues/47) | Blade mower | new device / feature | New device. | Old captures in issue. | Not planned. |
| [#42](https://github.com/tolwi/hassio-ecoflow-cloud/issues/42) | Smart Generator | new device / feature | New device. | Diagnostics in issue; upstream PR #929. | See #698. |

## STREAM / Smart Meter issues (other session, not triaged here)

#494, #504, #521, #524, #528, #533, #534, #540, #548, #549, #551, #567, #579, #582, #594, #613, #647, #653, #654, #663, #664, #665, #673, #679, #686, #689, #713, #717, #723, #745, #771, #776, #786, #803, #808, #811, #818, #843, #862, #893, #908, #922, #934
