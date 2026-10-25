"""Checks of the public (developer) API client against EcoFlow's documentation.

Reference: EcoFlow IoT Developer Platform, "General information" -
"HTTP access steps" and "General HTTP Header".
"""

import asyncio

from custom_components.ecoflow_cloud.api import public_api
from custom_components.ecoflow_cloud.api.public_api import EcoflowPublicApiClient


def _client(access_key: str = "ak", secret_key: str = "sk") -> EcoflowPublicApiClient:
    return EcoflowPublicApiClient("api-e.ecoflow.com", access_key, secret_key, "Home")


def test_nonce_is_six_digits(monkeypatch):
    # draw both ends of the range the client asks for
    for pick in (min, max):
        monkeypatch.setattr(public_api.random, "randint", lambda a, b, pick=pick: pick(a, b))
        assert len(EcoflowPublicApiClient._gen_nonce()) == 6


def test_sign_matches_documented_example():
    # "HTTP access steps", Step 8: the official test vector
    client = _client("Fp4SvIprYSDPXtYJidEtUAd1o", "WIbFEKre0s6sLnh4ei7SPUeYnptHG6V")
    client.nonce = "345164"
    client.timestamp = "1671171709428"
    key_values = "params.cmdSet=11&params.eps=0&params.id=24&sn=123456789"

    sign = client._EcoflowPublicApiClient__gen_sign(key_values)  # type: ignore[attr-defined]

    assert sign == "07c13b65e037faf3b153d51613638fa80003c4c38d2407379a7f52851af1473e"


def test_flat_params_are_sorted_by_key():
    # Step 1: parameters sorted by ASCII value, joined with = and &
    client = _client()
    concat = client._EcoflowPublicApiClient__sort_and_concat_params  # type: ignore[attr-defined]

    assert concat({"sn": "123456789", "id": "24", "cmdSet": "11"}) == "cmdSet=11&id=24&sn=123456789"


def test_device_list_without_data_is_empty(monkeypatch):
    # "Query the user's bound device list": data is not a required field.
    # EcoFlow answered this way in tolwi/hassio-ecoflow-cloud#791 and #598,
    # which then failed with KeyError: 'data'.
    client = _client()

    async def call_api(endpoint, params=None):
        return {"code": "0", "message": "Success"}

    monkeypatch.setattr(client, "call_api", call_api)

    assert asyncio.run(client.fetch_all_available_devices()) == []


class _FakeResponse:
    status = 200
    reason = "OK"

    async def json(self):
        return {"code": "0", "message": "Success", "data": {"sn": "BK31"}}


class _FakeGet:
    async def __aenter__(self):
        return _FakeResponse()

    async def __aexit__(self, *args):
        return False


class _FakeSession:
    def __init__(self):
        self.urls: list[str] = []

    def get(self, url, headers):
        self.urls.append(url)
        return _FakeGet()


def test_calls_reuse_the_given_session(monkeypatch):
    # tolwi#886: a new ClientSession per call means a new connection and DNS lookup each time
    def no_new_session(*args, **kwargs):
        raise AssertionError("a new aiohttp session was opened")

    monkeypatch.setattr(public_api.aiohttp, "ClientSession", no_new_session)
    session = _FakeSession()
    client = EcoflowPublicApiClient("api-e.ecoflow.com", "ak", "sk", "Home", session)  # type: ignore[arg-type]

    asyncio.run(client.call_api("/device/system/main/sn", {"sn": "BK61"}))
    asyncio.run(client.call_api("/device/system/main/sn", {"sn": "BK61"}))

    assert session.urls == ["https://api-e.ecoflow.com/iot-open/sign/device/system/main/sn?sn=BK61"] * 2
