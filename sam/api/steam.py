"""Load the Steam client library and expose the module-level Steam exports.

Platform-specific details -- where the library lives and how it is opened --
are delegated to a :class:`~sam.api.platform.SteamPlatform` strategy, chosen at
runtime by :func:`~sam.api.platform.current_platform`. This module therefore
stays platform-agnostic and only resolves the shared C exports
(``CreateInterface``, ``Steam_BGetCallback``, ``Steam_FreeLastCallback``).
"""

from __future__ import annotations

import ctypes
from ctypes import POINTER, byref, c_bool, c_int, c_void_p

from .platform import SteamPlatform, current_platform
from .types import CallbackMessage

_handle: ctypes.CDLL | None = None
_call_create_interface = None
_call_bgetcallback = None
_call_freelastcallback = None
_platform: SteamPlatform | None = None


def _get_platform() -> SteamPlatform:
    global _platform
    if _platform is None:
        _platform = current_platform()
    return _platform


def get_install_path() -> str | None:
    """Return Steam's install path, or ``None`` if it cannot be located."""
    return _get_platform().install_path()


def load(platform: SteamPlatform | None = None) -> bool:
    """Load the Steam client library and resolve exports. Idempotent.

    ``platform`` lets a caller inject a strategy (e.g. a fake in tests); by
    default the strategy for the current operating system is used.
    """
    global _handle, _call_create_interface, _call_bgetcallback
    global _call_freelastcallback, _platform

    if _handle is not None:
        return True

    if platform is not None:
        _platform = platform
    plat = _get_platform()

    install_path = plat.install_path()
    if not install_path:
        return False

    library_path = plat.library_path(install_path)
    if not library_path:
        return False

    try:
        module = plat.load_library(library_path)
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
