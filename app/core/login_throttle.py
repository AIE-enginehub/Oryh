"""Progressive backoff on failed logins, per account and per source address.

Neither login surface had any. A password could be guessed as fast as the
process would answer, and the only thing standing in front of it was whatever
the gateway happened to do — which is an IP token bucket, and an IP token
bucket does not notice one address trying one password against ten thousand
accounts, or ten thousand addresses trying ten thousand passwords against one.
The 2026-08-16 architecture review's 5.1.

Two keys, because the two attacks are different shapes:

  account   one account under sustained guessing, from anywhere
  address   one address working through a list of accounts

In-process and therefore per-replica. That is a real limitation and it is
still worth having: with N replicas an attacker gets N times the budget, which
is a constant factor, not the difference between bounded and unbounded. A
shared store is the right answer when there is one to share; there is not, and
waiting for it means shipping nothing.

Deliberately NOT applied to a successful password: the delay is a consequence
of failures, and a legitimate user who finally types the right password gets in
and the counter is cleared. Locking an account outright would hand anyone who
knows an email address a denial-of-service button.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

# Failures before the first delay. Below this a person mistyping their password
# notices nothing, which is most of what these counters see.
FREE_ATTEMPTS = 5

# Doubling from one second, capped. The cap matters: an uncapped exponential
# reaches "next Tuesday" in twenty failures and becomes the denial of service
# it was meant to prevent.
BASE_DELAY_SECONDS = 1.0
MAX_DELAY_SECONDS = 60.0

# A counter nobody has touched for this long is forgotten. Also what keeps the
# store bounded without an eviction policy: attackers stop, and typos are rare.
WINDOW_SECONDS = 900.0

# A hard ceiling on distinct keys, so a spray across a million addresses cannot
# grow this without limit. When it is hit the oldest are dropped, which favours
# the active attacker slightly and is better than unbounded memory.
MAX_KEYS = 10_000


@dataclass
class _Counter:
    failures: int = 0
    last_seen: float = 0.0


@dataclass
class LoginThrottle:
    _counters: dict[str, _Counter] = field(default_factory=dict)

    def _prune(self, now: float) -> None:
        stale = [key for key, counter in self._counters.items()
                 if now - counter.last_seen > WINDOW_SECONDS]
        for key in stale:
            del self._counters[key]
        if len(self._counters) > MAX_KEYS:
            oldest = sorted(self._counters.items(), key=lambda item: item[1].last_seen)
            for key, _ in oldest[: len(self._counters) - MAX_KEYS]:
                del self._counters[key]

    def _delay_for(self, key: str, now: float) -> float:
        counter = self._counters.get(key)
        if counter is None or now - counter.last_seen > WINDOW_SECONDS:
            return 0.0
        over = counter.failures - FREE_ATTEMPTS
        if over <= 0:
            return 0.0
        delay = min(BASE_DELAY_SECONDS * (2 ** (over - 1)), MAX_DELAY_SECONDS)
        remaining = delay - (now - counter.last_seen)
        return max(0.0, remaining)

    def retry_after(self, keys: list[str], *, now: float | None = None) -> float:
        """Seconds the caller must wait, 0 when it may proceed.

        The longest of the keys: an address that has earned a delay does not
        get to reset it by switching to a fresh account, and an account under
        attack is protected from every address at once.
        """
        now = time.monotonic() if now is None else now
        return max((self._delay_for(key, now) for key in keys), default=0.0)

    def record_failure(self, keys: list[str], *, now: float | None = None) -> None:
        now = time.monotonic() if now is None else now
        self._prune(now)
        for key in keys:
            counter = self._counters.get(key)
            if counter is None or now - counter.last_seen > WINDOW_SECONDS:
                counter = _Counter()
                self._counters[key] = counter
            counter.failures += 1
            counter.last_seen = now

    def record_success(self, keys: list[str]) -> None:
        for key in keys:
            self._counters.pop(key, None)

    def clear(self) -> None:
        self._counters.clear()


throttle = LoginThrottle()


def login_keys(email: str | None, client_host: str | None) -> list[str]:
    """The two keys for one attempt. Email is lowercased because addresses are
    not case-sensitive and an attacker alternating case would otherwise get a
    fresh budget per spelling."""
    keys = []
    if email:
        keys.append(f"account:{email.strip().lower()}")
    if client_host:
        keys.append(f"address:{client_host}")
    return keys
