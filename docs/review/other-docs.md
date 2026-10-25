# Review: PowerOcean, Smart Home Panel 1/2, WAVE, Glacier, Power Kits vs. EcoFlow public API docs

Scope: public-API device classes in `custom_components/ecoflow_cloud/devices/public/`
(`powerocean.py`, `smart_home_panel.py`, `smart_home_panel_2.py`, `wave2.py`, `powerkit.py`)
plus their internal counterparts where a doc fact clearly applies too (`devices/internal/wave2.py`,
`devices/internal/glacier.py`). Paths below are relative to `custom_components/ecoflow_cloud/`.

Sources: `TelosNox/ecoflow-research` `api-docs/power_ocean.md`, `smart_home_panel.md`,
`smarthomepanelii.md` (2026-08-03), `wave_air_conditioner.md`, `glacier.md`, `power_kits.md`;
open issues from `issues/tolwi.jsonl` (snapshot 2026-10-25). Upstream PRs
tolwi/hassio-ecoflow-cloud#937 and #953 were read from the upstream git refs.

None of these devices was available for a live test; every change rests on the doc section and, where
given, the issue values named in its commit message. No unique_id changed: where a key was wrong, the
entity reads the documented key and keeps the unique_id of the old key (`_legacy_unique_id` in
`devices/internal/wave2.py`), so no migration in the shared core was needed.

Severity: **high** = wrong value or a command with a side effect; **medium** = entity never updates /
documented data missing for many users; **low** = cosmetic, unit label, range edge.

## Findings

| Device | Finding | Doc ref / issue | Code location | Severity | Fixed? / why not |
|---|---|---|---|---|---|
| Power Kits | `pv1InWatts` / `pv2InWatts` divided by 10 (`InWattsSolarSensorEntity`), shows 10x too low | power_kits.md GetAllQuotaResponse > kitscc: "PV1/PV2 input power (W)"; #911 (15.455 V x 17534 mA = 271 W, sensor 27.1 W) | `devices/public/powerkit.py:291,320` | high | **Fixed** 3b86d49 |
| Power Kits | AC charging current number allowed 0 A | power_kits.md IC_LOW "AC input current (range: 1-23)" | `devices/public/powerkit.py` `numbers()` | low | **Fixed** 538eaba (min 1; the 16 A cap is an intentional safety limit and stays) |
| Power Kits | kitscc `chgEnergy`/`dayEnergy`, bbcin `dsgEnergy` exposed as mA current | power_kits.md kitscc/bbcin: "(Wh)" | `devices/public/powerkit.py:352,413` | low | **Fixed** 5fbe169 (EnergySensorEntity; still disabled by default) |
| Power Kits | kitscc `batWatts` divided by 1000 although doc says "(W)" | power_kits.md kitscc `batWatts` "Battery power (W)"; #911 shows the /1000 value (271.985 W) matching V x I | `devices/public/powerkit.py:285` | – | Not changed: live data in #911 contradicts the doc, the code matches the device |
| Power Kits | Several sub-devices create no entities (only the hub) | #878, #532; upstream fix proposed in tolwi/hassio-ecoflow-cloud#855 (sub-device discovery for flat quota response) | sub-device discovery in `config_flow.py` | medium | Not fixed: the cause is in the config flow, outside the device classes; #855 is a config-flow change the docs cannot confirm, see notes |
| Power Kits | LD_DC `chSwitch` / BBC_OUT `dischgParaSet` examples use moduleType 15362 (BBC_IN) and the hub SN as moduleSn | power_kits.md LD_DC, BBC_OUT | `devices/public/powerkit.py:112` (`dcSwitchFunction`), `switches()` | – | Not changed: doc examples are visibly copy-pasted (moduleType table says LD_DC = 15368); code follows them; no failure report |
| Power Kits | iclow "AC Output" switch reads `invSwSta`, which is an ichigh field | power_kits.md ichigh `invSwSta` | `devices/public/powerkit.py:696` | low | Not fixed: known TODO, needs a cross-sub-device read; no issue |
| Power Kits | `busVol` scaled as 0.1 mV (DeciMilliVolt), doc says mV | power_kits.md iclow `busVol` "Bus Voltage (mV)"; doc example 725, code comment 454198 | `devices/public/powerkit.py:271` | low | Not changed: example values disagree with each other, no live evidence |
| Power Kits | Undocumented in integration: BP `socUpperLimit`/`socLowerLimit`, `lcdStandbyMin`, `oilStartDownLimit`/`oilStopUpLimit`, BBC_IN `chgParaSet`, smart generator `powerOffGen` | power_kits.md Set & Get Quota | – | – | Report only: controls not added without a device to verify the per-module moduleSn addressing |
| Smart Home Panel | Setting Min Discharge Level resets Max Charge Level to 100 %: command read `heartbeat.backupChaDiscCfg.forceChargeHigh`, a key that is never reported | smart_home_panel.md "Pushing standby charging/discharging parameters" (cmdSet 11, id 29), GetCmdResponse key `backupChaDiscCfg.forceChargeHigh` | `devices/public/smart_home_panel.py:285` | high | **Fixed** e06a7a8, test 6b08716 |
| Smart Home Panel | All 20 `timeTask` slots arrive under one key; Scheduled Charge entities flap between slots | smart_home_panel.md timeTask: `index` "Task index", GetCmdResponse returns a list of tasks with their own index | `devices/public/smart_home_panel.py` `_absorb_time_task` | medium | **Fixed** 38efd74, adopted unchanged from tolwi/hassio-ecoflow-cloud#937 (author volkovskiyda) |
| Smart Home Panel | #937's second commit relabels battery-port `powType` as direction (0 idle, 1 discharging, 2 charging) | not in the doc (`infoList` is undocumented); author's 3-day history comparison | `devices/public/smart_home_panel.py:222,226` | low | Not adopted: no doc evidence, and it renames an attribute templates may use; can be taken from #937 on the owner's data alone |
| Smart Home Panel | Scheduled-charge command sends `timeScale: [-1]*18`, doc example uses 255/127 bytes | smart_home_panel.md "Setting the scheduled charging job" | `devices/public/smart_home_panel.py:492` | – | Not changed: -1 as a signed byte is 255; works for current users |
| Smart Home Panel | Min Discharge Level limited to 0-30 %, Max Charge Level 50-100 % | doc gives no range for `discLower` / `forceChargeHigh` | `devices/public/smart_home_panel.py` `numbers()` | – | Not changed: no documented range to compare against |
| Smart Home Panel | Not exposed: channel current config (id 20, cur 6/13/16/20/30), grid config (id 22), channel enable (id 26), load channel names (id 32), emergency mode (id 64), `heartbeat.workTime` / `backupFullCap` | smart_home_panel.md Set & Get Quota, heartbeat | – | – | Report only |
| Smart Home Panel 2 | Circuit on/off command uses `loadIncreInfo.hall1IncreInfo.ch{X}Sta`, the 2026-08-03 doc shows `hallIncreInfo` | smarthomepanelii.md Settings > "Turn on/off the circuit" | `devices/public/smart_home_panel_2.py:351` | – | Not changed: that doc example is malformed JSON (extra brace) and every other key, quota and set, uses `hall1IncreInfo`; no failure report |
| Smart Home Panel 2 | Generator charging power `oilEngineWatt` (500-3000) is not documented | smarthomepanelii.md (absent) | `devices/public/smart_home_panel_2.py:164` | – | Not changed: undocumented, not wrong per doc |
| Smart Home Panel 2 | `backupReserveSoc` limited to 10-50 % | doc gives no range | `devices/public/smart_home_panel_2.py:125` | – | Not changed |
| Smart Home Panel 2 | EPS switch also sends `smartBackupMode: 0` when switching EPS off | not in doc | `devices/public/smart_home_panel_2.py:222` | low | Not changed: deliberate mutual exclusion, no report of harm |
| Smart Home Panel 2 | MQTT quota carries no SoC; battery levels only refresh via quota/all | smarthomepanelii.md "Report Device Quota" example (wattInfo/loadInfo/backupInfo only); #546 | `devices/public/smart_home_panel_2.py` (QuotaScheduledStatusSensorEntity 60 s) | medium | No change needed: 60 s quota/all refresh is already in place; #546 can be closed upstream |
| Smart Home Panel 2 | Ranges match the doc: `chargeWattPower` 500-7200, `foceChargeHight` 80-100, `oilMaxOutputWatt` 3000-12000; `chXEnableSet` 1/2, `chXForceCharge` strings | smarthomepanelii.md Settings / Control | `devices/public/smart_home_panel_2.py` | – | OK |
| Smart Home Panel 2 | Not exposed: `masterCur` (60-100, "10x"), per-circuit `setAmp` (10/15/20/30/40/50/60), `Energy{1..3}Info.devInfo.type` | smarthomepanelii.md Settings, Live Data | – | – | Report only |
| WAVE 2 | Keys with trailing space / truncation: `"pd.psdrPower "`, `"pd.batPower "`, `"power.mpptPwr "`, `"power.acPwrI"` never match | wave_air_conditioner.md GetAllQuotaResponse: `pd.psdrPower`, `pd.batPower`, `power.mpptPwr`, `power.acPwrIn` | `devices/internal/wave2.py` `sensors()` | medium | **Fixed** cf0b735 (unique_id kept) |
| WAVE 2 | Main Battery Level reads `bms.soc`, Min/Max Cell Temperature read `bms.minCellTmp`/`bms.maxCellTmp`; none exists | wave_air_conditioner.md: `pd.batSoc` (0-100), `bms.minCellTemp`, `bms.maxCellTemp`; #783 ("State of Charge shows unknown as it always has") | `devices/internal/wave2.py` `sensors()` | medium | **Fixed** 285dc1b (unique_id kept) |
| WAVE 2 | Public MQTT reports (`typeCode` analysisPD / devStatus / analysisPOWER) stored as `unknown_<typeCode>.*`, no entity updates from MQTT | wave_air_conditioner.md Report Device Quota examples; fields listed as `pd.*` / `power.*` in GetAllQuotaResponse | `devices/public/wave2.py` `_prepare_data` | medium | **Fixed** d6d8cb1 (local to the WAVE 2 class; analysisBMS left out, it is BMS_SLAVE / moduleType 4) |
| WAVE 2 | `bms.tmp` (Battery Temperature) has no doc counterpart | wave_air_conditioner.md (absent) | `devices/internal/wave2.py:80` | low | Not changed: may exist on the internal API; no evidence either way |
| WAVE 2 | Setpoint in °F (60-86) when `pd.tempSys` = 1 | doc only gives 16-30 °C | `devices/internal/wave2.py:25` | – | Not changed: matches device behaviour reported in #402 (already addressed by the earlier "follow the device's temperature unit" fix; #402 can be closed upstream) |
| WAVE 2 | AC Out shows consumption, AC In 0 | #885 (WAVE 3, not WAVE 2) | `devices/internal/wave3.py` | – | Out of scope: WAVE 3 is internal-only and not in `wave_air_conditioner.md` |
| WAVE 2 | Not exposed: screen timeout (`display`), timer (`sacTiming`), buzzer (`beepEn`), temperature display, automatic drainage (`wteFthEn`), light strip (`rgbState`) | wave_air_conditioner.md Set & Get Quota | – | – | Report only |
| PowerOcean | `mpptPwr`, `evPwr`, `chargingStatus` documented but not mapped | power_ocean.md GetAllQuotaResponse; #795 (evPwr, chargingStatus) | `devices/public/powerocean.py:92-94` | medium | **Fixed** 45d18b5 (disabled by default, auto-enabled when quota/all reports them) |
| PowerOcean | Combined SoC read only as MQTT `96_8.bpSoc`; quota/all key is `bpSoc` | power_ocean.md "Battery SoC" | `devices/public/powerocean.py:69` | low | Not changed: changing the key would change the unique_id and MQTT is the live source; adding a second SoC entity would duplicate it |
| PowerOcean | Not exposed: `errorCode` (base64), PowerHeat `sectorA/B/Dhw.tempCurr`, `hpMaster.*`, PowerGlow `hrEnergyStream[].temp/hrPwr`, `emsErrCode.errCode` | power_ocean.md PowerHeat / PowerGlow / PowerPulse | – | – | Report only: these come from accessory devices whose quota layout (own SN or the inverter's) the doc does not settle |
| PowerOcean | `sysBatDsgDownLimit` requested | #765; not in power_ocean.md | – | – | Not done: undocumented field |
| PowerOcean | `hpMaster.tempAmbient` example -3270 | power_ocean.md PowerHeat | – | – | Note: looks like a "no sensor" sentinel; relevant if PowerHeat is ever mapped |
| Glacier | No public-API class; Glacier missing from the public device list | glacier.md documents the full public API; #366 | `devices/registry.py` `device_by_product` | medium | Not done: a new public device class for a device nobody here can test, and registry wiring; candidate for a follow-up with a tester |
| Glacier | Temperatures shown in °F when the unit is °F, setpoints only accept -25..10 (°C) | #586; glacier.md `pd.tmpUnit` (0 °C, 1 °F) but no °F range for `temp` | `devices/internal/glacier.py:93-130` | low | Not fixed: doc gives no °F range; same pattern as the WAVE 2 setpoint fix could follow once a °F range is known |
| Glacier | `temp`, `ecoMode`, `beepEn` (flag), `iceMake`, `deIce` commands match the doc; `InvertedBeeperEntity` only flips the icon, not the value | glacier.md Set & Get Quota | `devices/internal/glacier.py` | – | OK |
| Glacier | Not exposed: `blTime`, `tmpUnit`, `protectBat` (state/level), `sensorAdv`, `beep` | glacier.md Set & Get Quota | – | – | Report only |
| Smart Home Panel 3 | tolwi/hassio-ecoflow-cloud#953 adds grid status, backup reserve, operating mode, charge limit (internal protobuf) | no SHP3 document in api-docs; #950 | `devices/internal/smart_home_panel_3.py` | – | Not adopted: nothing in the docs to check it against; it should come in on the owner's own captures |

## Notes for the core owner (not changed here)

- `devices/public/data_bridge.py` `plain_to_status` knows only the pdStatus/bmsStatus family of
  `typeCode`s. Other JSON public devices with their own type codes (WAVE 2: analysisPD, devStatus,
  analysisPOWER, analysisBMS) end up under `unknown_<typeCode>.*`. WAVE 2 now maps its codes locally;
  a shared mapping would be cleaner if more devices need it.
- Power Kit sub-device discovery (#878, #532) happens in `config_flow.py`; upstream
  tolwi/hassio-ecoflow-cloud#855 (config_flow.py only) proposes a fix for flat quota responses.
- Several doc fields are documented with units the devices do not follow (Power Kit kitscc
  `batWatts` "W", live data mW per #911). Doc units are not proof on their own when live data disagrees.
