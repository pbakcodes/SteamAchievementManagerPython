"""Callback registration & dispatch.

Callback IDs are defined by the Steam SDK. When Steam has a callback ready it
returns a :class:`~sam.api.types.CallbackMessage` from
``Steam_BGetCallback``; the ``param_pointer`` holds a struct whose layout is
described by the corresponding :class:`ctypes.Structure`.
"""

from __future__ import annotations

import ctypes
from dataclasses import dataclass, field
from typing import Callable, Generic, TypeVar

from . import types as api_types

TStruct = TypeVar("TStruct", bound=ctypes.Structure)


@dataclass
class Callback(Generic[TStruct]):
    """Registration record for a Steam callback."""

    id: int
    struct_type: type[TStruct]
    handlers: list[Callable[[TStruct], None]] = field(default_factory=list)
    is_server: bool = False

    def add_handler(self, handler: Callable[[TStruct], None]) -> None:
        self.handlers.append(handler)

    def dispatch(self, pointer: int) -> None:
        data = ctypes.cast(pointer, ctypes.POINTER(self.struct_type))[0]
        for handler in list(self.handlers):
            handler(data)


# ---------------------------------------------------------------------------
# Standard SAM callbacks - IDs preserved from SAM.API.Callbacks/*.cs
# ---------------------------------------------------------------------------
class AppDataChanged(Callback[api_types.AppDataChanged]):
    def __init__(self):
        super().__init__(id=1001, struct_type=api_types.AppDataChanged)


class UserStatsReceived(Callback[api_types.UserStatsReceived]):
    def __init__(self):
        super().__init__(id=1101, struct_type=api_types.UserStatsReceived)


class UserStatsStored(Callback[api_types.UserStatsStored]):
    def __init__(self):
        super().__init__(id=1102, struct_type=api_types.UserStatsStored)
