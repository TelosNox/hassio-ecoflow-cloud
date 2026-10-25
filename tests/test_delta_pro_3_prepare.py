"""DELTA Pro 3 frame routing: JSON frames must not go through the protobuf decoder.

tolwi/hassio-ecoflow-cloud#924 / #925: a JSON status message logged two protobuf
decode errors before the JSON fallback handled it.
"""

import logging

import pytest

from custom_components.ecoflow_cloud.devices.internal.delta_pro_3 import DeltaPro3


@pytest.fixture
def device() -> DeltaPro3:
    return object.__new__(DeltaPro3)


def test_json_frame_is_parsed_without_protobuf_errors(device: DeltaPro3, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.DEBUG):
        result = device._prepare_data(b'{"params":{"status":1}}')

    assert result == {"params": {"status": 1}}
    assert "HeaderMessage" not in caplog.text
