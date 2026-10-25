# Triage: open tolwi issues for STREAM, Smart Meter and the shared core

Snapshot: `TelosNox/ecoflow-research` `issues/tolwi.jsonl` of 2026-10-25 (232 open issues).
Checked against this fork's `main` at `b228f12`, not against the version each reporter ran.
Scope: every open issue about STREAM (any model, incl. STREAM Microinverter), the EcoFlow
Smart Meter, or the shared core (auth, config flow, MQTT connection, setup errors,
HA-version breakage, logging). Issues that only concern another device (Delta, River,
PowerStream, PowerOcean, Power Kit, Glacier, Wave, SHP) are left out unless they report a
core failure. That makes 102 issues.

All issue numbers are `tolwi/hassio-ecoflow-cloud#n`. "fork:" means a commit in this repository.
`1cd3095` is the root of the fork's shallow history: code that already exists there came from
upstream before the fork history starts.

## Fixed on this branch

| Commit | Issue | Change |
|---|---|---|
| `ec1dc79` | #908, #830 | The app-API (internal) `StreamAC` had no status sensor at all, so on the private API nothing tracked online/offline and nothing reconnected when the stream went silent. It now registers `StatusSensorEntity(..., reconnect_when_stale=True)` like the public `StreamAC` (`devices/internal/stream_ac.py:365-373`). New entity `ecoflow-<sn>-status`; no unique_id changed. Test: `tests/test_stream_ac_status.py`. |

Note: on the public API the stall reconnect was confirmed by the reporter. On the app API,
#908 shows the same symptom and the maintainer's workaround there is pressing Reconnect. That a
plain `mqtt_client.reconnect()` (same client id, no fresh login) is enough on the app API has
not been verified on a device yet. If it is not, the next step is to reconnect the way the
Reconnect button does (`button.py:42-45`: stop, `login()`, start).

## Verdicts

Categories: **fixed in fork** · **bug (fork)** = confirmed in the fork's code · **dup** ·
**needs data** · **feature** · **not a bug / setup** · **stale/unclear**.

### STREAM (BK series, incl. STREAM Microinverter) and Smart Meter

| Issue | Title | Category | Verdict | Evidence / location | Action |
|---|---|---|---|---|---|
| #922 | STREAM Feed-in Control resets to OFF | needs data | No code path in the fork publishes a set command except HA service handlers (`switch.py:50-58`, `number.py`, `select.py`, `button.py`; the only `publish` callers are `api/__init__.py:145,152`). A state change with `user_id=null` is what every state the integration pushes looks like in the recorder, so it is not evidence of a write. The diagnostic "set" log lists everything seen on the subscribed `/set` topic, including commands from any other client that uses the same key (a second HA instance or config entry also sends `"from": "HomeAssistant"`). | Ask for a debug log of `custom_components.ecoflow_cloud.api.ecoflow_mqtt` (the `Sending ...` lines) around the 2→1 change, and whether another HA instance uses the same developer key. See core finding C6. |
| #893 | Stream Ultra: no charged/discharged energy (private API) | needs data | On the app API `stream_ac.proto` has no field for `accuChgEnergy`/`accuDsgEnergy`, so the sensors registered in `devices/internal/stream_ac.py` can never get a value. The public API provides them (`devices/public/stream_ac.py:44,48`). | Needs a raw app-API capture taken together with a public `quota/all` read, so the field can be mapped. Workaround: public API. |
| #686 | Stream AC Pro: battery power sign, cumulative energy | needs data | Sign: `powGetBpCms` is <0 discharge / >0 charge by design. Cumulative energy on the private API: same gap as #893. | Same as #893. |
| #862 | SoC entity named "Power Battery" | fixed in fork | fork `c0f22dc`. | — |
| #843 | Stream Ultra SoC always unknown (private API) | fixed in fork | `Champ_cmd21_2_field9` is mapped onto `soc`, field 15 onto `f32ShowSoc` (`devices/internal/stream_ac.py`, `_CHAMP_FIELD_ALIASES`; upstream PR #846, fork `d089057`). | — |
| #549 | Stream AC Pro: no battery charge | needs data | The 2025 report is pre-1.4. A 2026-08 comment (v1.7.1, AC Pro) still has `soc` at 0. On the private API `soc` comes from `Champ_cmd21_2_field9`, which was decoded on an Ultra X only. | Needs a raw app-API frame from an AC Pro, plus the API type. |
| #524 | Stream AC Pro / Pro battery percentage | stale/unclear | `soc` (public) and field 9 (private) exist since 1.4/`d089057`. No report against a current version. | Re-test on the fork. |
| #567 | STREAM AC Pro: no entities (1.3.0) | stale/unclear | 1.3.0. The AC Pro is covered by the `Stream AC` / `STREAM_AC` types today. "Disabled by config entry" means the entry itself was disabled. | Re-test. |
| #494 | STREAM AC PRO support | fixed in fork | Supported as `Stream AC` (public) / `STREAM_AC` (private). | — |
| #776 | Stream AC Pro (BK31) detected as PowerStream | needs data | The device type comes from `productName` in `/device/list` (`api/public_api.py:51-61`). The registry has no "Stream AC Pro" key, so an unmatched name only sets the dropdown default and the user picks the type. | Needs the raw `/device/list` entry (`productName`, `deviceName`) for a BK31. |
| #713 | Stream Max support | feature | Works when added as Stream Pro/Ultra (comment). `stream.md` documents the Max's single AC switch as `cfgRelay2Onoff`, which only the existing AC1 switch sends. | New device type. |
| #745 | Stream Microinverter (US) | feature | New variant. | — |
| #771 | PV Sum 0 on Ultra X after FW 1.0.2.1 | not a bug | `powGetPvSum`, `powGetSysLoad*` and `powGetBpCms` are system values that only the master unit reports (measured). The comments show the values moving to the AC Pro, i.e. the master role moved. Per-unit alternative: "PV Total" (fork `de59cfa`). | — |
| #663 | No PV Sum on Ultra X | not a bug | Same as #771 (master holds the sum). | — |
| #582 | Values 0 after FW 1.0.1.41 | not a bug | Same mechanism. The comments confirm the readings moved to the AC Pro. | — |
| #786 | PV Sum shows AC charging | needs data | A device/cloud data defect: samples alternate between `powGetPvSum`≈grid charge with `powGetSysGrid`=0 and correct samples (comment with raw samples; evcc sees the same values from `quota/all`). The integration passes the values through unchanged. | Check whether the per-string values (and with them fork "PV Total", `de59cfa`) stay correct in affected samples. If they do, that sensor is the mitigation. No heuristic filter without that data. |
| #679 | STREAM charging input shown as PV at night | dup | Duplicate of #786. | — |
| #808 | Stream Ultra: cumulative PV energy | fixed in fork | fork `de59cfa` (PV Total + PV Total Energy, upstream PR #842). | — |
| #673 | PV energy meter (Stream Ultra) | fixed in fork | fork `de59cfa`. | — |
| #689 | Stream Ultra switches/slider missing | fixed in fork | Reporter's 1.3.0 was too old. Reporters confirmed with 1.4. | — |
| #934 | Switches and slider gone (HA 2026.10, 1.7.2) | needs data | In the fork the switches/number are created unconditionally for public `StreamAC` (`devices/public/stream_ac.py:347-466`). A failed `quota/all` at startup ("server busy") is caught (`api/public_api.py`, `quota_all`), and the platforms are still set up. | Needs the `homeassistant.setup` / `ecoflow_cloud` log of a startup and the device type configured in the entry. |
| #717 | Custom load / permanent watts slider (Stream Ultra) | feature | `stream.md` documents only relay2/relay3, backup reserve, feed-in control, operating mode. No power setter. | Not possible via the documented API. |
| #579 | Stream Ultra: set base power | feature | Same as #717. | — |
| #613 | Stream Ultra: custom mode | feature | `cfgEnergyStrategyOperateMode` in `stream.md` covers self-powered / AI only. | — |
| #818 | STREAM Max Charge Level writable | feature | `stream.md` has no `cfgMaxChgSoc` for STREAM. | — |
| #594 | STREAM Microinverter output control | feature | No documented setter for `feedGridModePowLimit`. | — |
| #803 | Stream Microinverter regulation | dup | Duplicate of #594. | — |
| #534 | Stream AC: plug status / watts | feature | `powGetSchuko1/2` exist as disabled sensors (`devices/public/stream_ac.py:252-254`). | — |
| #533 | STREAM Microinverter: more entities | feature | — | — |
| #528 | Microinverter: enable disabled entities | not a bug / setup | Disabled entities are enabled in the HA entity settings, not in code. | — |
| #504 | How to add the Stream Microinverter | not a bug / setup | Supported (`Stream Microinverter` / `STREAM_MICROINVERTER`). | — |
| #548 | Microinverter 800 W only shows status | stale/unclear | 2025-08, no version info. | Re-test. |
| #521 | Ideas for the Stream series | feature | Partly done: AC1/AC2 switches, PV energy (`de59cfa`). | — |
| #653 | Cell voltages / temperatures (Ultra X) | feature | — | — |
| #665 | Additional sensors (Stream Ultra) | stale/unclear | No field list given. | — |
| #664 | Data refresh rate Stream Ultra X | fixed in fork | Telemetry stall → stall reconnect (fork `64187ab`, `83b10f5`, backoff `e76b27b`). | — |
| #811 | Up/down values, no data (Stream, Microinverter) | fixed in fork | Same stall. Reporters fixed it by pressing Reconnect every 5 min. The fork does this itself for public STREAM AC/Microinverter (`64187ab`), and for the app-API STREAM on this branch (`ec1dc79`). | — |
| #651 | Wrong Power AC when Stream Micro is offline | fixed in fork | Offline reset (upstream #656, fork `4286bc8`, option `a7ebbba`). A later comment reports zeros while producing: the microinverter's 5-15 min report gap exceeds `assume_offline_sec`, a setting. | — |
| #540 | Stream: "not allowed to get device info" | stale/unclear | EcoFlow-side restriction of 2025-07. Comments report it working again from 2025-09 with no change on the user side. | — |
| #541 | "not allowed to get device info" | stale/unclear | Same as #540. | — |
| #724 | "not allowed to get device info" (Power Kit v2) | not a bug / setup | Same EcoFlow error text: the device is not available to this developer key. | — |
| #908 | Data only updates after opening the app (Stream Ultra, private API) | fixed on this branch | No status sensor / stall reconnect on the app-API STREAM. | `ec1dc79` |
| #830 | Values stop until app is opened (STREAM AC Pro + Wave 3, private API) | fixed on this branch | Same as #908 for the STREAM part. The Wave 3 has no stall reconnect (out of scope). | `ec1dc79` |
| #654 | Smart Meter flips to assume_offline | fixed in fork | Public Smart Meter reconnects on stale data (fork `f54d916`, backoff `e76b27b`). The issue is filed as "Internal/Private API" but mentions renewing public keys. The app-API meter still has no stale reconnect (`devices/internal/smart_meter.py:400-401`). | If an app-API user confirms the stall, add `reconnect_when_stale=True` there too. |
| #647 | Smart Meter always 0 W (private API, 1.3.0) | needs data | The logged error (`'utf-8' codec can't decode` from `devices/__init__.py`) comes from the JSON parser, which the fork's app-API `SmartMeter` replaces with protobuf decoding (`devices/internal/smart_meter.py`, `_prepare_data`). So the reporter's entry did not run the protobuf decoder (older version or another device type). | Re-test on the fork with type `SMART_METER`. If still 0, send a debug log with the `cmd_func`/`cmd_id` lines. |
| #551 | Virtual clone of the Smart Meter | feature | Not something the cloud API offers. | — |

### Core: auth, config flow, MQTT, setup, HA versions, logging

| Issue | Title | Category | Verdict | Evidence / location | Action |
|---|---|---|---|---|---|
| #947 | Credentials logged at INFO | fixed in fork | fork `3e82225`. | — |
| #932 | Broken after HA 2026.10 | dup | Duplicate of #928. | — |
| #930 | Broken with HA 2026.10 | dup | Duplicate of #928. | — |
| #928 | protobuf==6.32.0 conflicts with HA 2026.10 | fixed in fork | `manifest.json:17` `protobuf>=6.32.0,<8` (upstream `38986e6`). CI resolves the manifest against HA's constraints (fork `78bf8da`). | — |
| #554 | Fails after HA core update (2025-08) | stale/unclear | No log. The same kind of failure as #928. | — |
| #835 | Breaks with HAOS 18.1 (jsonpath-ng not found) | not a bug / setup | `RequirementsNotFound` = HA's pip could not download. A counter-report runs the same stack fine. | — |
| #912 | Will not load: jsonpath-ng not found | not a bug / setup | Same. Comments trace it to DNS on the HA host. | — |
| #558 | jsonpath-ng 1.7.0 download error | not a bug / setup | `Failed to fetch ... wheels.home-assistant.io`: network. | — |
| #874 | Stopped working on HA 2025.1 after 1.1.0 → 1.5.0 | not a bug / setup | HA 2025.1 is too old for current releases (pyproject targets HA 2026.8 / Python 3.14). `hacs.json:4` still declares HA 2024.8.0, so HACS offers the update anyway. | Core finding C7. |
| #872 | River 3 Max: errors after 1.5.0 | fixed in fork | The `IntegrationSensor` `hass` argument removed in HA 2026.8 is handled (`sensor.py:63-64`). The JSON-parse log flood in the same report is open (C3). | — |
| #883 | CPU saturated: jsonpath re-parsed per update | fixed in fork | upstream `7cbf214`. | — |
| #415 | High CPU load | fixed in fork | Same root cause as #883 (`7cbf214`). | — |
| #493 | Crashes on restart, UI lag (1.3.0b6) | fixed in fork | The UI lag matches #883 (`7cbf214`). No log for the crash. | — |
| #877 | Error setting up entry: socket.gaierror at MQTT connect | bug (fork) | `api/ecoflow_mqtt.py:54-57` catches only `TimeoutError`. A DNS failure (`socket.gaierror`) or a refused connection escapes `EcoflowMQTTClient.__init__` → `api_client.start` (`__init__.py:307`) → the entry fails without `ConfigEntryNotReady`, so HA never retries. | Core finding C1 (api-core). |
| #206 | "Failed to set up" after reboot without internet | bug (fork) | Login failures retry since `fbb66dd` (`__init__.py:277-288`). The MQTT connect with no DNS still fails hard (#877). | C1. |
| #735 | Failed to set up: TimeoutError at MQTT connect | fixed in fork | upstream `f120947` (`api/ecoflow_mqtt.py:56`). | — |
| #813 | Not connecting: DNS timeout at login | fixed in fork | `aiohttp.ClientError` → `ConfigEntryNotReady` (`__init__.py:277-281`, `fbb66dd`). | — |
| #598 | KeyError 'data' when adding a device (public) | bug (fork) | `api/public_api.py:48` `for device in response["data"]` fails when `/device/list` succeeds without `data` (the reporter's key has no device bound). The config flow aborts with "unknown". | Core finding C2. |
| #396 | "unknown": KeyError 'productName' | fixed in fork | `api/public_api.py:51` uses `.get("productName", "undefined")` + name-prefix match. | — |
| #791 | Public API login "Unknown" | not a bug / setup | Comments: the developer account email differed from the app account. | — |
| #856 | Installed, no devices or entities | stale/unclear | No log. Reports "Integration Version 1.14.0", which does not exist. | — |
| #471 | Config flow 500 error (v1.2.0) | stale/unclear | Old version. Reinstall fixed it (comment). | — |
| #804 | API host setting not stored | stale/unclear | The fork's reconfigure flow writes `api_host` from the form into `new_data` and saves it (`config_flow.py:290-293`, `update_or_create`). Cannot be reproduced from the code. The reporter put the public host into the app-API form. | — |
| #678 | Data refresh period ignored | fixed in fork | Options edits were never saved (fork `f630d1d`, `config_flow.py:578-581`). | — |
| #782 | PowerStream: interval change has no effect, freezes | fixed in fork | Interval: `f630d1d`. The freeze part is the stall, see #560. PowerStream has no stall reconnect. | — |
| #901 | MQTT "Not authorized" repeatedly (public) | needs data | The fork stops paho from retrying rejected credentials and opens a reauth flow (`api/ecoflow_mqtt.py:126-135`, `api/__init__.py:172`, upstream `1234644`). Root cause is EcoFlow-side: new keys help for <2 days, a reboot (fresh `/certification`) does not (#876). One comment shows `Client identifier not valid`. | Needs a debug log of the first rejection after a working phase, and whether other clients (evcc, Node-RED, a 2nd HA) use the same key. Top-5 item 2. |
| #876 | Public MQTT credentials rejected | needs data | Same as #901. | — |
| #886 | Excessive DNS lookups | needs data | `api/public_api.py:85` opens a new `aiohttp.ClientSession` per call (no connection reuse). Lookups of `mqtt-e` every 15-30 s point to MQTT reconnects, which the refresh period does not affect. | Needs an `ecoflow_mqtt` INFO log ("Re-connecting", "MQTT disconnect"). Core finding C4. |
| #684 | Excessive retry / polling, suggest backoff | fixed in fork (partly) | Setup retries go through HA's `ConfigEntryNotReady` backoff (`fbb66dd`). Stale reconnects back off up to 1 h (`e76b27b`). Rejected credentials stop retrying (`1234644`). Not covered: a cooldown for `quota/all` polls on HTTP errors. | Remaining part is a feature. |
| #819 | AC output disabled after MQTT reconnect (Delta UPS) | needs data | As for #922: there is no write-back on reconnect or startup in the fork. Only HA service calls publish to `/set`. A null-context state change is a pushed state, not a command. | Ask for the `ecoflow_mqtt` debug log (`Sending ...`). C6. |
| #283 | Delta Pro only updates while the app is connected (245 comments) | fixed in fork (STREAM/SM) | The canonical stall issue. The fork reconnects on stale data for public STREAM AC, Microinverter, Smart Meter and now the app-API STREAM. Other device types (Delta, PowerStream, ...) have no stall reconnect. | Top-5 item 1. |
| #289 | Data freeze | dup | Duplicate of #283/#560. | — |
| #361 | Data only syncs with the app open | dup | Duplicate of #283/#560. | — |
| #560 | EcoFlow updates freeze | fixed in fork (STREAM/SM) | `64187ab`, `83b10f5`, `f54d916`, `e76b27b`. | — |
| #355 | Data not updated after HA reboots (1.2.0) | dup | Duplicate of #283. | — |
| #334 | Data freeze with public API | dup | Duplicate of #283. | — |
| #746 | Freeze or '0' (PowerStream) | dup | Duplicate of #560. No stall reconnect for PowerStream. | — |
| #758 | Still freezing (PowerStream, Stream) | dup | Duplicate of #560. The Stream part is fixed in fork. | — |
| #764 | Slow update (Delta Pro 3, public) | dup | Duplicate of #560. Not covered for DP3. | — |
| #499 | Values frozen while the cloud is down | fixed in fork | Offline reset (upstream #656, `4286bc8`, `a7ebbba`). | — |
| #592 | Disconnected items show the previous value | fixed in fork | Same (`4286bc8`). | — |
| #562 | Set PowerStream values to zero when offline | fixed in fork | Same. | — |
| #210 | UnicodeDecodeError log flood | bug (fork) | `devices/__init__.py:168-181`: every binary (protobuf) frame that reaches a JSON device class logs one WARNING ("Trying to load json") and one ERROR ("constant: ... Ignoring message"). A 2026-08 comment counts 5263 of each per day on 1.7.x. | Core finding C3. |
| #225 | MQTT error in log (2024, `mqtt/ecoflow_mqtt.py`) | stale/unclear | That module no longer exists. Today's form of it is #210. | — |
| #460 | Exception "signature is wrong" in quota_all | stale/unclear | 2025-03. The comment points to wifi drops / a key to renew. No current report. | — |
| #405 | Data only once after load | stale/unclear | Same trace as #460. 2025-01. | — |
| #407 | Integration stopped working (old import `POWER_WATT`) | fixed in fork | The reporter ran very old files. | — |
| #362 | KeyError 'type' after update from 0.13 | stale/unclear | Migration from 0.13 (2024). Removing and re-adding fixed it. | — |
| #340 | No more values displayed | stale/unclear | 2024, no data. | — |
| #247 | No data from the cloud | stale/unclear | 2024. | — |
| #565 | Second device shows only zeros | stale/unclear | 2025-08, PowerStream, no log. | — |
| #575 | Device connected but everything zero | stale/unclear | River 2 Max after firmware v3 (comments). Device-specific. | — |
| #566 | Missing from HACS | not a bug / setup | Repository listing, not code. | — |
| #216 | Add as HACS default repository | feature | Repository listing. | — |
| #400 | Install documentation | feature | Docs. | — |
| #261 | Local MQTT server | feature | — | — |

## Core findings for the api-core session

Not edited here (rule 7). Each finding has its evidence and a proposed fix.

- **C1 – setup fails hard when the broker cannot be resolved** (#877, #206). `api/ecoflow_mqtt.py:54-57`
  catches `TimeoutError` only. `socket.gaierror` and `ConnectionRefusedError` (both `OSError`)
  propagate out of `EcoflowMQTTClient.__init__` and `api_client.start` (`__init__.py:307`), so
  the entry ends in "Error setting up entry" and HA does not retry. Fix: catch `OSError` there
  (`TimeoutError` is a subclass), so paho's `reconnect_on_failure` retries the way it already
  does after a timeout. Alternative: wrap the `start` call in `__init__.py` and raise
  `ConfigEntryNotReady`.
- **C2 – KeyError 'data' on an account without devices** (#598). `api/public_api.py:48`. Fix:
  `for device in response.get("data") or []:`, so the flow ends in its existing
  `no_device_to_add` abort instead of "unknown".
- **C3 – one WARNING and one ERROR per binary frame** (#210, #872, #647). `devices/__init__.py:168-181`:
  the payload is decoded with `errors="ignore"`, which never raises, then parsed again from bytes,
  which raises `UnicodeDecodeError`. Fix: when the stripped payload does not start with `{`,
  return `{}` with a single DEBUG line (or warn once per device). Drop the second
  `json.loads(raw_data)`.
- **C4 – a new HTTP session per API call** (#886). `api/public_api.py:85` opens a fresh
  `aiohttp.ClientSession` per request: no keep-alive, a DNS lookup each time. Use HA's
  `async_get_clientsession(hass)`, which means passing `hass` into the client. Low priority.
  Also `api/public_api.py:46` logs the full `/device/list` response at INFO on every status poll.
  DEBUG is enough.
- **C5 – rejected MQTT credentials** (#901, #876). The fork's stop-and-reauth is correct for a
  bad key. The reports, though, describe keys that work and then stop after 1-2 days, which a
  reboot (fresh `/certification`) does not cure. That is not fixable client-side without more
  data. Worth logging the CONNACK reason together with the time since the last successful
  connect, and counting connects per client id (EcoFlow limits client ids per day, see the note
  in `api/public_api.py:18-23`).
- **C6 – outgoing commands are not traceable** (#922, #819). The only writers are HA service
  handlers, but `EcoflowMQTTClient.publish` logs at DEBUG only (`api/ecoflow_mqtt.py`,
  `publish`), so a user cannot show what was sent and when. Log every `/set` publish at INFO
  (topic, params, no credentials). Note for the analysis: paho keeps QoS 1 messages published
  while disconnected and sends them after the reconnect, so a command issued during an outage
  arrives late.
- **C7 – HACS minimum HA version is far too low** (#874). `hacs.json:4` says `2024.8.0`. The
  code targets Python 3.14 / HA 2026.8 (`pyproject.toml`, `sensor.py:63` shim). Set it to the
  oldest HA that CI actually installs.
- **Smart Meter, app API (my area, no change without evidence):** `devices/internal/smart_meter.py:316-323`
  logs "Ignoring EcoPacket for SN ..." but does not `continue`, so the packet is still decoded.
  No issue shows a wrong value from it. The app-API meter also lacks `reconnect_when_stale`
  (`:400-401`, see #654).
- **For stream-docs:** `stream.md` says that in a multi-unit system every command except
  AC1/AC2 must go to the main SN (`GET /iot-open/sign/device/system/main/sn`). The public
  `StreamAC` sends backup reserve, operating mode and feed-in control to its own SN
  (`devices/public/stream_ac.py:359-465`). Unclear whether a slave rejects them. Relevant
  context for #922.

## Top 5 open problems by impact

1. **Cloud telemetry stall on devices without stall reconnect** (#283 with 245 comments, #289,
   #361, #560, #746, #758, #764, #782). Fixed in the fork only for public STREAM AC, Microinverter
   and Smart Meter, and on this branch for the app-API STREAM, which still needs a device
   confirmation. PowerStream, Delta and the app-API Smart Meter still freeze until the app is
   opened. Next step: confirm `ec1dc79` on an app-API STREAM, then decide per device class.
2. **Public MQTT "Not authorized" after 1-2 days, cured only by new keys** (#876, #901). Total
   loss of telemetry. The cause is EcoFlow-side and unknown (C5).
3. **Unexplained setting changes: Feed-in Control OFF, AC output OFF** (#922, #819). Rare but
   safety-relevant. No write path found in the code. Needs C6 logging plus a debug log from the
   reporters.
4. **Setup crash without automatic retry when DNS fails at MQTT connect** (#877, #206). Simple
   fix (C1), affects every user whose HA starts before the network is up.
5. **Missing STREAM data on the app API** (#893, #686 cumulative energy; #549 AC Pro SoC) and the
   **log flood from binary frames** (#210, #872: thousands of ERROR lines a day, C3).
