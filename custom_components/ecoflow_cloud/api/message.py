import json
import random
from abc import ABC, abstractmethod
from typing import override

from paho.mqtt.client import PayloadType


class Message(ABC):
    @abstractmethod
    def to_mqtt_payload(self) -> PayloadType:
        raise NotImplementedError()

    @property
    def message_id(self) -> str | None:
        """The envelope id a reply carries back, if the message has one."""
        return None

    def describe(self) -> str:
        """Human readable form of the command for the log."""
        return type(self).__name__

    @staticmethod
    def gen_seq() -> int:
        return 999900000 + random.randint(10000, 99999)


JSONType = None | bool | int | float | str | list["JSONType"] | dict[str, "JSONType"]
JSONDict = dict[str, JSONType]


class PrivateAPIMessageProtocol(Message):
    def to_dict(self) -> dict:
        raise NotImplementedError()

    @override
    def describe(self) -> str:
        try:
            return json.dumps(self.to_dict(), default=str)
        except Exception:
            return super().describe()


class JSONMessage(Message):
    def __init__(self, data: JSONDict) -> None:
        super().__init__()
        self.data = data
        self._payload: JSONDict | None = None

    @staticmethod
    def prepare_payload(command: JSONDict) -> JSONDict:
        payload: JSONDict = {
            "from": "HomeAssistant",
            "id": str(Message.gen_seq()),
            "version": "1.0",
        }
        payload.update(command)
        return payload

    def payload(self) -> JSONDict:
        # Built once: the id that is sent must be the id a set_reply is matched against
        if self._payload is None:
            self._payload = JSONMessage.prepare_payload(self.data)
        return self._payload

    @property
    @override
    def message_id(self) -> str | None:
        message_id = self.payload().get("id")
        return None if message_id is None else str(message_id)

    @override
    def describe(self) -> str:
        return json.dumps(self.payload(), default=str)

    @override
    def to_mqtt_payload(self) -> PayloadType:
        return json.dumps(self.payload())
