"""Bookkeeping for outgoing set commands.

Kept free of hass and paho so the decisions can be tested on their own.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

# A main SN that was resolved is trusted for an hour: the master role of a
# linked STREAM system can move to another unit (tolwi#771, #582 comments).
MAIN_SN_TTL_SEC = 3600
# A failed lookup is retried sooner; until then the last known SN is used.
MAIN_SN_RETRY_SEC = 300

# stream.md, "Set & Get Quota": "In BKW systems with multiple devices, the
# parameters for the AC1 switch and AC2 switch are the serial number of the
# corresponding devices. For all other commands, you will first need to use
# this API to obtain the main device serial number." Only the system commands
# the doc lists are routed; anything else stays on the unit's own SN.
STREAM_SYSTEM_COMMAND_PARAMS = frozenset(
    {
        "cfgBackupReverseSoc",  # Backup reserve level
        "cfgEnergyStrategyOperateMode",  # Operating mode - Self-powered / AI Mode
        "cfgFeedGridMode",  # Feed-in control
        # STREAM 5000 Series: "obtain the main device SN before querying or setting
        # system-level values". devSwitch (AC socket) stays on the unit that owns it.
        "bpBackupConfig",  # Backup reserve switch and level
        "workMode",  # Operating mode
        "powerParameterConfig",  # Feed-to-grid limit switch
    }
)


class MainSnCache:
    """The main SN of the STREAM system a unit belongs to.

    Falls back to the unit's own SN until a lookup has succeeded, and keeps
    the last known main SN when a later lookup fails.
    """

    def __init__(self, own_sn: str, clock: Callable[[], float] = time.monotonic):
        self.own_sn = own_sn
        self._clock = clock
        self._main_sn: str | None = None
        self._next_refresh = 0.0
        self._refreshing = False
        # consecutive failed lookups, so the log can warn once instead of every retry
        self.failures = 0

    @property
    def sn(self) -> str:
        return self._main_sn or self.own_sn

    @property
    def resolved(self) -> bool:
        return self._main_sn is not None

    def due(self) -> bool:
        return not self._refreshing and self._clock() >= self._next_refresh

    def begin_refresh(self) -> bool:
        """Claim the next lookup; False when one is running or not due yet."""
        if not self.due():
            return False
        self._refreshing = True
        return True

    def accept(self, main_sn: str | None) -> bool:
        """Store a lookup result (None = failed). True if it differs from the last known main SN."""
        self._refreshing = False
        if not main_sn:
            self.failures += 1
            self._next_refresh = self._clock() + MAIN_SN_RETRY_SEC
            return False
        self.failures = 0
        changed = main_sn != self._main_sn
        self._main_sn = main_sn
        self._next_refresh = self._clock() + MAIN_SN_TTL_SEC
        return changed

    def invalidate(self) -> None:
        """Look the main SN up again at the next opportunity."""
        self._next_refresh = 0.0


def stream_command_target_sn(command: Mapping[str, Any], own_sn: str, main_sn: str) -> str:
    """The SN a STREAM set command has to be sent to."""
    params = command.get("params")
    if not isinstance(params, Mapping) or not params:
        return own_sn
    if all(key in STREAM_SYSTEM_COMMAND_PARAMS for key in params):
        return main_sn
    return own_sn


# How long a command that asked for an answer may stay unanswered. EcoFlow
# documents no limit; devices answer within seconds.
SET_REPLY_TIMEOUT_SEC = 30

# general_information.md, "Reply Topic's Common Field": code "0: success
# -1: this device don't belong to user -2: device offline"
SET_REPLY_CODES = {
    "-1": "the device does not belong to this account",
    "-2": "the device is offline",
}


def evaluate_set_reply(reply: Mapping[str, Any]) -> str | None:
    """Why the device rejected a command, or None if it did not.

    Only documented fields are judged: the common reply ``code`` and
    ``data.configOk`` (STREAM and DELTA Pro 3 "Set & Set Reply" examples) or
    ``data.cmdOk`` (STREAM 5000 Series). ``data.ack`` is left alone: the docs
    show both 0 and 1 in replies that carry code "0".
    """
    code = reply.get("code")
    if code is not None and str(code) != "0":
        reason = SET_REPLY_CODES.get(str(code)) or reply.get("message") or "unknown error"
        return f"code {code}: {reason}"
    data = reply.get("data")
    if isinstance(data, Mapping):
        for field in ("configOk", "cmdOk"):
            if data.get(field) is False:
                return f"{field} is false"
    return None


@dataclass
class PendingCommand:
    message_id: str
    device_sn: str
    target_sn: str
    description: str
    on_failure: Callable[[str], None]
    sent_at: float = 0.0


class PendingCommands:
    """Commands waiting for their set_reply, matched by the envelope id."""

    def __init__(self, timeout_sec: float = SET_REPLY_TIMEOUT_SEC, clock: Callable[[], float] = time.monotonic):
        self._timeout_sec = timeout_sec
        self._clock = clock
        self._pending: dict[str, PendingCommand] = {}
        self._lock = threading.Lock()

    def __len__(self) -> int:
        return len(self._pending)

    @property
    def timeout_sec(self) -> float:
        return self._timeout_sec

    def add(self, command: PendingCommand) -> None:
        command.sent_at = self._clock()
        with self._lock:
            self._pending[command.message_id] = command

    def match(self, reply: Mapping[str, Any]) -> PendingCommand | None:
        message_id = reply.get("id")
        if message_id is None:
            return None
        with self._lock:
            return self._pending.pop(str(message_id), None)

    def expire(self) -> list[PendingCommand]:
        deadline = self._clock() - self._timeout_sec
        with self._lock:
            expired = [c for c in self._pending.values() if c.sent_at <= deadline]
            for command in expired:
                del self._pending[command.message_id]
        return expired
