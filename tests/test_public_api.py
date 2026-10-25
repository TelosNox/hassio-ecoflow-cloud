"""Checks of the public (developer) API client against EcoFlow's documentation.

Reference: EcoFlow IoT Developer Platform, "General information" -
"HTTP access steps" and "General HTTP Header".
"""

from custom_components.ecoflow_cloud.api import public_api
from custom_components.ecoflow_cloud.api.public_api import EcoflowPublicApiClient


def _client(access_key: str = "ak", secret_key: str = "sk") -> EcoflowPublicApiClient:
    return EcoflowPublicApiClient("api-e.ecoflow.com", access_key, secret_key, "Home")


def test_nonce_is_six_digits(monkeypatch):
    # draw both ends of the range the client asks for
    for pick in (min, max):
        monkeypatch.setattr(public_api.random, "randint", lambda a, b, pick=pick: pick(a, b))
        assert len(EcoflowPublicApiClient._gen_nonce()) == 6
