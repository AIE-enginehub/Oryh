"""Letting itself in: which tenants to serve, and a credential for each.

The runner's tenant set used to be a JSON file on the runner host. Once every
workspace was subscribed by default, that file was the thing standing between
"a tenant exists" and "a tenant is driven" — and it could not be generated,
because the control plane stores only a hash of each key and shows the
plaintext once. A workspace created on Saturday waited for someone to edit a
file on Monday.

So the runner asks instead. Two calls, both platform-scoped, both narrow: list
the tenants with enabled subscriptions, and be issued one tenant's hosted
credential. Everything after that is unchanged — the per-tenant key does all
the real work, so `write_scope`, attribution and the tenant's grant set behave
exactly as they did when a human pasted the same key into a file.

The operator's credentials file still works and still wins: a key written by
hand is used as written, and this only fills the gaps. That is what keeps a
self-hosted or single-tenant deployment working with no fleet secret at all.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

from flow_runner.client import ApiError, Transport
from flow_runner.config import TenantCredential

log = logging.getLogger("flow_runner.bootstrap")


@dataclass
class Bootstrapper:
    base_url: str
    token: str
    transport: Transport
    state_file: str | None = None
    timeout: float = 30.0

    def call(self, method: str, path: str, *, expected: tuple[int, ...] = (200, 201)):
        url = self.base_url.rstrip("/") + path
        status, raw = self.transport.request(
            method, url,
            headers={"Content-Type": "application/json", "X-Flow-Runner-Bootstrap": self.token},
            body=None,
            timeout=self.timeout,
        )
        if status not in expected:
            raise ApiError(method, path, status, raw.decode(errors="replace"))
        return json.loads(raw) if raw else None

    def tenants(self) -> list[dict]:
        """Workspaces with at least one enabled subscription.

        `enabled` is the tenant's own lever, so this list shrinking is how a
        customer switching their last subscription off reaches the runner.
        """
        return self.call("GET", "/flow-runner/tenants")["data"]

    def credential(self, tenant_id: str) -> str:
        """Be issued this tenant's hosted key. Supersedes any previous one."""
        return self.call("POST", f"/flow-runner/tenants/{tenant_id}/credential")["data"][
            "plain_text_api_key"
        ]

    # --- remembering across restarts ------------------------------------

    def remembered(self) -> dict[str, str]:
        """Keys acquired on an earlier boot.

        Best-effort on purpose. Issuing supersedes and re-points, so a lost
        state file costs one extra mint per tenant and nothing else — which is
        why an unreadable or absent file is a shrug rather than a failure.
        """
        if not self.state_file:
            return {}
        try:
            loaded = json.loads(Path(self.state_file).read_text())
        except (OSError, ValueError):
            return {}
        return {
            str(k): str(v)
            for k, v in (loaded or {}).items()
            if isinstance(v, str) and v
        }

    def remember(self, acquired: dict[str, str]) -> None:
        if not self.state_file:
            return
        try:
            path = Path(self.state_file)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(acquired, ensure_ascii=False, indent=2))
            path.chmod(0o600)
        except OSError as exc:
            # Never fatal: the state file is an optimisation, and a runner that
            # died because it could not write a cache would be worse than one
            # that mints an extra key next boot.
            log.warning("could not write %s (%s); will re-issue after a restart",
                        self.state_file, exc)


def resolve_tenants(
    bootstrapper: Bootstrapper, configured: tuple[TenantCredential, ...]
) -> tuple[TenantCredential, ...]:
    """The tenant set: what the operator wrote, plus what the runner let itself into.

    Operator-written credentials win. Someone who put a key in the file meant
    that key — perhaps a tenant deliberately pinned to an older credential
    during an incident — and silently superseding it would make the file a lie.

    A failure here returns the configured set rather than an empty one. A
    control plane that is briefly unreachable must not read as "you serve
    nobody", which would park every tenant the runner already had.
    """
    by_tenant = {credential.tenant_id: credential.api_key for credential in configured}
    try:
        listed = bootstrapper.tenants()
    except (ApiError, OSError) as exc:
        log.warning("cannot list tenants from the control plane (%s); keeping %d configured",
                    exc, len(by_tenant))
        return configured

    remembered = bootstrapper.remembered()
    acquired: dict[str, str] = {}
    for row in listed:
        tenant_id = row["tenant_id"]
        if tenant_id in by_tenant:
            continue
        if tenant_id in remembered:
            acquired[tenant_id] = remembered[tenant_id]
            by_tenant[tenant_id] = remembered[tenant_id]
            continue
        try:
            key = bootstrapper.credential(tenant_id)
        except ApiError as exc:
            # One tenant's refusal is one tenant's refusal — a workspace that
            # switched everything off between the list and the issue answers
            # 409, and that must not stop the others being served.
            log.warning("tenant %s: could not obtain a credential (%s)", tenant_id, exc)
            continue
        log.info("tenant %s: let myself in (%s)", tenant_id, row.get("name") or "")
        acquired[tenant_id] = key
        by_tenant[tenant_id] = key

    # Only what we acquired is remembered — a reused key counts, which is why
    # the remembered branch above puts it back in. The operator's file is
    # theirs, and copying it into our state would duplicate a secret for no
    # reason and give a hand-pinned key a second, staler home.
    bootstrapper.remember(acquired)
    return tuple(
        TenantCredential(tenant_id=tenant_id, api_key=api_key)
        for tenant_id, api_key in by_tenant.items()
    )
