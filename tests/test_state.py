"""Unit tests for the persistent per-ticket State store."""
from __future__ import annotations

from bcwatcher.state import State


def test_fresh_state_is_uninitialized(tmp_path):
    st = State(str(tmp_path / "state.json"))
    assert st.initialized is False
    assert st.known_keys() == set()


def test_mark_initialized_persists(tmp_path):
    path = str(tmp_path / "state.json")
    st = State(path)
    st.mark_initialized()
    st.save()
    assert State(path).initialized is True


def test_last_comment_roundtrip(tmp_path):
    path = str(tmp_path / "state.json")
    st = State(path)
    st.set_last_comment("CON-1", "c99", "2026-07-22T10:00:00.000+0000")
    st.save()

    reloaded = State(path)
    assert reloaded.knows("CON-1")
    assert reloaded.last_comment_id("CON-1") == "c99"
    assert reloaded.last_comment_time("CON-1") == "2026-07-22T10:00:00.000+0000"
    assert reloaded.known_keys() == {"CON-1"}


def test_status_category_roundtrip(tmp_path):
    path = str(tmp_path / "state.json")
    st = State(path)
    st.set_status_category("CON-2", "done")
    st.save()
    assert State(path).status_category("CON-2") == "done"


def test_rca_flags(tmp_path):
    path = str(tmp_path / "state.json")
    st = State(path)
    assert st.rca_sent("CON-3") is False
    st.mark_rca_sent("CON-3")
    st.save()
    assert State(path).rca_sent("CON-3") is True
    # explicit reset
    st2 = State(path)
    st2.set_rca_sent("CON-3", False)
    st2.save()
    assert State(path).rca_sent("CON-3") is False


def test_corrupt_state_file_recovers(tmp_path):
    path = tmp_path / "state.json"
    path.write_text("{ not valid json", encoding="utf-8")
    st = State(str(path))
    # Should fall back to empty defaults rather than raising.
    assert st.initialized is False
    assert st.known_keys() == set()
