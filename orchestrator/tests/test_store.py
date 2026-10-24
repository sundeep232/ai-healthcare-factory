"""FileDemoStore tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from orchestrator.schemas import Demo, DemoStatus
from orchestrator.storage import DemoNotFoundError, FileDemoStore, InvalidTransitionError


@pytest.fixture
def store(tmp_path: Path) -> FileDemoStore:
    return FileDemoStore(tmp_path / "demos")


def test_roundtrip(store: FileDemoStore) -> None:
    demo = store.create(Demo(intent="a claims dashboard demo"))
    loaded = store.get(demo.demo_id)
    assert loaded.intent == "a claims dashboard demo"
    assert loaded.status == DemoStatus.PLANNED


def test_list_newest_first(store: FileDemoStore) -> None:
    now = datetime.now(timezone.utc)
    first = store.create(Demo(intent="first demo intent", created_at=now - timedelta(minutes=1)))
    second = store.create(Demo(intent="second demo intent", created_at=now))
    assert [d.demo_id for d in store.list()] == [second.demo_id, first.demo_id]


def test_unknown_and_malicious_ids(store: FileDemoStore) -> None:
    for bad in ("00000000-0000-0000-0000-000000000000", "../secrets", "..\\x", ""):
        with pytest.raises(DemoNotFoundError):
            store.get(bad)


def test_begin_moves_state_and_clears_error(store: FileDemoStore) -> None:
    demo = Demo(intent="some demo intent", status=DemoStatus.FAILED, error="old", failed_stage="apply")
    store.create(demo)
    moved = store.begin(demo.demo_id, {DemoStatus.FAILED}, DemoStatus.DEPLOYING)
    assert moved.status == DemoStatus.DEPLOYING
    assert moved.error is None and moved.failed_stage is None
    assert store.get(demo.demo_id).status == DemoStatus.DEPLOYING


def test_begin_blocks_second_claim(store: FileDemoStore) -> None:
    demo = store.create(Demo(intent="some demo intent", status=DemoStatus.GENERATED))
    store.begin(demo.demo_id, {DemoStatus.GENERATED}, DemoStatus.DEPLOYING)
    with pytest.raises(InvalidTransitionError, match="deploying"):
        store.begin(demo.demo_id, {DemoStatus.GENERATED}, DemoStatus.DEPLOYING)


def test_save_updates_timestamp(store: FileDemoStore) -> None:
    demo = store.create(Demo(intent="some demo intent"))
    before = store.get(demo.demo_id).updated_at
    demo.log("x", "hello")
    store.save(demo)
    after = store.get(demo.demo_id)
    assert after.updated_at >= before
    assert after.events[-1].message == "hello"
