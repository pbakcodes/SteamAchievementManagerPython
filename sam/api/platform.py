"""Platform strategies for locating and loading the Steam client library.

The exported C entry points and the vtable ABI of the Steam client are the same
everywhere, but *finding* the library and *opening* it differ per operating
system. Each :class:`SteamPlatform` encapsulates those differences so the rest
of :mod:`sam.api` never has to branch on ``sys.platform``; the single decision
point is :func:`current_platform`.
"""

from __future__ import annotations

import ctypes
import os
import struct
import sys
from typing import Protocol

_IS_64BIT = struct.calcsize("P") == 8

if sys.platform == "win32":
    import winreg


class SteamPlatform(Protocol):
    """Strategy describing how to locate and load the Steam client library."""

    #: File name of the client library on this platform.
    dll_name: str

    def install_path(self) -> str | None:
        """Return the Steam client install directory, or ``None``."""
        ...

    def library_path(self, install_path: str) -> str | None:
        """Return the absolute path to the client library, or ``None``."""
        ...

    def load_library(self, library_path: str) -> "ctypes.CDLL":
        """Open the client library and return the loaded handle."""
        ...


# ---------------------------------------------------------------------------
# Windows
# ---------------------------------------------------------------------------
class _WindowsPlatform:
    dll_name = "steamclient64.dll" if _IS_64BIT else "steamclient.dll"

    def install_path(self) -> str | None:
        for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            for subkey in (
                r"Software\Valve\Steam",
                r"Software\WOW6432Node\Valve\Steam",
            ):
                try:
                    with winreg.OpenKey(hive, subkey) as key:
                        value, _ = winreg.QueryValueEx(key, "InstallPath")
                        if value:
                            return value
                except OSError:
                    continue
        return None

    def library_path(self, install_path: str) -> str | None:
        path = os.path.join(install_path, self.dll_name)
        if os.path.exists(path):
            return path
        # Some installations only ship ``steamclient.dll`` even on 64-bit.
        alt = os.path.join(install_path, "steamclient.dll")
        if _IS_64BIT and os.path.exists(alt):
            return alt
        return None

    def load_library(self, library_path: str) -> "ctypes.CDLL":
        self._add_dll_search_dirs(os.path.dirname(library_path))
        return ctypes.CDLL(library_path)

    @staticmethod
    def _add_dll_search_dirs(install_path: str) -> None:
        for candidate in (install_path, os.path.join(install_path, "bin")):
            if os.path.isdir(candidate):
                try:
                    os.add_dll_directory(candidate)
                except (OSError, AttributeError):
                    pass


# ---------------------------------------------------------------------------
# POSIX (Linux / macOS share everything but the candidate directories)
# ---------------------------------------------------------------------------
class _PosixPlatform:
    dll_name = "steamclient.so"

    #: Bitness-specific subdirectories of the install path to search.
    _subdirs: tuple[str, ...] = ()
    _sdk_dir = "sdk64" if _IS_64BIT else "sdk32"

    def _candidate_roots(self) -> list[str]:
        roots: list[str] = []
        for var in ("STEAM_ROOT", "STEAM_BASE_FOLDER"):
            value = os.environ.get(var)
            if value:
                roots.append(value)
        return roots

    def install_path(self) -> str | None:
        for path in self._candidate_roots():
            if path and os.path.isdir(path):
                return os.path.realpath(path)
        return None

    def library_path(self, install_path: str) -> str | None:
        home = os.path.expanduser("~")
        candidates = [
            os.path.join(install_path, sub, self.dll_name) for sub in self._subdirs
        ]
        candidates.append(os.path.join(home, ".steam", self._sdk_dir, self.dll_name))
        candidates.append(os.path.join(install_path, self.dll_name))
        for path in candidates:
            if os.path.exists(path):
                return path
        return None

    def load_library(self, library_path: str) -> "ctypes.CDLL":
        # The picker connects as the Steam client itself (app id 0); ensure the
        # SDK always has an app id to read, even if the caller didn't set one.
        os.environ.setdefault("SteamAppId", "0")
        # RTLD_GLOBAL so steamclient's lazily-loaded plugins can resolve symbols
        # exported by the library.
        return ctypes.CDLL(library_path, mode=ctypes.RTLD_GLOBAL)


class _LinuxPlatform(_PosixPlatform):
    _subdirs = ("linux64", "ubuntu12_64") if _IS_64BIT else ("linux32", "ubuntu12_32")

    def _candidate_roots(self) -> list[str]:
        home = os.path.expanduser("~")
        return super()._candidate_roots() + [
            os.path.join(home, ".steam", "steam"),
            os.path.join(home, ".steam", "root"),
            os.path.join(home, ".local", "share", "Steam"),
            # Flatpak
            os.path.join(
                home, ".var", "app", "com.valvesoftware.Steam", "data", "Steam"
            ),
        ]


class _MacPlatform(_PosixPlatform):
    _subdirs = ("osx", "osx64", "osx32")

    def _candidate_roots(self) -> list[str]:
        return super()._candidate_roots() + [
            os.path.expanduser("~/Library/Application Support/Steam"),
        ]


def current_platform() -> SteamPlatform:
    """Return the :class:`SteamPlatform` strategy for the running OS."""
    if sys.platform == "win32":
        return _WindowsPlatform()
    if sys.platform == "darwin":
        return _MacPlatform()
    return _LinuxPlatform()
