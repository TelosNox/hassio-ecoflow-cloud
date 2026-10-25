import json
import logging
import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any, Final

from aiohttp import ClientResponse
from attr import dataclass
from homeassistant.components.diagnostics import async_redact_data

from homeassistant.util import dt

from ..device_data import DeviceData
from .commands import PendingCommand, PendingCommands, evaluate_set_reply
from .message import JSONMessage, Message

_LOGGER = logging.getLogger(__name__)

API_RESPONSE_TO_REDACT: Final = {"token", "email", "certificatePassword"}


# EcoFlow returns 8513 both for a bad access key and for one issued in another region
PUBLIC_API_AUTH_ERROR_CODES = frozenset({"8513"})


class EcoflowException(Exception):
    def __init__(self, message: str, code: str | None = None):
        super().__init__(message)
        # EcoFlow's numeric error code, when the failure came from an API response
        self.code = code


class EcoflowAuthException(EcoflowException):
    """Credentials were rejected - retrying with the same ones will not help."""


@dataclass
class EcoflowMqttInfo:
    url: str
    port: int
    username: str
    password: str
    client_id: str | None = None


class EcoflowApiClient(ABC):
    def __init__(self):
        from custom_components.ecoflow_cloud.api.ecoflow_mqtt import EcoflowMQTTClient

        self.mqtt_info: EcoflowMqttInfo
        self.devices: dict[str, Any] = {}
        self.mqtt_client: EcoflowMQTTClient
        self._mqtt_reconnect_last_attempt = 0.0
        self._mqtt_reconnect_count = 0
        # set by the integration, the only layer that can reach hass and the config entry
        self.on_auth_failure: Callable[[], None] | None = None
        self.pending_commands = PendingCommands()

    @abstractmethod
    async def login(self):
        pass

    @abstractmethod
    async def fetch_all_available_devices(self):
        pass

    @abstractmethod
    async def quota_all(self, device_sn: str | None):
        pass

    @abstractmethod
    def _create_device_info(
        self, device_sn: str, device_name: str, device_type: str, status: int = -1
    ) -> Any:
        pass

    @abstractmethod
    def _device_registry(self) -> dict[str, Any]:
        pass

    def configure_device(self, device_data: DeviceData, api_devices_info: dict[str, Any] | None = None):
        sn = device_data.parent.sn if device_data.parent is not None else device_data.sn
        status = -1
        if api_devices_info and sn in api_devices_info:
            status = api_devices_info[sn].status

        if device_data.parent is not None:
            info = self._create_device_info(device_data.parent.sn, device_data.name, device_data.parent.device_type, status)
        else:
            info = self._create_device_info(device_data.sn, device_data.name, device_data.device_type, status)

        from ..devices import DiagnosticDevice

        registry = self._device_registry()
        if device_data.device_type in registry:
            device = registry[device_data.device_type](info, device_data)
        elif device_data.parent is not None and device_data.parent.device_type in registry:
            device = registry[device_data.parent.device_type](info, device_data)
        else:
            device = DiagnosticDevice(info, device_data)

        self.add_device(device)
        return device

    def add_device(self, device):
        self.devices[device.device_data.sn] = device

    def remove_device(self, device):
        self.devices.pop(device.device_data.sn, None)

    def _accept_mqqt_certification(self, resp_json: dict):
        _LOGGER.debug("Received MQTT credentials: %s", async_redact_data(resp_json, API_RESPONSE_TO_REDACT))
        try:
            mqtt_url = resp_json["data"]["url"]
            mqtt_port = int(resp_json["data"]["port"])
            mqtt_username = resp_json["data"]["certificateAccount"]
            mqtt_password = resp_json["data"]["certificatePassword"]
            self.mqtt_info = EcoflowMqttInfo(mqtt_url, mqtt_port, mqtt_username, mqtt_password)
        except KeyError as key:
            raise EcoflowException(f"Failed to extract key {key} from MQTT credentials response")

        _LOGGER.info(f"Successfully extracted account: {self.mqtt_info.username}")

    async def _get_json_response(self, resp: ClientResponse) -> dict[str, Any]:
        if resp.status != 200:
            raise EcoflowException(f"Got HTTP status code {resp.status}: {resp.reason}")

        try:
            json_resp = await resp.json()
            response_message = json_resp["message"]
        except KeyError as key:
            raise EcoflowException(f"Failed to extract key {key} from {resp}")
        except Exception as error:
            # resp.text is a coroutine method; formatting it printed "<bound method ...>"
            raise EcoflowException(f"Failed to parse response (HTTP {resp.status}): {error}")

        raw_code = json_resp.get("code")
        code = None if raw_code is None else str(raw_code)
        if not self._is_success(code, str(response_message)):
            if code in PUBLIC_API_AUTH_ERROR_CODES:
                raise EcoflowAuthException(f"{response_message}", code=code)
            raise EcoflowException(f"{response_message}", code=code)

        return json_resp

    # The public API documents success as code "0" ("Response Body": "code ...
    # 0: success"); the app API is undocumented and keeps the message check.
    _SUCCESS_BY_CODE = False

    def _is_success(self, code: str | None, message: str) -> bool:
        if self._SUCCESS_BY_CODE and code is not None:
            return code == "0"
        return message.lower() == "success"

    def send_get_message(self, device_sn: str, command: dict | Message):
        if isinstance(command, dict):
            command = JSONMessage(command)

        self.mqtt_client.publish(self.devices[device_sn].device_info.get_topic, command.to_mqtt_payload())

    def send_set_message(self, device_sn: str, mqtt_state: dict[str, Any], command: dict | Message):
        if isinstance(command, dict):
            command = JSONMessage(command)

        device = self.devices[device_sn]
        topic = device.device_info.set_topic
        target_sn = device.set_command_target_sn(command)
        if target_sn != device.device_info.sn:
            routed_topic = self._set_topic_for(target_sn)
            if routed_topic is not None and isinstance(command, JSONMessage):
                topic = routed_topic
                if "sn" in command.data:
                    command.data["sn"] = target_sn
            else:
                target_sn = device.device_info.sn

        if not self.mqtt_client.is_connected():
            # paho would queue the command and deliver it whenever the next
            # connect succeeds, possibly hours later (tolwi#819, #922)
            _LOGGER.warning(
                "Not sending set command for %s, the MQTT connection is down: %s", device_sn, command.describe()
            )
            return

        captured = device.data.capture_target_state(mqtt_state) if device.evaluates_set_replies() else None
        sent_at = dt.utcnow()
        device.data.update_to_target_state(mqtt_state)
        # Every write is logged, so a setting that changed "by itself" can be
        # traced to a command from this integration or ruled out (tolwi#819, #922).
        # The payload carries the SN and the command, no credentials.
        if target_sn != device_sn:
            _LOGGER.info("Sending set command for %s to system main SN %s: %s", device_sn, target_sn, command.describe())
        else:
            _LOGGER.info("Sending set command for %s: %s", device_sn, command.describe())
        self.mqtt_client.publish(topic, command.to_mqtt_payload())

        if captured is not None and command.message_id is not None:
            routed = target_sn != device.device_info.sn

            def on_failure(reason: str) -> None:
                rolled_back = device.data.rollback_target_state(captured, sent_at)
                if rolled_back:
                    _LOGGER.warning("Restored the previous value of %s on %s", ", ".join(rolled_back), device_sn)
                if routed and device.main_sn_cache is not None:
                    # the master role may have moved to another unit
                    device.main_sn_cache.invalidate()

            self.pending_commands.add(
                PendingCommand(command.message_id, device_sn, target_sn, command.describe(), on_failure)
            )

    def on_set_reply(self, payload: bytes) -> None:
        """Called for every message on a set_reply topic."""
        if len(self.pending_commands) == 0:
            return
        try:
            reply = json.loads(payload)
        except ValueError:
            return
        if not isinstance(reply, dict):
            return
        command = self.pending_commands.match(reply)
        if command is None:
            return
        reason = evaluate_set_reply(reply)
        if reason is None:
            _LOGGER.info("Set command %s for %s accepted by %s", command.message_id, command.device_sn, command.target_sn)
            return
        _LOGGER.warning(
            "Set command %s for %s rejected by %s (%s): %s",
            command.message_id,
            command.device_sn,
            command.target_sn,
            reason,
            command.description,
        )
        command.on_failure(reason)

    def expire_pending_commands(self) -> None:
        for command in self.pending_commands.expire():
            _LOGGER.warning(
                "No set_reply from %s for set command %s of %s within %d s: %s",
                command.target_sn,
                command.message_id,
                command.device_sn,
                self.pending_commands.timeout_sec,
                command.description,
            )
            command.on_failure("no reply")

    def _set_topic_for(self, sn: str) -> str | None:
        """Set topic of another device of this account; None if the API has no such topic."""
        return None

    def _set_reply_topic_for(self, sn: str) -> str | None:
        return None

    async def fetch_main_sn(self, device_sn: str) -> str | None:
        """Main SN of the system the device belongs to; None if unknown."""
        return None

    async def async_refresh_main_sn(self, device) -> None:
        cache = device.main_sn_cache
        if cache is None or not cache.begin_refresh():
            return
        main_sn = None
        try:
            main_sn = await self.fetch_main_sn(device.device_info.sn)
        finally:
            changed = cache.accept(main_sn)
        if main_sn is None:
            if not cache.resolved and cache.failures == 1:
                _LOGGER.warning(
                    "Could not get the system main SN for %s, system commands go to its own SN for now",
                    device.device_info.sn,
                )
            return
        if changed:
            _LOGGER.info("System main SN for %s is %s", device.device_info.sn, main_sn)
        if main_sn != device.device_info.sn:
            # the device answers a command on the topic it was sent to
            reply_topic = self._set_reply_topic_for(main_sn)
            if reply_topic is not None and getattr(self, "mqtt_client", None) is not None:
                self.mqtt_client.add_topic(reply_topic)

    async def async_refresh_main_sns(self) -> None:
        for device in list(self.devices.values()):
            await self.async_refresh_main_sn(device)

    def start(self):
        _LOGGER.debug("Starting MQTT client for %s", self.mqtt_info.client_id)
        from custom_components.ecoflow_cloud.api.ecoflow_mqtt import EcoflowMQTTClient

        self.mqtt_client = EcoflowMQTTClient(self.mqtt_info, self.devices)
        self.mqtt_client.on_auth_failure = self.on_auth_failure
        self.mqtt_client.on_set_reply = self.on_set_reply
        self.mqtt_client.on_message_processed = self.expire_pending_commands

    def schedule_mqtt_reconnect(self, data_stale: bool = False, cooldown_sec: int = 60) -> int | None:
        """Return the new reconnect count if a reconnect should run, else None.

        ``data_stale`` exists because a dead socket is not the only failure
        mode: EcoFlow's cloud stops asking a device to report once the MQTT
        session registered for it goes away. Ours stays connected and
        subscribed and simply receives nothing, so is_connected() sees no
        problem. Callers that know their device should be reporting pass
        data_stale=True to reconnect anyway.
        """
        # reconnecting with rejected credentials only repeats the rejection
        if self.mqtt_client.auth_failed:
            return None

        if not data_stale and self.mqtt_client.is_connected():
            return None

        now = time.monotonic()
        if now - self._mqtt_reconnect_last_attempt < cooldown_sec:
            return None

        self._mqtt_reconnect_last_attempt = now
        self._mqtt_reconnect_count += 1
        return self._mqtt_reconnect_count

    @property
    def mqtt_reconnect_count(self) -> int:
        return self._mqtt_reconnect_count

    def stop(self):
        _LOGGER.debug("Stopping MQTT client for %s", self.mqtt_info.client_id)
        assert self.mqtt_client is not None
        self.mqtt_client.stop()
