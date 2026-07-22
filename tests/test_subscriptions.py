"""Subscription store, self-subscribe guardrails, and routing resolution."""
from __future__ import annotations

import pytest

import bcwatcher.subscriptions as subs
from bcwatcher.config import config


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(subs, "SUBS_FILE", str(tmp_path / "subscriptions.json"))
    monkeypatch.setattr(config, "projects", ["CON", "T3", "CL"])
    return subs


def _payload(**over):
    p = {
        "email": "alice@company.com",
        "name": "Alice",
        "audience": "support",
        "events": ["realtime"],
        "projects": ["CON"],
    }
    p.update(over)
    return p


def test_add_and_load(store):
    rec = store.add(_payload())
    assert rec["email"] == "alice@company.com"
    assert rec["created_at"] and rec["updated_at"]
    assert [r["email"] for r in store.load_all()] == ["alice@company.com"]


def test_email_and_audience_validation(store):
    with pytest.raises(ValueError):
        store.add(_payload(email="not-an-email"))
    with pytest.raises(ValueError):
        store.add(_payload(audience="ceo"))


def test_events_required(store):
    with pytest.raises(ValueError):
        store.add(_payload(events=[]))
    with pytest.raises(ValueError):
        store.add(_payload(events=["nonsense"]))


def test_unknown_projects_are_dropped(store):
    rec = store.add(_payload(projects=["CON", "ZZZ", "t3"]))
    assert rec["projects"] == ["CON", "T3"]


def test_channel_defaults_and_validates(store):
    assert store.add(_payload())["channel"] == "email"
    with pytest.raises(ValueError):
        store.add(_payload(channel="teams"))


def test_upsert_preserves_created_at(store):
    first = store.add(_payload())
    again = store.add(_payload(audience="manager"))
    assert again["created_at"] == first["created_at"]
    assert again["audience"] == "manager"
    assert len(store.load_all()) == 1


def test_remove(store):
    store.add(_payload())
    assert store.remove("ALICE@company.com") is True
    assert store.load_all() == []
    assert store.remove("ghost@company.com") is False


def test_resolve_filters_by_event(store):
    store.add(_payload(email="a@company.com", events=["realtime"]))
    store.add(_payload(email="b@company.com", events=["digest"]))
    assert {r["email"] for r in store.resolve("realtime")} == {"a@company.com"}
    assert {r["email"] for r in store.resolve("digest")} == {"b@company.com"}


def test_resolve_scopes_by_project(store):
    store.add(_payload(email="con@company.com", projects=["CON"]))
    store.add(_payload(email="all@company.com", projects=[]))
    case = {"member_keys": ["T3-9"], "priority": "Business Critical"}
    emails = {r["email"] for r in store.resolve("realtime", case)}
    assert emails == {"all@company.com"}


def test_resolve_scopes_by_priority(store):
    store.add(_payload(email="p1@company.com", priorities=["Business Critical"]))
    low = {"member_keys": ["CON-1"], "priority": "Low"}
    high = {"member_keys": ["CON-1"], "priority": "Business Critical"}
    assert store.resolve("realtime", low) == []
    assert {r["email"] for r in store.resolve("realtime", high)} == {"p1@company.com"}


def test_audience_map_groups(store):
    store.add(_payload(email="s@company.com", audience="support"))
    store.add(_payload(email="d@company.com", audience="dev"))
    amap = store.audience_map("realtime", {"member_keys": ["CON-1"], "priority": "X"})
    assert set(amap.keys()) == {"support", "dev"}
    assert amap["support"][0]["email"] == "s@company.com"


def test_inactive_excluded(store):
    store.add(_payload(active=False))
    assert store.resolve("realtime") == []
