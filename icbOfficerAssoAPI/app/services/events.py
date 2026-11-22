"""In-process change notifications and the live event log.

* `notify()`      — "something changed": open SSE connections re-send the results.
* `publish(...)`  — a named event (e.g. one processed ballot) that viewers should
                    receive exactly once, in order.  Kept in a bounded log so a
                    stream that wakes up late still gets everything it missed.
"""

import asyncio
from collections import deque
from typing import Any


class ChangeNotifier:
    def __init__(self) -> None:
        self._version = 0
        self._seq = 0
        self._events: deque[tuple[int, str, Any]] = deque(maxlen=500)
        self._waiters: set[asyncio.Event] = set()

    @property
    def version(self) -> int:
        return self._version

    @property
    def last_seq(self) -> int:
        return self._seq

    def notify(self) -> None:
        """Signal that dashboard data changed. Safe to call from any coroutine."""
        self._version += 1
        for waiter in list(self._waiters):
            waiter.set()

    def publish(self, kind: str, data: Any) -> int:
        """Append a live event (returns its sequence number) and wake listeners."""
        self._seq += 1
        self._events.append((self._seq, kind, data))
        self.notify()
        return self._seq

    def events_after(self, seq: int) -> list[tuple[int, str, Any]]:
        return [item for item in self._events if item[0] > seq]

    def latest(self, kind: str, election_id: int) -> Any | None:
        """The most recent `kind` event for an election (a screen opened mid-count shows it)."""
        for _, event_kind, data in reversed(self._events):
            if event_kind == kind and isinstance(data, dict) and data.get("election_id") == election_id:
                return data
        return None

    async def wait_for_change(self, last_seen_version: int, timeout: float) -> bool:
        """Wait until the version moves past `last_seen_version` or `timeout` elapses."""
        if self._version != last_seen_version:
            return True
        waiter = asyncio.Event()
        self._waiters.add(waiter)
        try:
            await asyncio.wait_for(waiter.wait(), timeout=timeout)
            return True
        except asyncio.TimeoutError:
            return False
        finally:
            self._waiters.discard(waiter)


notifier = ChangeNotifier()
