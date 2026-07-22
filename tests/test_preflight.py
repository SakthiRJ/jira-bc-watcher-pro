"""Preflight report structure and exit code (offline)."""
from __future__ import annotations

import types

from bcwatcher import preflight


class FakeTenant:
    id = "default"
    active = True

    def validate(self):
        return []


def _stub(monkeypatch, config_problems=None, llm_ok=True):
    monkeypatch.setattr(preflight.config, "validate", lambda: config_problems or [])
    monkeypatch.setattr(
        preflight.config,
        "llm_settings",
        lambda: types.SimpleNamespace(
            provider="groq",
            api_key="k" if llm_ok else "",
            model="m" if llm_ok else "",
        ),
    )
    monkeypatch.setattr(preflight.tenants, "load_tenants", lambda: [FakeTenant()])


def _status(results, name):
    return next(status for check, status, _ in results if check == name)


def test_collect_offline_all_pass(monkeypatch):
    _stub(monkeypatch)
    results = preflight.collect(check_net=False)
    assert _status(results, "config") == preflight.PASS
    assert _status(results, "llm") == preflight.PASS
    assert _status(results, "tenants") == preflight.PASS
    assert all(status != preflight.FAIL for _, status, _ in results)


def test_config_problem_is_fail(monkeypatch):
    _stub(monkeypatch, config_problems=["JIRA_EMAIL required"])
    results = preflight.collect(check_net=False)
    assert _status(results, "config") == preflight.FAIL


def test_llm_missing_is_fail(monkeypatch):
    _stub(monkeypatch, llm_ok=False)
    results = preflight.collect(check_net=False)
    assert _status(results, "llm") == preflight.FAIL


def test_main_returns_zero_when_ok(monkeypatch):
    _stub(monkeypatch)
    assert preflight.main(["--no-net"]) == 0


def test_main_returns_one_on_fail(monkeypatch):
    _stub(monkeypatch, config_problems=["bad"])
    assert preflight.main(["--no-net"]) == 1
