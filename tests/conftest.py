from __future__ import annotations

import asyncio
import inspect
from collections.abc import Callable
from typing import Any

import pytest


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "asyncio: run async test functions with asyncio.run")


def pytest_pyfunc_call(pyfuncitem: pytest.Function) -> bool | None:
    test_fn: Callable[..., Any] = pyfuncitem.obj
    if not inspect.iscoroutinefunction(test_fn):
        return None
    fixture_args = {
        name: pyfuncitem.funcargs[name]
        for name in pyfuncitem._fixtureinfo.argnames
        if name in pyfuncitem.funcargs
    }
    asyncio.run(test_fn(**fixture_args))
    return True
