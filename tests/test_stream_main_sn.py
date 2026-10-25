"""STREAM system commands go to the system's main SN.

Reference: stream.md, "Obtain the main device serial number of the STREAM
system" (GET /iot-open/sign/device/system/main/sn?sn=..., data.sn) and the
note on every system command: "If there are multiple devices, use the API to
obtain the serial number of the main device"; AC1/AC2 take the unit's own SN.
"""

import asyncio

from custom_components.ecoflow_cloud.api.commands import (
    MAIN_SN_RETRY_SEC,
    MAIN_SN_TTL_SEC,
    MainSnCache,
    stream_command_target_sn,
)
from tests.stream_fakes import ACCOUNT, MASTER, SLAVE, FakeClient, find_entity, make_stream

def test_target_sn_for_documented_system_commands():
    for params in (
        {"cfgBackupReverseSoc": 10},
        {"cfgEnergyStrategyOperateMode": {"operateSelfPoweredOpen": True}},
        {"cfgFeedGridMode": 2},
    ):
        assert stream_command_target_sn({"params": params}, SLAVE, MASTER) == MASTER


def test_target_sn_for_unit_and_unknown_commands():
    for params in ({"cfgRelay2Onoff": True}, {"cfgRelay3Onoff": False}, {"cfgSomethingNew": 1}, {}):
        assert stream_command_target_sn({"params": params}, SLAVE, MASTER) == SLAVE
    # a mixed command is not a pure system command
    assert stream_command_target_sn({"params": {"cfgFeedGridMode": 2, "cfgRelay2Onoff": True}}, SLAVE, MASTER) == SLAVE


def test_cache_falls_back_to_own_sn_and_keeps_last_known():
    now = [0.0]
    cache = MainSnCache(SLAVE, clock=lambda: now[0])
    assert cache.sn == SLAVE and cache.due()

    assert cache.begin_refresh()
    assert not cache.begin_refresh()  # one lookup at a time
    cache.accept(None)
    assert cache.sn == SLAVE and not cache.due()
    now[0] += MAIN_SN_RETRY_SEC
    assert cache.due()

    cache.begin_refresh()
    assert cache.accept(MASTER)
    assert cache.sn == MASTER
    now[0] += MAIN_SN_TTL_SEC - 1
    assert not cache.due()

    # a failed refresh keeps the last known main SN
    now[0] += 1
    cache.begin_refresh()
    cache.accept(None)
    assert cache.sn == MASTER

    cache.invalidate()
    assert cache.due()


def test_slave_sends_system_commands_to_main_sn():
    client = FakeClient(MASTER)
    device = make_stream(client)
    device.data.params["feedGridMode"] = 1
    asyncio.run(client.async_refresh_main_sns())
    assert client.lookups == [{"sn": SLAVE}]
    # the reply to a routed command arrives on the main unit's topic
    assert client.mqtt_client.topics == [f"/open/{ACCOUNT}/{MASTER}/set_reply"]  # type: ignore[attr-defined]

    find_entity(device, client, "feedGridMode").turn_on()
    asyncio.run(find_entity(device, client, "backupReverseSoc").async_set_native_value(20))
    find_entity(device, client, "energyStrategyOperateMode.operateSelfPoweredOpen").turn_on()
    find_entity(device, client, "relay2Onoff").turn_on()

    sent = client.mqtt_client.published  # type: ignore[attr-defined]
    assert [(topic, payload["sn"]) for topic, payload in sent] == [
        (f"/open/{ACCOUNT}/{MASTER}/set", MASTER),
        (f"/open/{ACCOUNT}/{MASTER}/set", MASTER),
        (f"/open/{ACCOUNT}/{MASTER}/set", MASTER),
        (f"/open/{ACCOUNT}/{SLAVE}/set", SLAVE),
    ]
    # the optimistic state stays on the unit whose entity sent it
    assert device.data.params["feedGridMode"] == 2


def test_master_and_unresolved_units_use_their_own_sn():
    for main_sn, sn in ((MASTER, MASTER), (None, SLAVE)):
        client = FakeClient(main_sn)
        device = make_stream(client, sn)
        asyncio.run(client.async_refresh_main_sns())
        assert client.mqtt_client.topics == []  # type: ignore[attr-defined]

        find_entity(device, client, "feedGridMode").turn_off()

        assert client.mqtt_client.published == [  # type: ignore[attr-defined]
            (f"/open/{ACCOUNT}/{sn}/set", client.mqtt_client.published[0][1])  # type: ignore[attr-defined]
        ]
        assert client.mqtt_client.published[0][1]["sn"] == sn  # type: ignore[attr-defined]
