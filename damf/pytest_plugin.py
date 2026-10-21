"""Pytest plugin and fixtures for DAMF hardware-in-the-loop testing."""

from __future__ import annotations

from typing import Any, Iterator

from damf.device import Device
from damf.lab import Lab


def pytest_addoption(parser: Any) -> None:
    """Register DAMF command-line options with pytest."""
    group = parser.getgroup("damf", "DAMF Hardware Lab Automation")
    group.addoption(
        "--damf-db",
        action="store",
        default=":memory:",
        help="Path to the DAMF SQLite resource pool database.",
    )
    group.addoption(
        "--damf-config",
        action="store",
        default=None,
        help="Path to a DAMF YAML/JSON lab configuration file.",
    )
    group.addoption(
        "--damf-board-type",
        action="store",
        default=None,
        help="Default board_type to acquire for the `damf_device` fixture.",
    )


try:
    import pytest

    @pytest.fixture(scope="session")
    def damf_lab(request: Any) -> Lab:
        """Session-scoped DAMF Lab fixture."""
        cfg_path = request.config.getoption("--damf-config")
        db_path = request.config.getoption("--damf-db")
        if cfg_path:
            return Lab.from_config(cfg_path)
        return Lab(db_path=db_path, seed_demo=(db_path == ":memory:"))

    @pytest.fixture(scope="function")
    def damf_device(damf_lab: Lab, request: Any) -> Iterator[Device]:
        """Function-scoped fixture that acquires a board from `damf_lab` and releases it after the test."""
        board_type = request.config.getoption("--damf-board-type")
        marker = request.node.get_closest_marker("damf_device")
        tags = None
        name = None
        if marker is not None:
            board_type = marker.kwargs.get("board_type", board_type)
            tags = marker.kwargs.get("tags")
            name = marker.kwargs.get("name")
        with damf_lab.acquire(name=name, board_type=board_type, tags=tags, owner=request.node.name) as dev:
            yield dev

except ImportError:
    # Pytest is optional at runtime; helper factory remains usable in unittest or custom runners.
    pass
