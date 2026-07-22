"""RCA queue persistence + state machine."""
from __future__ import annotations

import pytest

import bcwatcher.rca_store as rs


@pytest.fixture
def store_file(tmp_path, monkeypatch):
    monkeypatch.setattr(rs, "RCA_FILE", str(tmp_path / "rca_queue.json"))
    return rs


def _rec(rca_id="CON-1"):
    return {
        "id": rca_id,
        "primary_key": rca_id,
        "display_keys": [rca_id],
        "summary": "Outage",
        "subject": f"[RCA] {rca_id}",
        "body_html": "<h4>Root Cause</h4><p>x</p>",
    }


def test_upsert_defaults_and_get(store_file):
    rec = store_file.upsert(_rec())
    assert rec["status"] == store_file.PENDING
    assert rec["created_at"] and rec["updated_at"]
    assert store_file.get("CON-1")["subject"] == "[RCA] CON-1"
    assert [r["id"] for r in store_file.pending()] == ["CON-1"]


def test_upsert_same_id_updates_in_place(store_file):
    first = store_file.upsert(_rec())
    store_file.upsert({**_rec(), "subject": "[RCA] CON-1 updated"})
    all_records = store_file.load_all()
    assert len(all_records) == 1
    assert all_records[0]["subject"] == "[RCA] CON-1 updated"
    assert all_records[0]["created_at"] == first["created_at"]


def test_set_status_moves_out_of_pending(store_file):
    store_file.upsert(_rec())
    store_file.set_status("CON-1", store_file.SENT, approved_by="alice")
    assert store_file.pending() == []
    got = store_file.get("CON-1")
    assert got["status"] == store_file.SENT and got["approved_by"] == "alice"


def test_sent_record_not_resurrected_by_rescan(store_file):
    store_file.upsert(_rec())
    store_file.set_status("CON-1", store_file.SENT)
    store_file.upsert({**_rec(), "status": store_file.PENDING})
    assert store_file.get("CON-1")["status"] == store_file.SENT


def test_set_status_missing_raises(store_file):
    with pytest.raises(KeyError):
        store_file.set_status("nope", store_file.SENT)


def test_corrupt_file_recovers(store_file, tmp_path):
    with open(rs.RCA_FILE, "w", encoding="utf-8") as fh:
        fh.write("{ not json")
    assert store_file.load_all() == []
