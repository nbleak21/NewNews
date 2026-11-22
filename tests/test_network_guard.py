"""Verify the autouse network guard in conftest.py actually blocks real sockets."""

from __future__ import annotations

import socket

import pytest


def test_real_network_is_blocked() -> None:
    with pytest.raises(RuntimeError, match="network access is blocked"):
        socket.create_connection(("example.com", 80), timeout=1)
