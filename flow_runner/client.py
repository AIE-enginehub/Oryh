"""The record layer as seen from outside.

Deliberately the public REST surface and nothing else. The runner is ORYH's own
deployment of the same agent a customer could run on their laptop, and the
moment it reaches for the database directly that stops being true — the hosted
path would start being able to do things the self-hosted path cannot, and every
guarantee P0 established would need re-proving for two callers instead of one.

Transport is injectable so tests drive the real app in-process without a socket.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Protocol


class Transport(Protocol):
    def request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str],
        body: bytes | None,
        timeout: float,
    ) -> tuple[int, bytes]: ...


class UrllibTransport:
    """stdlib only, so the runner image needs nothing the API image lacks."""

    def request(self, method, url, *, headers, body, timeout):
        request = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.status, response.read()
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read()


class ApiError(RuntimeError):
    def __init__(self, method: str, path: str, status: int, body: str):
        super().__init__(f"{method} {path} -> {status}: {body[:300]}")
        self.status = status
        self.body = body


@dataclass
class OryhClient:
    """One tenant's view, authenticated as that tenant's hosted principal.

    One client per tenant, never a shared one that switches keys: the key is the
    tenant, and a client that could change which tenant it is would be one bug
    away from writing a decision into the wrong company.
    """

    base_url: str
    api_key: str
    transport: Transport
    timeout: float = 30.0

    def call(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        payload: Any | None = None,
        expected: tuple[int, ...] = (200, 201),
    ) -> Any:
        url = self.base_url.rstrip("/") + path
        if params:
            query = {k: _query_value(v) for k, v in params.items() if v is not None}
            if query:
                url = f"{url}?{urllib.parse.urlencode(query)}"
        body = None if payload is None else json.dumps(payload).encode()
        status, raw = self.transport.request(
            method, url,
            headers={"Content-Type": "application/json", "X-API-Key": self.api_key},
            body=body,
            timeout=self.timeout,
        )
        if status not in expected:
            raise ApiError(method, path, status, raw.decode(errors="replace"))
        return json.loads(raw) if raw else None

    def call_raw(self, method: str, path: str, *, expected: tuple[int, ...] = (200,)) -> bytes:
        """For the skill bundle, which is a zip rather than an envelope."""
        status, raw = self.transport.request(
            method, self.base_url.rstrip("/") + path,
            headers={"X-API-Key": self.api_key},
            body=None,
            timeout=self.timeout,
        )
        if status not in expected:
            raise ApiError(method, path, status, raw.decode(errors="replace"))
        return raw

    # --- the four things a run needs ------------------------------------

    def active_subscriptions(self) -> list[dict]:
        return self.call("GET", "/flow-subscriptions", params={"enabled": True})["data"]

    def has_active_workflow(self, entity_type: str, entity_kind: str) -> bool:
        """Whether the tenant has published the map this subscription follows.

        A subscription may deliberately be provisioned first. Asking this on
        every due poll makes publishing the definition the only action needed
        to wake it up, without spending an agent turn while the map is absent.
        """
        response = self.call(
            "GET",
            "/workflow-definitions",
            params={
                "entity_kind": entity_kind,
                "object_type": entity_type,
                "page": 1,
                "size": 1,
            },
        )
        meta = response.get("meta") or {}
        if "total" in meta:
            return int(meta["total"]) > 0
        return bool(response.get("data"))

    def queue_size(self, path: str, queue_filter: dict[str, Any]) -> int:
        """How many records nobody is assigned to act on.

        Asked with `size=1` because only the count matters: this is the check
        that decides whether spending an agent run is worth it, so it must cost
        far less than the run it is guarding.
        """
        return self.count(path, {**queue_filter, "without_open_todo": True})

    def count(self, path: str, params: dict[str, Any]) -> int:
        """meta.total of any list, asked with size=1 — a counter, not a read."""
        response = self.call("GET", path, params={**params, "page": 1, "size": 1})
        meta = response.get("meta") or {}
        if "total" in meta:
            return int(meta["total"])
        return len(response.get("data") or [])

    def report_driver_state(
        self, subscription_id: str, *, unmoved_runs: int, parked: bool, parked_reason: str | None
    ) -> dict:
        return self.call(
            "PATCH", f"/flow-subscriptions/{subscription_id}/driver-state",
            payload={
                "unmoved_runs": unmoved_runs,
                "parked": parked,
                "parked_reason": parked_reason,
            },
        )["data"]

    def open_run(self, **fields) -> dict:
        return self.call("POST", "/flow-runs", payload=fields)["data"]

    def close_run(self, run_id: str, **fields) -> dict:
        return self.call("PATCH", f"/flow-runs/{run_id}", payload=fields)["data"]


def _query_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)
