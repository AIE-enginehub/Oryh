"""What the runner is told, and what it is trusted with.

The tenant list is config, not a cross-tenant query: the runner holds one hosted
key per tenant it serves and can see nothing else. There is deliberately no
endpoint that hands it "every tenant with a subscription" — such an endpoint
would need a credential above the tenant line, and then a compromise of a
polling loop would reach every customer at once instead of the ones whose keys
it was given.

Keys arrive by file rather than environment because a mounted secret can be
rotated without recreating the container, and because process environments end
up in logs and crash reports.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class TenantCredential:
    tenant_id: str
    api_key: str


@dataclass(frozen=True)
class RunnerConfig:
    base_url: str
    tenants: tuple[TenantCredential, ...]
    # Kept so the loop can re-read it: tenants get added and keys rotated
    # without recreating the container, which only works if we look again.
    credentials_file: str | None = None
    # ORYH's own fleet secret. With it the runner asks the control plane which
    # tenants have enabled subscriptions and lets itself into each — which is
    # what makes a workspace created at 3am driven at 3am. Without it the
    # credentials file is the whole tenant set, as before: self-hosted runners
    # and single-tenant deployments never set this and lose nothing.
    bootstrap_token: str | None = None
    # Where acquired keys are remembered across restarts. Optional by design:
    # issuing supersedes the previous key and re-points every subscription, so
    # forgetting costs one extra mint per tenant, never correctness. Same
    # sensitivity as the credentials file — mount it the same way.
    state_file: str | None = None
    poll_interval_seconds: int = 30
    idle_report_seconds: int = 3600
    max_unmoved_runs: int = 3
    # Records one run may take on. Measured: the per-run overhead dominates
    # (1 record ~50-100s, 3 records 125s), so batching is worth it and the
    # binding constraint at depth is context length and the timeout, not
    # per-record cost. Whatever a run does not reach, the next pass finds
    # still sitting in the queue.
    max_records_per_run: int = 10
    # pi is a CLI harness, so this is a binary on PATH rather than a URL.
    pi_binary: str | None = None
    # The ceiling on one agent call — and, because the runner is single-threaded,
    # the ceiling on how long one tenant can hold the whole fleet. 900s was
    # chosen when a runner served one tenant; with the fleet bootstrap it meant
    # a quarter of an hour of everyone waiting on one stuck call, which was
    # watched happening.
    #
    # Not lower than this, though. The two measured points in the batch note
    # below fit to 210-390s for a full ten-record run, so a 180s ceiling would
    # cut healthy batches — and a killed run is worse than a slow one: it may
    # have moved records already, it reports an error, and it counts toward the
    # park. 420 covers the pessimistic fit with margin and still halves the
    # worst case.
    pi_timeout_seconds: float = 420.0
    pi_provider: str | None = None
    pi_model: str | None = None
    # The model provider's credential, ORYH's own. A file for the same
    # reason the tenant keys are: rotating it should not need a container
    # recreate, and a process environment ends up in logs and crash dumps.
    provider_env_file: str | None = None
    # Inline alternative to the file, for the same reason as the credentials:
    # nothing on disk for an agent's shell to read. {"VAR": "value"} JSON.
    provider_env_inline: dict[str, str] | None = None
    bundle_ttl_seconds: int = 3600
    workspace: str = "/var/tmp/oryh-flow-runner"
    # Runs the whole loop with the stub adapter: real polling, real ledger
    # rows, no agent spend. How a new tenant is switched on — watch what it
    # would have done for a day before letting it do it.
    dry_run: bool = False

    @property
    def uses_pi(self) -> bool:
        return not self.dry_run and bool(self.pi_binary)


def load_credentials(path: str | Path) -> tuple[TenantCredential, ...]:
    """`[{"tenant_id": "...", "api_key": "..."}]` — the hosted keys, which are
    shown exactly once at issuance and stored by whoever runs this."""
    raw = json.loads(Path(path).read_text())
    return tuple(
        TenantCredential(tenant_id=entry["tenant_id"], api_key=entry["api_key"])
        for entry in raw
    )


def _provider_env_inline(env: dict[str, str]) -> dict[str, str] | None:
    raw = env.get("ORYH_RUNNER_PROVIDER_ENV_JSON")
    if not raw:
        return None
    try:
        loaded = json.loads(raw)
    except ValueError:
        raise RuntimeError("ORYH_RUNNER_PROVIDER_ENV_JSON is not valid JSON")
    if not isinstance(loaded, dict):
        raise RuntimeError("ORYH_RUNNER_PROVIDER_ENV_JSON must be a JSON object")
    return {str(k): str(v) for k, v in loaded.items() if v}


def load_config(env: dict[str, str] | None = None) -> RunnerConfig:
    env = dict(os.environ if env is None else env)
    # Secrets may arrive as environment VALUES instead of mounted files. The
    # file form documented above trades rotation convenience for a file any
    # same-user process can read — and a live E2E run watched an agent's shell
    # read /run/secrets and use other tenants' hosted credentials. With the
    # env form there is nothing on disk to read, and the pi child never sees
    # this process's environment (the adapter builds the child env from a
    # whitelist), so the credentials exist only in this process's memory.
    # Rotation then means a pod restart, which kubernetes does on secret-env
    # changes anyway. Inline wins when both are set.
    credentials_path = env.get("ORYH_RUNNER_CREDENTIALS_FILE")
    tenants: tuple[TenantCredential, ...] = ()
    credentials_json = env.get("ORYH_RUNNER_CREDENTIALS_JSON")
    if credentials_json:
        try:
            tenants = tuple(
                TenantCredential(tenant_id=entry["tenant_id"], api_key=entry["api_key"])
                for entry in json.loads(credentials_json)
            )
        except (ValueError, KeyError, TypeError):
            # A malformed inline value fails loudly at boot: unlike the file,
            # nothing will re-read it later, so silence would mean a runner
            # that quietly serves no tenants for as long as the pod lives.
            raise RuntimeError("ORYH_RUNNER_CREDENTIALS_JSON is not valid credential JSON")
    elif credentials_path:
        try:
            tenants = load_credentials(credentials_path)
        except (OSError, ValueError, KeyError):
            # Missing or malformed at boot is not fatal — the file is mounted
            # and expected to change, and a fresh install has no tenants yet.
            # The run loop re-reads it and reports what it finds.
            pass
    return RunnerConfig(
        base_url=env.get("ORYH_RUNNER_BASE_URL", "http://api:8000/api/v1"),
        tenants=tenants,
        credentials_file=credentials_path,
        bootstrap_token=env.get("ORYH_RUNNER_BOOTSTRAP_TOKEN") or None,
        state_file=env.get("ORYH_RUNNER_STATE_FILE") or None,
        poll_interval_seconds=int(env.get("ORYH_RUNNER_POLL_INTERVAL_SECONDS", "30")),
        idle_report_seconds=int(env.get("ORYH_RUNNER_IDLE_REPORT_SECONDS", "3600")),
        max_unmoved_runs=int(env.get("ORYH_RUNNER_MAX_UNMOVED_RUNS", "3")),
        max_records_per_run=int(env.get("ORYH_RUNNER_MAX_RECORDS_PER_RUN", "10")),
        pi_binary=env.get("ORYH_RUNNER_PI_BINARY") or None,
        pi_timeout_seconds=float(env.get("ORYH_RUNNER_PI_TIMEOUT_SECONDS", "420")),
        pi_provider=env.get("ORYH_RUNNER_PI_PROVIDER") or None,
        pi_model=env.get("ORYH_RUNNER_PI_MODEL") or None,
        provider_env_file=env.get("ORYH_RUNNER_PROVIDER_ENV_FILE") or None,
        provider_env_inline=_provider_env_inline(env),
        bundle_ttl_seconds=int(env.get("ORYH_RUNNER_BUNDLE_TTL_SECONDS", "3600")),
        workspace=env.get("ORYH_RUNNER_WORKSPACE", "/var/tmp/oryh-flow-runner"),
        dry_run=env.get("ORYH_RUNNER_DRY_RUN", "false").lower() == "true",
    )
