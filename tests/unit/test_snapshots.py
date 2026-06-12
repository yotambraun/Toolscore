"""Tests for the snapshot store and snapshot_check state machine."""

from __future__ import annotations

import json

import pytest

from toolscore.core import ToolScoreAssertionError
from toolscore.snapshots import Snapshot, SnapshotStore, snapshot_check

# ---------------------------------------------------------------------------
# Snapshot dataclass
# ---------------------------------------------------------------------------


def test_snapshot_fills_timestamps_and_version() -> None:
    snap = Snapshot(name="t", calls=[{"tool": "search", "args": {}}])
    assert snap.created_at
    assert snap.updated_at == snap.created_at
    assert snap.toolscore_version  # filled from package __version__
    assert snap.schema_version == 1
    assert snap.approved is False
    assert snap.source == "pytest"


def test_snapshot_respects_explicit_fields() -> None:
    snap = Snapshot(
        name="t",
        calls=[],
        approved=True,
        source="record",
        created_at="2020-01-01T00:00:00+00:00",
        updated_at="2020-01-02T00:00:00+00:00",
        toolscore_version="9.9.9",
    )
    assert snap.created_at == "2020-01-01T00:00:00+00:00"
    assert snap.updated_at == "2020-01-02T00:00:00+00:00"
    assert snap.toolscore_version == "9.9.9"
    assert snap.source == "record"


def test_snapshot_to_from_dict_round_trip() -> None:
    snap = Snapshot(
        name="tests/test_agent.py::test_booking",
        calls=[{"tool": "search_flights", "args": {"destination": "NYC"}}],
        approved=True,
        source="trace",
    )
    data = snap.to_dict()
    # On-disk shape matches the spec.
    assert set(data) == {
        "schema_version",
        "name",
        "created_at",
        "updated_at",
        "toolscore_version",
        "approved",
        "source",
        "calls",
    }
    restored = Snapshot.from_dict(data)
    assert restored == snap


def test_snapshot_to_dict_json_serializable() -> None:
    snap = Snapshot(name="t", calls=[{"tool": "x", "args": {"a": 1}}])
    # Should not raise.
    json.dumps(snap.to_dict())


# ---------------------------------------------------------------------------
# SnapshotStore
# ---------------------------------------------------------------------------


def test_store_no_mkdir_on_construction(tmp_path) -> None:
    root = tmp_path / "snaps"
    SnapshotStore(root)
    assert not root.exists()


def test_store_no_mkdir_on_list_or_load(tmp_path) -> None:
    root = tmp_path / "snaps"
    store = SnapshotStore(root)
    assert store.list() == []
    assert store.load("missing") is None
    assert store.exists("missing") is False
    assert not root.exists()


def test_store_mkdir_lazy_on_save(tmp_path) -> None:
    root = tmp_path / "a" / "b" / "snaps"
    store = SnapshotStore(root)
    assert not root.exists()
    store.save(Snapshot(name="t", calls=[]))
    assert root.exists()


def test_store_save_load_round_trip(tmp_path) -> None:
    store = SnapshotStore(tmp_path)
    snap = Snapshot(
        name="tests/test_agent.py::test_booking[NYC]",
        calls=[{"tool": "search_flights", "args": {"destination": "NYC"}}],
        approved=True,
    )
    store.save(snap)
    loaded = store.load(snap.name)
    assert loaded is not None
    assert loaded.name == snap.name
    assert loaded.calls == snap.calls
    assert loaded.approved is True


@pytest.mark.parametrize(
    "name",
    [
        "tests/test_agent.py::test_booking",
        "tests/test_agent.py::test_booking[param-1]",
        "a/b/c/deeply/nested",
        'weird < > | * ? " chars',
        "../../evil",
        "..\\..\\evil",
    ],
)
def test_store_path_stays_inside_root(tmp_path, name) -> None:
    store = SnapshotStore(tmp_path)
    path = store.path_for(name)
    resolved = path.resolve()
    # No path traversal escapes the root.
    assert resolved.parent == tmp_path.resolve()
    assert path.suffix == ".json"


def test_store_path_unique_per_name(tmp_path) -> None:
    store = SnapshotStore(tmp_path)
    # Two names that sanitize identically must still map to distinct files
    # thanks to the sha1 suffix.
    p1 = store.path_for("a/b")
    p2 = store.path_for("a\\b")
    assert p1 != p2


def test_store_save_non_serializable_arg_raises_valueerror(tmp_path) -> None:
    # A non-JSON-serializable arg value (datetime/Decimal/numpy scalar from
    # auto_extract) must raise a helpful ValueError and leave NO file behind.
    from datetime import datetime, timezone

    store = SnapshotStore(tmp_path)
    bad = Snapshot(
        name="bad",
        calls=[{"tool": "t", "args": {"when": datetime(2020, 1, 1, tzinfo=timezone.utc)}}],
    )
    with pytest.raises(ValueError, match="JSON-serializable") as exc:
        store.save(bad)
    assert "bad" in str(exc.value)
    # No partial/temp file is left on disk.
    assert list(tmp_path.glob("*")) == []


def test_store_failed_resave_leaves_existing_file_unchanged(tmp_path) -> None:
    # A failed atomic re-save (non-serializable arg) must not corrupt or replace
    # the previously approved baseline on disk.
    from datetime import datetime, timezone

    store = SnapshotStore(tmp_path)
    good = Snapshot(name="g", calls=[{"tool": "t", "args": {"q": "y"}}], approved=True)
    path = store.save(good)
    before = path.read_text(encoding="utf-8")
    bad = Snapshot(
        name="g",
        calls=[{"tool": "t", "args": {"d": datetime(2020, 1, 1, tzinfo=timezone.utc)}}],
    )
    with pytest.raises(ValueError):
        store.save(bad)
    assert path.read_text(encoding="utf-8") == before


def test_store_traversal_name_round_trips(tmp_path) -> None:
    store = SnapshotStore(tmp_path)
    snap = Snapshot(name="../../evil", calls=[{"tool": "x", "args": {}}])
    store.save(snap)
    loaded = store.load("../../evil")
    assert loaded is not None
    assert loaded.name == "../../evil"
    # File physically lives in the root, not outside it.
    files = list(tmp_path.glob("*.json"))
    assert len(files) == 1


def test_store_load_corrupt_json_raises_valueerror(tmp_path) -> None:
    store = SnapshotStore(tmp_path)
    path = store.path_for("broken")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{ not valid json", encoding="utf-8")
    with pytest.raises(ValueError) as exc:
        store.load("broken")
    assert str(path) in str(exc.value)


def test_store_load_wrong_shape_raises_valueerror(tmp_path) -> None:
    store = SnapshotStore(tmp_path)
    path = store.path_for("wrong")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
    with pytest.raises(ValueError) as exc:
        store.load("wrong")
    assert str(path) in str(exc.value)


def test_store_approve_flips_and_bumps_updated_at(tmp_path) -> None:
    store = SnapshotStore(tmp_path)
    snap = Snapshot(
        name="t",
        calls=[],
        created_at="2020-01-01T00:00:00+00:00",
        updated_at="2020-01-01T00:00:00+00:00",
    )
    store.save(snap)
    approved = store.approve("t")
    assert approved.approved is True
    # updated_at is refreshed by save (no longer the frozen 2020 value).
    assert approved.updated_at != "2020-01-01T00:00:00+00:00"
    # created_at is preserved.
    reloaded = store.load("t")
    assert reloaded is not None
    assert reloaded.approved is True


def test_store_approve_missing_raises_keyerror(tmp_path) -> None:
    store = SnapshotStore(tmp_path)
    with pytest.raises(KeyError):
        store.approve("nope")


def test_store_delete(tmp_path) -> None:
    store = SnapshotStore(tmp_path)
    store.save(Snapshot(name="t", calls=[]))
    assert store.exists("t")
    store.delete("t")
    assert not store.exists("t")
    # Deleting again is a no-op.
    store.delete("t")


def test_store_list_sorted_and_pending(tmp_path) -> None:
    store = SnapshotStore(tmp_path)
    store.save(Snapshot(name="charlie", calls=[], approved=True))
    store.save(Snapshot(name="alpha", calls=[], approved=False))
    store.save(Snapshot(name="bravo", calls=[], approved=True))

    names = [s.name for s in store.list()]
    assert names == ["alpha", "bravo", "charlie"]

    pending = [s.name for s in store.pending()]
    assert pending == ["alpha"]


def test_store_list_skips_corrupt_files(tmp_path) -> None:
    store = SnapshotStore(tmp_path)
    store.save(Snapshot(name="good", calls=[]))
    bad = tmp_path / "garbage.json"
    bad.write_text("nope", encoding="utf-8")
    listed = [s.name for s in store.list()]
    assert listed == ["good"]


# ---------------------------------------------------------------------------
# snapshot_check state machine
# ---------------------------------------------------------------------------

CALLS = [{"tool": "search_flights", "args": {"destination": "NYC"}}]


@pytest.fixture
def store(tmp_path) -> SnapshotStore:
    return SnapshotStore(tmp_path / "snaps")


def test_check_create_locally_warns_and_writes_pending(monkeypatch, store) -> None:
    monkeypatch.delenv("CI", raising=False)
    with pytest.warns(UserWarning, match="approve"):
        result = snapshot_check("test_x", CALLS, store=store)
    assert result is None
    snap = store.load("test_x")
    assert snap is not None
    assert snap.approved is False
    assert snap.calls == CALLS


def test_check_create_in_ci_raises_and_does_not_write(monkeypatch, store) -> None:
    monkeypatch.setenv("CI", "true")
    with pytest.raises(ToolScoreAssertionError, match="does not exist"):
        snapshot_check("test_x", CALLS, store=store)
    # CI must NOT mint snapshots.
    assert store.load("test_x") is None


def test_check_update_overwrites_and_approves(monkeypatch, store) -> None:
    monkeypatch.delenv("CI", raising=False)
    # Seed an existing pending snapshot with different calls.
    store.save(Snapshot(name="test_x", calls=[{"tool": "old", "args": {}}]))
    with pytest.warns(UserWarning, match="updated"):
        result = snapshot_check("test_x", CALLS, store=store, update=True)
    assert result is None
    snap = store.load("test_x")
    assert snap is not None
    assert snap.approved is True
    assert snap.calls == CALLS


def test_check_update_creates_when_missing(monkeypatch, store) -> None:
    monkeypatch.delenv("CI", raising=False)
    with pytest.warns(UserWarning, match="updated"):
        snapshot_check("fresh", CALLS, store=store, update=True)
    snap = store.load("fresh")
    assert snap is not None
    assert snap.approved is True
    assert snap.calls == CALLS


def test_check_pending_local_warns_and_returns_none(monkeypatch, store) -> None:
    monkeypatch.delenv("CI", raising=False)
    store.save(Snapshot(name="test_x", calls=CALLS, approved=False))
    with pytest.warns(UserWarning, match="pending approval"):
        result = snapshot_check("test_x", CALLS, store=store)
    assert result is None


def test_check_pending_in_ci_raises(monkeypatch, store) -> None:
    monkeypatch.setenv("CI", "1")
    store.save(Snapshot(name="test_x", calls=CALLS, approved=False))
    with pytest.raises(ToolScoreAssertionError, match="pending approval"):
        snapshot_check("test_x", CALLS, store=store)


def test_check_approved_match_returns_score_1(monkeypatch, store) -> None:
    monkeypatch.delenv("CI", raising=False)
    store.save(Snapshot(name="test_x", calls=CALLS, approved=True))
    result = snapshot_check("test_x", CALLS, store=store)
    assert result is not None
    assert result.score == pytest.approx(1.0)


def test_check_approved_match_works_in_ci(monkeypatch, store) -> None:
    monkeypatch.setenv("CI", "true")
    store.save(Snapshot(name="test_x", calls=CALLS, approved=True))
    result = snapshot_check("test_x", CALLS, store=store)
    assert result is not None
    assert result.score == pytest.approx(1.0)


def test_check_approved_mismatch_raises(monkeypatch, store) -> None:
    monkeypatch.delenv("CI", raising=False)
    store.save(Snapshot(name="test_x", calls=CALLS, approved=True))
    drifted = [{"tool": "book_hotel", "args": {"city": "LA"}}]
    with pytest.raises(ToolScoreAssertionError):
        snapshot_check("test_x", drifted, store=store, min_score=1.0)


def test_check_approved_raw_openai_response_goes_through_auto_extract(monkeypatch, store) -> None:
    monkeypatch.delenv("CI", raising=False)
    store.save(Snapshot(name="test_x", calls=CALLS, approved=True))
    openai_response = {
        "choices": [
            {
                "message": {
                    "tool_calls": [
                        {
                            "function": {
                                "name": "search_flights",
                                "arguments": '{"destination": "NYC"}',
                            }
                        }
                    ]
                }
            }
        ]
    }
    result = snapshot_check("test_x", openai_response, store=store)
    assert result is not None
    assert result.score == pytest.approx(1.0)


def test_check_create_from_raw_openai_response(monkeypatch, store) -> None:
    monkeypatch.delenv("CI", raising=False)
    openai_response = {
        "choices": [
            {
                "message": {
                    "tool_calls": [
                        {
                            "function": {
                                "name": "search_flights",
                                "arguments": '{"destination": "NYC"}',
                            }
                        }
                    ]
                }
            }
        ]
    }
    with pytest.warns(UserWarning):
        snapshot_check("test_x", openai_response, store=store)
    snap = store.load("test_x")
    assert snap is not None
    assert snap.calls == CALLS


def test_check_weights_pass_through(monkeypatch, store) -> None:
    monkeypatch.delenv("CI", raising=False)
    store.save(Snapshot(name="test_x", calls=CALLS, approved=True))
    # A perfect match still scores 1.0 with custom weights; the call must not error.
    result = snapshot_check(
        "test_x",
        CALLS,
        store=store,
        weights={"selection_accuracy": 1.0},
    )
    assert result is not None
    assert result.score == pytest.approx(1.0)


def test_check_strict_pass_through(monkeypatch, store) -> None:
    monkeypatch.delenv("CI", raising=False)
    store.save(
        Snapshot(name="test_x", calls=[{"tool": "f", "args": {"n": 1}}], approved=True),
    )
    # In lenient mode 1 == 1.0; in strict mode they would differ. Use matching
    # types so a perfect score is expected and confirm strict is accepted.
    result = snapshot_check(
        "test_x",
        [{"tool": "f", "args": {"n": 1}}],
        store=store,
        strict=True,
    )
    assert result is not None
    assert result.score == pytest.approx(1.0)


def test_check_default_store_used_when_none(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.chdir(tmp_path)
    with pytest.warns(UserWarning):
        snapshot_check("default_store_test", CALLS)
    # Default root is .toolscore/snapshots under cwd.
    created = list((tmp_path / ".toolscore" / "snapshots").glob("*.json"))
    assert len(created) == 1


# ---------------------------------------------------------------------------
# load_gold_standard accepts a snapshot file
# ---------------------------------------------------------------------------


def test_load_gold_standard_accepts_snapshot_file(tmp_path) -> None:
    from toolscore.core import load_gold_standard

    store = SnapshotStore(tmp_path)
    snap = Snapshot(
        name="t",
        calls=[
            {"tool": "search_flights", "args": {"destination": "NYC"}},
            {"tool": "book_hotel", "args": {"city": "NYC"}},
        ],
        approved=True,
    )
    path = store.save(snap)

    gold = load_gold_standard(path)
    assert [c.tool for c in gold] == ["search_flights", "book_hotel"]
    assert gold[0].args == {"destination": "NYC"}
