"""When to spend a run, and the record that one was spent.

The design rule the whole component follows: **a signal decides when to look,
state decides what to do.** Nothing here interprets a workflow; it counts
unattended records and, if there are any, asks the agent to look. Losing a
wake-up costs latency and never correctness, because the next pass rediscovers
the same queue — the same property that lets `without_open_todo` be a
self-healing work queue rather than a delivery mechanism.

Everything expensive or unrecoverable is decided here rather than in the agent:
whether a run is worth spending, whether one is already in flight, and how many
times an item may fail to move before someone is told.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from flow_runner.adapter import RunnerAdapter, RunRequest, RunResult
from flow_runner.client import ApiError, OryhClient
from flow_runner.queues import queue_location, workflow_entity_kind

log = logging.getLogger("flow_runner")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class SubscriptionState:
    """What the dispatcher remembers between passes.

    In memory on purpose, and now genuinely so: what is left here is only
    scheduling hints, and losing them on restart costs one redundant poll.

    The unmoved counter and the park used to live here too, which was wrong —
    forgetting those cost money, because a queue that would not drain resumed
    burning a run every cadence after each restart. They are subscription state
    now, read back from the record layer on every pass.
    """

    last_polled_at: datetime | None = None
    last_idle_report_at: datetime | None = None
    # The reason the last idle report gave, if it gave one. Every drivable
    # builtin is now subscribed by default, so most workspaces carry several
    # subscriptions waiting on a workflow definition nobody has written yet.
    # Those are a configuration state, not a heartbeat: saying
    # `workflow_definition_missing` once an hour forever buries the runs that
    # mean something under rows that say the same thing all year.
    last_idle_reason: str | None = None


@dataclass
class Dispatcher:
    client: OryhClient
    adapter: RunnerAdapter
    tenant_id: str
    base_url: str
    # After this many runs that found work and moved nothing, stop spending on
    # it. A queue that will not drain is a poison message: without this it
    # burns a run every cadence forever, and the ledger shows a healthy agent
    # working hard on an item that never leaves.
    max_unmoved_runs: int = 3
    # How often an idle subscription still writes a row, so "no runs lately"
    # can be told apart from "nothing to do lately".
    idle_report_seconds: int = 3600
    # Records one run may take on; the rest wait for the next pass.
    max_records_per_run: int = 10
    state: dict[str, SubscriptionState] = field(default_factory=dict)

    def state_for(self, subscription_id: str) -> SubscriptionState:
        return self.state.setdefault(subscription_id, SubscriptionState())

    def due(self, subscription: dict, now: datetime) -> bool:
        if subscription.get("parked_at"):
            # Read from the subscription, not remembered: a restart, a deploy, or
            # a second replica all see the same stop.
            return False
        state = self.state_for(subscription["id"])
        if state.last_polled_at is None:
            return True
        cadence = timedelta(seconds=int(subscription.get("cadence_seconds") or 300))
        return now - state.last_polled_at >= cadence

    def poll_once(self, trigger: str = "cadence") -> list[dict]:
        """One pass over this tenant's enabled subscriptions.

        Returns the runs it recorded, so a caller — a test, an operator's
        one-shot invocation — can see what a pass actually did.
        """
        try:
            subscriptions = self.client.active_subscriptions()
        except ApiError as exc:
            # A tenant whose hosted key was switched off answers 401 here. That
            # is an unsubscription, not an incident: say so once and move on.
            log.warning("tenant %s: cannot read subscriptions: %s", self.tenant_id, exc)
            return []

        recorded = []
        now = utc_now()
        for subscription in subscriptions:
            if not self.due(subscription, now):
                continue
            self.state_for(subscription["id"]).last_polled_at = now
            run, spent_agent = self.dispatch(subscription, trigger=trigger)
            if run is not None:
                recorded.append(run)
            if spent_agent:
                # One agent turn per tenant per pass, and then it is somebody
                # else's turn.
                #
                # The whole runner is single-threaded: `__main__` walks the
                # tenants in order and every agent call blocks the process.
                # Without this break a tenant with work in all seven families
                # held the loop for seven consecutive agent calls — measured at
                # 50-100s each — so twenty-six other workspaces waited nine
                # minutes on one. The comment over that loop says a tenant's
                # failure is its own; that is true of exceptions, which are
                # caught, and was never true of time.
                #
                # Nothing is dropped. The subscriptions after this one never
                # had `last_polled_at` touched, so they are still due on the
                # next pass, while this one is not — the queue rotates by
                # itself and no family can starve behind a busier one.
                #
                # This bounds what ONE tenant takes; it does not raise the
                # fleet's throughput, which is still one agent call at a time.
                # That needs concurrency across tenants, and wants real load
                # numbers before anyone picks a shape for it.
                break
        return recorded

    def dispatch(self, subscription: dict, *, trigger: str) -> tuple[dict | None, bool]:
        """Returns (the ledger row, whether an agent turn was spent).

        The second half is what lets `poll_once` be fair: every cheap outcome —
        no workflow definition, an empty queue, a failed check — costs
        milliseconds and should not stop the pass, while the one expensive
        outcome should.
        """
        entity_type = subscription["entity_type"]
        state = self.state_for(subscription["id"])
        try:
            workflow_ready = self.client.has_active_workflow(
                entity_type, workflow_entity_kind(subscription)
            )
        except ApiError as exc:
            log.warning("tenant %s: workflow check failed for %s: %s", self.tenant_id, entity_type, exc)
            self.note_progress(
                subscription, queue_size=0, advanced=None,
                result=RunResult(ok=False, error=str(exc)), entity_type=entity_type,
            )
            return self.record_failed_check(subscription, trigger=trigger, error=str(exc)), False
        if not workflow_ready:
            return self.report_idle(
                subscription,
                state,
                trigger=trigger,
                detail={"reason": "workflow_definition_missing"},
            ), False

        path, query = queue_location(subscription)
        try:
            queue_size = self.client.queue_size(path, query)
        except ApiError as exc:
            # A queue check that keeps failing is usually a `queue_filter`
            # naming a status this tenant's lifecycle does not have — a
            # subscription that can never work, not a passing outage. Left as a
            # log line it would fail silently forever in a container nobody
            # reads, so it goes in the ledger where the tenant sees it and
            # counts toward parking like any other run that moved nothing.
            log.warning("tenant %s: queue check failed for %s: %s", self.tenant_id, entity_type, exc)
            self.note_progress(
                subscription, queue_size=0, advanced=None,
                result=RunResult(ok=False, error=str(exc)), entity_type=entity_type,
            )
            return self.record_failed_check(subscription, trigger=trigger, error=str(exc)), False

        if queue_size == 0:
            return self.report_idle(subscription, state, trigger=trigger), False

        started_at = utc_now()
        run = self.client.open_run(
            entity_type=entity_type,
            subscription_id=subscription["id"],
            trigger=trigger,
            started_at=started_at.isoformat(),
            queue_size=queue_size,
            detail={
                "driver_skill": subscription["driver_skill"],
                "queue_path": path,
                # Never let a bounded batch read as a drained queue: "advanced
                # 10" beside a queue of 200 has to be legible as progress, not
                # completion.
                **({"batch_limit": self.max_records_per_run}
                   if queue_size > self.max_records_per_run else {}),
            },
        )
        evidence_before = self.progress_marks(entity_type)
        result = self.adapter.run(
            RunRequest(
                tenant_id=self.tenant_id,
                entity_type=entity_type,
                driver_skill=subscription["driver_skill"],
                base_url=self.base_url,
                api_key=self.client.api_key,
                queue_size=queue_size,
                run_id=run["id"],
                trigger=trigger,
                max_records=self.max_records_per_run,
                queue_filter=subscription.get("queue_filter") or {},
            )
        )
        # What actually moved is a question for the record layer, not for the
        # agent that just ran. An adapter may report a number (pi asks the model
        # for one) but a confused run is exactly the case where that number is
        # wrong, and it is the one figure in the ledger people will trust. So
        # re-count the queue: whatever left it, left it.
        advanced = result.items_advanced
        detail = dict(result.detail)
        try:
            remaining = self.client.queue_size(path, query)
            advanced = max(0, queue_size - remaining)
            detail["queue_remaining"] = remaining
        except ApiError as exc:
            log.warning("tenant %s: could not re-count %s: %s", self.tenant_id, entity_type, exc)

        # A multi-stage flow can make real progress while the queue count
        # stands still: the run assigns an approver todo, the approver acts
        # fast, and the still-submitted record is back in the queue before the
        # re-count — a live E2E run parked a healthy subscription after three such
        # runs. New approval facts or todos for this entity type during the
        # run are progress the queue diff cannot see.
        other_progress = False
        evidence_after = self.progress_marks(entity_type)
        if evidence_before is not None and evidence_after is not None:
            facts_new = max(0, evidence_after[0] - evidence_before[0])
            todos_new = max(0, evidence_after[1] - evidence_before[1])
            other_progress = facts_new > 0 or todos_new > 0
            if other_progress:
                detail["progress_evidence"] = {
                    "approval_facts_new": facts_new, "todos_new": todos_new,
                }

        self.note_progress(
            subscription, queue_size=queue_size, result=result,
            advanced=advanced, entity_type=entity_type,
            other_progress=other_progress,
        )
        return self.client.close_run(
            run["id"],
            status="succeeded" if result.ok else "failed",
            finished_at=utc_now().isoformat(),
            items_advanced=advanced,
            error=result.error,
            detail=detail,
        ), True

    def record_failed_check(self, subscription: dict, *, trigger: str, error: str) -> dict | None:
        """Best-effort: if the queue read failed because the API is unreachable,
        writing the ledger row will fail too. Nothing is lost — the next pass
        tries again — so this must never be the thing that raises."""
        now = utc_now()
        try:
            run = self.client.open_run(
                entity_type=subscription["entity_type"],
                subscription_id=subscription["id"],
                trigger=trigger,
                started_at=now.isoformat(),
                detail={"driver_skill": subscription["driver_skill"], "stage": "queue_check"},
            )
            return self.client.close_run(
                run["id"], status="failed", finished_at=now.isoformat(), error=error[:4000]
            )
        except ApiError:
            return None

    def report_idle(
        self,
        subscription: dict,
        state: SubscriptionState,
        *,
        trigger: str,
        detail: dict | None = None,
    ) -> dict | None:
        """An empty queue costs no run — but silence is ambiguous, so say
        "looked, nothing here" occasionally rather than never.

        Two different silences, throttled differently. "Looked, nothing to do"
        is a heartbeat and keeps its hourly beat. A stated `reason` is a
        standing condition — no workflow definition published — and is recorded
        when it CHANGES, not on a clock: the tenant needs to know it once, and
        the newest run for that subscription goes on saying it until the
        situation moves.
        """
        now = utc_now()
        reason = (detail or {}).get("reason")
        if reason is not None:
            if state.last_idle_reason == reason:
                return None
        elif state.last_idle_reason is not None:
            # A condition lifting is news in the direction that matters most —
            # the customer published the map and this is now live. Reported
            # regardless of the heartbeat clock, which would otherwise swallow
            # it for up to an hour because the blocked report stamped it.
            pass
        elif (
            state.last_idle_report_at is not None
            and now - state.last_idle_report_at < timedelta(seconds=self.idle_report_seconds)
        ):
            return None
        state.last_idle_report_at = now
        state.last_idle_reason = reason
        run = self.client.open_run(
            entity_type=subscription["entity_type"],
            subscription_id=subscription["id"],
            trigger=trigger,
            started_at=now.isoformat(),
            queue_size=0,
            detail={"driver_skill": subscription["driver_skill"], **(detail or {})},
        )
        return self.client.close_run(
            run["id"], status="skipped", finished_at=now.isoformat(), items_advanced=0
        )

    def progress_marks(self, entity_type: str) -> tuple[int, int] | None:
        """(approval facts, todos) for this entity type — monotonic counters,
        so any growth across a run is evidence something moved. Best-effort:
        None means "could not tell", never "no progress"."""
        try:
            return (
                self.client.count("/approval-records", {"entity_type": entity_type}),
                self.client.count("/todos", {"entity_type": entity_type}),
            )
        except ApiError as exc:
            log.warning("tenant %s: progress marks unavailable: %s", self.tenant_id, exc)
            return None

    def note_progress(
        self, subscription: dict, *, queue_size: int, result, advanced: int | None,
        entity_type: str, other_progress: bool = False,
    ) -> None:
        """Record whether this subscription is getting anywhere.

        Written through to the record layer rather than kept here, so the stop
        survives a restart. A failure to report is not fatal — the next pass
        reports again — but it does mean one extra run may be spent, which is the
        cheaper of the two ways to be wrong.
        """
        moved = bool(result.ok and ((advanced or 0) > 0 or other_progress))
        unmoved = 0 if moved else int(subscription.get("unmoved_runs") or 0) + 1
        park = unmoved >= self.max_unmoved_runs
        reason = None
        if park:
            reason = (
                f"{unmoved} run(s) found work and moved nothing "
                f"(queue {queue_size}); needs a look before it will run again"
            )
        try:
            self.client.report_driver_state(
                subscription["id"], unmoved_runs=unmoved, parked=park, parked_reason=reason
            )
        except ApiError as exc:
            log.warning(
                "tenant %s: could not record driver state for %s: %s",
                self.tenant_id, entity_type, exc,
            )
            return
        if park:
            # Deliberately loud. Clearing it is a person's decision because the
            # cause is usually outside the runner — a definition that routes
            # nowhere, an approver with no employee record.
            log.error(
                "tenant %s: parked %s after %d run(s) that moved nothing (queue %d) — "
                "publish the next definition, or PATCH the subscription with clear_park, "
                "once the cause is fixed",
                self.tenant_id, entity_type, unmoved, queue_size,
            )
