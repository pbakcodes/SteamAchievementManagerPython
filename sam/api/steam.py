"""Load ``steamclient(64).dll`` and expose the module-level Steam exports."""

from __future__ import annotations

import ctypes
import ctypes.wintypes
import os
import struct
import sys
import winreg
from ctypes import POINTER, byref, c_bool, c_int, c_void_p

from .types import CallbackMessage

_IS_64BIT = struct.calcsize("P") == 8
_DLL_NAME = "steamclient64.dll" if _IS_64BIT else "steamclient.dll"

_handle: ctypes.CDLL | None = None
_call_create_interface = None
_call_bgetcallback = None
_call_freelastcallback = None


def get_install_path() -> str | None:
    """Return Steam's install path from the Windows registry, or ``None``."""
    if sys.platform != "win32":
        return None
    for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        for subkey in (r"Software\Valve\Steam", r"Software\WOW6432Node\Valve\Steam"):
            try:
                with winreg.OpenKey(hive, subkey) as key:
                    value, _ = winreg.QueryValueEx(key, "InstallPath")
                    if value:
                        return value
            except OSError:
                continue
    return None


def _add_dll_search_dirs(install_path: str) -> list:
    """Register Steam's directories on the DLL search path (Python 3.8+)."""
    cookies = []
    for candidate in (install_path, os.path.join(install_path, "bin")):
        if os.path.isdir(candidate):
            try:
                cookies.append(os.add_dll_directory(candidate))
            except (OSError, AttributeError):
                pass
    return cookies


def load() -> bool:
    """Load ``steamclient(64).dll`` and resolve exports. Idempotent."""
    global _handle, _call_create_interface, _call_bgetcallback, _call_freelastcallback

    if _handle is not None:
        return True

    install_path = get_install_path()
    if not install_path:
        return False

    _add_dll_search_dirs(install_path)

    dll_path = os.path.join(install_path, _DLL_NAME)
    if not os.path.exists(dll_path):
        # Some Steam installations only ship ``steamclient.dll`` even on 64-bit.
        alt = os.path.join(install_path, "steamclient.dll")
        if _IS_64BIT and os.path.exists(alt):
            dll_path = alt
        else:
            return False

    try:
        module = ctypes.CDLL(dll_path)
    except OSError:
        return False

    # CreateInterface(const char *version, int *returnCode) -> void *
    create_interface = module.CreateInterface
    create_interface.restype = c_void_p
    create_interface.argtypes = [ctypes.c_char_p, ctypes.c_void_p]

    # Steam_BGetCallback(pipe, out message, out call) -> bool
    bgetcallback = module.Steam_BGetCallback
    bgetcallback.restype = c_bool
    bgetcallback.argtypes = [c_int, POINTER(CallbackMessage), POINTER(c_int)]

    # Steam_FreeLastCallback(pipe) -> bool
    freelastcb = module.Steam_FreeLastCallback
    freelastcb.restype = c_bool
    freelastcb.argtypes = [c_int]

    _handle = module
    _call_create_interface = create_interface
    _call_bgetcallback = bgetcallback
    _call_freelastcallback = freelastcb
    return True


def create_interface(version: str) -> int:
    """Return the raw address of an interface instance, or 0."""
    assert _call_create_interface is not None, "Steam.load() was not called"
    address = _call_create_interface(version.encode("ascii"), None)
    return int(address) if address else 0


def get_callback(pipe: int):
    """Return ``(True, CallbackMessage)`` if a callback is queued, else ``(False, None)``."""
    assert _call_bgetcallback is not None, "Steam.load() was not called"
    message = CallbackMessage()
    call = c_int(0)
    ok = _call_bgetcallback(pipe, byref(message), byref(call))
    return (bool(ok), message if ok else None)


def free_last_callback(pipe: int) -> bool:
    assert _call_freelastcallback is not None, "Steam.load() was not called"
    return bool(_call_freelastcallback(pipe))
