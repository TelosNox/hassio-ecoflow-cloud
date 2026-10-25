# Review: public-API core

Scope: `custom_components/ecoflow_cloud/api/` (`public_api.py`, `__init__.py`, `ecoflow_mqtt.py`, `message.py`), the setup path in `__init__.py`, and `devices/__init__.py`, `devices/data_holder.py`, `devices/status_tracker.py`, `devices/status_coordinator.py` where they implement protocol behaviour.

Reference: EcoFlow IoT Developer Platform documentation, "General information" (`api-docs/general_information.md` in the private research repo, served 2026-10-25, last changed by EcoFlow 2026-05). Section names below are the headings of that document.

## Findings

| # | Finding | Doc reference | Code location | Severity | Fixed? / why not |
|---|---|---|---|---|---|
| 1 | Nonce drawn from `randint(10000, 1000000)`: about 9% of requests send a 5-digit nonce, one value a 7-digit one | "General HTTP Header": nonce, "Random number, 6 digits" | `api/public_api.py` `call_api`, `__init__` | Low | **Fixed** (`_gen_nonce`, 100000-999999). No issue shows EcoFlow rejecting other lengths today |
| 2 | `fetch_all_available_devices` indexes `response["data"]`; a success response without `data` aborts setup with "Unknown" / `KeyError: 'data'` | "Query the user's bound device list": "Only returns the device bound to itself, not by share"; `data` not marked Required | `api/public_api.py` `fetch_all_available_devices` | Medium | **Fixed**: empty list plus a warning naming the documented cause. Proven by tolwi#791, tolwi#598 |
| 3 | Request signing verified against the official test vector (steps 1, 3-5) | "HTTP access steps", Step 8 | `api/public_api.py` `__gen_sign`, `__sort_and_concat_params` | - | Conforms. Pinned with pytest (`tests/test_public_api.py`) |
| 4 | Nested/array parameter flattening (`a.b=`, `ids[0]=`) is not implemented; `__sort_and_concat_params` only handles flat dicts | "HTTP access steps", Step 2 | `api/public_api.py` `__sort_and_concat_params` | Info | Not fixed: the only signed parameter set the code sends is `{"sn": ...}`. Needed only if HTTP `PUT/POST /device/quota` is ever used (see suggestions) |
| 5 | Success is detected by `message == "success"`, the doc defines it by `code == "0"` | every endpoint's Response Body: "code ... 0: success" | `api/__init__.py` `_get_json_response` | Low | Not fixed: shared with the private API, and no response with `code "0"` but another message (or vice versa) has been reported. Error `code` is already carried in the exception |
| 6 | Only `api-e.ecoflow.com` / `api-a.ecoflow.com` are offered; the doc names only `https://api.ecoflow.com` | "Host" | `config_flow.py` `_api_schema` (out of this scope) | Info | Not fixed: the regional hosts are what EcoFlow's portals issue keys for, and 8513 on region mismatch is already explained in the UI. The documented host itself is not offered |
| 7 | All HTTP endpoints used match path and method: `GET /iot-open/sign/certification`, `GET /iot-open/sign/device/list`, `GET /iot-open/sign/device/quota/all?sn=` | "MQTT certificate acquisition", "Query the user's bound device list", "Query device's all quota infomation" | `api/public_api.py` | - | Conforms |
| 8 | Certification `protocol` (`mqtt` / `mqtts`) is ignored; TLS is always used | "MQTT certificate acquisition", AppCertification.protocol | `api/__init__.py` `_accept_mqqt_certification`, `api/ecoflow_mqtt.py` `tls_set` | Low | Not fixed: every reported certification (doc example, tolwi#876) is `mqtts`/8883; no evidence EcoFlow serves plain `mqtt` |
| 9 | Topics `/open/{account}/{sn}/quota`, `/set`, `/set_reply`, `/status` match | "MQTT Topic" | `api/public_api.py` `_create_device_info` | - | Conforms. The integration also subscribes to its own `/set` (app→device) to log sent commands; harmless |
| 10 | Status message `params.status` 0/1 evaluated as explicit online/offline | "Report Device status" | `devices/__init__.py` `_prepare_data_status_topic` | - | Conforms |
| 11 | Set envelope: `id` (string), `version "1.0"`, `from`, `params`, device-specific `operateType` | "Request Topic's Common Field" | `api/message.py` `JSONMessage.prepare_payload`, device classes | - | Conforms. `id` is random within 90 000 values rather than e.g. a timestamp; uniqueness is only "per request" and replies are not matched by id, so no effect |
| 12 | `set_reply` result `code` (0 ok, -1 not the user's device, -2 device offline) is stored for diagnostics only; the optimistic target state from `update_to_target_state` is never rolled back on a failed reply | "Reply Topic's Common Field" | `api/__init__.py` `send_set_message`, `devices/data_holder.py` | Low | Not fixed: behaviour change across all devices; the next telemetry overwrites the optimistic value anyway. Listed as a suggestion |
| 13 | MQTT client id `Hassio-{certificateAccount}-{group}` is static per config entry | not documented (the "10 client ids per day" note in `public_api.py` comes from a forum post, not from EcoFlow's documentation) | `api/public_api.py` `login` | - | Conforms to the undocumented limit; nothing in the doc to check against |
| 14 | No rate limits or connection limits are documented | - | - | - | Nothing to check |
| 15 | `_get_json_response` formats `resp.text` (a bound method, never awaited) into the parse error | - | `api/__init__.py` `_get_json_response` | Info | Not fixed: cosmetic, error text only; no protocol relevance |

## Documented capabilities not used (suggestions only)

- **MQTT `/get` and `/get_reply`** ("MQTT Topic": "Get some quota", app→device). The public client sets `get_topic=None`. The general document does not specify the payload. If a get request keeps EcoFlow's cloud asking the device to report, this would be the documented alternative to the stale-telemetry reconnect (compare tolwi#830, where a protobuf get kept a private-API STREAM reporting). It needs a capture before anyone builds on it.
- **`set_reply` evaluation** (finding 12): log or surface `code -1/-2` and drop the optimistic state on failure.
- **HTTP `PUT /iot-open/sign/device/quota`** ("Setting device's function") returns a synchronous `code`, unlike fire-and-forget MQTT `/set`. It would need Step 2 flattening (finding 4) and the JSON body as signing input (Step 7).
- **HTTP `POST /iot-open/sign/device/quota`** (selected quotas) as a lighter alternative to `quota/all` for polling single values.
- **`GET /iot-open/sign/device/system/main/sn`** (`stream.md`): the main device serial of a STREAM system. Device-session topic, listed for completeness.
- **`POST /iot-open/sign/device/quota/data`** (history, `stream.md`, `power_ocean.md`, `smarthomepanelii.md`): not needed for live entities.

## Open issues in tolwi/hassio-ecoflow-cloud

| Issue | Topic | Explained by a deviation above? |
|---|---|---|
| #791, #598 | Public API setup fails "Unknown", `KeyError: 'data'` | **Yes, finding 2** (fixed). Root cause on EcoFlow's side: developer account ≠ device owner account, or devices only shared |
| #876, #901 | MQTT `Not authorized` / `Client identifier not valid`; new keys help for < 2 days | No. Signing and certification flow conform; recreating the entry (new `/certification`, same client id) did not help, new keys (new `certificateAccount`, so also new client id) did. The doc says nothing about broker-side blocking. Open question |
| #405, #406, #355 | `signature is wrong` / no data after some time, fixed by regenerating keys | No. The signature matches the official vector (finding 3). Finding 1 would cause sporadic failures, not persistent ones |
| #541, #724 | `current device is not allowed to get device info` on `quota/all` | No. Request conforms; EcoFlow-side permission per device |
| #684 | Retry bursts / temporary blacklist | No documented rate limit to violate (finding 14). The fork already backs off MQTT reconnects |
| #830, #596, #283 | Values stop updating until the app is opened | No protocol deviation; see the `/get` suggestion. The fork's `reconnect_when_stale` targets this |
| #886 | Many DNS lookups | No. Not related to the documented protocol |
| #947 | Credentials in logs | Already addressed in the fork (redaction) |

## Open questions

1. Does EcoFlow block an MQTT account/client id after some time (tolwi#876, #901)? Distinguishing account from client id would need a test with new keys but the old client id string, or vice versa.
2. What payload does the public `/get` topic accept, and does a get keep a STREAM reporting? Needs a capture.
3. Should the config flow tell the user that no devices were found (and why) instead of aborting with "every device in this account has already been added"? `config_flow.py` is outside this session's scope; the warning added in finding 2 shows up in the log.
