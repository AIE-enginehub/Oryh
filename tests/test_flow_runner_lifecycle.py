"""How the runner process behaves around its credentials file.

The file is mounted rather than baked into the environment so tenants can be
added and keys rotated without recreating the container. That only pays off if
the process survives long enough to notice a change — so "no tenants yet" and
"file not written yet" have to be ordinary states, not crashes.
"""

from __future__ import annotations

import json
from pathlib import Path

from flow_runner.__main__ import build_adapter, reconcile
from flow_runner.config import load_config


def config_for(path: Path, **extra):
    return load_config({"ORYH_RUNNER_CREDENTIALS_FILE": str(path), **extra})


def write(path: Path, tenants: list[tuple[str, str]]) -> None:
    path.write_text(json.dumps([{"tenant_id": t, "api_key": k} for t, k in tenants]))


def test_a_missing_credentials_file_is_not_fatal(tmp_path: Path) -> None:
    """A fresh install has no file yet — and docker helpfully creates a
    *directory* at a bind-mount path that does not exist. Neither may take the
    process down, or it restart-loops and is never alive to read the file once
    someone writes it."""
    config = config_for(tmp_path / "not-written-yet.json")
    assert config.tenants == ()
    assert config.credentials_file is not None

    dispatchers = reconcile(config, build_adapter(config), None, {})
    assert dispatchers == {}


def test_an_empty_file_idles_rather_than_failing(tmp_path: Path) -> None:
    path = tmp_path / "creds.json"
    write(path, [])
    config = config_for(path)
    assert reconcile(config, build_adapter(config), None, {}) == {}


def test_a_tenant_added_later_is_picked_up(tmp_path: Path) -> None:
    path = tmp_path / "creds.json"
    write(path, [])
    config = config_for(path)
    adapter = build_adapter(config)

    dispatchers = reconcile(config, adapter, None, {})
    assert dispatchers == {}

    write(path, [("tenant-a", "key-a")])
    dispatchers = reconcile(config, adapter, None, dispatchers)
    assert list(dispatchers) == ["tenant-a"]
    assert dispatchers["tenant-a"].client.api_key == "key-a"


def test_unrelated_tenants_keep_their_state_across_a_reload(tmp_path: Path) -> None:
    """Adding a tenant must not reset everyone else's cadence timers or revive
    a subscription that was parked for not draining."""
    path = tmp_path / "creds.json"
    write(path, [("tenant-a", "key-a")])
    config = config_for(path)
    adapter = build_adapter(config)

    dispatchers = reconcile(config, adapter, None, {})
    first = dispatchers["tenant-a"]
    first.state_for("sub-1").parked = True

    write(path, [("tenant-a", "key-a"), ("tenant-b", "key-b")])
    dispatchers = reconcile(config, adapter, None, dispatchers)

    assert dispatchers["tenant-a"] is first
    assert dispatchers["tenant-a"].state_for("sub-1").parked is True
    assert set(dispatchers) == {"tenant-a", "tenant-b"}


def test_a_rotated_key_replaces_the_dispatcher(tmp_path: Path) -> None:
    path = tmp_path / "creds.json"
    write(path, [("tenant-a", "old-key")])
    config = config_for(path)
    adapter = build_adapter(config)
    dispatchers = reconcile(config, adapter, None, {})

    write(path, [("tenant-a", "new-key")])
    dispatchers = reconcile(config, adapter, None, dispatchers)

    assert dispatchers["tenant-a"].client.api_key == "new-key"


def test_a_removed_tenant_stops_being_driven(tmp_path: Path) -> None:
    path = tmp_path / "creds.json"
    write(path, [("tenant-a", "key-a"), ("tenant-b", "key-b")])
    config = config_for(path)
    adapter = build_adapter(config)
    dispatchers = reconcile(config, adapter, None, {})

    write(path, [("tenant-a", "key-a")])
    dispatchers = reconcile(config, adapter, None, dispatchers)

    assert set(dispatchers) == {"tenant-a"}


def test_a_half_written_file_keeps_the_current_tenants(tmp_path: Path) -> None:
    """Editing a mounted file is not atomic. Catching the write mid-flight must
    not stop work for tenants that were already being driven."""
    path = tmp_path / "creds.json"
    write(path, [("tenant-a", "key-a")])
    config = config_for(path)
    adapter = build_adapter(config)
    dispatchers = reconcile(config, adapter, None, {})

    path.write_text('[{"tenant_id": "tenant-a", "api_k')  # truncated mid-write
    dispatchers = reconcile(config, adapter, None, dispatchers)

    assert set(dispatchers) == {"tenant-a"}
