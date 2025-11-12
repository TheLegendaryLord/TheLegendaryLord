"""Pytest configuration for tests."""

from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _install_telebot_stub() -> None:
    """Install a lightweight telebot stub for tests."""

    if "telebot" in sys.modules:
        return
    telebot_module = ModuleType("telebot")
    telebot_module.TeleBot = SimpleNamespace  # type: ignore[attr-defined]
    types_module = ModuleType("telebot.types")
    types_module.Message = SimpleNamespace  # type: ignore[attr-defined]
    sys.modules["telebot"] = telebot_module
    sys.modules["telebot.types"] = types_module


def _install_requests_stub() -> None:
    """Install a lightweight requests stub for tests."""

    if "requests" in sys.modules:
        return
    requests_module = ModuleType("requests")

    class _Session:
        def post(self, *args, **kwargs):  # pragma: no cover - replaced in tests
            raise NotImplementedError

    requests_module.Session = _Session  # type: ignore[attr-defined]
    sys.modules["requests"] = requests_module


_install_requests_stub()


_install_telebot_stub()
