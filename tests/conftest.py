"""The test suite never needs credentials or live provider/network access."""

import os
import socket

import pytest

# Set before test collection imports app.main. A user's model-enabled shell must not
# turn an ordinary `pytest` command into a billable evaluation.
os.environ["REASONER_MODE"] = "extractive"
os.environ["PIPELINE_MODE"] = "baseline"


@pytest.fixture(autouse=True)
def block_outbound_network(monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError("Network disabled in tests; use in-process or mocked transports.")

    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket.socket, "connect_ex", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)
