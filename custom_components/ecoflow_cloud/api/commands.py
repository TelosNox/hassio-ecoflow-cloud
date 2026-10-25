"""Bookkeeping for outgoing set commands.

Kept free of hass and paho so the decisions can be tested on their own.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
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
