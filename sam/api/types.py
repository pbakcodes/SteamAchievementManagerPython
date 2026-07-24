"""C-compatible types and structures used by the Steam client interfaces."""

from __future__ import annotations

import ctypes
from enum import IntEnum


class AccountType(IntEnum):
    Invalid = 0
    Individual = 1
    Multiset = 2
    GameServer = 3
    AnonGameServer = 4
    Pending = 5
    ContentServer = 6
    Clan = 7
    Chat = 8
    P2PSuperSeeder = 9


class UserStatType(IntEnum):
    Invalid = 0
    Integer = 1
    Float = 2
    AverageRate = 3
    Achievements = 4
    GroupAchievements = 5


# ---------------------------------------------------------------------------
# Callback message layout returned by Steam_BGetCallback.
# ---------------------------------------------------------------------------
class CallbackMessage(ctypes.Structure):
    _pack_ = 1
    _fields_ = [
        ("user", ctypes.c_int),
        ("id", ctypes.c_int),
        ("param_pointer", ctypes.c_void_p),
        ("param_size", ctypes.c_int),
    ]


# ---------------------------------------------------------------------------
# Callback payloads.
# ---------------------------------------------------------------------------
class AppDataChanged(ctypes.Structure):
    _pack_ = 1
    _fields_ = [
        ("id", ctypes.c_uint32),
        ("result", ctypes.c_bool),
    ]


class UserStatsReceived(ctypes.Structure):
    _pack_ = 1
    _fields_ = [
        ("game_id", ctypes.c_uint64),
        ("result", ctypes.c_int),
        ("steam_id_user", ctypes.c_uint64),
    ]


class UserStatsStored(ctypes.Structure):
    _pack_ = 1
    _fields_ = [
        ("game_id", ctypes.c_uint64),
        ("result", ctypes.c_int),
    ]


# ---------------------------------------------------------------------------
# Handy aliases.
# ---------------------------------------------------------------------------
CallHandle = ctypes.c_uint64  # Steam SDK "SteamAPICall_t".
INVALID_CALL_HANDLE = 0


def encode_cstring(value: str) -> bytes:
    """Encode a python string as a NUL-terminated UTF-8 buffer for Steam."""
    if value is None:
        return b""
    return value.encode("utf-8") + b"\x00"


def decode_cstring(pointer: int | None, max_length: int | None = None) -> str | None:
    """Read a NUL-terminated UTF-8 string from a raw pointer address."""
    if pointer in (None, 0):
        return None
    if max_length is None:
        raw = ctypes.string_at(pointer)
    else:
        raw = ctypes.string_at(pointer, max_length).split(b"\x00", 1)[0]
    return raw.decode("utf-8", errors="replace")
