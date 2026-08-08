"""The runner process: one dispatcher per tenant, polled on a fixed interval.

Polling first, on purpose. It needs no new API surface, it is provably
self-healing, and the LLM cost is bounded by real work rather than by how often
we look — the poll itself is one cheap count. A `pg_notify` wake-up to cut the
"submitted → manager sees it" latency slots in later without the dispatchers
changing: it would only make a subscription due sooner, and due-ness is already
the only thing the loop asks.
"""

from __future__ import annotations

import argparse
import logging
import signal
import sys
import time

from datetime import timedelta
from pathlib import Path

from flow_runner.adapter import PiAgentAdapter, StubAdapter
from flow_runner.bundles import BundleStore
from flow_runner.client import OryhClient, UrllibTransport
from flow_runner.bootstrap import Bootstrapper, resolve_tenants
from flow_runner.config import RunnerConfig, load_config, load_credentials
from flow_runner.dispatcher import Dispatcher

log = logging.getLogger("flow_runner")


def build_adapter(config: RunnerConfig):
    workspace = Path(config.workspace)
    if not config.uses_pi:
        return StubAdapter()
    return PiAgentAdapter(
        bundle_store=BundleStore(
            workspace=workspace / "bundles",
            ttl=timedelta(seconds=config.bundle_ttl_seconds),
        ),
        pi_binary=config.pi_binary,
        timeout=config.pi_timeout_seconds,
        provider=config.pi_provider,
        model=config.pi_model,
        provider_env_file=config.provider_env_file,
        provider_env_inline=config.provider_env_inline,
        workspace=workspace / "runs",
    )


def dispatcher_for(config: RunnerConfig, adapter, transport, tenant) -> Dispatcher:
    return Dispatcher(
        client=OryhClient(base_url=config.base_url, api_key=tenant.api_key, transport=transport),
        adapter=adapter,
        tenant_id=tenant.tenant_id,
        base_url=config.base_url,
        max_unmoved_runs=config.max_unmoved_runs,
        max_records_per_run=config.max_records_per_run,
        idle_report_seconds=config.idle_report_seconds,
    )


def build_dispatchers(config: RunnerConfig) -> list[Dispatcher]:
    adapter, transport = build_adapter(config), UrllibTransport()
    return [dispatcher_for(config, adapter, transport, t) for t in config.tenants]


def reconcile(
    config: RunnerConfig, adapter, transport, current: dict[str, Dispatcher]
) -> dict[str, Dispatcher]:
    """Work out who to serve this pass, and match the dispatcher set to it.

    Two sources, checked every pass so neither needs a container recreate:

    - the operator's credentials file, which wins where it speaks;
    - the control plane, when a bootstrap token is configured — that is what
      makes a workspace created an hour ago driven now, rather than waiting
      for someone to edit a file on this host.

    Dispatchers for tenants that are still wanted are kept as they are, so
    cadence timers and parked subscriptions survive a change that has nothing
    to do with them.
    """
    try:
        tenants = load_credentials(config.credentials_file) if config.credentials_file else ()
    except (OSError, ValueError, KeyError) as exc:
        # A half-written or malformed file must not take the runner down: keep
        # driving whoever we were already driving and try again next pass.
        log.warning("credentials file unreadable (%s); keeping the current tenant set", exc)
        return current

    if config.bootstrap_token:
        tenants = resolve_tenants(
            Bootstrapper(
                base_url=config.base_url,
                token=config.bootstrap_token,
                transport=transport,
                state_file=config.state_file,
            ),
            tenants,
        )

    wanted = {t.tenant_id: t for t in tenants}
    for gone in set(current) - set(wanted):
        log.info("tenant %s: no longer configured; stopped driving it", gone)
    updated = {}
    for tenant_id, tenant in wanted.items():
        existing = current.get(tenant_id)
        if existing is not None and existing.client.api_key == tenant.api_key:
            updated[tenant_id] = existing
        else:
            if existing is not None:
                log.info("tenant %s: credential changed; reloaded", tenant_id)
            else:
                log.info("tenant %s: now being driven", tenant_id)
            updated[tenant_id] = dispatcher_for(config, adapter, transport, tenant)
    return updated


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Drive hosted approval flows.")
    parser.add_argument(
        "--once",
        action="store_true",
        help="run a single pass and exit (operator nudge, smoke check)",
    )
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s"
    )

    config = load_config()
    adapter, transport = build_adapter(config), UrllibTransport()
    log.info(
        "polling %s every %ss, adapter=%s, batch<=%d",
        config.base_url, config.poll_interval_seconds,
        "pi" if config.uses_pi else "stub (no agent spend)",
        config.max_records_per_run,
    )

    stopping = False

    def stop(_signum, _frame):
        nonlocal stopping
        stopping = True
        log.info("stop requested; finishing the current pass")

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    dispatchers: dict[str, Dispatcher] = {}
    idle_announced = False

    while not stopping:
        dispatchers = reconcile(config, adapter, transport, dispatchers)
        if not dispatchers:
            # Not an error, and not a reason to die: a runner with no tenants
            # yet is the normal state of a fresh install. Say so once, then wait
            # for someone to write the file.
            if not idle_announced:
                log.warning(
                    "serving no tenants — idling. %s. Either way it is picked up "
                    "within %ss without restarting this container",
                    (
                        "No workspace has an enabled flow subscription yet"
                        if config.bootstrap_token
                        else f"Add one to {config.credentials_file}"
                    ),
                    config.poll_interval_seconds,
                )
                idle_announced = True
        else:
            idle_announced = False
        for dispatcher in dispatchers.values():
            # One tenant's failure is one tenant's failure. It must not take
            # the pass down for everyone else sharing this process.
            try:
                for run in dispatcher.poll_once():
                    log.info(
                        "tenant %s: %s run %s -> %s (queue %s, advanced %s)",
                        dispatcher.tenant_id, run["entity_type"], run["id"],
                        run["status"], run.get("queue_size"), run.get("items_advanced"),
                    )
            except Exception:
                log.exception("tenant %s: pass failed", dispatcher.tenant_id)
        if args.once:
            return 0
        for _ in range(config.poll_interval_seconds):
            if stopping:
                break
            time.sleep(1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
