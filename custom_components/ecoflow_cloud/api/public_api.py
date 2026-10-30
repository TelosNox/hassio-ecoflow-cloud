import hashlib
import hmac
import logging
import random
import time
from typing import Any

import aiohttp
from homeassistant.components.diagnostics import async_redact_data

from custom_components.ecoflow_cloud.devices.data_holder import PreparedData

from ..devices import EcoflowDeviceInfo
from . import API_RESPONSE_TO_REDACT, EcoflowApiClient

_LOGGER = logging.getLogger(__name__)

# from FB
# client_id limits for MQTT connections
# If you are using MQTT to connect to the API be aware that only 10 unique client IDs are allowed per day.
# As such, it is suggested that you choose a static client_id for your application or integration to use consistently.
# If your code generates a unique client_id (as mine did) for each connection,
# you can exceed this limit very quickly when testing or debugging code.


def flatten_sign_params(data: dict[str, Any]) -> str:
    """The key=value string a JSON body is signed with (general_information.md, steps 1-2)."""
    items: list[tuple[str, str]] = []

    def expand(prefix: str, value: Any) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                expand(f"{prefix}.{key}" if prefix else str(key), item)
        elif isinstance(value, list):
            for index, item in enumerate(value):
                expand(f"{prefix}[{index}]", item)
        elif isinstance(value, bool):
            items.append((prefix, "true" if value else "false"))
        else:
            items.append((prefix, str(value)))

    expand("", data)
    return "&".join(f"{key}={value}" for key, value in sorted(items))


class EcoflowPublicApiClient(EcoflowApiClient):
    _SUCCESS_BY_CODE = True

    def __init__(
        self,
        api_domain: str,
        access_key: str,
        secret_key: str,
        group: str,
        session: aiohttp.ClientSession | None = None,
    ):
        super().__init__()
        # HA's shared session keeps connections (and DNS results) alive between
        # the polls; without one, each call opens and closes its own (tolwi#886)
        self._session = session
        self.api_domain = api_domain
        # strip here too: entries stored before the config flow sanitized them
        self.access_key = access_key.strip()
        self.secret_key = secret_key.strip()
        self.group = group
        self.nonce = self._gen_nonce()
        self.timestamp = str(int(time.time() * 1000))

    async def login(self):
        _LOGGER.info("Requesting IoT MQTT credentials")
        response = await self.call_api("/certification")
        self._accept_mqqt_certification(response)
        self.mqtt_info.client_id = f"Hassio-{self.mqtt_info.username}-{self.group.replace(' ', '-')}"

    async def fetch_all_available_devices(self) -> list[EcoflowDeviceInfo]:
        _LOGGER.info("Requesting all devices")
        response = await self.call_api("/device/list")
        _LOGGER.debug("Received devices: %s", response)
        result = []
        # "data" is optional in the documented response and absent when the
        # account has no devices of its own: shared devices are not listed
        devices = response.get("data") or []
        if not devices:
            _LOGGER.warning(
                "EcoFlow lists no devices for this developer account. Only devices bound to the "
                "account the developer keys belong to are listed, not devices shared with it"
            )
        for device in devices:
            _LOGGER.debug(str(device))
            sn = device["sn"]
            product_name = device.get("productName", "undefined")
            if product_name == "undefined":
                from ..devices.registry import device_by_product

                device_list = list(device_by_product.keys())
                device_list.sort(key=len, reverse=True)
                for devicetype in device_list:
                    if "deviceName" in device and device["deviceName"].lower().startswith(devicetype.lower()):
                        product_name = devicetype
                        break
            from ..devices.registry import device_by_product, device_by_sn_prefix

            if product_name not in device_by_product:
                product_name = device_by_sn_prefix.get(sn[:4], product_name)
            device_name = device.get("deviceName", f"{product_name}-{sn}")
            status = int(device["online"])
            result.append(self._create_device_info(sn, device_name, product_name, status))

        return result

    def _device_registry(self) -> dict[str, Any]:
        from custom_components.ecoflow_cloud.devices.registry import device_by_product
        return device_by_product

    async def quota_all(self, device_sn: str | None):
        target_devices = [device_sn] if device_sn else list(self.devices)

        for sn in target_devices:
            try:
                raw = await self.call_api("/device/quota/all", {"sn": sn})
                if "data" in raw:
                    self.devices[sn].data.add_data(PreparedData(None, {"params": raw["data"]}, raw, False))
            except Exception:
                _LOGGER.exception("Error retrieving %s", sn)

    @staticmethod
    def _gen_nonce() -> str:
        # EcoFlow specifies the nonce header as a 6-digit random number
        return str(random.randint(100000, 999999))

    async def call_api(self, endpoint: str, params: dict[str, str] | None = None) -> dict:
        if self._session is not None:
            return await self._call_api(self._session, endpoint, params)
        async with aiohttp.ClientSession() as session:
            return await self._call_api(session, endpoint, params)

    async def _call_api(
        self, session: aiohttp.ClientSession, endpoint: str, params: dict[str, str] | None
    ) -> dict:
        self.nonce = self._gen_nonce()
        self.timestamp = str(int(time.time() * 1000))
        params_str = ""
        if params is not None:
            params_str = self.__sort_and_concat_params(params)

        sign = self.__gen_sign(params_str)

        headers = {
            "accessKey": self.access_key,
            "nonce": self.nonce,
            "timestamp": self.timestamp,
            "sign": sign,
        }

        _LOGGER.debug("Request: %s %s.", str(endpoint), str(params_str))
        # the context manager releases the connection to the pool on every path
        async with session.get(
            f"https://{self.api_domain}/iot-open/sign{endpoint}?{params_str}",
            headers=headers,
        ) as resp:
            json_resp = await self._get_json_response(resp)
        _LOGGER.debug(
            "Request: %s %s. Response : %s",
            str(endpoint),
            str(params_str),
            async_redact_data(json_resp, API_RESPONSE_TO_REDACT),
        )
        return json_resp

    async def fetch_main_sn(self, device_sn: str) -> str | None:
        # stream.md, "Obtain the main device serial number of the STREAM system":
        # GET /iot-open/sign/device/system/main/sn?sn=<any SN of the system>,
        # response data.sn = "the serial number of the main device"
        try:
            response = await self.call_api("/device/system/main/sn", {"sn": device_sn})
        except Exception as error:
            _LOGGER.debug("Main SN lookup for %s failed: %s", device_sn, error)
            return None
        data = response.get("data")
        if isinstance(data, dict) and isinstance(data.get("sn"), str) and data["sn"]:
            return data["sn"]
        return None

    async def quota_data(self, device_sn: str, begin_time: str, end_time: str, code: str) -> dict:
        # stream.md, "Historical data": POST /iot-open/sign/device/quota/data,
        # body {"sn", "params": {"beginTime", "endTime", "code"}}, times in UTC
        return await self.post_api(
            "/device/quota/data",
            {"sn": device_sn, "params": {"beginTime": begin_time, "endTime": end_time, "code": code}},
        )

    async def post_api(self, endpoint: str, body: dict[str, Any]) -> dict:
        if self._session is not None:
            return await self._post_api(self._session, endpoint, body)
        async with aiohttp.ClientSession() as session:
            return await self._post_api(session, endpoint, body)

    async def _post_api(self, session: aiohttp.ClientSession, endpoint: str, body: dict[str, Any]) -> dict:
        self.nonce = self._gen_nonce()
        self.timestamp = str(int(time.time() * 1000))
        # general_information.md, signature steps 2 and 7: a JSON body is
        # signed like a query string, nested keys expanded to a.b and a[0]
        sign = self.__gen_sign(flatten_sign_params(body))
        headers = {
            "accessKey": self.access_key,
            "nonce": self.nonce,
            "timestamp": self.timestamp,
            "sign": sign,
            "Content-Type": "application/json;charset=UTF-8",
        }
        _LOGGER.debug("Request: POST %s %s.", endpoint, body)
        async with session.post(
            f"https://{self.api_domain}/iot-open/sign{endpoint}",
            headers=headers,
            json=body,
        ) as resp:
            json_resp = await self._get_json_response(resp)
        _LOGGER.debug("Request: POST %s. Response : %s", endpoint, async_redact_data(json_resp, API_RESPONSE_TO_REDACT))
        return json_resp

    def _set_topic_for(self, sn: str) -> str | None:
        return f"/open/{self.mqtt_info.username}/{sn}/set"

    def _set_reply_topic_for(self, sn: str) -> str | None:
        return f"/open/{self.mqtt_info.username}/{sn}/set_reply"

    def _create_device_info(
        self, device_sn: str, device_name: str, device_type: str, status: int = -1
    ) -> EcoflowDeviceInfo:
        return EcoflowDeviceInfo(
            public_api=True,
            sn=device_sn,
            name=device_name,
            device_type=device_type,
            status=status,
            data_topic=f"/open/{self.mqtt_info.username}/{device_sn}/quota",
            set_topic=f"/open/{self.mqtt_info.username}/{device_sn}/set",
            set_reply_topic=f"/open/{self.mqtt_info.username}/{device_sn}/set_reply",
            get_topic=None,
            get_reply_topic=None,
            status_topic=f"/open/{self.mqtt_info.username}/{device_sn}/status",
        )

    def __gen_sign(self, query_params: str | None) -> str:
        target_str = f"accessKey={self.access_key}&nonce={self.nonce}&timestamp={self.timestamp}"
        if query_params:
            target_str = query_params + "&" + target_str

        return self.__encrypt_hmac_sha256(target_str, self.secret_key)

    def __sort_and_concat_params(self, params: dict[str, str]) -> str:
        # Sort the dictionary items by key
        sorted_items = sorted(params.items(), key=lambda x: x[0])

        # Create a list of "key=value" strings
        param_strings = [f"{key}={value}" for key, value in sorted_items]

        # Join the strings with '&'
        return "&".join(param_strings)

    def __encrypt_hmac_sha256(self, message: str, secret_key: str) -> str:
        # Convert the message and secret key to bytes
        message_bytes = message.encode("utf-8")
        secret_bytes = secret_key.encode("utf-8")

        # Create the HMAC
        hmac_obj = hmac.new(secret_bytes, message_bytes, hashlib.sha256)

        # Get the hexadecimal representation of the HMAC
        hmac_digest = hmac_obj.hexdigest()

        return hmac_digest
