"""Outgoing set commands: the id, the audit log line.

References: EcoFlow "General information", "Request Topic's Common Field"
("id: Message ID, unique per request ... Response will return the same id");
tolwi/hassio-ecoflow-cloud#819, #922 (settings changed without a traceable command).
"""

import json

from custom_components.ecoflow_cloud.api.message import JSONMessage


def test_json_message_id_is_stable_across_serialisations():
    # A set_reply can only be matched if the id that went out is the id we keep
    message = JSONMessage({"sn": "BK11", "params": {"cfgFeedGridMode": 2}})

    first = json.loads(message.to_mqtt_payload())  # type: ignore[arg-type]
    second = json.loads(message.to_mqtt_payload())  # type: ignore[arg-type]

    assert first["id"] == second["id"] == message.message_id


def test_json_message_describe_is_the_sent_payload():
    message = JSONMessage({"sn": "BK11", "params": {"cfgFeedGridMode": 2}})

    assert json.loads(message.describe()) == json.loads(message.to_mqtt_payload())  # type: ignore[arg-type]
