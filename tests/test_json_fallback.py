"""The JSON parser of the base device on non-JSON frames.

tolwi#210, #872: every binary frame that reached a JSON device class logged
a WARNING ("Trying to load json") and an ERROR ("constant: ... Ignoring
message") - thousands of lines a day.
"""

import logging

from tests.stream_fakes import MASTER, FakeClient, make_stream


def test_binary_frame_is_ignored_quietly(caplog):
    device = make_stream(FakeClient(MASTER), MASTER)

    with caplog.at_level(logging.DEBUG):
        result = device._prepare_data(b"\x0a\x8f\x01\xff\xfe\x12binary")

    assert result == {"params": {}, "raw_data": {}}  # StreamAC wraps the empty dict
    assert [r.levelno for r in caplog.records if "non-JSON" in r.getMessage()] == [logging.DEBUG]
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]


def test_malformed_json_still_warns(caplog):
    device = make_stream(FakeClient(MASTER), MASTER)

    with caplog.at_level(logging.WARNING):
        device._prepare_data(b'{"params": {"soc": 5}')

    assert [r.levelno for r in caplog.records] == [logging.WARNING]


def test_json_is_parsed():
    device = make_stream(FakeClient(MASTER), MASTER)

    assert device._prepare_data(b'{"params": {"soc": 5}}')["params"]["soc"] == 5
