"""Data classes for achievements & statistics.

Direct translation of the classes under ``SAM.Game.Stats``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import IntFlag
from typing import Optional


class StatFlags(IntFlag):
    NoneFlag = 0
    IncrementOnly = 1 << 0
    Protected = 1 << 1
    UnknownPermission = 1 << 2


class StatIsProtectedException(Exception):
    """Raised when the user attempts to edit a protected stat."""


# ---------------------------------------------------------------------------
# Schema (definitions loaded from the game's ``UserGameStatsSchema`` file).
# ---------------------------------------------------------------------------
@dataclass
class AchievementDefinition:
    id: str = ""
    name: str = ""
    description: str = ""
    icon_normal: str = ""
    icon_locked: str = ""
    is_hidden: bool = False
    permission: int = 0

    def __str__(self) -> str:
        return f"{self.name or self.id}: {self.permission}"


@dataclass
class StatDefinition:
    id: str = ""
    display_name: str = ""
    permission: int = 0


@dataclass
class IntegerStatDefinition(StatDefinition):
    min_value: int = -(2**31)
    max_value: int = 2**31 - 1
    max_change: int = 0
    increment_only: bool = False
    set_by_trusted_game_server: bool = False
    default_value: int = 0


@dataclass
class FloatStatDefinition(StatDefinition):
    min_value: float = float("-inf")
    max_value: float = float("inf")
    max_change: float = 0.0
    increment_only: bool = False
    default_value: float = 0.0


# ---------------------------------------------------------------------------
# Runtime state
# ---------------------------------------------------------------------------
@dataclass
class AchievementInfo:
    id: str = ""
    is_achieved: bool = False
    unlock_time: Optional[datetime] = None
    permission: int = 0
    icon_normal: Optional[str] = None
    icon_locked: Optional[str] = None
    name: str = ""
    description: str = ""


class StatInfo:
    """Base class for a modifiable stat value shown in the grid."""

    def __init__(
        self,
        stat_id: str,
        display_name: str,
        permission: int,
        increment_only: bool,
    ):
        self.id = stat_id
        self.display_name = display_name
        self.permission = permission
        self.is_increment_only = increment_only

    # Subclasses must override:
    @property
    def value(self):
        raise NotImplementedError

    @value.setter
    def value(self, new_value):
        raise NotImplementedError

    @property
    def is_modified(self) -> bool:
        raise NotImplementedError

    @property
    def extra(self) -> str:
        flags = StatFlags.NoneFlag
        if self.is_increment_only:
            flags |= StatFlags.IncrementOnly
        if (self.permission & 2) != 0:
            flags |= StatFlags.Protected
        if (self.permission & ~2) != 0:
            flags |= StatFlags.UnknownPermission
        return flags.name or "NoneFlag" if flags == StatFlags.NoneFlag else str(flags).replace("StatFlags.", "")


class IntStatInfo(StatInfo):
    def __init__(
        self,
        stat_id: str,
        display_name: str,
        permission: int,
        increment_only: bool,
        original_value: int,
    ):
        super().__init__(stat_id, display_name, permission, increment_only)
        self.original_value = original_value
        self._int_value = original_value

    @property
    def int_value(self) -> int:
        return self._int_value

    @int_value.setter
    def int_value(self, new: int) -> None:
        self._int_value = int(new)

    @property
    def value(self) -> int:
        return self._int_value

    @value.setter
    def value(self, new_value) -> None:
        parsed = int(str(new_value))
        if (self.permission & 2) != 0 and self._int_value != parsed:
            raise StatIsProtectedException()
        self._int_value = parsed

    @property
    def is_modified(self) -> bool:
        return self._int_value != self.original_value


class FloatStatInfo(StatInfo):
    def __init__(
        self,
        stat_id: str,
        display_name: str,
        permission: int,
        increment_only: bool,
        original_value: float,
    ):
        super().__init__(stat_id, display_name, permission, increment_only)
        self.original_value = float(original_value)
        self._float_value = float(original_value)

    @property
    def float_value(self) -> float:
        return self._float_value

    @float_value.setter
    def float_value(self, new: float) -> None:
        self._float_value = float(new)

    @property
    def value(self) -> float:
        return self._float_value

    @value.setter
    def value(self, new_value) -> None:
        parsed = float(str(new_value))
        if (self.permission & 2) != 0 and self._float_value != parsed:
            raise StatIsProtectedException()
        self._float_value = parsed

    @property
    def is_modified(self) -> bool:
        return self._float_value != self.original_value
