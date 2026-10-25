"""RIVER 3 frame routing.

tolwi/hassio-ecoflow-cloud#872 / #936: protobuf frames without a decoder were
handed to the JSON parser, which logged a WARNING + ERROR pair every ~10 s.
"""

import logging

import pytest

from custom_components.ecoflow_cloud.devices.internal.river3 import River3


@pytest.fixture
def device() -> River3:
    return object.__new__(River3)


def test_json_frame_is_parsed_as_json(device: River3) -> None:
    assert device._prepare_data(b'{"params":{"status":1}}') == {"params": {"status": 1}}


def test_undecodable_protobuf_frame_is_dropped_quietly(device: River3, caplog: pytest.LogCaptureFixture) -> None:
    # Starts like a protobuf envelope (field 1, length-delimited) but carries
    # nothing the decoder knows; the second byte is a newline, which the old
    # code tried to parse as JSON.
    with caplog.at_level(logging.WARNING):
        assert device._prepare_data(b"\x0a\x0a\xcd\x01\x02") == {}

    assert caplog.text == ""
