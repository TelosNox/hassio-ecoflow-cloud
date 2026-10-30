## STREAM_5000_AC

*Sensors*
- System Battery Level (`sysEnergyStreamReport-bpSoc`)
- System PV Power (`sysEnergyStreamReport-pvPwr`)
- System Battery Power (`sysEnergyStreamReport-bpPwr`)
- System Load Power (`sysEnergyStreamReport-loadPwr`)
- System Grid Power (`sysEnergyStreamReport-gridPwr`)
- On-Grid Power (`sysEnergyStreamReport-onGridPwr`)
- Status

*Switches*
- Backup Reserve Enabled (`bpBackupConfig-backupSocOnOff` -> `{"sn": "SN", "cmdId": 38, "cmdFunc": 254, "dirDest": 1, "dirSrc": 1, "dest": 2, "needAck": true, "params": {"bpBackupConfig": {"backupSocOnOff": true}}}`)
- Feed-in Limit (`powerParameterConfig-feedToGridLimitOnOff` -> `{"sn": "SN", "cmdId": 38, "cmdFunc": 254, "dirDest": 1, "dirSrc": 1, "dest": 2, "needAck": true, "params": {"powerParameterConfig": {"feedToGridLimitOnOff": true}}}`)
- AC Socket (`devSwitch-acSocketOnoff` -> `{"sn": "SN", "cmdId": 38, "cmdFunc": 254, "dirDest": 1, "dirSrc": 1, "dest": 2, "needAck": true, "params": {"devSwitch": {"acSocketOnoff": true}}}`)

*Sliders (numbers)*
- Backup Reserve Level (`bpBackupConfig-backupSoc` -> `{"sn": "SN", "cmdId": 38, "cmdFunc": 254, "dirDest": 1, "dirSrc": 1, "dest": 2, "needAck": true, "params": {"bpBackupConfig": {"backupSocOnOff": true, "backupSoc": 6666}}}` [0 - 100])

*Selects*
- Operating Mode (`workMode` -> `{"sn": "SN", "cmdId": 38, "cmdFunc": 254, "dirDest": 1, "dirSrc": 1, "dest": 2, "needAck": true, "params": {"workMode": "VALUE"}}` [Self-consumption (SELF_CONSUMPTION), AI mode (AI_MODE), Timer tasks (TIMER_TASK), POU mode (POU_MODE)])


