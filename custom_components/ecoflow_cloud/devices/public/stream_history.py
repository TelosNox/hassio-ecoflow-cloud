"""History of a STREAM system from the public API.

Reference: stream.md, "Historical data": POST /iot-open/sign/device/quota/data
with ``beginTime``/``endTime`` ("in UTC timezone") and a metric ``code``.
"If there are multiple devices, use the API to obtain the serial number of
the main device", so every query uses the system main SN (MainSnCache).

Time model: the API aggregates over UTC days. A "today" value would restart
at UTC midnight, which is 01:00 or 02:00 local time in Central Europe. The
sensors therefore show the last *completed* UTC day, with that date as an
attribute, and have no state_class: they never reset during a local day and
the recorder compiles no statistics of its own from them. The long-term
record is the external statistic ``ecoflow_cloud:<main_sn>_<series>``: one
row per UTC day, starting at 00:00 UTC, with ``state`` = that day's value
and a continuous ``sum``. Imports overwrite rows with the same start, so a
re-import never duplicates, and every update continues from the last row.

The extra "1"/"2" split of the grid and battery metrics is not documented;
it follows tolwi/hassio-ecoflow-cloud#812 (1 = import / charge,
2 = export / discharge).
"""

from __future__ import annotations

import asyncio
import dataclasses
import logging
import re
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime, timedelta
from typing import TYPE_CHECKING, Any, Protocol

from homeassistant.components.recorder.models import StatisticData, StatisticMeanType, StatisticMetaData
from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfEnergy, UnitOfMass
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity, DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt
from homeassistant.util.unit_conversion import EnergyConverter, MassConverter

from ... import DEFAULT_HISTORY_BACKFILL_DAYS, MAX_HISTORY_BACKFILL_DAYS
from ...api import EcoflowApiClient, EcoflowException
from ...api.commands import MAIN_SN_RETRY_SEC
from ...entities import EcoFlowAbstractEntity
from .. import const

if TYPE_CHECKING:
    from ...api.public_api import EcoflowPublicApiClient
    from .stream_ac import StreamAC

_LOGGER = logging.getLogger(__name__)

STATISTIC_SOURCE = "ecoflow_cloud"
HISTORY_DATA_KEY = "__stream_history"


# A completed day only changes when EcoFlow revises it; it is read again
# a few times a day, not on every update.
UPDATE_INTERVAL = timedelta(hours=1)
REFRESH_COMPLETED_DAY_SEC = 6 * 3600
# EcoFlow documents no rate limit. A backfill is spread over several
# updates: at most this many requests per update, one per second.
MAX_REQUESTS_PER_UPDATE = 120
REQUEST_INTERVAL_SEC = 1.0
BACKLOG_UPDATE_INTERVAL = timedelta(minutes=5)

CODE_SOLAR = "BK621-App-HOME-SOLAR-ENERGY-FLOW-solor-line-NOTDISTINGUISH-MASTER_DATA"
CODE_LOAD = "BK621-App-HOME-LOAD-ENERGY-FLOW-consumption-prop_arc-NOTDISTINGUISH-MASTER_DATA"
CODE_GRID = "BK621-App-HOME-GRID-ENERGY-FLOW-grid_prop_bar-NOTDISTINGUISH-MASTER_DATA"
CODE_BATTERY = "BK621-App-HOME-SOC-ENERGY-FLOW-battery-prop_bar-NOTDISTINGUISH-MASTER_DATA"
CODE_CO2 = "BK621-App-HOME-CO2-WEIGHT-FLOW-impact-progress_arc-NOTDISTINGUISH-MASTER_DATA"
CODE_SAVINGS = "BK621-App-HOME-SAVING-CURRENCY-FLOW-earnings-progress_arc-NOTDISTINGUISH-MASTER_DATA"
CODE_INDEPENDENCE = "BK621-App-HOME-INDEPENDENCE-PERCENT-FLOW-indep-progress_bar-NOTDISTINGUISH-MASTER_DATA"

KIND_ENERGY = "energy"
KIND_MASS = "mass"
KIND_CURRENCY = "currency"
KIND_PERCENT = "percent"


@dataclasses.dataclass(frozen=True)
class HistorySeries:
    key: str  # entity key and statistic suffix
    title: str
    kind: str
    extra: str | None = None  # the item of a split metric (grid, battery); None = the only item


@dataclasses.dataclass(frozen=True)
class HistoryMetric:
    code: str
    series: tuple[HistorySeries, ...]


# The metrics stream.md lists with a day (or finer) lookup period, queried one UTC day at a time
DAILY_METRICS: tuple[HistoryMetric, ...] = (
    HistoryMetric(CODE_SOLAR, (HistorySeries("solar_energy", const.STREAM_HISTORY_SOLAR_ENERGY, KIND_ENERGY),)),
    HistoryMetric(CODE_LOAD, (HistorySeries("home_consumption", const.STREAM_HISTORY_HOME_CONSUMPTION, KIND_ENERGY),)),
    HistoryMetric(
        CODE_GRID,
        (
            HistorySeries("grid_import", const.STREAM_HISTORY_GRID_IMPORT, KIND_ENERGY, "1"),
            HistorySeries("grid_export", const.STREAM_HISTORY_GRID_EXPORT, KIND_ENERGY, "2"),
        ),
    ),
    HistoryMetric(
        CODE_BATTERY,
        (
            HistorySeries("battery_charge", const.STREAM_HISTORY_BATTERY_CHARGE, KIND_ENERGY, "1"),
            HistorySeries("battery_discharge", const.STREAM_HISTORY_BATTERY_DISCHARGE, KIND_ENERGY, "2"),
        ),
    ),
    HistoryMetric(CODE_CO2, (HistorySeries("co2_reduction", const.STREAM_HISTORY_CO2_REDUCTION, KIND_MASS),)),
    HistoryMetric(CODE_SAVINGS, (HistorySeries("solar_savings", const.STREAM_HISTORY_SOLAR_SAVINGS, KIND_CURRENCY),)),
)

# Lookup period "Year": a percentage of the year so far, not summable per day
INDEPENDENCE_KEY = "energy_independence"
INDEPENDENCE_SERIES = HistorySeries(INDEPENDENCE_KEY, const.STREAM_HISTORY_ENERGY_INDEPENDENCE, KIND_PERCENT)


class HistoryDataError(Exception):
    """A response the history cannot use; retrying the same query will not help."""


def statistic_id(main_sn: str, key: str) -> str:
    object_id = re.sub(r"[^a-z0-9]+", "_", f"{main_sn}_{key}".lower()).strip("_")
    return f"{STATISTIC_SOURCE}:{object_id}"


def last_completed_utc_day(now: datetime) -> date:
    return now.astimezone(UTC).date() - timedelta(days=1)


def utc_day_query(day: date) -> tuple[str, str]:
    """beginTime/endTime of one UTC day, in the documented 'yyyy-MM-dd HH:mm:ss' format."""
    return f"{day.isoformat()} 00:00:00", f"{day.isoformat()} 23:59:59"


def utc_day_start(day: date) -> datetime:
    return datetime(day.year, day.month, day.day, tzinfo=UTC)


def quota_data_items(response: dict[str, Any]) -> list[dict[str, Any]]:
    """The items of a /device/quota/data response: data.data, next to an inner code."""
    outer = response.get("data")
    if outer is None:
        return []
    if isinstance(outer, list):
        items: Any = outer
    elif isinstance(outer, dict):
        inner_code = outer.get("code")
        if inner_code is not None and str(inner_code) != "0":
            raise HistoryDataError(f"code {inner_code}: {outer.get('message')}")
        items = outer.get("data")
    else:
        raise HistoryDataError(f"unexpected data {outer!r}")
    if items is None:
        return []
    if not isinstance(items, list):
        raise HistoryDataError(f"unexpected data.data {items!r}")
    return [item for item in items if isinstance(item, dict)]


def series_value(items: list[dict[str, Any]], series: HistorySeries) -> tuple[float, str | None] | None:
    """The value of one series in its own unit (Wh, g or the currency), None if absent."""
    for item in items:
        if series.extra is not None and str(item.get("extra")) != series.extra:
            continue
        raw = item.get("indexValue")
        if raw is None or isinstance(raw, bool):
            raise HistoryDataError(f"indexValue {raw!r}")
        try:
            value = float(raw)  # documented as number and as string
        except (TypeError, ValueError) as error:
            raise HistoryDataError(f"indexValue {raw!r}") from error
        unit = item.get("unit") if isinstance(item.get("unit"), str) else None
        return _normalize(series, value, unit)
    return None


def _normalize(series: HistorySeries, value: float, unit: str | None) -> tuple[float, str | None]:
    lowered = (unit or "").strip().lower()
    if series.kind == KIND_ENERGY:
        if lowered in ("", "wh"):  # stream.md examples: "wh"
            return value, UnitOfEnergy.WATT_HOUR
        if lowered == "kwh":
            return value * 1000, UnitOfEnergy.WATT_HOUR
        raise HistoryDataError(f"unit {unit!r} for {series.key}")
    if series.kind == KIND_MASS:
        if lowered in ("", "g"):  # stream.md example: "g"
            return value, UnitOfMass.GRAMS
        if lowered == "kg":
            return value * 1000, UnitOfMass.GRAMS
        raise HistoryDataError(f"unit {unit!r} for {series.key}")
    # a currency symbol as the app shows it (e.g. "€"), or "%"
    return value, unit.strip() if unit and unit.strip() else None


def statistic_metadata(main_sn: str, series: HistorySeries, unit: str | None) -> StatisticMetaData:
    unit_class = None
    if series.kind == KIND_ENERGY:
        unit_class = EnergyConverter.UNIT_CLASS
    elif series.kind == KIND_MASS:
        unit_class = MassConverter.UNIT_CLASS
    return StatisticMetaData(
        source=STATISTIC_SOURCE,
        statistic_id=statistic_id(main_sn, series.key),
        name=f"STREAM {main_sn} {series.title.removesuffix(' (last UTC day)')}",
        unit_of_measurement=unit,
        unit_class=unit_class,
        has_sum=True,
        mean_type=StatisticMeanType.NONE,
    )


@dataclasses.dataclass(frozen=True)
class LastStatistic:
    day: date
    state: float
    sum: float


class StatisticsStore(Protocol):
    async def async_last(self, statistic_id: str) -> LastStatistic | None: ...

    def add(self, metadata: StatisticMetaData, rows: list[StatisticData]) -> None: ...


@dataclasses.dataclass(frozen=True)
class DayValue:
    day: date
    value: float
    unit: str | None


@dataclasses.dataclass(frozen=True)
class YearValue:
    year: int
    value: float


type QuotaDataFetch = Callable[[str, str, str, str], Awaitable[dict[str, Any]]]


class StreamHistory:
    """Reads the daily history of one STREAM system and imports it as statistics.

    Free of hass, so the import can be tested with recorded responses.
    """

    def __init__(
        self,
        main_sn: str,
        fetch: QuotaDataFetch,
        store: StatisticsStore,
        backfill_days: int = DEFAULT_HISTORY_BACKFILL_DAYS,
        *,
        clock: Callable[[], datetime] = dt.utcnow,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[Any]] = asyncio.sleep,
        max_requests: int = MAX_REQUESTS_PER_UPDATE,
        request_interval: float = REQUEST_INTERVAL_SEC,
    ):
        self.main_sn = main_sn
        self._fetch = fetch
        self._store = store
        self.backfill_days = min(max(backfill_days, 1), MAX_HISTORY_BACKFILL_DAYS)
        self._clock = clock
        self._monotonic = monotonic
        self._sleep = sleep
        self._max_requests = max_requests
        self._request_interval = request_interval
        self.values: dict[str, DayValue] = {}
        self.independence: YearValue | None = None
        # True when the last update ran out of requests before it was done
        self.backlog = False
        self._budget = 0
        self._requests = 0
        # when the newest completed day was last read, per code
        self._refreshed: dict[str, tuple[date, float]] = {}
        # codes whose last data error was logged, so a persisting one is logged once
        self._data_errors: set[str] = set()

    async def async_update(self) -> None:
        now = self._clock()
        newest_day = last_completed_utc_day(now)
        self._budget = self._max_requests
        self._requests = 0
        self.backlog = False
        for metric in DAILY_METRICS:
            await self._update_metric(metric, newest_day)
        await self._update_independence(now)

    def _fresh(self, code: str, day: date) -> bool:
        refreshed = self._refreshed.get(code)
        return (
            refreshed is not None
            and refreshed[0] == day
            and self._monotonic() - refreshed[1] < REFRESH_COMPLETED_DAY_SEC
        )

    async def _query(self, begin: str, end: str, code: str) -> list[dict[str, Any]]:
        if self._requests > 0:
            await self._sleep(self._request_interval)
        self._budget -= 1
        self._requests += 1
        return quota_data_items(await self._fetch(self.main_sn, begin, end, code))

    def _data_error(self, code: str, day: date | int, error: HistoryDataError) -> None:
        log = _LOGGER.debug if code in self._data_errors else _LOGGER.warning
        log("Unusable STREAM history of %s for %s (%s): %s", self.main_sn, day, code, error)
        self._data_errors.add(code)

    async def _update_metric(self, metric: HistoryMetric, newest_day: date) -> None:
        last = {
            series.key: await self._store.async_last(statistic_id(self.main_sn, series.key))
            for series in metric.series
        }
        first_day = newest_day - timedelta(days=self.backfill_days - 1)
        # every series continues at its last row, which is read again
        day = min(row.day if row is not None else first_day for row in last.values())
        if day > newest_day or (day == newest_day and self._fresh(metric.code, newest_day)):
            return

        fetched: list[tuple[date, dict[str, tuple[float, str | None]]]] = []
        try:
            while day <= newest_day:
                if self._budget <= 0:
                    self.backlog = True
                    break
                items = await self._query(*utc_day_query(day), metric.code)
                if not items and day == newest_day:
                    # not aggregated yet; the next update asks again
                    break
                values: dict[str, tuple[float, str | None]] = {}
                for series in metric.series:
                    # a day without data (before the system was set up) counts as 0
                    values[series.key] = series_value(items, series) or (0.0, None)
                self._data_errors.discard(metric.code)
                fetched.append((day, values))
                if day == newest_day:
                    self._refreshed[metric.code] = (day, self._monotonic())
                day += timedelta(days=1)
        except HistoryDataError as error:
            self._data_error(metric.code, day, error)
        finally:
            # also after a failed request: what was read so far is imported
            if fetched:
                self._import(metric, fetched, last)

    def _import(
        self,
        metric: HistoryMetric,
        fetched: list[tuple[date, dict[str, tuple[float, str | None]]]],
        last: dict[str, LastStatistic | None],
    ) -> None:
        for series in metric.series:
            row = last[series.key]
            # the last row is overwritten, so the sum continues from the one before it
            total = row.sum - row.state if row is not None else 0.0
            rows: list[StatisticData] = []
            unit = None
            for day, values in fetched:
                if row is not None and day < row.day:
                    continue
                value, day_unit = values[series.key]
                unit = day_unit or unit
                total += value
                rows.append(StatisticData(start=utc_day_start(day), state=value, sum=total))
                self.values[series.key] = DayValue(day, value, day_unit or self._unit(series.key))
            if rows:
                self._store.add(statistic_metadata(self.main_sn, series, unit or self._unit(series.key)), rows)

    def _unit(self, key: str) -> str | None:
        known = self.values.get(key)
        return known.unit if known is not None else None

    async def _update_independence(self, now: datetime) -> None:
        today = now.astimezone(UTC).date()
        if self.independence is not None and self.independence.year == today.year and self._fresh(CODE_INDEPENDENCE, today):
            return
        if self._budget <= 0:
            self.backlog = True
            return
        # lookup period "Year": the query returns the year its beginTime is in
        year = today.year
        try:
            items = await self._query(f"{year}-01-01 00:00:00", f"{year}-12-31 23:59:59", CODE_INDEPENDENCE)
            found = series_value(items, INDEPENDENCE_SERIES)
        except HistoryDataError as error:
            self._data_error(CODE_INDEPENDENCE, year, error)
            return
        self._data_errors.discard(CODE_INDEPENDENCE)
        self._refreshed[CODE_INDEPENDENCE] = (today, self._monotonic())
        if found is not None:
            self.independence = YearValue(year, found[0])


class RecorderStatisticsStore:
    """The recorder's long-term statistics, as StreamHistory needs them."""

    def __init__(self, hass: HomeAssistant):
        self._hass = hass

    async def async_last(self, statistic_id: str) -> LastStatistic | None:
        from homeassistant.components.recorder import get_instance
        from homeassistant.components.recorder.statistics import get_last_statistics

        rows = await get_instance(self._hass).async_add_executor_job(
            get_last_statistics, self._hass, 1, statistic_id, False, {"state", "sum"}
        )
        found = rows.get(statistic_id)
        if not found:
            return None
        row = found[0]
        return LastStatistic(
            datetime.fromtimestamp(row["start"], UTC).date(),
            row.get("state") or 0.0,
            row.get("sum") or 0.0,
        )

    def add(self, metadata: StatisticMetaData, rows: list[StatisticData]) -> None:
        from homeassistant.components.recorder.statistics import async_add_external_statistics

        async_add_external_statistics(self._hass, metadata, rows)


class StreamHistoryCoordinator(DataUpdateCoordinator[None]):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, history: StreamHistory):
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"EcoFlow STREAM history {history.main_sn}",
            update_interval=UPDATE_INTERVAL,
            always_update=True,
        )
        self.history = history

    async def _async_update_data(self) -> None:
        # DataUpdateCoordinator logs the first failure and the recovery, not every retry
        try:
            await self.history.async_update()
        except (EcoflowException, TimeoutError, OSError) as error:
            raise UpdateFailed(f"STREAM history of {self.history.main_sn}: {error}") from error
        finally:
            self.update_interval = BACKLOG_UPDATE_INTERVAL if self.history.backlog else UPDATE_INTERVAL


def is_history_owner(device_sn: str, main_sn: str, configured_sns: set[str]) -> bool:
    """Whether this unit creates the history of its system.

    The main unit does. A unit whose main unit is configured in no entry
    does too; when several are, the first one to claim the main SN wins.
    """
    return device_sn == main_sn or main_sn not in configured_sns


def _configured_public_sns(hass: HomeAssistant) -> set[str]:
    from ... import CONF_ACCESS_KEY, CONF_DEVICE_LIST, ECOFLOW_DOMAIN

    sns: set[str] = set()
    for entry in hass.config_entries.async_entries(ECOFLOW_DOMAIN):
        if entry.disabled_by is None and CONF_ACCESS_KEY in entry.data:
            sns.update(entry.data.get(CONF_DEVICE_LIST, {}))
    return sns


def async_setup_stream_history(
    hass: HomeAssistant,
    entry: ConfigEntry,
    client: EcoflowPublicApiClient,
    async_add_entities: AddEntitiesCallback,
) -> None:
    from .stream_ac import StreamAC

    for device in client.devices.values():
        if isinstance(device, StreamAC) and device.device_info.public_api:
            entry.async_create_background_task(
                hass,
                _async_setup_device_history(hass, entry, client, device, async_add_entities),
                f"ecoflow stream history {device.device_info.sn}",
            )


async def _async_setup_device_history(
    hass: HomeAssistant,
    entry: ConfigEntry,
    client: EcoflowPublicApiClient,
    device: StreamAC,
    async_add_entities: AddEntitiesCallback,
) -> None:
    from ... import ECOFLOW_DOMAIN

    cache = device.main_sn_cache
    assert cache is not None
    # the history belongs to the main SN; never guess it from the unit's own SN
    while not cache.resolved:
        await client.async_refresh_main_sn(device)
        if not cache.resolved:
            await asyncio.sleep(MAIN_SN_RETRY_SEC)

    main_sn = cache.sn
    sn = device.device_info.sn
    if not is_history_owner(sn, main_sn, _configured_public_sns(hass)):
        _LOGGER.debug("STREAM history of %s is created by its main unit, not by %s", main_sn, sn)
        return
    claims: dict[str, str] = hass.data[ECOFLOW_DOMAIN].setdefault(HISTORY_DATA_KEY, {})
    if main_sn in claims:
        _LOGGER.debug("STREAM history of %s already set up, not again for %s", main_sn, sn)
        return
    claims[main_sn] = entry.entry_id

    def release() -> None:
        if claims.get(main_sn) == entry.entry_id:
            claims.pop(main_sn)

    entry.async_on_unload(release)

    history = StreamHistory(
        main_sn,
        client.quota_data,
        RecorderStatisticsStore(hass),
        device.device_data.options.history_backfill_days,
    )
    coordinator = StreamHistoryCoordinator(hass, entry, history)
    _LOGGER.info(
        "STREAM history of system %s on %s, statistics %s",
        main_sn,
        sn,
        ", ".join(statistic_id(main_sn, s.key) for m in DAILY_METRICS for s in m.series),
    )
    entities: list[SensorEntity] = [
        StreamHistorySensorEntity(client, device, coordinator, series) for m in DAILY_METRICS for series in m.series
    ]
    entities.append(StreamIndependenceSensorEntity(client, device, coordinator))
    async_add_entities(entities)
    await coordinator.async_refresh()


_DEVICE_CLASS = {
    KIND_ENERGY: SensorDeviceClass.ENERGY,
    KIND_MASS: SensorDeviceClass.WEIGHT,
}
_DEFAULT_UNIT = {
    KIND_ENERGY: UnitOfEnergy.WATT_HOUR,
    KIND_MASS: UnitOfMass.GRAMS,
}


class _StreamHistoryEntity(SensorEntity, EcoFlowAbstractEntity, CoordinatorEntity[StreamHistoryCoordinator]):  # type: ignore[misc]
    _attr_should_poll = False

    def __init__(self, client: EcoflowApiClient, device: StreamAC, coordinator: StreamHistoryCoordinator, title: str, key: str):
        CoordinatorEntity.__init__(self, coordinator)
        EcoFlowAbstractEntity.__init__(self, client, device, title, f"history.{key}")
        # the system's history, so the main SN, whichever unit carries it
        self._attr_unique_id = self._gen_unique_id(coordinator.history.main_sn, f"history.{key}")
        self._history = coordinator.history


class StreamHistorySensorEntity(_StreamHistoryEntity):
    """The value of the last completed UTC day; no state_class, the statistic is the record."""

    def __init__(self, client: EcoflowApiClient, device: StreamAC, coordinator: StreamHistoryCoordinator, series: HistorySeries):
        super().__init__(client, device, coordinator, series.title, series.key)
        self._series = series
        self._attr_device_class = _DEVICE_CLASS.get(series.kind)
        self._attr_native_unit_of_measurement = _DEFAULT_UNIT.get(series.kind)
        if series.kind == KIND_CURRENCY:
            self._attr_icon = "mdi:cash-plus"
        elif series.kind == KIND_MASS:
            self._attr_icon = "mdi:molecule-co2"

    @property
    def available(self) -> bool:
        # a failed update keeps the day that was read; it does not go stale within the day
        return self._history.values.get(self._series.key) is not None

    @property
    def native_value(self) -> float | None:
        value = self._history.values.get(self._series.key)
        return value.value if value is not None else None

    @property
    def native_unit_of_measurement(self) -> str | None:
        if self._series.kind == KIND_CURRENCY:
            value = self._history.values.get(self._series.key)
            return value.unit if value is not None else None
        return self._attr_native_unit_of_measurement

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        value = self._history.values.get(self._series.key)
        attributes: dict[str, Any] = {
            "system_main_sn": self._history.main_sn,
            "statistic_id": statistic_id(self._history.main_sn, self._series.key),
        }
        if value is not None:
            attributes["date"] = value.day.isoformat()
            attributes["period_start"] = utc_day_start(value.day).isoformat()
            attributes["period_end"] = utc_day_start(value.day + timedelta(days=1)).isoformat()
        return attributes


class StreamIndependenceSensorEntity(_StreamHistoryEntity):
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:home-lightning-bolt"

    def __init__(self, client: EcoflowApiClient, device: StreamAC, coordinator: StreamHistoryCoordinator):
        super().__init__(client, device, coordinator, const.STREAM_HISTORY_ENERGY_INDEPENDENCE, INDEPENDENCE_KEY)

    @property
    def available(self) -> bool:
        return self._history.independence is not None

    @property
    def native_value(self) -> float | None:
        return self._history.independence.value if self._history.independence is not None else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        attributes: dict[str, Any] = {"system_main_sn": self._history.main_sn}
        if self._history.independence is not None:
            attributes["year"] = self._history.independence.year
        return attributes
