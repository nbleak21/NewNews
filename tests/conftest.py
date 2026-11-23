# Copyright (c) 2026 Nick L
# SPDX-License-Identifier: MIT
"""Shared test setup.

Hard-blocks real network access so AGENTS.md rule 8 ("tests never touch the
network") cannot be violated by accident -- e.g. a build path that falls back
to a bare ``httpx.Client()`` instead of an injected mock transport. All HTTP in
the suite goes through ``httpx.MockTransport`` / ``pytest-httpx``, which never
open a real socket, so this guard is invisible to correct tests and only fires
on an unmocked outbound connection.
"""

from __future__ import annotations

import socket

import pytest


@pytest.fixture(autouse=True)
def _no_real_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def _blocked(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError(
            "network access is blocked in tests (AGENTS.md rule 8); "
            "mock the transport instead of opening a real connection"
        )

    monkeypatch.setattr(socket.socket, "connect", _blocked)
    monkeypatch.setattr(socket.socket, "connect_ex", _blocked)
