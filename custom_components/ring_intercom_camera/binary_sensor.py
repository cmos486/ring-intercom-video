"""Binary sensor exposing whether a live view session is open.

Requested in issue #5. The device has a single analog capture path, so knowing
when a browser is streaming lets automations avoid competing with it — and
makes a leaked session count visible instead of silently pinning snapshots to
the cache.

Reports browser live-view sessions only. The server-side snapshot session is
short-lived and internal; including it would make this flap on every
entity-picture refresh.
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

from .session import LiveSessionTracker, get_session_tracker

_LOGGER = logging.getLogger(__name__)


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Set up the live-session binary sensors."""
    ring_entries = hass.config_entries.async_entries("ring")
    if not ring_entries:
        return

    entities = []
    for entry in ring_entries:
        ring_data = getattr(entry, "runtime_data", None)
        if ring_data is None:
            continue

        try:
            for device in ring_data.devices.other:
                if device.kind == "intercom_handset_video":
                    entities.append(
                        RingIntercomLiveSession(
                            device, get_session_tracker(hass, device.device_api_id)
                        )
                    )
        except Exception:
            _LOGGER.exception("Error discovering Ring Intercom devices")

    if entities:
        async_add_entities(entities)


class RingIntercomLiveSession(BinarySensorEntity):
    """True while at least one browser holds a live view of the intercom."""

    _attr_should_poll = False
    _attr_device_class = BinarySensorDeviceClass.RUNNING

    def __init__(self, device, sessions: LiveSessionTracker) -> None:
        """Initialize the sensor."""
        self._device = device
        self._sessions = sessions
        self._attr_name = f"{device.name} Live Session"
        self._attr_unique_id = f"ring_intercom_live_session_{device.device_api_id}"

    async def async_added_to_hass(self) -> None:
        """Subscribe to session changes."""
        self.async_on_remove(
            self._sessions.add_listener(self._handle_session_change)
        )

    @callback
    def _handle_session_change(self) -> None:
        """Write the new state when a session opens or closes."""
        self.async_write_ha_state()

    @property
    def is_on(self) -> bool:
        """Return True while a browser live view is open."""
        return self._sessions.active

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose the count, which is what mutual-exclusion logic wants.

        A wallpanel permanently displaying the intercom card holds a session
        open indefinitely, so a naive "act only when idle" automation will
        never fire. That is the hardware being honest: one signal, one
        consumer at a time.
        """
        return {
            "device_id": self._device.device_api_id,
            "session_count": self._sessions.count,
        }
