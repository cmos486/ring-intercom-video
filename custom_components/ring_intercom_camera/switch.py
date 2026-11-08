"""Switch deciding whether live views take the intercom audio.

On (default): current behaviour — a live view (companion card, browser) gets
the visitor's audio, and the physical handset's speaker goes silent while
the session is open.

Off: live views are video-only. The handset keeps hearing the visitor, so
the picture can be shown on a TV or wallpanel while the conversation happens
on the handset. Toggling while a session is open applies immediately: Ring
accepts stream_options / camera_options on a running session.
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

from .audio import AudioState, apply_audio_live, get_audio_state

_LOGGER = logging.getLogger(__name__)


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Set up the audio switches."""
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
                        RingIntercomAudioSwitch(
                            device, get_audio_state(device.device_api_id)
                        )
                    )
        except Exception:
            _LOGGER.exception("Error discovering Ring Intercom devices")

    if entities:
        async_add_entities(entities)


class RingIntercomAudioSwitch(SwitchEntity, RestoreEntity):
    """Whether live-view sessions may take the intercom audio."""

    _attr_should_poll = False
    _attr_icon = "mdi:volume-high"

    def __init__(self, device, audio: AudioState) -> None:
        """Initialize the switch."""
        self._device = device
        self._audio = audio
        self._attr_name = f"{device.name} Audio"
        self._attr_unique_id = f"ring_intercom_audio_{device.device_api_id}"

    async def async_added_to_hass(self) -> None:
        """Restore the last state and subscribe to changes."""
        last = await self.async_get_last_state()
        if last is not None and last.state in ("on", "off"):
            self._audio.set(last.state == "on")
        self.async_on_remove(self._audio.add_listener(self._handle_change))

    @callback
    def _handle_change(self) -> None:
        self.async_write_ha_state()

    @property
    def is_on(self) -> bool:
        return self._audio.enabled

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"device_id": self._device.device_api_id}

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._set(False)

    async def _set(self, enabled: bool) -> None:
        self._audio.set(enabled)
        # push to running sessions (registered by the patched RingOther)
        streams = getattr(self._device, "_webrtc_streams", {})
        for session_id, stream in list(streams.items()):
            try:
                if await apply_audio_live(stream, enabled):
                    _LOGGER.info(
                        "%s: audio %s on running session %s",
                        self._device.name, "enabled" if enabled else "disabled", session_id,
                    )
            except Exception:
                _LOGGER.exception("Failed to switch audio on session %s", session_id)
