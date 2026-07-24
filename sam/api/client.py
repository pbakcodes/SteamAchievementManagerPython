"""The high-level :class:`Client` — mirrors ``SAM.API.Client`` in the C# port."""

from __future__ import annotations

import os
from typing import List, TypeVar

from . import steam
from .callbacks import Callback
from .errors import ClientInitializeException, ClientInitializeFailure
from .wrappers import (
    SteamApps001,
    SteamApps008,
    SteamClient018,
    SteamUser012,
    SteamUserStats013,
    SteamUtils005,
)

T = TypeVar("T", bound=Callback)


class Client:
    """Owns a Steam pipe / user pair and exposes the individual interfaces."""

    def __init__(self):
        self.steam_client: SteamClient018 | None = None
        self.steam_user: SteamUser012 | None = None
        self.steam_user_stats: SteamUserStats013 | None = None
        self.steam_utils: SteamUtils005 | None = None
        self.steam_apps001: SteamApps001 | None = None
        self.steam_apps008: SteamApps008 | None = None

        self._pipe: int = 0
        self._user: int = 0
        self._disposed = False
        self._callbacks: List[Callback] = []
        self._running_callbacks = False

    # -----------------------------------------------------------------
    def initialize(self, app_id: int) -> None:
        """Connect to Steam.

        ``app_id`` may be ``0`` (for the picker) or a specific Steam App ID
        (for the manager). The Steam SDK requires the ``SteamAppId``
        environment variable to be set before the client can be created.
        """
        install_path = steam.get_install_path()
        if not install_path:
            raise ClientInitializeException(
                ClientInitializeFailure.GetInstallPath,
                "failed to get Steam install path",
            )

        if app_id:
            os.environ["SteamAppId"] = str(app_id)

        if not steam.load():
            raise ClientInitializeException(
                ClientInitializeFailure.Load, "failed to load SteamClient"
            )

        client_addr = steam.create_interface("SteamClient018")
        if not client_addr:
            raise ClientInitializeException(
                ClientInitializeFailure.CreateSteamClient,
                "failed to create ISteamClient018",
            )

        self.steam_client = SteamClient018(client_addr)

        self._pipe = self.steam_client.create_steam_pipe()
        if not self._pipe:
            raise ClientInitializeException(
                ClientInitializeFailure.CreateSteamPipe, "failed to create pipe"
            )

        self._user = self.steam_client.connect_to_global_user(self._pipe)
        if not self._user:
            raise ClientInitializeException(
                ClientInitializeFailure.ConnectToGlobalUser,
                "failed to connect to global user",
            )

        self.steam_utils = self.steam_client.get_steam_utils005(self._pipe)
        if app_id > 0 and self.steam_utils.get_app_id() != app_id:
            raise ClientInitializeException(
                ClientInitializeFailure.AppIdMismatch, "appID mismatch"
            )

        self.steam_user = self.steam_client.get_steam_user012(self._user, self._pipe)
        self.steam_user_stats = self.steam_client.get_steam_user_stats013(
            self._user, self._pipe
        )
        self.steam_apps001 = self.steam_client.get_steam_apps001(
            self._user, self._pipe
        )
        self.steam_apps008 = self.steam_client.get_steam_apps008(
            self._user, self._pipe
        )

    # -----------------------------------------------------------------
    def create_and_register_callback(self, callback_cls: type[T]) -> T:
        callback = callback_cls()
        self._callbacks.append(callback)
        return callback

    def run_callbacks(self, server: bool) -> None:
        if self._running_callbacks:
            return
        self._running_callbacks = True
        try:
            while True:
                ok, message = steam.get_callback(self._pipe)
                if not ok:
                    break
                assert message is not None
                for callback in self._callbacks:
                    if callback.id == message.id and callback.is_server == server:
                        try:
                            callback.dispatch(int(message.param_pointer))
                        except Exception:
                            # A misbehaving handler must not stop the pump.
                            import traceback

                            traceback.print_exc()
                steam.free_last_callback(self._pipe)
        finally:
            self._running_callbacks = False

    # -----------------------------------------------------------------
    def dispose(self) -> None:
        if self._disposed:
            return
        if self.steam_client is not None and self._pipe:
            if self._user:
                try:
                    self.steam_client.release_user(self._pipe, self._user)
                except Exception:
                    pass
                self._user = 0
            try:
                self.steam_client.release_steam_pipe(self._pipe)
            except Exception:
                pass
            self._pipe = 0
        self._disposed = True

    def __enter__(self) -> "Client":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.dispose()

    def __del__(self):  # pragma: no cover
        try:
            self.dispose()
        except Exception:
            pass
