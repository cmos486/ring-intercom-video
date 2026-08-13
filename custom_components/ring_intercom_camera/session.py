"""Live-view session tracking, shared between the camera and binary_sensor platforms.

The Ring Intercom digitizes a single analog CVBS signal, so the hardware has
exactly one capture path. When a second WebRTC session is opened against the
same device while a browser is already streaming, that second session
negotiates normally and receives H.264 — but the frames carry no picture.

That is why the server-side snapshot returns an all-black JPEG whenever
someone has the live view open (issue #5): it opens its own aiortc session
alongside the browser's. The fix is to know when browser sessions are open, so
the snapshot can decline to open a competing one and serve its cache instead.

The tracker lives in hass.data rather than on either entity, so the two
platforms don't depend on each other's setup order.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from .const import DATA_SESSION_TRACKERS, DOMAIN

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant


class LiveSessionTracker:
    """Tracks open browser live-view sessions for one intercom device.

    Only browser sessions are tracked. The server-side snapshot session is
    deliberately excluded: it is short-lived and internal, and including it
    would make the exposed binary_sensor flap on every entity-picture refresh.
    """

    def __init__(self) -> None:
        """Initialize an empty tracker."""
        self._sessions: set[str] = set()
        self._listeners: list[Callable[[], None]] = []

    @property
    def active(self) -> bool:
        """Return True if at least one browser session is open."""
        return bool(self._sessions)

    @property
    def count(self) -> int:
        """Return the number of open browser sessions."""
        return len(self._sessions)

    @property
    def session_ids(self) -> list[str]:
        """Return the open session ids, for diagnostics."""
        return sorted(self._sessions)

    def add(self, session_id: str) -> None:
        """Register a browser session as open."""
        if session_id in self._sessions:
            return
        self._sessions.add(session_id)
        self._notify()

    def discard(self, session_id: str) -> None:
        """Register a browser session as closed.

        Tolerates unknown ids: HA may close a session that never got as far as
        being registered, and a double close must not raise.
        """
        if session_id not in self._sessions:
            return
        self._sessions.discard(session_id)
        self._notify()

    def add_listener(self, listener: Callable[[], None]) -> Callable[[], None]:
        """Subscribe to changes. Returns a callable that unsubscribes."""
        self._listeners.append(listener)

        def _remove() -> None:
            if listener in self._listeners:
                self._listeners.remove(listener)

        return _remove

    def _notify(self) -> None:
        """Notify listeners, isolating one listener's failure from the rest."""
        for listener in list(self._listeners):
            listener()


def get_session_tracker(
    hass: "HomeAssistant", device_api_id: int
) -> LiveSessionTracker:
    """Return the tracker for a device, creating it on first use.

    Called from both platforms during setup, so whichever runs first creates
    the tracker and the other finds the same instance.
    """
    trackers: dict[int, LiveSessionTracker] = hass.data.setdefault(
        DOMAIN, {}
    ).setdefault(DATA_SESSION_TRACKERS, {})
    return trackers.setdefault(device_api_id, LiveSessionTracker())
