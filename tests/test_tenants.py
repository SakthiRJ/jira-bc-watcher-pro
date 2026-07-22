"""Tenant model + loader: default-from-config, file parsing, per-project grouping."""
from __future__ import annotations

import json

import bcwatcher.tenants as T
from bcwatcher.config import config


def test_default_tenant_from_config(monkeypatch):
    monkeypatch.setattr(config, "jira_base_url", "https://x.atlassian.net")
    monkeypatch.setattr(config, "jira_email", "a@b.com")
    monkeypatch.setattr(config, "jira_api_token", "tok")
    monkeypatch.setattr(config, "projects", ["CON", "T3"])
    monkeypatch.setattr(config, "priorities", ["Business Critical"])
    t = T.default_tenant()
    assert t.id == "default"
    assert t.priority == "Business Critical"
    assert t.projects == ["CON", "T3"]
    assert t.grouping_for("CON").rollup_subtasks_to_epic is True


def test_from_dict_resolves_env_secret_and_overrides(monkeypatch):
    monkeypatch.setenv("ACME_TOKEN", "secret123")
    data = {
        "id": "acme",
        "name": "Acme Corp",
        "jira": {
            "base_url": "https://acme.atlassian.net/",
            "email": "ops@acme.com",
            "api_token": "env:ACME_TOKEN",
        },
        "projects": ["ACME"],
        "priorities": ["Critical", "Business Critical"],
        "grouping": {"cross_project_links": False},
        "grouping_overrides": {"ACME": {"rollup_subtasks_to_epic": False}},
    }
    t = T.Tenant.from_dict(data)
    assert t.jira_api_token == "secret123"
    assert t.jira_base_url == "https://acme.atlassian.net"
    assert t.priorities == ["Critical", "Business Critical"]
    assert t.priority == "Critical"
    assert t.grouping.cross_project_links is False
    # Per-project override wins for ACME, tenant default applies elsewhere.
    assert t.grouping_for("ACME").rollup_subtasks_to_epic is False
    assert t.grouping_for("OTHER").cross_project_links is False


def test_validate_flags_missing_fields():
    t = T.Tenant.from_dict({"id": "x", "jira": {}, "projects": [], "priorities": []})
    problems = t.validate()
    assert any("base_url" in p for p in problems)
    assert any("project" in p for p in problems)
    assert any("api_token" in p for p in problems)


def test_public_dict_redacts_token():
    t = T.Tenant.from_dict({
        "id": "x",
        "jira": {"base_url": "b", "email": "e", "api_token": "SUPERSECRETVALUE"},
        "projects": ["P"],
        "priorities": ["C"],
    })
    pub = t.public_dict()
    assert pub["jira_api_token"] == "***"
    assert "SUPERSECRETVALUE" not in json.dumps(pub)


def test_load_tenants_default_when_file_absent(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "tenants_file", str(tmp_path / "nope.json"))
    loaded = T.load_tenants()
    assert len(loaded) == 1 and loaded[0].id == "default"


def test_load_tenants_from_file(monkeypatch, tmp_path):
    f = tmp_path / "tenants.json"
    f.write_text(
        json.dumps({"tenants": [{
            "id": "acme",
            "jira": {"base_url": "https://a", "email": "e", "api_token": "tok"},
            "projects": ["ACME"],
            "priorities": ["Critical"],
            "active": True,
        }]}),
        encoding="utf-8",
    )
    monkeypatch.setattr(config, "tenants_file", str(f))
    assert [t.id for t in T.load_tenants()] == ["acme"]
    assert [t.id for t in T.active_tenants()] == ["acme"]
    assert T.get_tenant("acme").projects == ["ACME"]
    assert T.get_tenant("ghost") is None
