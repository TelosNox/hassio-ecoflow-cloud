# Core findings: changes and decisions

Scope: the "core findings" that the review reports in this directory left for the core
(`api/`, `devices/__init__.py`, `devices/data_holder.py`, `entities/`, `__init__.py`,
`config_flow.py`, `hacs.json`), plus the two unique_id cases from `delta-docs.md`.
Sources: the reports in `docs/review/`, the EcoFlow developer docs in the private
`TelosNox/ecoflow-research` repo (`api-docs/general_information.md`, `api-docs/stream.md`,
`api-docs/delta_2_max.md`, `api-docs/delta_pro_3.md`), the issue snapshots there, and
the paho-mqtt 2.1.0 / Home Assistant sources this integration runs on.

Branch `fork/core-findings`, one commit per finding. Every commit message names its evidence.
Nothing here changes a unique_id, the domain or the config-entry version.

## Changed

| # | Finding | Source report | Evidence | Change | Test | Status |
|---|---|---|---|---|---|---|
| 1 | STREAM system commands go to the unit's own SN; the doc says the system's main SN | stream-docs.md U1 / C1; triage-tolwi-stream-core.md ("For stream-docs"); api-core.md suggestions | stream.md "Obtain the main device serial number of the STREAM system" (`GET /iot-open/sign/device/system/main/sn?sn=`, `data.sn`): "AC1 switch and AC2 switch are the serial number of the corresponding devices. For all other commands, you will first need to use this API"; every system command repeats it | `api/commands.py` `MainSnCache` (own SN until resolved, TTL 1 h, retry 5 min, keeps the last known SN on failure) + `stream_command_target_sn` (routes only `cfgBackupReverseSoc`, `cfgEnergyStrategyOperateMode`, `cfgFeedGridMode`; AC1/AC2 and anything else stay on the unit). Resolved at setup and from the STREAM status sensor when due; a routed command uses `/open/<acct>/<main>/set` with `sn` = main; the client subscribes to the main's `set_reply`. Only the public `StreamAC` opts in. Diagnostics show `system_main_sn` | `tests/test_stream_main_sn.py` | Fixed (`62714eb`) |
| 2a | Outgoing commands not traceable (writes "without user action") | triage-tolwi-stream-core.md C6; stream-docs.md C2; triage-tolwi-devices.md (#819) | tolwi#819, #922; publish logged at DEBUG only | One INFO line per command: device SN, main SN if routed, full JSON payload (no credentials, no topic). JSON payload built once so the logged id is the sent id | `tests/test_set_commands.py` | Fixed (`1879b87`) |
| 2b | paho's locks disabled while paho runs its own thread | found in this session (path of #819/#922) | `homeassistant/components/mqtt/async_client.py`: `setup()` replaces the 7 paho locks with `NullLock` "since the client ... will never run in multiple threads"; this client calls `loop_start()` and publishes from the event loop and executor threads | Use paho's `Client` directly (AsyncMQTTClient = Client + lock swap) | `tests/test_mqtt_client.py::test_paho_keeps_its_locks` (fails on the old code) | Fixed (`13309e8`) |
| 2c | A command can be applied long after the user action, right "after a reconnect" | triage-tolwi-stream-core.md C6 note, stream-docs.md C2, triage-tolwi-devices.md (#819) | paho 2.1.0: `publish()` keeps QoS 1 messages without PUBACK in `_out_messages`, also on `MQTT_ERR_NO_CONN` (no queue limit); `_handle_connack` resends all of them after `on_connect`, with `clean_session=True` too | `send_set_message` refuses to send while disconnected (WARNING, no optimistic state); the MQTT client drops messages older than 60 s from paho's queue in `on_connect` (WARNING) | `tests/test_mqtt_client.py`, `tests/test_set_commands.py::test_no_set_command_while_disconnected` | Fixed (`a0826ee`) |
| 2d | Audit: other paths that publish on the set topic | task | Code read: only HA service handlers call `send_set_message` (switch `turn_on/off`, number `set_native_value`, select `select_option`, button `press`, Wave 3 climate). Nothing in `async_restore_state` (SHP/SHP3 load stored data only), `_on_connect` (subscribe), stale reconnect / Reconnect button (stop, login, start), options change (reload; the app API sends a `latestQuotas` *get*), entity construction or `async_added_to_hass` | – | – | No further path found |
| 3 | `set_reply` stored for diagnostics only; optimistic state never rolled back | api-core.md finding 12; triage-shuette.md core 1 | general_information.md "Reply Topic's Common Field" (same `id`; `code` 0 / -1 / -2); stream.md "Set & Set Reply" (`data.configOk`, `actionId`); shuette #181, #185 | `evaluate_set_reply` (code != "0", `configOk` false; `ack` deliberately not judged: docs show ack 0 and 1 with code "0"), `PendingCommands` (match by id, 30 s timeout). On rejection/timeout: WARNING, optimistic value restored unless the device reported the key since or a later command changed it; failed routed command forces a new main-SN lookup. Opt-in `BaseDevice.evaluates_set_replies()`; only public `StreamAC` | `tests/test_set_commands.py` | Fixed (`bd9e9e7`) |
| 4 | DNS failure / refused connection at the first MQTT connect fails the setup without retry | triage-tolwi-stream-core.md C1 | tolwi#877 (`socket.gaierror`), #206; only `TimeoutError` was caught | Catch `OSError`, WARNING, always `loop_start()` - its `loop_forever(retry_first_connection=True)` retries (checked with paho 2.1.0 and an unresolvable host: 4 retries in 5 s at 1 s delay) | `tests/test_mqtt_client.py::test_failed_first_connect_is_retried_by_paho` | Fixed (`7ab85e8`) |
| 5 | WARNING + ERROR per binary frame in the JSON fallback | triage-tolwi-stream-core.md C3; triage-tolwi-devices.md | tolwi#210 (5263 of each per day), #872 | One parse; non-JSON at DEBUG, malformed JSON (starts with `{`) one WARNING | `tests/test_json_fallback.py` | Fixed (`d001e7d`) |
| 6 | New aiohttp session per HTTP call; `/device/list` logged at INFO on every poll | triage-tolwi-stream-core.md C4 | tolwi#886 | HA's shared session passed in from `async_setup_entry` (config flow keeps a session per call); `async with session.get`; device list at DEBUG | `tests/test_public_api.py::test_calls_reuse_the_given_session` | Fixed (`55597be`) |
| 7 | Config flow says "every device has already been added" when the account lists none | api-core.md open question 3 | general_information.md "Query the user's bound device list": "Only returns the device bound to itself, not by share"; tolwi#598, #791 | New abort `no_devices_found` naming the cause, all 8 translations | `tests/test_config_flow_devices.py` | Fixed (`161592e`) |
| 8 | `hacs.json` declares HA 2024.8.0 | triage-tolwi-stream-core.md C7 | tolwi#874; HA `package_constraints.txt`: protobuf==6.31.1 in 2025.8.0, ==6.32.0 from 2025.9.0 (manifest needs >=6.32.0) | `"homeassistant": "2025.9.0"` | – (no code) | Fixed (`dd5f2a1`) |
| 9 | Success detected by `message == "success"` | api-core.md finding 5 | general_information.md, every Response Body: "code ... 0: success" | Public client decides by `code` (message only if no code); app API unchanged | `tests/test_public_api.py` | Fixed (`2447da3`) |
| 10 | DELTA 2 Max generator start/stop levels read keys the device never sends | delta-docs.md (core: unique_id migration) | delta_2_max.md BMS `openOilSoc`/`closeOilSoc` -> `bms_emsStatus.minOpenOilEb` / `maxCloseOilEb`; `diag/delta_2_max.json` has only these | Read the documented keys, keep the old unique_ids (`entities.keep_unique_id`, the WAVE 2 pattern) instead of a registry migration, see "Why no `_migrate_entity_unique_id`" | `tests/test_delta_docs.py::TestDelta2MaxGeneratorLevels` | Fixed (`8979379`), untested on a device |
| 11 | Public DELTA Pro 3 output switches / AC charging read set-command names | delta-docs.md (core: unique_id migration) | delta_pro_3.md: quota `flowInfoAcHvOut`, `flowInfoAcLvOut`, `flowInfo12v`, `flowInfo24v` "(0: off, 2: on.)", `plugInInfoAcInChgPowMax`; same naming in the dump in tolwi#465 | `FlowInfoSwitch` (2 on, 0 off, else unchanged), slider reads the quota key, commands unchanged, unique_ids kept | `tests/test_delta_docs.py::TestPublicDeltaPro3QuotaKeys` | Fixed (`6e43c85`), untested on a device. Risk: a DELTA 3 Plus dump spells `flowInfo_12v` |
| 12 | Parse error message formats the unawaited `resp.text` | api-core.md finding 15 | `aiohttp.ClientResponse.text` is a coroutine method | Message names the HTTP status | `tests/test_public_api.py` | Fixed (`45603b2`) |

## Why no `_migrate_entity_unique_id`

Rows 10 and 11 change the key an entity reads. A registry migration would also need a
config-entry version bump (13 -> 14). `async_setup_entry` returns `False` when
`entry.version != CONFIG_VERSION`, so after a bump any older release refuses to load the
entry - a user who rolls back loses the integration until they update again. Keeping the
unique_id of the old key (`entities.keep_unique_id`, as `devices/internal/wave2.py`
already does) changes no unique_id, keeps history and automations, and needs no
migration. The rule "key changes only via `_migrate_entity_unique_id`" protects the
unique_id; here it does not change.

## Not changed, with reason

| Finding | Source report | Reason |
|---|---|---|
| `ChargingStateSensorEntity` maps 1 = charging, 2 = discharging (tolwi#920) | delta-docs.md | Shared by DELTA 2, RIVER 2 / 2 Max / 2 Pro, Glacier, Power Kit. delta_2_max.md defines `bms_emsStatus.chgState` as a charger phase (0 off, 1 CC, 2 CV, 3 UPS, 4 PARA), which would make "2" a charging phase, but the DELTA 2 doc gives no enum, #920 has no values, and "charging while discharging" is not explained by CC/CV either. A change would relabel the state for six device types without one captured value. Needs `bms_emsStatus.chgState` and `pd.chgDsgState` from a DELTA 2 while charging and while discharging |
| `data_bridge.plain_to_status` knows only the pd/bms family of type codes | other-docs.md | Only WAVE 2 needed more codes and maps them locally (`d6d8cb1`). No other device reports unknown type codes; a shared table would change keys for nothing |
| STREAM slave reports 0 for system fields | triage-shuette.md core 2; stream-docs.md U10 | Design decision (unknown vs 0, which value marks a follower). Not a protocol deviation; the fork labels them as system values |
| Operating-mode switches can send `false` | stream-docs.md U2 | Device-class decision (replace two switches by a select = new unique_id); device answer to `false` unknown. With row 3 a rejection now shows up as a WARNING and the switch flips back - see live test |
| Nested/array parameter flattening in signing | api-core.md finding 4 | Only flat `{"sn": ...}` is signed; needed only for HTTP PUT/POST quota |
| Certification `protocol` ignored, only regional hosts offered | api-core.md findings 6, 8 | No evidence EcoFlow serves plain MQTT; regional hosts are what the portals issue keys for |
| MQTT "Not authorized" after 1-2 days | api-core.md, triage-tolwi-stream-core.md C5, #876/#901 | Out of scope. No concrete cause found in the code: the client id is static per entry (`Hassio-<account>-<group>`, group unique per entry), rejected credentials stop paho and start reauth. Not guessed |
| App-gating freezes on devices without stale reconnect (PowerStream, DELTA, app-API Smart Meter) | triage-tolwi-devices.md, triage-tolwi-stream-core.md | `reconnect_when_stale` is opt-in per device on evidence; no confirmation for those classes |
| PowerStream `supplyPriority` unknown after restart (#942, upstream #943) | triage-tolwi-devices.md | App-API get after SUBACK; no PowerStream to test, protocol not in the public docs |
| DELTA Pro 3 public updates only every 5 min (#772, #764) | triage-tolwi-devices.md | Needs data: diagnostics show missing MQTT pushes, nothing in the code to fix |
| `1006 not allowed to get device info` needs a clearer error | triage-tolwi-devices.md | EcoFlow-side permission; appears at `quota_all`, which already logs it per SN |
| Cooldown for `quota/all` on HTTP errors (#684), client-id counting (#355) | triage-tolwi-stream-core.md | Feature, no failure attributable to it |
| 8513 on per-device calls must not escalate to reauth | triage-shuette.md core 3 | Conforms: `quota_all` and the status poll catch every exception per SN; only login maps 8513 to `ConfigEntryAuthFailed` |
| Reconnect log flood, diagnostics name redaction, uint32 placeholder on PowerOcean energy | triage-shuette.md core 4-6 | Log/diagnostics cosmetics or "likely" evidence only (shuette's tracker); left for a device session |
| App-API Smart Meter: missing `continue` after "Ignoring EcoPacket", no stale reconnect | triage-tolwi-stream-core.md | No issue shows a wrong value; no confirmation of the stall on the app-API meter |
| PowerStream `power_step` option migration | stream-docs.md C3 | Changes stored user options; needs the owner's decision |

## Behaviour that changed for every device

- A set command while the MQTT connection is down is not sent (WARNING) instead of being
  queued until the next connect.
- Unacknowledged messages older than 60 s are not resent after a reconnect.
- paho runs with its locks (no functional change intended).
- One INFO line per set command.
- Binary frames on JSON device classes no longer log WARNING + ERROR.
- A failed first MQTT connect is retried by paho.
- Public API: HTTP requests reuse HA's session; success is decided by `code`.

STREAM-only (public `StreamAC`): main-SN routing, `set_reply` evaluation with rollback.

## Log lines (STREAM, public API)

```
INFO  ... api: System main SN for BK61XXXXXXXXXXXX is BK31XXXXXXXXXXXX
INFO  ... api.ecoflow_mqtt: Subscribed to MQTT topic /open/<account>/BK31XXXXXXXXXXXX/set_reply
INFO  ... api: Sending set command for BK61XXXXXXXXXXXX to system main SN BK31XXXXXXXXXXXX: {"from": "HomeAssistant", "id": "999954321", "version": "1.0", "sn": "BK31XXXXXXXXXXXX", "cmdId": 17, "cmdFunc": 254, "dirDest": 1, "dirSrc": 1, "dest": 2, "needAck": true, "params": {"cfgFeedGridMode": 2}}
INFO  ... api: Set command 999954321 for BK61XXXXXXXXXXXX accepted by BK31XXXXXXXXXXXX
INFO  ... api: Sending set command for BK61XXXXXXXXXXXX: {... "params": {"cfgRelay2Onoff": true}}
WARNING ... api: Set command 999912345 for BK61XXXXXXXXXXXX rejected by BK31XXXXXXXXXXXX (configOk is false): {...}
WARNING ... api: No set_reply from BK31XXXXXXXXXXXX for set command 999912345 of BK61XXXXXXXXXXXX within 30 s: {...}
WARNING ... api: Restored the previous value of 'feedGridMode' on BK61XXXXXXXXXXXX
WARNING ... api: Not sending set command for BK61XXXXXXXXXXXX, the MQTT connection is down: {...}
WARNING ... api.ecoflow_mqtt: Not resending a message for BK61XXXXXXXXXXXX from 312 s ago that the broker never acknowledged
WARNING ... api: Could not get the system main SN for BK61XXXXXXXXXXXX, system commands go to its own SN for now
```

Logger names are below `custom_components.ecoflow_cloud`.
