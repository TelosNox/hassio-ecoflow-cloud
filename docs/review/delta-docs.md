# Review: DELTA / RIVER 2 Pro device classes vs. EcoFlow public-API docs

Scope: public-API classes (`devices/public/…`) for DELTA 2, DELTA 2 Max, DELTA Pro,
DELTA Pro 3, DELTA Pro Ultra, DELTA 3 Max, DELTA 3 Max Plus and RIVER 2 Pro, plus
their internal counterparts where a doc fact clearly applies too.

Sources (private repo `TelosNox/ecoflow-research`, snapshot 2026-10-25):
`api-docs/delta_2.md`, `delta_2_max.md`, `delta_pro.md`, `delta_pro_3.md`,
`delta_pro_ultra.md`, `delta_3_max.md`, `delta_3_max_plus.md`, `river_2_pro.md`;
issues from `issues/tolwi.jsonl`; `diag/*.json` dumps in this repo. Upstream PRs
tolwi#904, #906, #921, #925, #944 were fetched read-only from
`tolwi/hassio-ecoflow-cloud` (`pull/<n>/head`).

Note on structure: the public DELTA 2, DELTA 2 Max and RIVER 2 Pro classes are thin
wrappers that inherit sensors and commands from the internal classes
(`devices/internal/delta2.py`, `delta2_max.py`, `river2_pro.py`), so fixes there
apply to both APIs.

"Not in the doc" alone was not treated as a defect: the docs list only a subset of the
quota fields the devices actually send (e.g. `cycles`, slave-battery keys). Only
contradictions with the doc, a diag dump or an issue were counted.

Severity: **high** = control does nothing / wrong value shown; **medium** = misleading
state or unit; **low** = cosmetic or unverified gap.

## Findings

| Device | Finding | Doc ref / issue | Code location | Severity | Fixed? / why not |
|---|---|---|---|---|---|
| DELTA 2 Max | X-Boost switch sends `acOutCfg` with only `xboost`; the device ignores it | `delta_2_max.md` INV "AC discharging settings" (all four fields, `out_voltage` 4294967295); tolwi#900 (reporter confirmed the full payload works) | `devices/internal/delta2_max.py` switches, `inv.cfgAcXboost` | high | **Fixed** (5b16ad3) |
| DELTA 2 Max | Timeout selects crossed: "Unit Timeout" reads `inv.standbyMin` (AC) but writes PD; "AC Timeout" reads `mppt.carStandbyMin` (car) and writes MPPT with `standbyMins` instead of `standbyMin`; device timeout missing | `delta_2_max.md` PD / INV / MPPT `standbyTime` (`standbyMin`); tolwi#324; `diag/delta_2_max.json` has all three keys | `devices/internal/delta2_max.py` selects | high | **Fixed** (03d03b0): titles + commands follow the key, new `pd.standbyMin` select; existing unique_ids unchanged |
| DELTA 2 Max | Smart-generator start/stop numbers read `bms_emsStatus.minOpenOilEbSoc` / `maxCloseOilEbSoc`, which the device never sends | `delta_2_max.md` BMS `openOilSoc`/`closeOilSoc` → `bms_emsStatus.minOpenOilEb` / `maxCloseOilEb`; `diag/delta_2_max.json` has only the doc keys | `devices/internal/delta2_max.py` numbers | medium | **Not fixed**: needs a key → unique_id change, i.e. a `_migrate_entity_unique_id` entry in top-level `__init__.py` (core, owned by another session). Proposed: `ecoflow[-api]-<sn>-bms-emsStatus-minOpenOilEbSoc` → `…-minOpenOilEb`, same for `maxCloseOilEbSoc` → `maxCloseOilEb`, for DELTA_2_MAX / "DELTA 2 Max" |
| DELTA 2 Max | AC charging command hard-codes `fastChgWatts: 2000`, so every slider change also rewrites the fast-charging limit; slider max fixed at 2400 | `delta_2_max.md` INV `acChgCfg` (`fastChgWatts` + `slowChgWatts`); tolwi#778 (1800 W variants); diag: `inv.FastChgWatts` 2400, `inv.acChgRatedPower` 2400 | `devices/internal/delta2_max.py` `ChargingPowerEntity` | medium | **Not fixed**: doc gives no "keep" value for `fastChgWatts`; sending the current `inv.FastChgWatts` would be the fix but is untested on a device; dynamic max needs a core number feature |
| DELTA 2 Max | "Battery Charging State" maps `bms_emsStatus.chgState` 1→charging, 2→discharging; doc enum is 0 disabled, 1 CC, 2 CV, 3 UPS, 4 PARA (2 is also charging) | `delta_2_max.md` GetAllQuotaResponse `bms_emsStatus.chgState`; possibly tolwi#920 (DELTA 2, "charging and discharging swapped") | `sensor.py` `ChargingStateSensorEntity` (shared), used by `internal/delta2.py`, `delta2_max.py`, … | medium | **Not fixed**: shared sensor class used by many devices; DELTA 2 doc gives no enum for this field, and #920 does not include values. Candidate: use `pd.chgDsgState` (doc: 1 discharging, 2 charging) for the displayed state |
| DELTA 2 Max | `lcdCfg` sends `brighLevel: 255`; doc range is 0–3 | `delta_2_max.md` PD `lcdCfg` | `devices/internal/delta2_max.py` screen timeout select | low | Not fixed: no issue shows the command failing; 255 is the integration-wide "unchanged" convention |
| DELTA 2 Max | 12 V switch state read from `pd.carState`, doc returns `mppt.carState` | `delta_2_max.md` MPPT `mpptCar` | `devices/internal/delta2_max.py` | low | Not fixed: both keys exist in the diag dump with the same value; changing it changes the unique_id |
| DELTA 2 | `lcdCfg` sends `brighLevel: 255`, doc says it "must be set to 3; other values are invalid" | `delta_2.md` PD `lcdCfg` | `devices/internal/delta2.py` selects | low | Not fixed: no issue report of the screen timeout failing; changing it also changes the internal-API payload |
| DELTA 2 | AC charging slider max 1200 W; app allows 1500 W with an extra battery | tolwi#255, #323 (no doc range) | `devices/internal/delta2.py` `ChargingPowerEntity` | low | Not fixed: not a doc deviation; needs a dynamic max (core number feature) |
| DELTA 2 | `acChgCfg` sends `chgPauseFlag: 255`, doc defines 0/1 | `delta_2.md` MPPT `acChgCfg` | `devices/internal/delta2.py` | low | Not fixed: no failure reported; 255 likely "unchanged" |
| DELTA 2 | 12 V DC charge current options 4/6/8 A, doc range 4000–10000 mA | `delta_2.md` MPPT `dcChgCfg` | `devices/const.py` `DC_CHARGE_CURRENT_OPTIONS` | low | Not fixed: device spec is 8 A; doc range looks generic |
| DELTA Pro (public) | `mppt.carOutWatts` shown ×10 | tolwi#455 (two users: app 6 W/7 W, HA 60 W/70 W); internal class already divides by 10; doc says W | `devices/public/delta_pro.py` sensors | high | **Fixed** (e0c87f9): `OutWattsDcSensorEntity` |
| DELTA Pro (public) | X-Boost and AC switches send `id 66` with only one of `enabled` / `xboost`; the doc sends both | `delta_pro.md` "Setting the X-Boost switch" | `devices/public/delta_pro.py` switches | medium | Not fixed: same pattern as tolwi#900 but no DELTA Pro report; payload for "unchanged" not documented |
| DELTA Pro (public) | Backup-reserve / AC-always-on keys `pd.bppowerSoc`, `pd.watthisconfig`, `pd.acautooutConfig` (cmd ids 94/95) are not in the doc and not in `diag/delta_pro.json` | `delta_pro.md` (absent) | `devices/public/delta_pro.py` | low | Not fixed: unverifiable without device data |
| DELTA Pro 3 (public) | Beeper inverted: `BeeperEntity` treats 0 as on; doc `enBeep`/`cfgBeepEn` true = on | `delta_pro_3.md` "Sets the beeper switch", `enBeep` | `devices/public/delta_pro_3.py` switches | high | **Fixed** (e7b9053) |
| DELTA Pro 3 (public) | `cmsChgDsgState` (0/1/2 enum) and `cmsBmsRunState` (0/1) exposed as battery % | `delta_pro_3.md` GetAllQuotaResponse | `devices/public/delta_pro_3.py` sensors | medium | **Fixed** (afef63d) |
| DELTA Pro 3 (public) | `plugInInfoAcInFeq` exposed as battery % | `delta_pro_3.md` "AC input frequency" | `devices/public/delta_pro_3.py` sensors | medium | **Fixed** (2b769b1) |
| DELTA Pro 3 (public) | Output switches read `cfgHvAcOutOpen`, `cfgLvAcOutOpen`, `cfgDc12vOutOpen`, `cfgDc24vOutOpen`, which are set-command names, not quota fields; the device reports `flowInfoAcHvOut`, `flowInfoAcLvOut`, `flowInfo12v`, `flowInfo24v` (0 off, 2 on). State only ever shows the last value HA sent | `delta_pro_3.md` set commands + GetAllQuotaResponse `flowInfo*` | `devices/public/delta_pro_3.py` switches | high | **Not fixed**: needs a key → unique_id migration (core `__init__.py`) and a 0/2 state mapping (the `FlowControlSwitch` pattern from `delta3_max_plus.py`). Proposed migration `ecoflow-api-<sn>-cfgHvAcOutOpen` → `…-flowInfoAcHvOut` etc. |
| DELTA Pro 3 (public) | AC charging slider reads `cfgPlugInInfoAcInChgPowMax` (set name); quota is `plugInInfoAcInChgPowMax` | `delta_pro_3.md` "Sets the maximum AC charging power" | `devices/public/delta_pro_3.py` numbers | high | **Not fixed**: unique_id migration needed (core), same as above |
| DELTA Pro 3 (public) | Commands omit `needAck: true` and send 0/1 where the doc uses `true`/`false` | `delta_pro_3.md` all set commands | `devices/public/delta_pro_3.py` | low | Not fixed: tolwi#615 comments report public-API controls working as is |
| DELTA Pro 3 (public) | `bleStandbyTime` doc unit "h", but doc example 200 and tolwi#428 dump 3600; select uses minute options | `delta_pro_3.md`; tolwi#428 | `devices/public/delta_pro_3.py` selects | low | Not fixed: doc contradicts itself; unit unknown |
| DELTA Pro 3 (public) | `plugInInfoAcOutType` select key not in the doc | `delta_pro_3.md` (absent) | `devices/public/delta_pro_3.py` selects | low | Not fixed: unverifiable |
| DELTA Pro 3 (public) | Documented but not exposed: backup reserve (`cfgEnergyBackup`), GFCI, AC output frequency, PV H/L max current, Power In/Out max charge power, battery order, screen brightness | `delta_pro_3.md` set commands | — | low | Not fixed: feature gap, not a deviation |
| DELTA Pro 3 (internal) | `pow_get_12v`, `pow_get_24v`, `pow_get_5p8`, `pow_get_4p8_1/2` divided by 10; doc and proto say float W | `delta_pro_3.md` `powGet12v…` (W); `ef_dp3_iobroker.proto`; port of tolwi#944 | `devices/internal/delta_pro_3.py` sensors | high | **Fixed** (859b1ae), credited to SeoFood |
| DELTA Pro 3 (internal) | Output switches state unknown and no effect (tolwi#837); max charge level not saved (tolwi#615) | issues; internal uses TCP `id`-style JSON commands, not the doc's `cmdId 17 / cmdFunc 254` | `devices/internal/delta_pro_3.py` | high | Not fixed: internal (app-API) protocol, not covered by the public doc; tolwi#921 rewrites the setters, tolwi#904 sends AC charging power via protobuf, tolwi#906 adds backup reserve via protobuf. None can be verified without a DP3, so not ported |
| DELTA Pro 3 (internal) | JSON payloads first go through the protobuf decoder and log errors (tolwi#924) | tolwi#925 | `devices/internal/delta_pro_3.py` `_prepare_data` | low | Not ported: log noise only, unrelated to the doc |
| DELTA Pro Ultra | AC charge set sends only one of `chgC20Watts` / `chg5p8Watts`; doc example sends both | `delta_pro_ultra.md` `YJ751_PD_AC_CHG_SET` | `devices/public/delta_pro_ultra.py` numbers | low | Not fixed: no failure reported |
| DELTA Pro Ultra | `outAcL11Vol`, `outAcL11Amp`, `outAcL12Vol` used but not listed in the doc (L12Amp, L14Vol/Amp are) | `delta_pro_ultra.md` | `devices/public/delta_pro_ultra.py` sensors | low | Not fixed: looks like a doc gap |
| DELTA 3 Max Plus | Commands, keys, `flowInfo*` (≠ 4 = on) and charge-state enum match the doc | `delta_3_max_plus.md` | `devices/public/delta3_max_plus.py` | — | No deviation found |
| DELTA 3 Max | No public-API class; doc is the Max Plus doc minus AC2 and PV2 | `delta_3_max.md`; tolwi#738 | `devices/registry.py` | medium | **Report only** (missing device): `Delta3MaxPlus` minus `flowInfoAc2Out` / `powGetPv2` would cover it |
| RIVER 2 Pro | Documented commands (`mpptCar`, `acOutCfg`, `watthConfig`, `upsConfig`, `dsgCfg`) match | `river_2_pro.md` | `devices/internal/river2_pro.py` | — | No deviation found; open issues (tolwi#350, #364, #379) are connectivity / feature requests |

## Core findings (for the core session)

- **unique_id migrations needed** in top-level `__init__.py` (`_migrate_entity_unique_id`):
  DELTA 2 Max generator start/stop keys and the public DELTA Pro 3 output switches and
  AC-charging slider (rows above). Device-side changes can follow once the migration exists.
- `sensor.py` `ChargingStateSensorEntity` maps 1 = charging, 2 = discharging. The DELTA 2 Max
  doc defines `bms_emsStatus.chgState` as a charger-phase enum (CC/CV/UPS/PARA), and the
  DELTA Pro 3 / DELTA 3 Max Plus `cms*ChgDsgState` use 1 = discharging, 2 = charging.
  Probably related to tolwi#920.

## Fixes in this branch

| Commit | Change |
|---|---|
| 5b16ad3 | DELTA 2 Max: full `acOutCfg` payload for X-Boost |
| 03d03b0 | DELTA 2 Max: unit / AC / car timeout selects write what they read |
| e0c87f9 | DELTA Pro (public): car output power in 0.1 W |
| e7b9053 | DELTA Pro 3 (public): beeper not inverted |
| afef63d | DELTA Pro 3 (public): charge state / BMS run state not shown as % |
| 2b769b1 | DELTA Pro 3 (public): AC input frequency in Hz |
| 859b1ae | DELTA Pro 3 (internal): DC port power in W (port of tolwi#944) |
| d511e5d | Tests for the above (`tests/test_delta_docs.py`) |

None of these could be tested on real hardware (only STREAM devices are available).
