# Triage: shuette42/ecoflow-energy-ha issues vs. this fork

Source: all 131 issues (open and closed, with comments) of
[shuette42/ecoflow-energy-ha](https://github.com/shuette42/ecoflow-energy-ha) (MIT) as of 2026-10-25,
plus its parsers (`custom_components/ecoflow_energy/ecoflow/parsers/`, commit `6830cd3`), `const.py`,
`documentation/` and test fixtures. Each issue was checked against the corresponding fork device file.

Classification: **Yes - fixed** (the fork had the same problem, fixed on this branch) ·
**Fork already correct** · **N/A** (device the fork does not support, or a shuette-specific code
path / private-API control the fork handles differently) · **Useful knowledge** (no bug, but a field
meaning or device behaviour worth keeping) · **Known / tracked** (already handled or tracked in the
fork) · **Core note** (finding for the api-core session).

## Fixes on this branch

| Commit | Fix | Evidence |
|---|---|---|
| 9c97b42 | Smart Meter (internal): phase L1/L3 currents were swapped (`currentL1` = 784, `currentL3` = 958). Now 958/959/784 = L1/L2/L3, like voltage 956/957/771 and power 962/963/772. Keys/unique_ids unchanged. Test on a real masked BK21 get_reply frame. | #331: app showed A 0 W / 0.00 A, C 90 W / 0.84 A; on that frame the fork showed 1.764 A on the idle L1 |
| d3af2f1 | Smart Meter (public + internal): the per-phase net counters and the overall net counter are import minus export and fall while exporting. They were `TOTAL_INCREASING` (each fall = meter reset) and dropped values ≤ 0. New `NetEnergySensorEntity` (`TOTAL`). Internal "daily" titles were wrong, they are lifetime counters. | #331 midnight capture: `.1+.2+.3 = .7`, `.4-.6 = .7`, no counter resets; phase B counter fell during an export test |
| 767f59d | DELTA 3 family (internal): BMS heartbeats of an extra battery (`num` ≥ 1) overwrote the built-in battery's keys, so SoC/temperature flipped and lifetime counters jumped. Extra-battery reports are now dropped. Approach taken over from shuette42 (`_MAIN_PACK`). | #304: DELTA 3 Plus, pack 0 12.990 kWh / pack 1 11.147 kWh in one get-all reply; stable after shuette's fix |
| dbb30a1 | DELTA 3 Max Plus: AC charging power slider was the DELTA 3's 100-1500 W; now 200-2400 W (others unchanged). | #100, #181: app slider 200-2400 W on three units |
| d405872 | PowerOcean (public): `bpRemainWatth` (energy left in a pack) was `energy` / `TOTAL_INCREASING`; now `energy_storage` / `MEASUREMENT`. | #10, #132; shuette `const.py` |
| 4960a2b | STREAM (public + internal): `powGetBpCms` renamed "System Battery Power" (display name only). It is the system aggregate that only one unit of a linked group fills; the unit's own battery power is In Power / Out Power. | #486; fork's own quota sample: 1915 W vs inputWatts 900 W = 44.671 A × 20.161 V |

Users of a renamed sensor keep their entity_id; Home Assistant may show a one-time statistics repair for
the sensors whose state class changed (Smart Meter net counters, PowerOcean pack remaining energy).

## Special attention items

- **#486 (Stream Ultra battery discharge stays 0 W):** affects the fork. Proto field 518 = public
  `powGetBpCms` is the group aggregate (AC side), filled only by the unit computing the system block; the
  others send 0. shuette now derives per-unit battery power from the BMS frame 32/50 f26/f27 (DC pack side,
  about once a minute, up to ~10 % above the AC figure at a few hundred W, much more at low load: 63 W vs
  7 W in the app). In the fork's public quota the per-unit equivalents are `inputWatts` / `outputWatts`
  (matches `amp × vol` in the sample; that they are exactly f26/f27 is inferred, not captured). Fixed by
  naming; a signed per-unit "Battery Power (unit)" = inputWatts − outputWatts would be a cheap follow-up.
- **Smart Meter semantics (#331, #402):** fixed as above. Further knowledge: power factor (618) is sent
  as 0.0 in every frame (meaningless); phase current is an RMS figure including non-active current, so
  V × I need not match the active power; `.5` of the energy record never appears; the official API returns
  an empty `quota/all` for a BK21 (#331; the fork's own comment at `public/smart_meter.py:104` agrees,
  its data arrives over MQTT only). The fork's public Smart Meter keys come from the cloud's own mapping, whose names (`todayActive*`, `totalActiveEnergy`, `totalReactiveEnergy`)
  match the vendor schema shuette proved misleading: `todayActive` = lifetime import, `todayActiveL1..3`
  and `totalActiveEnergy` = lifetime net, export is the field the vendor calls reactive.
- **Delta 3 / River:** #304 and #181/#100 fixed. Delta 2 Max PV2 scale (#516) and AC charge speed (#95)
  are already correct in the fork. River 3 Plus with an extra battery probably has the #304 problem too
  (`internal/river3.py:539` decodes every BMS report into the same keys) — no capture, so not changed.
- **Controls that silently do nothing:** DELTA 3 AC charge power needs field 125 next to field 54 —
  already done in the fork. STREAM Max Charge SoC < 50 % is applied but not reported back (#337).
  The general lesson (#185, #181): the fork shows a written value as accepted before the device confirms
  it, see core notes.

## Core findings for the api-core session

1. **Optimistic writes.** `EcoFlowBaseCommandEntity.send_set_message` (`entities/__init__.py:260`) pushes
   the target value into the data holder and `EcoflowMQTTClient.publish` (`api/ecoflow_mqtt.py`) is
   fire-and-forget. A write the device discards silently (shuette #181: half of a combined setting;
   #185: write never acknowledged) shows as accepted until the next report. shuette now waits for the
   broker ack / the device's read-back.
2. **System block on followers (#486, #323, #336).** On every unit except the one that computes the system
   figures, `powGetSysGrid`, `powGetSysLoad`, `powGetPvSum`, `powGetBpCms`, `sysGridConnectionPower`,
   `powGetSysLoadFromBp/FromGrid` and `cmsBattSoc` arrive as 0.0 in every frame. shuette publishes them as
   unknown when the system SoC is 0 and the unit SoC > 0. The fork publishes the zeros (labelled as system
   values now). A generic "zero on a follower = unknown" rule belongs in the STREAM/core layer.
3. **Reauth.** Fork maps only error 8513 at login to `ConfigEntryAuthFailed` (`__init__.py:282`,
   `api/__init__.py:20`) and connection errors to `ConfigEntryNotReady` — correct for #2, #289, #437, #531.
   EcoFlow also returns 8513 for devices not bound to the key (#2); make sure per-device quota calls never
   escalate it.
4. **Reconnect log flood (#562).** Each failed MQTT reconnect logs a warning without the device;
   shuette logs once per outage per device.
5. **Diagnostics (#341).** The device name carries the serial suffix; redact names against the serial.
6. **uint32 placeholder.** PowerOcean leaves unpopulated fields at 4294967295 (seen on percent fields, #88);
   shuette also drops it on energy totals. `ScaledEnergySensorEntity` (`public/powerocean.py:31`) would
   publish 4294967 kWh on a `TOTAL_INCREASING` sensor. Cheap guard; evidence only "likely".

## Knowledge worth keeping (no fork bug)

- STREAM BK: Backup Reserve floor = Min Discharge SoC + 3 (BK31, #264); `feedGridMode` 2 = on, 1 = off
  (#603); f996/f997 = PV3/PV4 W, f998-1001 their V/A (#522); linked units propagate Max Charge SoC (#337);
  BK41/BK51 layouts unverified (#136).
- STREAM 5000/AC 5000: "Solar Power" field is the third-party ("Other") figure (#258); 200 W default output
  without tasks (#458); 32/50 f8 = signed pack current mA, f26/f27 = pack charge/discharge W (#393);
  Max Grid Input Power (cfg 10.2) governs grid charging, writing 10.1 leaves 10.2 untouched (#284); with UPS
  on the device itself books socket load as grid→battery (#627).
- PowerStream: quota is deci-W, `gridConsWatts` < 0 = export, `pvXInputCur` scale unsettled (#230).
- DELTA 3 Max Plus: charge mode (field 125) reports only on change, no steady read-back (#181).
- PowerOcean: enums for work mode / pcsRunSta / feed mode / EMS work state in shuette
  `parsers/powerocean_http.py`; `RUNSTA_STOP` = portal "System stopped" (#528); a parallel pair reports one
  row per inverter plus a total row (#347, #436).
- RIVER 2 Max: USB 1 is the sum of the three USB-A ports (#585).

## All issues

| shuette issue | Topic | Affects fork? | Evidence | Fork location | Action |
|---|---|---|---|---|---|
| [#634](https://github.com/shuette42/ecoflow-energy-ha/issues/634) (open) | [PowerPulse] Add remaining telemetry (power sources and diagnostics) | N/A | PowerPulse/PowerGlow wallbox, not supported by the fork | - | none |
| [#632](https://github.com/shuette42/ecoflow-energy-ha/issues/632) (open) | [PowerPulse 2] Wallbox Start Charging refused while the status reads Vehicle connected (preparing) | N/A | PowerPulse/PowerGlow wallbox, not supported by the fork | - | none |
| [#631](https://github.com/shuette42/ecoflow-energy-ha/issues/631) (open) | PowerOcean Plus (R372): Backup Reserve cannot be set – Solar Surplus Threshold never reported, write fails with misleading "did not reach the device" | N/A | PowerOcean Plus backup reserve write (private API) | - | none |
| [#629](https://github.com/shuette42/ecoflow-energy-ha/issues/629) (open) | STREAM 5000: PV energy calculated from HA power readings is 7–11% below EcoFlow app | No (known) | PV integral below app on ES21 - does not reproduce on the user's BK devices | - | none |
| [#627](https://github.com/shuette42/ecoflow-energy-ha/issues/627) (open) | STREAM AC 5000 AC Port power is reported as battery charging | Useful knowledge | AC socket on AC5000 with UPS on is booked as grid->battery by the device itself | internal/stream_ac_5000.py | none |
| [#618](https://github.com/shuette42/ecoflow-energy-ha/issues/618) (open) | OCEAN Smart Electrical Panel 40: switch individual circuits on and off | Useful knowledge | Circuit switching needs a recorded app write | internal/ocean_pro.py | none (fork read-only) |
| [#603](https://github.com/shuette42/ecoflow-energy-ha/issues/603) (open) | STREAM Ultra X: Feed-in Control on/off switch | Fork already correct | `feedGridMode` 2 = feed-in on, 1 = off (BK61 Standard mode); write `cfgFeedGridMode` | public/stream_ac.py:448-465 | none (enableValue 2 / disableValue 1 already) |
| [#596](https://github.com/shuette42/ecoflow-energy-ha/issues/596) (open) | Support for EcoFlow Smart Meter Dual CT-1074 – separate solar production sensor | Useful knowledge | Dual CT solar clamp: location unknown; 'Third-party solar' is the 'Other' figure | - | none |
| [#591](https://github.com/shuette42/ecoflow-energy-ha/issues/591) (open) | [PowerPulse 2] Add missing Smart Charging entities and safe Smart-mode configuration | N/A | PowerPulse/PowerGlow wallbox, not supported by the fork | - | none |
| [#590](https://github.com/shuette42/ecoflow-energy-ha/issues/590) (closed) | [PowerPulse 2] Clarify charging-status labels based on observed device behavior | N/A | PowerPulse/PowerGlow wallbox, not supported by the fork | - | none |
| [#588](https://github.com/shuette42/ecoflow-energy-ha/issues/588) (open) | [PowerGlow] Add remaining telemetry (power sources and diagnostics) | N/A | PowerPulse/PowerGlow wallbox, not supported by the fork | - | none |
| [#585](https://github.com/shuette42/ecoflow-energy-ha/issues/585) (closed) | New device support: RIVER 2 Max | Useful knowledge | RIVER 2 Max: USB 1 is the sum of the three USB-A ports | internal/river2_max.py | none |
| [#575](https://github.com/shuette42/ecoflow-energy-ha/issues/575) (open) | PowerOcean DC Fit (HC31) detected but not supported - no parser available | Useful knowledge | HC31 PowerOcean DC Fit | - | none |
| [#573](https://github.com/shuette42/ecoflow-energy-ha/issues/573) (closed) | Please add support for PowerOcean Plus Prefix R373 | Useful knowledge | R373 prefix | - | none |
| [#572](https://github.com/shuette42/ecoflow-energy-ha/issues/572) (closed) | [BUG] Stream AC System keeps a removed battery in HA | N/A | shuette-specific (own coordinator/config flow/diagnostics): removed unit stays a device | - | none |
| [#568](https://github.com/shuette42/ecoflow-energy-ha/issues/568) (closed) | STEAM AC 5000 Battery power stuck until opening app | Known / tracked | Per-unit f54.1.4 unsigned; signed f50.1.4 only in full-state get_reply -> stuck value | internal/stream_ac_5000.py:539 | none here; tracked as TelosNox/hassio-ecoflow-cloud#6 (f50 latching) |
| [#566](https://github.com/shuette42/ecoflow-energy-ha/issues/566) (open) | PowerPulse 2 linked to a PowerOcean: settings writes use the timing of a wallbox that reports on its own | N/A | PowerPulse/PowerGlow wallbox, not supported by the fork | - | none |
| [#562](https://github.com/shuette42/ecoflow-energy-ha/issues/562) (closed) | Enhanced Mode: a network outage fills the log with identical reconnect warnings | Core note | Reconnect warnings per attempt flood the log, no device name | api/ecoflow_mqtt.py | for api-core session |
| [#561](https://github.com/shuette42/ecoflow-energy-ha/issues/561) (open) | Linked STREAM 5000 + Stream Ultra X: Backup Reserve can be set on both units, is it one shared setting? | Useful knowledge | Linked STREAM 5000 + Ultra X: Backup Reserve exists on both units, maybe one shared setting (open) | public/stream_ac.py:349 | none |
| [#554](https://github.com/shuette42/ecoflow-energy-ha/issues/554) (closed) | Extend Backup Reserve control to RE41 | N/A | Ocean 2 (RE41), not supported by the fork | - | none |
| [#553](https://github.com/shuette42/ecoflow-energy-ha/issues/553) (closed) | PowerPulse 2: Controls not showing | N/A | PowerPulse/PowerGlow wallbox, not supported by the fork | - | none |
| [#549](https://github.com/shuette42/ecoflow-energy-ha/issues/549) (closed) | Stream Ultra linked to a STREAM AC 5000: PV string sensors have two sources | Fork already correct | Two writers for one PV sensor on AC5000+Ultra pair | internal/stream_ac_5000.py:_own_entry (own serial only) | none |
| [#536](https://github.com/shuette42/ecoflow-energy-ha/issues/536) (closed) | STREAM AC 5000 linked with a Stream Ultra: per-unit battery power unsigned, and missing per-unit readings | Known / tracked | Per-unit battery power unsigned when linked; per-unit grid connection f50.1.7 | internal/stream_ac_5000.py:536-543 | none here (#6) |
| [#531](https://github.com/shuette42/ecoflow-energy-ha/issues/531) (closed) | Enhanced Mode: no internet at Home Assistant startup asks for re-authentication instead of retrying | Fork already correct | No internet at startup -> reauth | __init__.py:276-281 (ConfigEntryNotReady) | none |
| [#528](https://github.com/shuette42/ecoflow-energy-ha/issues/528) (closed) | Add status information to show if device has stopped | Useful knowledge | pcsRunSta RUNSTA_STOP = 'System stopped' in portal | public/powerocean.py | candidate disabled entity |
| [#522](https://github.com/shuette42/ecoflow-energy-ha/issues/522) (closed) | [Feature Request / Device Support] Map PV3 and PV4 voltage and current fields across BK series (BK11, BK12/BK31, BK61) | Useful knowledge | Proto 254/21 f996/f997 = PV3/PV4 W, f998-1001 = PV3/PV4 V/A (pairing verified, 3 vs 4 order from one owner) | internal/stream_ac.py (_ultra_x_pv_sensors) | none; public path uses plugInInfoPv3/4* |
| [#519](https://github.com/shuette42/ecoflow-energy-ha/issues/519) (closed) | [STREAM 5000 AC] AC Output power entity | Useful knowledge | AC Output Power on AC5000 exists | - | candidate for the STREAM-5000 session |
| [#516](https://github.com/shuette42/ecoflow-energy-ha/issues/516) (closed) | Delta 2 Max (R351): Solar 2 / PV2 readings appear to be scaled down by a factor of 10 in Enhanced Mode | Fork already correct | PV2 fields are plain W/mV/mA (shuette divided by 10) | internal/delta2_max.py:61-65 | none |
| [#515](https://github.com/shuette42/ecoflow-energy-ha/issues/515) (closed) | [PowerPulse 2] False Start Charging timeout in Solar mode when Continuous Charging is OFF | N/A | PowerPulse/PowerGlow wallbox, not supported by the fork | - | none |
| [#510](https://github.com/shuette42/ecoflow-energy-ha/issues/510) (open) | Ocean 2 Plus (RE41): expose scheduled charging / work mode | N/A | Ocean 2 Plus (RE41), not supported by the fork | - | none |
| [#495](https://github.com/shuette42/ecoflow-energy-ha/issues/495) (closed) | [PowerPulse 2] Add Screen and LED controls (settings field `4.21`) | N/A | PowerPulse/PowerGlow wallbox, not supported by the fork | - | none |
| [#493](https://github.com/shuette42/ecoflow-energy-ha/issues/493) (closed) | [PowerPulse 2] Add Plug-and-Play switch (`switchBits` 0x02) | N/A | PowerPulse/PowerGlow wallbox, not supported by the fork | - | none |
| [#491](https://github.com/shuette42/ecoflow-energy-ha/issues/491) (closed) | [PowerPulse 2] Clarify “Wallbox Charging Current” as charging-current setpoint | N/A | PowerPulse/PowerGlow wallbox, not supported by the fork | - | none |
| [#490](https://github.com/shuette42/ecoflow-energy-ha/issues/490) (closed) | [PowerPulse 2] Add Battery Discharge Block switch (`switchBits` 0x01) | N/A | PowerPulse/PowerGlow wallbox, not supported by the fork | - | none |
| [#486](https://github.com/shuette42/ecoflow-energy-ha/issues/486) (open) | Stream Ultra: Batterieentladeleistung bleibt bei 0 W | **Yes - fixed** | `powGetBpCms` = proto 254/21 f518, group aggregate (AC side) filled only by the unit that computes the system figures; others send 0. Per-unit DC power = BMS 32/50 f26/f27. Fork sample: powGetBpCms 1915 W vs this unit's inputWatts 900 = amp 44.671 A x vol 20.161 V (gridSysDeviceCnt 2) | public/stream_ac.py:203, internal/stream_ac.py:266, const.py STREAM_POWER_BATTERY | Renamed to "System Battery Power" (4960a2b). Per-unit value already exposed as In/Out Power. Other system fields (powGetSysGrid/SysLoad/PvSum/SysLoadFrom*, sysGridConnectionPower) also read 0 on followers - see core/STREAM notes |
| [#482](https://github.com/shuette42/ecoflow-energy-ha/issues/482) (closed) | [PowerPulse 2] Add Phase Setting control (Auto / One phase / Three phases) | N/A | PowerPulse/PowerGlow wallbox, not supported by the fork | - | none |
| [#481](https://github.com/shuette42/ecoflow-energy-ha/issues/481) (closed) | [PowerPulse 2] Add “Custom Charging Current” control | N/A | PowerPulse/PowerGlow wallbox, not supported by the fork | - | none |
| [#480](https://github.com/shuette42/ecoflow-energy-ha/issues/480) (closed) | [PowerPulse 2] Add controls for Solar “Continuous charging” and “Solar minimum charging current” | N/A | PowerPulse/PowerGlow wallbox, not supported by the fork | - | none |
| [#464](https://github.com/shuette42/ecoflow-energy-ha/issues/464) (open) | Device support: Delta Pro Ultra (Y711), Smart Home Panel 2 (HD31), HT31 | Useful knowledge | DPU (Y711) Remaining Time semantics unconfirmed | public/delta_pro_ultra.py | none |
| [#458](https://github.com/shuette42/ecoflow-energy-ha/issues/458) (closed) | STREAM AC 5000 - "Home Power" 200W fixed | Useful knowledge | 200 W 'Home Power' = unit's default strategy (200 W + plug load without tasks) | - | none |
| [#437](https://github.com/shuette42/ecoflow-energy-ha/issues/437) (closed) | In standard mode offline BK01 (STREAM Micro Inverter) devices trigger false account-wide reauthentication on empty (but successful) API responses | Fork already correct | Empty but successful API answer for offline BK01 -> false reauth | __init__.py:276-287 | none; see core notes |
| [#436](https://github.com/shuette42/ecoflow-energy-ha/issues/436) (open) | PowerOcean pair: publish per-inverter Solar and Battery entities | Useful knowledge | Per-inverter rows of a pair; solar-surplus threshold re-send loop | - | none |
| [#434](https://github.com/shuette42/ecoflow-energy-ha/issues/434) (closed) | Add support for EcoFlow Smart Panel 40 – serial prefix HR61 | Useful knowledge | Smart Panel 40 HR61 | internal/ocean_pro.py | none |
| [#427](https://github.com/shuette42/ecoflow-energy-ha/issues/427) (open) | OCEAN Pro inverter and battery (E7 P2S, serial prefix HR51) | Useful knowledge | OCEAN Pro HR51 + panel HR61; circuit switching unconfirmed | internal/ocean_pro.py (read-only) | none |
| [#420](https://github.com/shuette42/ecoflow-energy-ha/issues/420) (open) | Programmatic Adjustment of Power Ocean Charge and Feed-in Schedule Times | N/A | Schedule times (private API) | - | none |
| [#419](https://github.com/shuette42/ecoflow-energy-ha/issues/419) (closed) | PowerOcean: expose battery control mode status and investigate Protobuf control | N/A | Battery control mode (private API) | - | none |
| [#402](https://github.com/shuette42/ecoflow-energy-ha/issues/402) (closed) | Smart Meter (BK21): Phase Current and Power values are physically inconsistent | Useful knowledge | Phase current is RMS incl. non-active share, power is active only - they need not multiply out | public/smart_meter.py:32-34 | none |
| [#401](https://github.com/shuette42/ecoflow-energy-ha/issues/401) (closed) | STREAM 5000 linked pair: PV1-PV4 exposed for only one device and assigned incorrectly | Known / handled | Linked pair PV entries merged | internal/stream_ac_5000.py:_own_entry | none (fork already per-serial) |
| [#394](https://github.com/shuette42/ecoflow-energy-ha/issues/394) (closed) | 2 x Stream AC 5000 | Useful knowledge | Linked AC5000 pair reports system SoC/power on both units | - | none |
| [#393](https://github.com/shuette42/ecoflow-energy-ha/issues/393) (closed) | STREAM AC 5000 (ES22): battery charge/discharge power sensors report 0 W while actively charging | Useful knowledge | 32/50 f8 = signed pack current (mA), f26/f27 = per-pack charge/discharge W | internal/stream_ac_5000.py | none |
| [#381](https://github.com/shuette42/ecoflow-energy-ha/issues/381) (closed) | PowerOcean: feed power to grid control via scheduled tasks | N/A | Feed to grid via scheduled tasks (private API) | - | none |
| [#347](https://github.com/shuette42/ecoflow-energy-ha/issues/347) (closed) | EcoFlow Energy with Dual Single Phase Power Ocean J32E | Useful knowledge | Parallel pair: energy flow list, one row per inverter + total row | public/powerocean.py | none |
| [#341](https://github.com/shuette42/ecoflow-energy-ha/issues/341) (closed) | Diagnostics publish the device name unredacted, which carries the serial suffix | Core note | Diagnostics: device name carries serial suffix | diagnostics.py | for api-core session |
| [#339](https://github.com/shuette42/ecoflow-energy-ha/issues/339) (closed) | Device support: EcoFlow Solar Tracker (model codes HZ31 / S02F) — identity confirmed, field mapping + raw captures attached | N/A | Solar Tracker, not supported by the fork | - | none |
| [#337](https://github.com/shuette42/ecoflow-energy-ha/issues/337) (closed) | Max Charge SoC on STREAM AC Pro: accepts below 50%, and only the master of a linked system appears to take the write | Useful knowledge | Max Charge SoC < 50 % is applied by the unit but the unit keeps reporting the old value (firmware V1.0.2.1); linked units propagate the limit | public/stream_ac.py:112 (read-only sensor) | none; fork has no writable Max Charge SoC on public STREAM |
| [#336](https://github.com/shuette42/ecoflow-energy-ha/issues/336) (closed) | Battery SOC reads 0% on three of four STREAM AC Pro units | Fork already correct | Follower units send system SoC as 0 | public/stream_ac.py:98 | none; cmsBattSoc is disabled-by-default/auto and labelled system-wide |
| [#335](https://github.com/shuette42/ecoflow-energy-ha/issues/335) (closed) | Stream AC Pro Max-SOC cant be set anymore in V1.18 1.18.1 | Useful knowledge | see #337 | - | none |
| [#331](https://github.com/shuette42/ecoflow-energy-ha/issues/331) (closed) | Add support for native EcoFlow Smart Meter EF-EM-P3-120 (BK21 / EFSMARTMETER-EU-120A) | **Yes - fixed** | BK21 private proto: current 958/959/784 = L1/L2/L3; energy record 773 = six lifetime counters, .1/.2/.3/.7 net (can fall), .4 import, .6 export; power factor 618 always 0 | internal/proto/ef_smartmeter.proto:32-37, internal/smart_meter.py:150-245, public/smart_meter.py:38-60 | L1/L3 current swap fixed (9c97b42); net counters TOTAL instead of TOTAL_INCREASING, 'daily' titles corrected (d3af2f1) |
| [#328](https://github.com/shuette42/ecoflow-energy-ha/issues/328) (closed) | PowerOcean: grid charging control via scheduled tasks | N/A | Grid charging via scheduled tasks (private API) | - | none |
| [#326](https://github.com/shuette42/ecoflow-energy-ha/issues/326) (closed) | Support PowerOcean Single Phase 6 kW (serial prefix J329) | Useful knowledge | J329 prefix | - | none |
| [#323](https://github.com/shuette42/ecoflow-energy-ha/issues/323) (closed) | Stream Ultra X SoC fluctuates between master unit and overall system charge on each poll / push | Fork already correct | Unit SoC (`soc`, f242) vs system SoC (`cmsBattSoc`, f262) must not share one sensor | public/stream_ac.py:98, :291 | none (fork has separate Battery Level / System Battery Level since 68d95b1, c0f22dc) |
| [#321](https://github.com/shuette42/ecoflow-energy-ha/issues/321) (closed) | PowerFlow PowerOcean J329 support | Useful knowledge | J329 prefix | - | none |
| [#304](https://github.com/shuette42/ecoflow-energy-ha/issues/304) (closed) | DELTA 3 Plus (P351) detected but skipped as unsupported – no parser available | **Yes - fixed** | BMS heartbeat f1 `num`: 0 built-in battery, 1+ extra battery; both wrote the same keys (D3 Plus: pack 0 12.990 kWh, pack 1 11.147 kWh) | internal/delta3.py:887, :898, :908 | Extra-battery reports dropped (767f59d) |
| [#297](https://github.com/shuette42/ecoflow-energy-ha/issues/297) (closed) | Options flow offers devices the integration cannot handle | N/A | shuette-specific (own coordinator/config flow/diagnostics) | - | none |
| [#296](https://github.com/shuette42/ecoflow-energy-ha/issues/296) (open) | Support for Ecoflow River 3 | Useful knowledge | River 3 support in shuette; River 3 Plus extra battery may hit the same pack-number issue as #304 (unverified) | internal/river3.py:539 | none - no capture |
| [#289](https://github.com/shuette42/ecoflow-energy-ha/issues/289) (closed) | Stream microinverter going offline at low/no PV triggers spurious "credentials expired" reauth prompt | Fork already correct | Offline microinverter / empty quota triggered reauth | __init__.py:276-287 (only login errors 8513 -> reauth) | none; see core notes |
| [#287](https://github.com/shuette42/ecoflow-energy-ha/issues/287) (closed) | Enhanced mode: Delta 2 Max expansion battery sensors unavailable, EMS state dropped, and two devices skipped | Useful knowledge | Delta 2 Max: bms_slave1/2 keys, soh vs cycSoh vs full/design cap | internal/delta2_max.py | none |
| [#284](https://github.com/shuette42/ecoflow-energy-ha/issues/284) (closed) | STREAM AC 5000: make Max Grid Input Power writable | Useful knowledge | Max Grid Input Power (cfg 10.2) is the setting that governs grid charging; writing 10.1/10.2 leaves the other untouched | internal/stream_ac_5000.py chgPowLimit / feedGridModePowLimit | none (fork already writes partial property 10) |
| [#267](https://github.com/shuette42/ecoflow-energy-ha/issues/267) (closed) | Support PowerOcean (serial prefix HJ36) | Useful knowledge | HJ36 prefix | - | none |
| [#264](https://github.com/shuette42/ecoflow-energy-ha/issues/264) (closed) | Stream AC Pro: Backup Reserve slider offers values the device rejects | Fork already correct | Backup Reserve floor = Min Discharge SoC + 3, measured on BK31 | public/stream_ac.py:349-371 (BatteryBackupLevel with cmsMinDsgSoc, offset 3) | none |
| [#258](https://github.com/shuette42/ecoflow-energy-ha/issues/258) (closed) | STREAM 5000 / AC 5000: Solar Power is the third-party figure, not the unit's own solar | Useful knowledge | STREAM 5000 'Solar Power' field is the third-party ('Other') figure, not own strings | - | fork exposes own pvPower only |
| [#247](https://github.com/shuette42/ecoflow-energy-ha/issues/247) (closed) | Support for PowerPulse wallbox (serial prefix C376) | N/A | PowerPulse/PowerGlow wallbox, not supported by the fork | - | none |
| [#245](https://github.com/shuette42/ecoflow-energy-ha/issues/245) (closed) | Support for PowerOcean (3p) and PowerPulse 1 | Useful knowledge | PowerOcean 3p | - | none |
| [#237](https://github.com/shuette42/ecoflow-energy-ha/issues/237) (closed) | Raw data capture stops working the moment a device is supported | N/A | shuette-specific (own coordinator/config flow/diagnostics) | - | none |
| [#234](https://github.com/shuette42/ecoflow-energy-ha/issues/234) (closed) | STREAM AC 5000: a task deleted in the EcoFlow app is not retracted from the setpoints | N/A | AC5000 task list retraction (shuette's schedule entities) | - | none |
| [#231](https://github.com/shuette42/ecoflow-energy-ha/issues/231) (closed) | Stream 5000 support | Known | STREAM 5000 support (source of the fork's ES21 work) | internal/stream_ac_5000.py | none |
| [#230](https://github.com/shuette42/ecoflow-energy-ha/issues/230) (closed) | PowerStream support | Fork already correct | PowerStream quota is deci-W (pv1 510 + pv2 580 = 1090 = invOutputWatts); gridConsWatts < 0 = export; pvXInputCur scale unsettled | public/powerstream.py:43-63 | none |
| [#225](https://github.com/shuette42/ecoflow-energy-ha/issues/225) (closed) | Power Ocean J327 | Useful knowledge | J327 single phase | - | none |
| [#220](https://github.com/shuette42/ecoflow-energy-ha/issues/220) (closed) | Whole-number readings show a decimal place | N/A | Display precision | - | none |
| [#219](https://github.com/shuette42/ecoflow-energy-ha/issues/219) (closed) | Battery Energy mismatch | Useful knowledge | PowerOcean energy balance closes per frame; counters within 0.5 % of web app | - | none |
| [#216](https://github.com/shuette42/ecoflow-energy-ha/issues/216) (closed) | DELTA 3 MAX (D3N1) and LFP Batterys of 2KW and 5KW (HW51ZEH...) not recognized | Useful knowledge | D3N1 = DELTA 3 Max, same family | - | none |
| [#205](https://github.com/shuette42/ecoflow-energy-ha/issues/205) (closed) | Add parser support for PowerOcean Plus (serial prefix R372) — "unknown product" in Enhanced Mode | Useful knowledge | R372 PowerOcean Plus | - | none |
| [#194](https://github.com/shuette42/ecoflow-energy-ha/issues/194) (closed) | Support for PowerOcean J32B | Useful knowledge | J32B prefix | - | none |
| [#188](https://github.com/shuette42/ecoflow-energy-ha/issues/188) (closed) | Powerstream : no information | N/A | PowerStream detection in shuette | - | none |
| [#185](https://github.com/shuette42/ecoflow-energy-ha/issues/185) (closed) | DELTA 2 Max: Max Charge SoC writes from HA no longer update device/app in v1.15.0 | N/A | Writes reported as sent before broker ack (shuette's MQTT layer) | - | core note: fork publish is fire-and-forget too, see core notes |
| [#184](https://github.com/shuette42/ecoflow-energy-ha/issues/184) (closed) | Support for EcoFlow DELTA 3 Ultra (D511...) | N/A | DELTA 3 Ultra connectivity, no data | - | none |
| [#182](https://github.com/shuette42/ecoflow-energy-ha/issues/182) (closed) | DELTA 3 serial prefix P231 not routed to existing DELTA 3 parser in v1.15.0 | Useful knowledge | Base DELTA 3 (P231) uses the Max Plus message set | registry.py:65 | none |
| [#181](https://github.com/shuette42/ecoflow-energy-ha/issues/181) (closed) | Delta 3 Max Plus: AC charging control (grid charge on/off, power limit, charge mode) | **Yes - fixed** (range) | AC charge power + charge mode are one setting (field 54 + 125); Max Plus app range 200-2400 W; charge mode reports only on change (no read-back) | internal/delta3.py:114 (companion already sent), :389-399 | Max Plus range 200-2400 W (dbb30a1); write already correct |
| [#177](https://github.com/shuette42/ecoflow-energy-ha/issues/177) (closed) | Support the EcoFlow STREAM AC 5000 | Known | STREAM AC 5000 support (source of fixtures) | internal/stream_ac_5000.py | none |
| [#165](https://github.com/shuette42/ecoflow-energy-ha/issues/165) (closed) | PowerOcean HJ35 serial prefix not recognized | Useful knowledge | HJ35 prefix | - | none |
| [#161](https://github.com/shuette42/ecoflow-energy-ha/issues/161) (closed) | Add support for WAVE 3 (AC71) air conditioner | Useful knowledge | WAVE 3 not readable over IoT API (1006), app path only | internal/wave3.py | none |
| [#145](https://github.com/shuette42/ecoflow-energy-ha/issues/145) (closed) | Add support for EcoFlow Ocean 2 (serial prefix RE11) | N/A | Ocean 2, not supported by the fork | - | none |
| [#141](https://github.com/shuette42/ecoflow-energy-ha/issues/141) (closed) | Add support for Stream Micro (BK01) | N/A | Stream Micro (BK01) parser in shuette | - | none |
| [#140](https://github.com/shuette42/ecoflow-energy-ha/issues/140) (closed) | Stream Ultra / Ultra X: make AC1 and AC2 controllable (switch entities) | Useful knowledge | AC1/AC2 writes confirmed on BK31 only; BK11/BK61 unconfirmed | public/stream_ac.py:376-411 (relay2/relay3 cfgRelay*Onoff) | none; fork uses the documented public-API write |
| [#139](https://github.com/shuette42/ecoflow-energy-ha/issues/139) (closed) | Stream Ultra / Ultra X: expose per-panel PV energy | Fork already correct | Per-string PV power/energy BK11/BK61 | public/stream_ac.py:212-250 | none |
| [#136](https://github.com/shuette42/ecoflow-energy-ha/issues/136) (closed) | Verify BK41 (Stream Max) and BK51 (Stream AC) telemetry against real hardware | Useful knowledge | BK41/BK51 layout unverified (assumed = BK31) | - | none |
| [#135](https://github.com/shuette42/ecoflow-energy-ha/issues/135) (closed) | Add support for EcoFlow Smart Meter (SM3A) | N/A | SM3A (Shelly-based) meter, no data path | - | none |
| [#132](https://github.com/shuette42/ecoflow-energy-ha/issues/132) (closed) | PowerOcean Pack 2 remaining-capacity entity stays unavailable after enabling | **Yes - fixed** | bpRemainWatth is energy left in a pack (falls on discharge); shuette: energy_storage / measurement | public/powerocean.py:190 | EnergyStorageSensorEntity (d405872) |
| [#119](https://github.com/shuette42/ecoflow-energy-ha/issues/119) (closed) | Switches and numbers show no state for up to two minutes after a restart in Enhanced mode | N/A | shuette-specific (own coordinator/config flow/diagnostics): control state restore after restart | - | none |
| [#118](https://github.com/shuette42/ecoflow-energy-ha/issues/118) (closed) | Device type classification falls back to product name when API returns device_type: unknown | N/A | shuette-specific (own coordinator/config flow/diagnostics) | - | none |
| [#111](https://github.com/shuette42/ecoflow-energy-ha/issues/111) (closed) | Delta 3 Max Plus (D3M... serial) never contacted in Enhanced Mode – zero MQTT attempts logged | Useful knowledge | D3 Max Plus public API exposes 27 keys, AC charge settings not among them | public/delta3_max_plus.py | none |
| [#110](https://github.com/shuette42/ecoflow-energy-ha/issues/110) (closed) | All entities show 'unknown' on DELTA 3 Max Plus despite API returning data (availability_stage: stale) | N/A | Routing 'DELTA 3 Max Plus' to the Delta 2 Max parser in shuette | registry.py:67, :122 | none |
| [#105](https://github.com/shuette42/ecoflow-energy-ha/issues/105) (closed) | European STREAM AC Pro and P1 Meter detected but no entities created | N/A | STREAM AC Pro onboarding / P1 meter not a device | - | none |
| [#103](https://github.com/shuette42/ecoflow-energy-ha/issues/103) (closed) | Delta Pro and Smart Home Panel 2 has no energy entities (KWh) | N/A | Entities came from ef_ble | - | none |
| [#100](https://github.com/shuette42/ecoflow-energy-ha/issues/100) (closed) | DELTA 3 Max Plus detected and configuration succeeds, but no devices/entities are created | **Yes - fixed** (range) | Max Plus AC charge slider 200-2400 W on three units | internal/delta3.py:389 | see #181 |
| [#98](https://github.com/shuette42/ecoflow-energy-ha/issues/98) (closed) | feat: add support for Stream AC Pro | Fork already correct | AC outlet switches, backup-reserve floor (BK31) | public/stream_ac.py:374-411 | none |
| [#95](https://github.com/shuette42/ecoflow-energy-ha/issues/95) (closed) | DELTA 2 Max: AC Charge Speed number entity sends wrong value / falls back to 400 W | Fork already correct | AC charge speed = inv.SlowChgWatts; write slowChgWatts | internal/delta2_max.py:303-311 | none |
| [#93](https://github.com/shuette42/ecoflow-energy-ha/issues/93) (closed) | Any chance Delta 3 Plus could be supported? | N/A | Delta 3 Plus request | - | none |
| [#89](https://github.com/shuette42/ecoflow-energy-ha/issues/89) (closed) | EcoFlow device detected but skipped due to “no parser available” (J32E device) | Useful knowledge | J32E/J32D prefix | - | none |
| [#88](https://github.com/shuette42/ecoflow-energy-ha/issues/88) (closed) | Power Ocean Plus (30KW) | Useful knowledge | PowerOcean Plus prefixes R371/R374/HJ3C; 4294967295 = unpopulated field placeholder on percent fields | public/powerocean.py | none (placeholder on energy fields only 'LIKELY') |
| [#86](https://github.com/shuette42/ecoflow-energy-ha/issues/86) (closed) | PowerOcean Charge upper limit | N/A | Charge upper limit (private API) | - | none |
| [#85](https://github.com/shuette42/ecoflow-energy-ha/issues/85) (closed) | PowerOcean Feed-in mode controls and feed-in power cap | N/A | Feed-in mode controls (private API) | - | none |
| [#84](https://github.com/shuette42/ecoflow-energy-ha/issues/84) (closed) | PowerOcean — Toggle scheduled charge/discharge tasks | N/A | PowerOcean scheduled tasks (private API) | - | none |
| [#71](https://github.com/shuette42/ecoflow-energy-ha/issues/71) (closed) | Add support for EcoFlow STREAM Ultra X | N/A | Stream Ultra X onboarding (shuette) | - | none |
| [#65](https://github.com/shuette42/ecoflow-energy-ha/issues/65) (closed) | Solar Energy stopped updating | N/A | shuette Riemann integrator clock | - | none |
| [#51](https://github.com/shuette42/ecoflow-energy-ha/issues/51) (closed) | "Solarenergie" entity is not increasing | N/A | shuette Riemann integrator | - | none |
| [#50](https://github.com/shuette42/ecoflow-energy-ha/issues/50) (closed) | “Batterie Lade-/Entladezustand” not showing the correct state | N/A | Charge/discharge state derived with hysteresis (shuette) | - | none |
| [#28](https://github.com/shuette42/ecoflow-energy-ha/issues/28) (closed) | Enhanced Mode creates coordinators for unsupported devices | N/A | shuette-specific (own coordinator/config flow/diagnostics) | - | none |
| [#27](https://github.com/shuette42/ecoflow-energy-ha/issues/27) (closed) | Power Pulse (1) Entities missing | N/A | PowerPulse/PowerGlow wallbox, not supported by the fork | - | none |
| [#24](https://github.com/shuette42/ecoflow-energy-ha/issues/24) (closed) | Rename entities to their app counterpart settings | Useful knowledge | Entity names aligned with app (e.g. EMS discharge floor = Backup Reserve) | public/powerocean.py | none |
| [#21](https://github.com/shuette42/ecoflow-energy-ha/issues/21) (closed) | Solarenergy today, year, total | N/A | Daily/annual solar sensors | - | none |
| [#10](https://github.com/shuette42/ecoflow-energy-ha/issues/10) (closed) | „Batterierestkapazität“ does not show the total capacity of all battery packs | Useful knowledge | Packs arrive one per heartbeat, index by pack serial | public/powerocean.py:_inject_battery_params | none |
| [#9](https://github.com/shuette42/ecoflow-energy-ha/issues/9) (closed) | feat: add diagnostic_mode config option for extended diagnostics | N/A | shuette-specific (own coordinator/config flow/diagnostics) | - | none |
| [#8](https://github.com/shuette42/ecoflow-energy-ha/issues/8) (closed) | feat: add region support (EU/US) for API endpoints | N/A | Region support | - | none (fork uses api host) |
| [#7](https://github.com/shuette42/ecoflow-energy-ha/issues/7) (closed) | feat: add PowerGlow and PowerPulse 2 device support | N/A | PowerPulse/PowerGlow wallbox, not supported by the fork | - | none |
| [#6](https://github.com/shuette42/ecoflow-energy-ha/issues/6) (closed) | feat: add PowerOcean controls (feed-in limit, battery charge management) | N/A | PowerOcean controls (private API) | - | none |
| [#5](https://github.com/shuette42/ecoflow-energy-ha/issues/5) (closed) | Battery pack numbering starts with "Pack 2" instead of "Pack 1" | Useful knowledge | Phantom EMS entry in pack list | public/powerocean.py | none |
| [#4](https://github.com/shuette42/ecoflow-energy-ha/issues/4) (closed) | PowerPulse 2 Entities are missing | N/A | PowerPulse/PowerGlow wallbox, not supported by the fork | - | none |
| [#3](https://github.com/shuette42/ecoflow-energy-ha/issues/3) (closed) | PowerGlow entities missing | N/A | PowerPulse/PowerGlow wallbox, not supported by the fork | - | none |
| [#2](https://github.com/shuette42/ecoflow-energy-ha/issues/2) (closed) | Message "Authentication expired for EcoFlow Energy" | Fork already correct | 8513 for devices not bound to the key -> reauth loop | api/__init__.py:19-20, :135 | none; see core notes |
| [#1](https://github.com/shuette42/ecoflow-energy-ha/issues/1) (closed) | PowerPulse 2 is detected as an "unknown device" (or similar) | N/A | PowerPulse/PowerGlow wallbox, not supported by the fork | - | none |
