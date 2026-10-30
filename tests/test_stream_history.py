"""STREAM system history: /device/quota/data and the statistics import.

Reference: stream.md, "Historical data" (beginTime/endTime in UTC, query the
main SN), general_information.md (signature of a JSON body). The documented
responses are in fixtures/stream_history/stream_md_examples.json.
"""

import asyncio
import copy
import hashlib
import hmac
import json
import logging
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from homeassistant.components.recorder.statistics import valid_statistic_id
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.ecoflow_cloud import (
    DEFAULT_HISTORY_BACKFILL_DAYS,
    OPTS_HISTORY_BACKFILL_DAYS,
    extract_devices,
)
from custom_components.ecoflow_cloud.api import EcoflowException
from custom_components.ecoflow_cloud.api.public_api import EcoflowPublicApiClient, flatten_sign_params
from custom_components.ecoflow_cloud.devices.public import stream_history as sh
from custom_components.ecoflow_cloud.devices.public.stream_history import (
    CODE_BATTERY,
    CODE_CO2,
    CODE_GRID,
    CODE_INDEPENDENCE,
    CODE_LOAD,
    CODE_SAVINGS,
    CODE_SOLAR,
    REFRESH_COMPLETED_DAY_SEC,
    LastStatistic,
    StreamHistory,
    StreamSystems,
    is_history_owner,
    last_completed_utc_day,
    statistic_id,
    utc_day_query,
)
from tests.stream_fakes import MASTER, SLAVE

EXAMPLES = json.loads((Path(__file__).parent / "fixtures" / "stream_history" / "stream_md_examples.json").read_text(encoding="utf-8"))
EXAMPLE_BY_CODE = {
    CODE_SOLAR: EXAMPLES["solar"],
    CODE_LOAD: EXAMPLES["load"],
    CODE_GRID: EXAMPLES["grid"],
    CODE_BATTERY: EXAMPLES["battery"],
    CODE_CO2: EXAMPLES["co2"],
    CODE_SAVINGS: EXAMPLES["savings"],
    CODE_INDEPENDENCE: EXAMPLES["independence"],
}
BERLIN = ZoneInfo("Europe/Berlin")


def day_response(code: str, day: date) -> dict[str, Any]:
    """The documented example of the code, its values scaled by the day of month."""
    response = copy.deepcopy(EXAMPLE_BY_CODE[code])
    if code != CODE_INDEPENDENCE:
        for item in response["data"]["data"]:
            item["indexValue"] = str(float(item["indexValue"]) * day.day / 18)
    return response


class FakeApi:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str, str]] = []
        self.fail_after: int | None = None
        self.override: dict[tuple[str, str], dict[str, Any]] = {}

    async def quota_data(self, sn: str, begin: str, end: str, code: str) -> dict[str, Any]:
        if self.fail_after is not None and len(self.calls) >= self.fail_after:
            raise EcoflowException("Request too frequent", code="8521")
        self.calls.append((sn, begin, end, code))
        day = date.fromisoformat(begin[:10])
        if (code, begin) in self.override:
            return self.override[(code, begin)]
        return day_response(code, day)


class FakeStore:
    """Long-term statistics keyed like the recorder: (statistic_id, start) is unique."""

    def __init__(self) -> None:
        self.rows: dict[str, dict[datetime, dict[str, Any]]] = {}
        self.metadata: dict[str, Any] = {}

    async def async_last(self, statistic_id: str) -> LastStatistic | None:
        rows = self.rows.get(statistic_id)
        if not rows:
            return None
        start = max(rows)
        return LastStatistic(start.date(), rows[start]["state"], rows[start]["sum"])

    def add(self, metadata, rows) -> None:
        assert valid_statistic_id(metadata["statistic_id"])
        self.metadata[metadata["statistic_id"]] = metadata
        for row in rows:
            assert row["start"].tzinfo is UTC and row["start"].hour == 0 and row["start"].minute == 0
            self.rows.setdefault(metadata["statistic_id"], {})[row["start"]] = dict(row)

    def series(self, key: str, sn: str = MASTER) -> list[tuple[date, float, float]]:
        rows = self.rows.get(statistic_id(sn, key), {})
        return [(start.date(), rows[start]["state"], rows[start]["sum"]) for start in sorted(rows)]


class Clock:
    def __init__(self, now: datetime) -> None:
        self.now = now
        self.mono = 0.0

    def __call__(self) -> datetime:
        return self.now

    def advance(self, delta: timedelta) -> None:
        self.now += delta
        self.mono += delta.total_seconds()


async def no_sleep(_: float) -> None:
    return None


def make_history(api: FakeApi, store: FakeStore, clock: Clock, backfill_days: int = 3, **kwargs) -> StreamHistory:
    return StreamHistory(
        MASTER,
        api.quota_data,
        store,
        backfill_days,
        clock=clock,
        monotonic=lambda: clock.mono,
        sleep=no_sleep,
        **kwargs,
    )


# --- request and response format ---------------------------------------------


def test_json_body_signature_matches_documented_example():
    # general_information.md, "Step8: verify that the steps to generate the signature are correct"
    body = {"sn": "123456789", "params": {"cmdSet": 11, "id": 24, "eps": 0}}
    flat = flatten_sign_params(body)
    assert flat == "params.cmdSet=11&params.eps=0&params.id=24&sn=123456789"
    target = flat + "&accessKey=Fp4SvIprYSDPXtYJidEtUAd1o&nonce=345164&timestamp=1671171709428"
    sign = hmac.new(b"WIbFEKre0s6sLnh4ei7SPUeYnptHG6V", target.encode(), hashlib.sha256).hexdigest()
    assert sign == "07c13b65e037faf3b153d51613638fa80003c4c38d2407379a7f52851af1473e"
    # nested lists, step 2
    assert flatten_sign_params({"ids": [1, 2], "deviceList": [{"id": 1}], "name": "demo1"}) == (
        "deviceList[0].id=1&ids[0]=1&ids[1]=2&name=demo1"
    )


class _Response:
    status = 200

    async def json(self) -> dict[str, Any]:
        return EXAMPLES["solar"]

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args) -> None:
        return None


class _Session:
    def __init__(self) -> None:
        self.posts: list[dict[str, Any]] = []

    def post(self, url: str, headers: dict[str, str], json: dict[str, Any]) -> _Response:
        self.posts.append({"url": url, "headers": headers, "json": json})
        return _Response()


def test_quota_data_posts_signed_json_body(monkeypatch):
    session = _Session()
    client = EcoflowPublicApiClient(
        "api-e.ecoflow.com", "Fp4SvIprYSDPXtYJidEtUAd1o", "WIbFEKre0s6sLnh4ei7SPUeYnptHG6V", "Home", session  # type: ignore[arg-type]
    )
    monkeypatch.setattr(client, "_gen_nonce", lambda: "345164")
    monkeypatch.setattr("custom_components.ecoflow_cloud.api.public_api.time.time", lambda: 1671171709.428)

    begin, end = utc_day_query(date(2025, 9, 18))
    response = asyncio.run(client.quota_data(MASTER, begin, end, CODE_SOLAR))

    assert response == EXAMPLES["solar"]
    post = session.posts[0]
    assert post["url"] == "https://api-e.ecoflow.com/iot-open/sign/device/quota/data"
    assert post["json"] == {
        "sn": MASTER,
        "params": {"beginTime": "2025-09-18 00:00:00", "endTime": "2025-09-18 23:59:59", "code": CODE_SOLAR},
    }
    headers = post["headers"]
    assert headers["Content-Type"] == "application/json;charset=UTF-8"
    assert headers["nonce"] == "345164" and headers["timestamp"] == "1671171709428"
    target = (
        f"params.beginTime=2025-09-18 00:00:00&params.code={CODE_SOLAR}&params.endTime=2025-09-18 23:59:59"
        f"&sn={MASTER}&accessKey=Fp4SvIprYSDPXtYJidEtUAd1o&nonce=345164&timestamp=1671171709428"
    )
    assert headers["sign"] == hmac.new(b"WIbFEKre0s6sLnh4ei7SPUeYnptHG6V", target.encode(), hashlib.sha256).hexdigest()


def test_documented_responses_parse_into_series_values():
    def value(code: str, key: str):
        series = next(s for m in sh.DAILY_METRICS if m.code == code for s in m.series if s.key == key)
        return sh.series_value(sh.quota_data_items(EXAMPLE_BY_CODE[code]), series)

    assert value(CODE_SOLAR, "solar_energy") == (9945.0, "Wh")
    assert value(CODE_LOAD, "home_consumption") == (12094.0, "Wh")
    assert value(CODE_GRID, "grid_import") == (2886.0, "Wh")
    assert value(CODE_GRID, "grid_export") == (0.0, "Wh")
    # the items are not in extra order
    assert value(CODE_BATTERY, "battery_charge") == (1967.0, "Wh")
    assert value(CODE_BATTERY, "battery_discharge") == (2425.0, "Wh")
    assert value(CODE_CO2, "co2_reduction") == (3970.0, "g")
    assert value(CODE_SAVINGS, "solar_savings") == (0.0, "€")
    assert sh.series_value(sh.quota_data_items(EXAMPLES["independence"]), sh.INDEPENDENCE_SERIES) == (19.5, "%")


def test_units_are_normalized_and_unknown_ones_rejected():
    series = sh.DAILY_METRICS[0].series[0]
    assert sh.series_value([{"indexValue": 1.5, "unit": "kWh"}], series) == (1500.0, "Wh")
    with pytest.raises(sh.HistoryDataError):
        sh.series_value([{"indexValue": 1, "unit": "MJ"}], series)
    with pytest.raises(sh.HistoryDataError):
        sh.series_value([{"indexValue": "n/a", "unit": "wh"}], series)
    with pytest.raises(sh.HistoryDataError):
        sh.quota_data_items({"code": "0", "message": "Success", "data": {"code": "1001", "message": "param error"}})
    assert sh.quota_data_items({"code": "0", "message": "Success"}) == []


def test_statistic_ids_are_valid_and_lowercase():
    assert statistic_id(MASTER, "solar_energy") == "ecoflow_cloud:bk31masterunit01_solar_energy"
    for metric in sh.DAILY_METRICS:
        for series in metric.series:
            assert valid_statistic_id(statistic_id("BK31-Master unit", series.key))
    metadata = sh.statistic_metadata(MASTER, sh.DAILY_METRICS[0].series[0], "Wh")
    assert metadata["source"] == "ecoflow_cloud" and metadata["has_sum"] and metadata["unit_class"] == "energy"


# --- UTC day boundary ---------------------------------------------------------


def test_last_completed_day_changes_at_utc_midnight_not_local_midnight():
    # 2026-10-25 is the end of daylight saving time in Europe/Berlin
    local = datetime(2026, 10, 24, 23, 59, tzinfo=BERLIN)
    assert last_completed_utc_day(local) == date(2026, 10, 23)
    # local midnight: still the same UTC day
    assert last_completed_utc_day(datetime(2026, 10, 25, 0, 30, tzinfo=BERLIN)) == date(2026, 10, 23)
    # 02:00 CEST = 00:00 UTC
    assert last_completed_utc_day(datetime(2026, 10, 25, 1, 59, tzinfo=BERLIN)) == date(2026, 10, 23)
    assert last_completed_utc_day(datetime(2026, 10, 25, 2, 0, tzinfo=BERLIN)) == date(2026, 10, 24)
    # winter time: UTC midnight is 01:00 local
    assert last_completed_utc_day(datetime(2026, 12, 2, 0, 59, tzinfo=BERLIN)) == date(2026, 11, 30)
    assert last_completed_utc_day(datetime(2026, 12, 2, 1, 0, tzinfo=BERLIN)) == date(2026, 12, 1)
    assert utc_day_query(date(2026, 10, 24)) == ("2026-10-24 00:00:00", "2026-10-24 23:59:59")


def test_sensor_value_holds_over_local_midnight_and_moves_at_utc_midnight():
    api, store = FakeApi(), FakeStore()
    clock = Clock(datetime(2026, 10, 24, 23, 30, tzinfo=BERLIN).astimezone(UTC))
    history = make_history(api, store, clock)

    asyncio.run(history.async_update())
    before = history.values["solar_energy"]
    assert before.day == date(2026, 10, 23)

    # local midnight passes (00:30 CEST): nothing to reset, the same completed day stays
    clock.advance(timedelta(hours=1))
    asyncio.run(history.async_update())
    assert history.values["solar_energy"] == before

    # 02:00 CEST = 00:00 UTC: the next day completes
    clock.advance(timedelta(hours=1, minutes=30))
    assert clock.now == datetime(2026, 10, 25, 0, 0, tzinfo=UTC)
    asyncio.run(history.async_update())
    assert history.values["solar_energy"].day == date(2026, 10, 24)
    assert store.series("solar_energy")[-1][0] == date(2026, 10, 24)
    assert (MASTER, "2026-10-24 00:00:00", "2026-10-24 23:59:59", CODE_SOLAR) in api.calls


# --- main SN ------------------------------------------------------------------


def test_history_queries_the_main_sn():
    api, store = FakeApi(), FakeStore()
    history = make_history(api, store, Clock(datetime(2026, 10, 25, 12, tzinfo=UTC)))
    asyncio.run(history.async_update())
    assert api.calls and {call[0] for call in api.calls} == {MASTER}
    assert set(store.rows) == {statistic_id(MASTER, s.key) for m in sh.DAILY_METRICS for s in m.series}


def test_only_the_main_unit_owns_the_system_history():
    configured = {MASTER, SLAVE}
    assert is_history_owner(MASTER, MASTER, configured)
    # the slave of a configured master creates nothing: no duplicates per unit
    assert not is_history_owner(SLAVE, MASTER, configured)
    # a slave whose master is in no config entry carries the system history
    assert is_history_owner(SLAVE, MASTER, {SLAVE})


def test_configured_sns_come_from_enabled_public_entries():
    entries = [
        SimpleNamespace(disabled_by=None, data={"access_key": "a", "devices_list": {MASTER: {}}}),
        SimpleNamespace(disabled_by=None, data={"username": "u", "devices_list": {"PRIVATE": {}}}),
        SimpleNamespace(disabled_by="user", data={"access_key": "a", "devices_list": {"DISABLED": {}}}),
        SimpleNamespace(disabled_by=None, data={"access_key": "a", "devices_list": {SLAVE: {}}}),
    ]
    hass = SimpleNamespace(config_entries=SimpleNamespace(async_entries=lambda domain: entries))
    assert sh._configured_public_sns(hass) == {MASTER, SLAVE}  # type: ignore[arg-type]


class FakeSystemsStore:
    def __init__(self, data: dict[str, str] | None = None) -> None:
        self.data = data
        self.saves = 0

    async def async_load(self) -> dict[str, str] | None:
        return self.data

    async def async_save(self, data: dict[str, str]) -> None:
        self.data = data
        self.saves += 1


def test_system_id_stays_when_the_main_role_moves_and_across_restarts():
    store = FakeSystemsStore()

    async def run() -> None:
        systems = StreamSystems(store)
        assert await systems.async_system_id(MASTER, MASTER) == MASTER
        assert await systems.async_system_id(SLAVE, MASTER) == MASTER
        # the role moves to the other unit
        assert await systems.async_system_id(SLAVE, SLAVE) == MASTER
        assert await systems.async_system_id(MASTER, SLAVE) == MASTER
        assert store.saves == 2  # only when something new was learned
        # restart while the other unit has the role
        restarted = StreamSystems(store)
        assert await restarted.async_system_id(SLAVE, SLAVE) == MASTER

    asyncio.run(run())


def test_carrier_follows_the_main_unit():
    systems = StreamSystems(FakeSystemsStore())
    configured = {MASTER, SLAVE}
    assert systems.carries(MASTER, MASTER, MASTER, configured)
    assert not systems.carries(MASTER, SLAVE, MASTER, configured)
    assert systems.carries(MASTER, SLAVE, SLAVE, configured)
    assert not systems.carries(MASTER, MASTER, SLAVE, configured)


def test_first_unit_without_configured_main_carries_until_released():
    systems = StreamSystems(FakeSystemsStore())
    assert systems.carries("SYS", "UNIT1", "MAIN", {"UNIT1", "UNIT2"})
    assert not systems.carries("SYS", "UNIT2", "MAIN", {"UNIT1", "UNIT2"})
    systems.release("UNIT1")
    assert systems.carries("SYS", "UNIT2", "MAIN", {"UNIT1", "UNIT2"})


def test_statistic_continues_when_the_main_role_moves():
    api, store = FakeApi(), FakeStore()
    clock = Clock(datetime(2026, 10, 25, 12, tzinfo=UTC))
    old_main = make_history(api, store, clock)
    new_main = make_history(api, store, clock)

    async def run() -> None:
        old_main.assign(MASTER, MASTER)
        await old_main.async_update()
        clock.advance(timedelta(days=1))
        # the next update of each unit: the role moved, the system id did not
        old_main.deactivate()
        new_main.assign(SLAVE, MASTER)
        await new_main.async_update()

    asyncio.run(run())
    assert api.calls[-1][0] == SLAVE
    assert old_main.values == {} and old_main.independence is None and not old_main.backlog
    assert new_main.values["solar_energy"].day == date(2026, 10, 25)
    assert set(store.rows) == {statistic_id(MASTER, s.key) for m in sh.DAILY_METRICS for s in m.series}
    rows = store.series("solar_energy")
    assert [row[0] for row in rows] == [date(2026, 10, day) for day in range(22, 26)]
    total = 0.0
    for _, state, row_sum in rows:
        total += state
        assert row_sum == pytest.approx(total)


def test_unit_taking_the_role_back_reads_its_day_again():
    api, store = FakeApi(), FakeStore()
    history = make_history(api, store, Clock(datetime(2026, 10, 25, 12, tzinfo=UTC)))

    async def run() -> None:
        history.assign(MASTER, MASTER)
        await history.async_update()
        history.deactivate()
        history.assign(MASTER, MASTER)
        await history.async_update()

    asyncio.run(run())
    assert history.values["solar_energy"].day == date(2026, 10, 24)
    assert history.independence is not None


def test_coordinator_shows_nothing_on_a_unit_without_the_role():
    api, store = FakeApi(), FakeStore()
    history = make_history(api, store, Clock(datetime(2026, 10, 25, 12, tzinfo=UTC)))
    roles: list[tuple[str, str] | None] = [(MASTER, MASTER), None]

    async def role() -> tuple[str, str] | None:
        return roles.pop(0)

    coordinator = SimpleNamespace(history=history, update_interval=None, _role=role)
    asyncio.run(sh.StreamHistoryCoordinator._async_update_data(coordinator))  # type: ignore[arg-type]
    assert history.values and history.active
    requests = len(api.calls)
    asyncio.run(sh.StreamHistoryCoordinator._async_update_data(coordinator))  # type: ignore[arg-type]
    assert not history.values and not history.active and len(api.calls) == requests
    assert coordinator.update_interval == sh.UPDATE_INTERVAL


def test_entities_belong_to_their_unit_and_statistics_to_the_system():
    from tests.stream_fakes import FakeClient, make_stream

    client = FakeClient(MASTER)
    slave = make_stream(client, SLAVE)
    history = make_history(FakeApi(), FakeStore(), Clock(datetime(2026, 10, 25, tzinfo=UTC)))
    history.assign(SLAVE, MASTER)
    coordinator = SimpleNamespace(history=history)
    entity = sh.StreamHistorySensorEntity(client, slave, coordinator, sh.DAILY_METRICS[0].series[0])  # type: ignore[arg-type]
    assert entity.unique_id == f"ecoflow-api-{SLAVE}-history-solar-energy"
    independence = sh.StreamIndependenceSensorEntity(client, slave, coordinator)  # type: ignore[arg-type]
    assert independence.unique_id == f"ecoflow-api-{SLAVE}-history-energy-independence"
    assert entity.state_class is None and entity.native_value is None and not entity.available
    assert entity.device_info is not None and entity.device_info["serial_number"] == SLAVE

    history.values["solar_energy"] = sh.DayValue(date(2026, 10, 24), 9945.0, "Wh")
    assert entity.available and entity.native_value == 9945.0
    assert entity.extra_state_attributes == {
        "system_main_sn": SLAVE,
        "statistic_id": "ecoflow_cloud:bk31masterunit01_solar_energy",
        "date": "2026-10-24",
        "period_start": "2026-10-24T00:00:00+00:00",
        "period_end": "2026-10-25T00:00:00+00:00",
    }
    savings = sh.StreamHistorySensorEntity(client, slave, coordinator, sh.DAILY_METRICS[-1].series[0])  # type: ignore[arg-type]
    history.values["solar_savings"] = sh.DayValue(date(2026, 10, 24), 1.25, "€")
    assert savings.native_unit_of_measurement == "€" and savings.device_class is None


# --- statistics import --------------------------------------------------------


def test_backfill_imports_daily_rows_with_continuous_sum():
    api, store = FakeApi(), FakeStore()
    history = make_history(api, store, Clock(datetime(2026, 10, 25, 12, tzinfo=UTC)), backfill_days=3)
    asyncio.run(history.async_update())

    solar = store.series("solar_energy")
    assert [row[0] for row in solar] == [date(2026, 10, 22), date(2026, 10, 23), date(2026, 10, 24)]
    states = [9945 * d / 18 for d in (22, 23, 24)]
    assert [row[1] for row in solar] == pytest.approx(states)
    assert [row[2] for row in solar] == pytest.approx([states[0], states[0] + states[1], sum(states)])
    assert store.metadata[statistic_id(MASTER, "solar_savings")]["unit_of_measurement"] == "€"
    assert history.independence is not None and history.independence.value == 19.5


def test_reimport_overwrites_instead_of_duplicating():
    api, store = FakeApi(), FakeStore()
    clock = Clock(datetime(2026, 10, 25, 12, tzinfo=UTC))
    history = make_history(api, store, clock)
    asyncio.run(history.async_update())
    first = {key: dict(rows) for key, rows in store.rows.items()}

    # a new process: the same day again, read from the last row on
    restarted = make_history(api, store, clock)
    asyncio.run(restarted.async_update())
    assert {key: dict(rows) for key, rows in store.rows.items()} == first

    # EcoFlow revises the last day: the row is replaced and the sum follows
    begin = "2026-10-24 00:00:00"
    api.override[(CODE_SOLAR, begin)] = {
        "code": "0",
        "message": "Success",
        "data": {"code": "0", "data": [{"unit": "wh", "indexValue": "20000"}]},
    }
    clock.advance(timedelta(seconds=REFRESH_COMPLETED_DAY_SEC))
    asyncio.run(restarted.async_update())
    solar = store.series("solar_energy")
    assert len(solar) == 3
    assert solar[-1][1] == 20000 and solar[-1][2] == pytest.approx(solar[-2][2] + 20000)


def test_import_continues_from_the_last_row():
    api, store = FakeApi(), FakeStore()
    clock = Clock(datetime(2026, 10, 25, 12, tzinfo=UTC))
    history = make_history(api, store, clock, backfill_days=90)
    asyncio.run(history.async_update())
    api.calls.clear()

    clock.advance(timedelta(days=2))
    asyncio.run(history.async_update())
    solar_calls = [call[1] for call in api.calls if call[3] == CODE_SOLAR]
    # the last imported day again, then the new ones; never the whole backfill
    assert solar_calls == ["2026-10-24 00:00:00", "2026-10-25 00:00:00", "2026-10-26 00:00:00"]
    solar = store.series("solar_energy")
    assert len(solar) == 92
    assert solar[-1][2] == pytest.approx(sum(row[1] for row in solar))


def test_completed_day_is_not_read_on_every_update():
    api, store = FakeApi(), FakeStore()
    clock = Clock(datetime(2026, 10, 25, 12, tzinfo=UTC))
    history = make_history(api, store, clock)
    asyncio.run(history.async_update())
    api.calls.clear()

    clock.advance(timedelta(hours=1))
    asyncio.run(history.async_update())
    assert api.calls == []

    clock.advance(timedelta(seconds=REFRESH_COMPLETED_DAY_SEC))
    asyncio.run(history.async_update())
    # one query per code: the newest day and the year
    assert len(api.calls) == len(sh.DAILY_METRICS) + 1


def test_backfill_is_chunked_over_updates():
    api, store = FakeApi(), FakeStore()
    clock = Clock(datetime(2026, 10, 25, 12, tzinfo=UTC))
    history = make_history(api, store, clock, backfill_days=10, max_requests=25)

    asyncio.run(history.async_update())
    assert history.backlog and len(api.calls) == 25
    asyncio.run(history.async_update())
    asyncio.run(history.async_update())
    assert not history.backlog

    for metric in sh.DAILY_METRICS:
        for series in metric.series:
            rows = store.series(series.key)
            assert [row[0] for row in rows] == [date(2026, 10, 15) + timedelta(days=i) for i in range(10)]
            assert rows[-1][2] == pytest.approx(sum(row[1] for row in rows))


def test_requests_are_spaced():
    api, store = FakeApi(), FakeStore()
    sleeps: list[float] = []

    async def sleep(seconds: float) -> None:
        sleeps.append(seconds)

    history = StreamHistory(
        MASTER, api.quota_data, store, 1, clock=lambda: datetime(2026, 10, 25, 12, tzinfo=UTC), sleep=sleep
    )
    asyncio.run(history.async_update())
    assert len(sleeps) == len(api.calls) - 1 and set(sleeps) == {sh.REQUEST_INTERVAL_SEC}


# --- error paths --------------------------------------------------------------


def test_api_error_keeps_what_was_read_and_resumes():
    api, store = FakeApi(), FakeStore()
    clock = Clock(datetime(2026, 10, 25, 12, tzinfo=UTC))
    history = make_history(api, store, clock, backfill_days=5)
    api.fail_after = 2

    with pytest.raises(EcoflowException):
        asyncio.run(history.async_update())
    assert [row[0] for row in store.series("solar_energy")] == [date(2026, 10, 20), date(2026, 10, 21)]

    api.fail_after = None
    api.calls.clear()
    asyncio.run(history.async_update())
    solar_calls = [call[1][:10] for call in api.calls if call[3] == CODE_SOLAR]
    assert solar_calls == ["2026-10-21", "2026-10-22", "2026-10-23", "2026-10-24"]
    rows = store.series("solar_energy")
    assert len(rows) == 5 and rows[-1][2] == pytest.approx(sum(row[1] for row in rows))


def test_newest_day_without_data_is_asked_again():
    api, store = FakeApi(), FakeStore()
    clock = Clock(datetime(2026, 10, 25, 0, 10, tzinfo=UTC))
    history = make_history(api, store, clock)
    empty = {"code": "0", "message": "Success", "data": {"code": "0", "data": []}}
    api.override[(CODE_SOLAR, "2026-10-24 00:00:00")] = empty
    api.override[(CODE_SOLAR, "2026-10-22 00:00:00")] = empty

    asyncio.run(history.async_update())
    # an older day without data counts as 0; the newest is not written yet
    assert [(row[0], row[1]) for row in store.series("solar_energy")] == [
        (date(2026, 10, 22), 0.0),
        (date(2026, 10, 23), pytest.approx(9945 * 23 / 18)),
    ]
    assert history.values["solar_energy"].day == date(2026, 10, 23)

    del api.override[(CODE_SOLAR, "2026-10-24 00:00:00")]
    clock.advance(timedelta(hours=1))
    asyncio.run(history.async_update())
    assert store.series("solar_energy")[-1][0] == date(2026, 10, 24)
    assert history.values["solar_energy"].day == date(2026, 10, 24)


def test_unusable_response_is_logged_once(caplog):
    api, store = FakeApi(), FakeStore()
    clock = Clock(datetime(2026, 10, 25, 12, tzinfo=UTC))
    history = make_history(api, store, clock, backfill_days=1)
    api.override[(CODE_GRID, "2026-10-24 00:00:00")] = {
        "code": "0",
        "message": "Success",
        "data": {"code": "0", "data": [{"unit": "MJ", "extra": "1", "indexValue": "1"}]},
    }

    with caplog.at_level(logging.DEBUG, logger=sh.__name__):
        for _ in range(3):
            asyncio.run(history.async_update())
            clock.advance(timedelta(hours=1))
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert store.series("grid_import") == []
    # the other metrics are not held up
    assert store.series("solar_energy")[-1][0] == date(2026, 10, 24)


def test_coordinator_turns_api_errors_into_update_failed():
    history = SimpleNamespace(system_id=MASTER, backlog=True, assign=lambda *_: None)

    async def failing_update() -> None:
        raise EcoflowException("Request too frequent", code="8521")

    history.async_update = failing_update

    async def role() -> tuple[str, str]:
        return MASTER, MASTER

    coordinator = SimpleNamespace(history=history, update_interval=None, _role=role)
    with pytest.raises(UpdateFailed):
        asyncio.run(sh.StreamHistoryCoordinator._async_update_data(coordinator))  # type: ignore[arg-type]
    assert coordinator.update_interval == sh.BACKLOG_UPDATE_INTERVAL


# --- option -------------------------------------------------------------------


def _entry(device_options: dict[str, Any]) -> Any:
    options = {
        "refresh_period_sec": 5,
        "power_step": -1,
        "diagnostic_mode": False,
        "verbose_status_mode": False,
        "assume_offline_sec": 300,
        "reset_sensors_on_offline": True,
        **device_options,
    }
    return SimpleNamespace(
        data={"devices_list": {MASTER: {"device_name": "Pro", "device_type": "Stream PRO"}}},
        options={"devices_list": {MASTER: options}},
    )


def test_backfill_option_defaults_for_existing_entries():
    assert extract_devices(_entry({}))[MASTER].options.history_backfill_days == DEFAULT_HISTORY_BACKFILL_DAYS
    assert extract_devices(_entry({OPTS_HISTORY_BACKFILL_DAYS: 30}))[MASTER].options.history_backfill_days == 30
    # clamped, chunked anyway
    assert StreamHistory(MASTER, FakeApi().quota_data, FakeStore(), 0).backfill_days == 1
