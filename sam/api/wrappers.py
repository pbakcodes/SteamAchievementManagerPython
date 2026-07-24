"""Wrappers for the Steam client vtable interfaces.

Each Steam interface returned by ``ISteamClient::Get*`` (and by
``CreateInterface``) is a pointer to a C++ object whose first field is a
pointer to a vtable of member function pointers. To call a method we:

1. read the vtable pointer at ``*object_address``;
2. read the function pointer at ``vtable + slot_index * pointer_size``;
3. wrap it with :func:`ctypes.CFUNCTYPE`;
4. invoke it with the interface's own address as the first ("this") argument.

This module targets 64-bit Windows, where the Microsoft x64 ABI is uniform for
all functions (no ``__thiscall`` gymnastics needed).
"""

from __future__ import annotations

import ctypes
from ctypes import (
    CFUNCTYPE,
    POINTER,
    c_bool,
    c_char_p,
    c_float,
    c_int,
    c_uint32,
    c_uint64,
    c_void_p,
    cast,
    sizeof,
)
from typing import Callable

from . import steam
from .types import (
    CallHandle,
    encode_cstring,
    decode_cstring,
)


_PTR = sizeof(c_void_p)


def _vfn(address: int, slot: int) -> int:
    """Return the raw function address at ``slot`` in ``address``'s vtable."""
    if not address:
        raise RuntimeError("null interface pointer")
    vtable = ctypes.cast(address, POINTER(c_void_p))[0]
    if not vtable:
        raise RuntimeError("null vtable")
    slot_addr = vtable + slot * _PTR
    return ctypes.cast(slot_addr, POINTER(c_void_p))[0] or 0


class _Wrapper:
    """Base class holding the raw interface pointer."""

    def __init__(self, address: int):
        self.address = int(address)

    def __bool__(self) -> bool:
        return self.address != 0


# ---------------------------------------------------------------------------
# ISteamClient018 - slot indices from Interfaces/ISteamClient018.cs
# ---------------------------------------------------------------------------
class SteamClient018(_Wrapper):
    _CreateSteamPipe = 0
    _ReleaseSteamPipe = 1
    _ConnectToGlobalUser = 2
    _CreateLocalUser = 3
    _ReleaseUser = 4
    _GetISteamUser = 5
    _GetISteamGameServer = 6
    _SetLocalIPBinding = 7
    _GetISteamFriends = 8
    _GetISteamUtils = 9
    _GetISteamMatchmaking = 10
    _GetISteamMatchmakingServers = 11
    _GetISteamGenericInterface = 12
    _GetISteamUserStats = 13
    _GetISteamGameServerStats = 14
    _GetISteamApps = 15

    def create_steam_pipe(self) -> int:
        fn = CFUNCTYPE(c_int, c_void_p)(_vfn(self.address, self._CreateSteamPipe))
        return int(fn(self.address))

    def release_steam_pipe(self, pipe: int) -> bool:
        fn = CFUNCTYPE(c_bool, c_void_p, c_int)(
            _vfn(self.address, self._ReleaseSteamPipe)
        )
        return bool(fn(self.address, pipe))

    def connect_to_global_user(self, pipe: int) -> int:
        fn = CFUNCTYPE(c_int, c_void_p, c_int)(
            _vfn(self.address, self._ConnectToGlobalUser)
        )
        return int(fn(self.address, pipe))

    def release_user(self, pipe: int, user: int) -> None:
        fn = CFUNCTYPE(None, c_void_p, c_int, c_int)(
            _vfn(self.address, self._ReleaseUser)
        )
        fn(self.address, pipe, user)

    # -- individual interface getters -------------------------------------
    def _get_interface(self, slot: int, *args) -> int:
        # Signature is one of:
        #   (self, int user, int pipe, const char *version)      -- user-scoped
        #   (self, int pipe, const char *version)                -- utils
        arg_types = [c_void_p] + [c_int] * (len(args) - 1) + [c_char_p]
        fn = CFUNCTYPE(c_void_p, *arg_types)(_vfn(self.address, slot))
        result = fn(self.address, *args)
        return int(result) if result else 0

    def get_steam_user012(self, user: int, pipe: int) -> "SteamUser012":
        addr = self._get_interface(
            self._GetISteamUser, user, pipe, b"SteamUser012"
        )
        return SteamUser012(addr)

    def get_steam_user_stats013(self, user: int, pipe: int) -> "SteamUserStats013":
        addr = self._get_interface(
            self._GetISteamUserStats,
            user,
            pipe,
            b"STEAMUSERSTATS_INTERFACE_VERSION013",
        )
        return SteamUserStats013(addr)

    def get_steam_utils005(self, pipe: int) -> "SteamUtils005":
        # ISteamClient::GetISteamUtils takes (pipe, version), no user.
        fn = CFUNCTYPE(c_void_p, c_void_p, c_int, c_char_p)(
            _vfn(self.address, self._GetISteamUtils)
        )
        result = fn(self.address, pipe, b"SteamUtils005")
        return SteamUtils005(int(result) if result else 0)

    def get_steam_apps001(self, user: int, pipe: int) -> "SteamApps001":
        addr = self._get_interface(
            self._GetISteamApps,
            user,
            pipe,
            b"STEAMAPPS_INTERFACE_VERSION001",
        )
        return SteamApps001(addr)

    def get_steam_apps008(self, user: int, pipe: int) -> "SteamApps008":
        addr = self._get_interface(
            self._GetISteamApps,
            user,
            pipe,
            b"STEAMAPPS_INTERFACE_VERSION008",
        )
        return SteamApps008(addr)


# ---------------------------------------------------------------------------
# ISteamUser012
# ---------------------------------------------------------------------------
class SteamUser012(_Wrapper):
    _GetHSteamUser = 0
    _LoggedOn = 1
    _GetSteamID = 2

    def is_logged_in(self) -> bool:
        fn = CFUNCTYPE(c_bool, c_void_p)(_vfn(self.address, self._LoggedOn))
        return bool(fn(self.address))

    def get_steam_id(self) -> int:
        # CSteamID (64-bit) is returned by out-pointer in some builds and by
        # value in others. The vtable slot's signature is
        # ``void GetSteamID(this, CSteamID *out)``.
        fn = CFUNCTYPE(None, c_void_p, POINTER(c_uint64))(
            _vfn(self.address, self._GetSteamID)
        )
        out = c_uint64(0)
        fn(self.address, ctypes.byref(out))
        return int(out.value)


# ---------------------------------------------------------------------------
# ISteamUtils005
# ---------------------------------------------------------------------------
class SteamUtils005(_Wrapper):
    _GetSecondsSinceAppActive = 0
    _GetSecondsSinceComputerActive = 1
    _GetConnectedUniverse = 2
    _GetServerRealTime = 3
    _GetIPCountry = 4
    _GetImageSize = 5
    _GetImageRGBA = 6
    _GetCSERIPPort = 7
    _GetCurrentBatteryPower = 8
    _GetAppID = 9

    def get_connected_universe(self) -> int:
        fn = CFUNCTYPE(c_int, c_void_p)(
            _vfn(self.address, self._GetConnectedUniverse)
        )
        return int(fn(self.address))

    def get_ip_country(self) -> str | None:
        fn = CFUNCTYPE(c_void_p, c_void_p)(_vfn(self.address, self._GetIPCountry))
        return decode_cstring(fn(self.address))

    def get_image_size(self, index: int) -> tuple[int, int] | None:
        fn = CFUNCTYPE(c_bool, c_void_p, c_int, POINTER(c_uint32), POINTER(c_uint32))(
            _vfn(self.address, self._GetImageSize)
        )
        w = c_uint32(0)
        h = c_uint32(0)
        if not fn(self.address, index, ctypes.byref(w), ctypes.byref(h)):
            return None
        return int(w.value), int(h.value)

    def get_image_rgba(self, index: int, buffer: bytearray) -> bool:
        fn = CFUNCTYPE(c_bool, c_void_p, c_int, c_void_p, c_int)(
            _vfn(self.address, self._GetImageRGBA)
        )
        buf = (ctypes.c_ubyte * len(buffer)).from_buffer(buffer)
        return bool(fn(self.address, index, ctypes.cast(buf, c_void_p), len(buffer)))

    def get_app_id(self) -> int:
        fn = CFUNCTYPE(c_uint32, c_void_p)(_vfn(self.address, self._GetAppID))
        return int(fn(self.address))


# ---------------------------------------------------------------------------
# ISteamApps001
# ---------------------------------------------------------------------------
class SteamApps001(_Wrapper):
    _GetAppData = 0

    def get_app_data(self, app_id: int, key: str) -> str | None:
        fn = CFUNCTYPE(c_int, c_void_p, c_uint32, c_char_p, c_void_p, c_int)(
            _vfn(self.address, self._GetAppData)
        )
        length = 1024
        buf = ctypes.create_string_buffer(length)
        result = fn(
            self.address,
            app_id,
            key.encode("utf-8"),
            ctypes.cast(buf, c_void_p),
            length,
        )
        if result == 0:
            return None
        return decode_cstring(ctypes.addressof(buf), length)


# ---------------------------------------------------------------------------
# ISteamApps008
# ---------------------------------------------------------------------------
class SteamApps008(_Wrapper):
    _IsSubscribed = 0
    _IsLowViolence = 1
    _IsCybercafe = 2
    _IsVACBanned = 3
    _GetCurrentGameLanguage = 4
    _GetAvailableGameLanguages = 5
    _IsSubscribedApp = 6

    def is_subscribed_app(self, game_id: int) -> bool:
        fn = CFUNCTYPE(c_bool, c_void_p, c_uint32)(
            _vfn(self.address, self._IsSubscribedApp)
        )
        return bool(fn(self.address, game_id))

    def get_current_game_language(self) -> str | None:
        fn = CFUNCTYPE(c_void_p, c_void_p)(
            _vfn(self.address, self._GetCurrentGameLanguage)
        )
        return decode_cstring(fn(self.address))


# ---------------------------------------------------------------------------
# ISteamUserStats013 - achievement / stat management
# ---------------------------------------------------------------------------
class SteamUserStats013(_Wrapper):
    _GetStatFloat = 0
    _GetStatInteger = 1
    _SetStatFloat = 2
    _SetStatInteger = 3
    _UpdateAvgRateStat = 4
    _GetAchievement = 5
    _SetAchievement = 6
    _ClearAchievement = 7
    _GetAchievementAndUnlockTime = 8
    _StoreStats = 9
    _GetAchievementIcon = 10
    _GetAchievementDisplayAttribute = 11
    _IndicateAchievementProgress = 12
    _GetNumAchievements = 13
    _GetAchievementName = 14
    _RequestUserStats = 15
    _GetUserStatFloat = 16
    _GetUserStatInt = 17
    _GetUserAchievement = 18
    _GetUserAchievementAndUnlockTime = 19
    _ResetAllStats = 20

    # -- stat get / set --------------------------------------------------
    def get_stat_int(self, name: str):
        fn = CFUNCTYPE(c_bool, c_void_p, c_char_p, POINTER(c_int))(
            _vfn(self.address, self._GetStatInteger)
        )
        out = c_int(0)
        ok = fn(self.address, name.encode("utf-8"), ctypes.byref(out))
        return (bool(ok), int(out.value))

    def get_stat_float(self, name: str):
        fn = CFUNCTYPE(c_bool, c_void_p, c_char_p, POINTER(c_float))(
            _vfn(self.address, self._GetStatFloat)
        )
        out = c_float(0.0)
        ok = fn(self.address, name.encode("utf-8"), ctypes.byref(out))
        return (bool(ok), float(out.value))

    def set_stat_int(self, name: str, value: int) -> bool:
        fn = CFUNCTYPE(c_bool, c_void_p, c_char_p, c_int)(
            _vfn(self.address, self._SetStatInteger)
        )
        return bool(fn(self.address, name.encode("utf-8"), int(value)))

    def set_stat_float(self, name: str, value: float) -> bool:
        fn = CFUNCTYPE(c_bool, c_void_p, c_char_p, c_float)(
            _vfn(self.address, self._SetStatFloat)
        )
        return bool(fn(self.address, name.encode("utf-8"), float(value)))

    # -- achievements ----------------------------------------------------
    def get_achievement(self, name: str):
        fn = CFUNCTYPE(c_bool, c_void_p, c_char_p, POINTER(c_bool))(
            _vfn(self.address, self._GetAchievement)
        )
        out = c_bool(False)
        ok = fn(self.address, name.encode("utf-8"), ctypes.byref(out))
        return (bool(ok), bool(out.value))

    def get_achievement_and_unlock_time(self, name: str):
        fn = CFUNCTYPE(c_bool, c_void_p, c_char_p, POINTER(c_bool), POINTER(c_uint32))(
            _vfn(self.address, self._GetAchievementAndUnlockTime)
        )
        achieved = c_bool(False)
        unlock = c_uint32(0)
        ok = fn(
            self.address,
            name.encode("utf-8"),
            ctypes.byref(achieved),
            ctypes.byref(unlock),
        )
        return (bool(ok), bool(achieved.value), int(unlock.value))

    def set_achievement(self, name: str, state: bool) -> bool:
        slot = self._SetAchievement if state else self._ClearAchievement
        fn = CFUNCTYPE(c_bool, c_void_p, c_char_p)(_vfn(self.address, slot))
        return bool(fn(self.address, name.encode("utf-8")))

    def store_stats(self) -> bool:
        fn = CFUNCTYPE(c_bool, c_void_p)(_vfn(self.address, self._StoreStats))
        return bool(fn(self.address))

    def request_user_stats(self, steam_id: int) -> int:
        fn = CFUNCTYPE(c_uint64, c_void_p, c_uint64)(
            _vfn(self.address, self._RequestUserStats)
        )
        return int(fn(self.address, steam_id))

    def reset_all_stats(self, achievements_too: bool) -> bool:
        fn = CFUNCTYPE(c_bool, c_void_p, c_bool)(
            _vfn(self.address, self._ResetAllStats)
        )
        return bool(fn(self.address, bool(achievements_too)))

    def get_achievement_icon(self, name: str) -> int:
        fn = CFUNCTYPE(c_int, c_void_p, c_char_p)(
            _vfn(self.address, self._GetAchievementIcon)
        )
        return int(fn(self.address, name.encode("utf-8")))

    def get_achievement_display_attribute(self, name: str, key: str) -> str | None:
        fn = CFUNCTYPE(c_void_p, c_void_p, c_char_p, c_char_p)(
            _vfn(self.address, self._GetAchievementDisplayAttribute)
        )
        result = fn(self.address, name.encode("utf-8"), key.encode("utf-8"))
        return decode_cstring(result)
