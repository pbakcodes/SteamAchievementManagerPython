"""Errors raised by the Steam client bindings."""

from __future__ import annotations

from enum import IntEnum


class ClientInitializeFailure(IntEnum):
    Unknown = 0
    GetInstallPath = 1
    Load = 2
    CreateSteamClient = 3
    CreateSteamPipe = 4
    ConnectToGlobalUser = 5
    AppIdMismatch = 6


class ClientInitializeException(Exception):
    """Raised when the Steam client cannot be initialised."""

    def __init__(self, failure: ClientInitializeFailure, message: str = ""):
        super().__init__(message)
        self.failure = failure
