"""The tenant's own skill bundle, on disk, where the agent can load it.

The hosted runner installs exactly what the customer's own agent would install:
`GET /my/skill-bundle` with the hosted key, rendered for that principal. Nobody
maintains a second copy of the flow skills for hosted tenants — if they could
drift, the promise that hosted and self-hosted are the same agent would be a
claim rather than a fact.

Bundles land in a per-tenant directory. The namespacing that lets one laptop
hold two employers' bundles (`oryh-skills-<slug>/`, keys rendered per skill)
does the same job here, and the directory split is a second fence behind it.
"""

from __future__ import annotations

import io
import json
import logging
import shutil
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from flow_runner.client import OryhClient, Transport, UrllibTransport

log = logging.getLogger("flow_runner.bundles")


class BundleError(RuntimeError):
    pass


@dataclass
class InstalledBundle:
    root: Path
    install_dir: str
    # registry name -> directory name on disk. The subscription names the
    # canonical skill (`oryh-timesheet-approval-flow`); on disk it is the
    # tenant-scoped `oryh-<slug>-timesheet-approval-flow`.
    installed_as: dict[str, str]
    fetched_at: datetime

    def skill_path(self, skill_name: str) -> Path:
        directory = self.installed_as.get(skill_name)
        if directory is None:
            raise BundleError(
                f"skill {skill_name!r} is not in this tenant's bundle "
                f"(have: {sorted(self.installed_as)})"
            )
        path = self.root / self.install_dir / directory
        if not (path / "SKILL.md").is_file():
            raise BundleError(f"{path}/SKILL.md missing from the downloaded bundle")
        return path


@dataclass
class BundleStore:
    """Downloads and caches bundles, one directory per tenant.

    Re-downloads on a TTL rather than comparing hashes because
    `/my/skills/manifest` only serves user-bound keys — a service principal
    cannot do the cheap comparison. Wasteful at scale and worth fixing there;
    at one download per tenant per hour it is not worth working around here.
    """

    workspace: Path
    ttl: timedelta = timedelta(hours=1)
    transport: Transport = field(default_factory=UrllibTransport)
    installed: dict[str, InstalledBundle] = field(default_factory=dict)

    def ensure(
        self, base_url: str, api_key: str, tenant_id: str, *, refresh: bool = False
    ) -> InstalledBundle:
        cached = self.installed.get(tenant_id)
        if cached is not None and not refresh and _utc_now() - cached.fetched_at < self.ttl:
            return cached
        bundle = self.download(base_url, api_key, tenant_id)
        self.installed[tenant_id] = bundle
        return bundle

    def download(self, base_url: str, api_key: str, tenant_id: str) -> InstalledBundle:
        client = OryhClient(base_url=base_url, api_key=api_key, transport=self.transport)
        raw = client.call_raw("GET", "/my/skill-bundle")
        root = self.workspace / tenant_id
        # Replace rather than merge: a skill the tenant's role no longer covers
        # must disappear from disk too, or the agent keeps a capability the
        # record layer has already taken away.
        if root.exists():
            shutil.rmtree(root)
        root.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            _extract_safely(archive, root)

        manifests = list(root.glob("*/manifest.json"))
        if not manifests:
            raise BundleError("bundle contains no manifest.json")
        manifest = json.loads(manifests[0].read_text())
        install_dir = manifest.get("install_dir") or manifests[0].parent.name
        installed_as = {
            entry["name"]: entry["installed_as"] for entry in manifest.get("skills", [])
        }
        log.info(
            "tenant %s: installed %d skill(s) under %s", tenant_id, len(installed_as), install_dir
        )
        return InstalledBundle(
            root=root,
            install_dir=install_dir,
            installed_as=installed_as,
            fetched_at=_utc_now(),
        )


def _extract_safely(archive: zipfile.ZipFile, destination: Path) -> None:
    """Refuse entries that escape the destination.

    The archive comes from our own API, so this is not the defence that matters
    — but an unpacker that trusts its input is the wrong thing to have in a
    process that runs an agent, and the check costs nothing.
    """
    destination = destination.resolve()
    for member in archive.infolist():
        target = (destination / member.filename).resolve()
        if not target.is_relative_to(destination):
            raise BundleError(f"refusing archive entry outside the bundle root: {member.filename!r}")
    archive.extractall(destination)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)
