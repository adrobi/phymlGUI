"""TEMPORARY pytest plugin: report test phases that lower the refcount of True/False
(an over-decref in a C extension; fatal at exit on Python < 3.12)."""
import sys

import pytest


def _counts():
    return sys.getrefcount(True), sys.getrefcount(False)


def _probe(item, phase):
    t0, f0 = _counts()
    yield
    t1, f1 = _counts()
    if t1 < t0 or f1 < f0:
        print(f'\nREFPROBE {phase:8} dTrue={t1 - t0:+5} dFalse={f1 - f0:+5} {item.nodeid}', flush=True)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_setup(item):
    yield from _probe(item, 'setup')


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_call(item):
    yield from _probe(item, 'call')


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_teardown(item):
    yield from _probe(item, 'teardown')
