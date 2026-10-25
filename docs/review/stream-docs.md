# Review: STREAM / PowerStream / Smart Plug / Smart Meter vs. EcoFlow public API docs

Scope: `devices/public/stream_ac.py`, `stream_pv_helpers.py`, `stream_microinverter.py`,
`powerstream.py`, `smart_plug.py`, `smart_meter.py`, their constants, and the matching
internal files where a doc fact clearly applies.

Sources: `ecoflow-research/api-docs/stream.md`, `power_stream_micro_inverter.md`,
`smart_plug.md` (EcoFlow IoT developer docs, state 2026-05), issue snapshots
`issues/tolwi.jsonl` (open issues) and `issues/shuette42.jsonl` (2026-10-25).
There is no EcoFlow document for the Smart Meter.

Severity: **high** = corrupts data or long-term statistics, **medium** = wrong value or a
control that sends something the doc excludes, **low** = cosmetic, missing optional field,
or doc inconsistency, **info** = confirmation only.

## Findings

| # | Finding | Doc ref / issue | Code location | Severity | Fixed? / why not |
|---|---|---|---|---|---|
| F1 | Backup reserve slider: the live limits replaced the static 3–95 % range, so with `cmsMaxChgSoc` = 100 the slider offered 96–100 %. | stream.md, "Backup reserve level": "Recommended level: 3–95%", "3% higher than the discharging level"; shuette42#264 (min tracking measured on hardware) | `number.py` `BatteryBackupLevel._updated`, used by `public/stream_ac.py` `numbers()` | medium | **Fixed** (f8738cc): live limits only narrow the static range. Behaviour-neutral for the other users (they pass 5..100). Test `tests/test_battery_backup_level.py`. |
| F2 | PowerStream Min Discharge Level allowed 0. | power_stream_micro_inverter.md, `WN511_SET_BAT_LOWER_PACK`: "lowerLimit: 1-30" | `public/powerstream.py` `numbers()` | low | **Fixed** (0b9cd4a): min 1. |
| F3 | PowerStream `20_1.batInputCur` mapped as mA; the doc gives 0.1 A (positive = discharging). 15 A showed as 150 mA. | power_stream_micro_inverter.md, heartbeat(20_1): "BAT input current. Unit: 0.1 A. A positive value indicates discharging…" | `public/powerstream.py`, `internal/powerstream.py` (same heartbeat field) | medium | **Fixed** (81ecbe1): `DeciampSensorEntity`. unique_id unchanged; HA converts mA→A history. |
| F4 | PowerStream Custom Load Power step was the generic 100 W default although the device takes 0.1 W. Explains tolwi#750 ("step size of 100W", reporter assumed an API limit). | power_stream_micro_inverter.md, `WN511_SET_PERMANENT_WATTS_PACK`: "unit: 0.1 W", MQTT example `permanentWatts: 213`; tolwi#750 | `public/powerstream.py`, `internal/powerstream.py` | medium | **Fixed** (66166fb): `default_charging_power_step()` = 1. Only new config entries pick it up; existing entries keep their stored `power_step` option (change it in the device options). |
| F5 | Smart Meter net energy counters (per phase + total net) were `TOTAL_INCREASING` and dropped values ≤ 0. They fall during export → HA books each dip as a meter reset and adds the full reading to statistics. | shuette42#331: 773.1/.2/.3 = cumulative per-phase net, 773.4 = import, 773.6 = export, 773.7 = net; "773.4 − 773.6 = 773.7"; "Phase B … −277 W. Its net-energy counter decreased" | `public/smart_meter.py` (`todayActiveL1-3`, `totalActiveEnergy`), `internal/smart_meter.py` (`energyL1-3daily`, `netEnergyConsumption`), new `sensor.py` `NetEnergySensorEntity` | high | **Fixed** (e803a19): `state_class` TOTAL, negatives accepted, 0 still ignored. Import/export counters stay `TOTAL_INCREASING`. Test `tests/test_net_energy_sensor.py`. |
| U1 | System-level STREAM set commands (backup reserve, self-powered / AI mode, feed-in) go to the entity's own SN. The doc says: get the main SN first; only AC1/AC2 take the unit's own SN. On a linked system, these controls on the slave unit may be ignored or act on the wrong unit. | stream.md, "Obtain the main device serial number…" and every system command: "use the API to obtain the serial number of the main device"; shuette42#561 (backup reserve possibly one shared setting) | `public/stream_ac.py` `numbers()`, `switches()` (`"sn": self.device_info.sn`) | medium | **Not fixed** – needs `GET /iot-open/sign/device/system/main/sn` and routing in `api/` (core). Live test L2. |
| U2 | Operating-mode switches can send `false`. The doc requires exactly one of self-powered / AI mode to be `true`, and documents only `true` writes. Turning "Self-powered" off sends `{operateSelfPoweredOpen: false}` alone; device behaviour undefined. | stream.md, GetAllQuotaResponse: "one of them must be "true" and the other must be "false""; set examples only send `true` | `public/stream_ac.py` `switches()` | medium | **Not fixed** – the clean fix is a select (Self-powered / AI) that only sends `true`; that replaces two entities (new unique_id), which needs the user's decision, and the device's answer to `false` is unknown. Live test L3. |
| U3 | AC1/AC2 switches are created for every public STREAM type. The doc: AC1/AC2 unsupported on STREAM Max and STREAM AC; STREAM Max has one "AC switch" on `relay2Onoff`. The public type "Stream AC" is also what STREAM AC Pro owners pick, so gating by type would break them. | stream.md, "AC1 switch"/"AC2 switch"/"AC switch" support lists; shuette42#136, #140 | `public/stream_ac.py` `switches()`, `devices/registry.py` | low | **Not fixed** – needs SN-prefix gating (BK41 = Max, BK51 = AC), registry/core decision. No owner report of a wrong write. |
| U4 | PowerStream Custom Load Power max is 800 W; the doc says 0–600 W. 800 W PowerStream variants exist (tolwi#384 cites 0–800), and the device reports `ratedPower` (example 6000 = 600 W). | power_stream_micro_inverter.md, "Range: 0 W–600 W"; heartbeat `ratedPower` | `public/powerstream.py`, `internal/powerstream.py` | low | **Not fixed** – lowering to 600 would break 800 W units. Proposal: derive max from `20_1.ratedPower / 10`. |
| U5 | Internal PowerStream limits differ from the public doc: Max Charge Level 50–100 (doc 70–100), Min Discharge Level 0–30 (doc 1–30). | power_stream_micro_inverter.md set commands | `internal/powerstream.py` `numbers()` | low | **Not fixed** – the doc covers the public command set; the internal protobuf path may have been widened on purpose and nobody reported a rejected value. |
| U6 | PowerStream `feedProtect` (Feed-in control, 0/1) is documented in the public heartbeat but not exposed publicly (the internal device has a switch). No public set command is documented. | power_stream_micro_inverter.md, heartbeat(20_1) `feedProtect` | `public/powerstream.py` | low | **Not fixed** – read-only value of limited use; could be added later as a disabled sensor. |
| U7 | Smart Plug `2_1.maxCur` (0.1 A) is attached unscaled as an attribute of the mA current sensor. | smart_plug.md, heartbeat(2_1): "maxCur … Maximum output current: 0.1 A" | `public/smart_plug.py` | low | **Not fixed** – attribute only; `.attr()` has no scaling hook. |
| U8 | Smart Plug `2_1.freq`, `errCode`, `warnCode` documented but not exposed. | smart_plug.md, heartbeat(2_1) | `public/smart_plug.py` | low | **Not fixed** – optional, no issue asks for it. |
| U9 | Doc errors in stream.md: `powGetSysGrid` and `cmsBattSoc` are both described as "System real-time load power, unit: W" (copy-paste; `cmsBattSoc` is a % value, see the examples). The HTTP response example shows `powGetBpCms` = +1064.9 while feeding 1064.9 W into the grid with 0 W PV, which contradicts the field text "Positive values refer to the battery's charging power". | stream.md, GetAllQuotaResponse table + response example; tolwi#686 ("Power Battery negative value while discharging") | `const.py` `STREAM_POWER_BATTERY` comment (`<0 discharge / >0 charge`) | info | No change – tolwi#686 confirms the field text (negative = discharging); our mapping and comment match it. |
| U10 | System fields (`powGetBpCms`, `powGetPvSum`, `powGetSysGrid`, `powGetSysLoad*`, `cmsBattSoc`, `cmsBattFullEnergy`, `sysGridConnectionPower`) are reported only by the master; a slave sends 0, which HA shows as a real 0 W / 0 %. | stream.md describes them as "System …"/"aggregated"; shuette42#486, #336, #323; user-measured facts | `public/stream_ac.py` | medium | **Not fixed** – the fork already labels them as system values. Showing "unknown" on the slave (shuette's approach) needs the `distributedDeviceStatus` / `seriesConnectDeviceStatus` value and a design decision. |
| U11 | Backup reserve max = `cmsMaxChgSoc`; the doc says "less than the charging level" (strict). | stream.md, "Backup reserve level" | `number.py` `BatteryBackupLevel` | low | **Not fixed** – "less than" vs "≤" is not evidenced by a device rejection. |
| U12 | Internal Smart Meter display names "L1/L2/L3 net energy daily" are wrong: the counters are cumulative, not daily. | shuette42#331 ("None of the counters reset at local midnight") | `const.py` `SMART_METER_RECORD_ENERGY_L*_DAILY` | low | **Not fixed** – display name only, not part of the public scope; can follow with the core/internal session. |

## Confirmed mappings (no change)

| Field | Our mapping | Evidence |
|---|---|---|
| `feedGridMode` | switch, on = 2, off = 1, writes `cfgFeedGridMode` | stream.md "Feed-in control (1-off, 2-on)"; shuette42#603 (2 = on, 1 = off on a BK61) |
| `relay2Onoff` / `relay3Onoff` | AC1 / AC2, `cfgRelay2Onoff` / `cfgRelay3Onoff` (bool), own SN | stream.md AC1/AC2 rows |
| `backupReverseSoc` | `cfgBackupReverseSoc` int, min = `cmsMinDsgSoc` + 3 | stream.md; shuette42#264 |
| `cfgEnergyStrategyOperateMode.{operateSelfPoweredOpen, operateIntelligentScheduleModeOpen}` | nested param object, cmdId 17 / cmdFunc 254 / dest 2 | stream.md set examples (envelope identical) |
| `gridConnectionPower` | W, input positive / feed-in negative (raw) | stream.md GetAllQuotaResponse |
| `powGetBpCms` | W, + charge / − discharge, system aggregate | stream.md field text; tolwi#686; shuette42#486 |
| `powGetPvSum` | W, system aggregate (master only) | stream.md "System real-time PV power"; tolwi#771/#663 explained by it; fork's per-unit `pvWattsTotal` covers the unit |
| `cmsBattSoc` vs `soc` | system SoC vs per-unit SoC | shuette42#323, #336; fork's naming |
| `cmsMaxChgSoc` / `cmsMinDsgSoc` | read-only sensors | stream.md documents no set command for them; shuette42#337 shows undocumented writes are applied but not reported back |
| PowerStream `pv1/2InputVolt`, `pv1/2InputCur`, `batInputVolt`, `batTemp`, `invFreq` | 0.1 V / 0.1 A / 0.1 °C / 0.1 Hz | power_stream_micro_inverter.md heartbeat |
| PowerStream `supplyPriority`, `upperLimit`, `invBrightness` | select 0/1, 70–100, 0–1023 | power_stream_micro_inverter.md set commands |
| Smart Plug `switchSta`, `brightness`, `current`, `watts`, `volt` | switch writes `plugSwitch` 1/0; 0–1023; mA; 0.1 W; V | smart_plug.md |
| Smart Meter `todayActive` / `totalReactiveEnergy` | lifetime import / lifetime export, `TOTAL_INCREASING` | shuette42#331 (773.4 import, 773.6 export – EcoFlow's message definition calls 773.5/.6 "reactive") |
| Smart Meter phase current vs power | passed through unchanged | shuette42#402: current is RMS incl. non-active share, power is active only – not a mapping bug |

## Issues vs. doc deviations

| Issue | Explained by a doc deviation? |
|---|---|
| tolwi#750 PowerStream 100 W step | **Yes** – F4 (integration default, the device takes 0.1 W). |
| tolwi#771, #663 no PV Sum on Ultra X | Yes, by the doc's scope: `powGetPvSum` is a system field, reported by the master only (U10). The per-unit `pvWattsTotal` added in the fork is the answer. |
| tolwi#686 Power Battery negative when discharging | No deviation – confirms the doc's sign convention (U9). |
| tolwi#922 Feed-in control resets to OFF | Not by a doc deviation. The report shows `cfgFeedGridMode = 1` writes from HomeAssistant without a user action and null context, same pattern as tolwi#819 → core (C2). U1 is relevant on that multi-unit setup but does not explain an unsolicited write. |
| tolwi#786, #679 PV Sum carries grid-charge power | No – frosty-geek's samples show the values arrive wrong from `quota/all` (also in evcc); device/cloud. |
| tolwi#818, #723 writable max charge / discharge limits | No set command documented for `cmsMaxChgSoc`/`cmsMinDsgSoc`; out of scope until EcoFlow documents it. |
| tolwi#717, #579 base load / custom load for STREAM | Not in stream.md. |
| tolwi#893 no charge/discharge energy on Stream Ultra (internal API) | Not a public doc topic; the public device has `accuChgEnergy`/`accuDsgEnergy`. |
| tolwi#903 PowerStream custom load resets to 0 (internal API) | Not explained by the doc. |
| tolwi#647 Smart Meter 0 W (internal API, utf-8 decode errors) | No – decoding path. |
| tolwi#654 Smart Meter assume_offline | No – core/status tracking. |
| shuette42#486, #336, #323 | Confirm the system-vs-unit split (U10, fork naming). |
| shuette42#264, #603, #337, #402, #331 | Confirm our mapping (see table above); #331 drives F5. |
| shuette42#136, #140 | Model support matrix for AC switches (U3). |

## Findings for the core session

- **C1 – main-SN routing (U1).** stream.md requires the system's main SN for backup reserve, operating mode and feed-in (`GET /iot-open/sign/device/system/main/sn?sn=<any unit>`); AC1/AC2 use the unit's own SN. Today every command goes to the entity's own SN. Proposal: resolve the main SN in `api/` (cache it, refresh on reconnect) and let a device command opt into "send to system main SN".
- **C2 – unsolicited feed-in OFF writes (tolwi#922, #819).** Two acknowledged `cfgFeedGridMode = 1` writes from HomeAssistant, one without a user action, null context. Check whether a switch command is replayed or a restored state is written back after an MQTT reconnect or resubscribe.
- **C3 – power step option (F4).** `power_step` is stored when the entry is created, so existing PowerStream entries keep 100 W. If wanted, a one-time options migration could lower it to the new default when the stored value equals the old default.
- **C4 – Smart Meter public `quota/all`** returns no `data` (known); F5 only helps where MQTT delivers `gridConnectionDataRecord.*`.

## Live tests on the user's STREAM Pro (master) + STREAM Ultra X + Smart Meter

- **L1 – backup reserve range (F1).** Open the Backup Reserve number on the Pro. With Max Charge Level at 100 the slider must end at 95; with Max Charge Level at e.g. 80 (set in the app) it must end at 80. The lower bound must be Min Discharge Level + 3.
- **L2 – main-SN routing (U1).** With diagnostics on, toggle "Feed-in control" on the **Ultra X** (slave) entity. Check (a) whether the set_reply says `configOk: true`, (b) whether the **Pro's** `feedGridMode` changes, (c) what the EcoFlow app shows. Repeat with Backup Reserve on the Ultra X (e.g. +1 %). If the slave write has no effect, C1 is needed; if it propagates, U1 is harmless for this pair.
- **L3 – operating mode false write (U2).** With Self-powered on, switch "Operating mode – Self-powered" **off** in HA. Record the `set_reply` (`cfgEnergyStrategyOperateMode`) and both quota fields 30 s later, and what the app shows. Does AI mode switch on, does the device reject it, or are both off?
- **L4 – Smart Meter net counters (F5).** Check that the public meter delivers `gridConnectionDataRecord.*` over MQTT at all (Developer Tools → entity "Net energy consumption" has a value). If the system ever exports: "Net energy consumption" and the per-phase "Lifetime net usage" must go down, and the energy statistics must not show a spike. HA may raise a one-time repair note about the changed state class.
- **L5 – system fields on the slave (U10).** While the system charges, confirm the Ultra X shows 0 W on "Power Battery" (`powGetBpCms`) and 0 on "Power PV Sum"; that is device behaviour, not a decode error.
