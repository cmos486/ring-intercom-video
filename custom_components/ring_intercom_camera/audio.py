"""Per-device audio policy for live-view sessions.

Ring routes the intercom's incoming audio to whichever WebRTC session asks
for it (live_view audio_enabled=true + camera_options stealth_mode=false,
what ring-client-api calls activateCameraSpeaker). While that is the case
the physical handset still shows video but its speaker is silent.

AudioState holds, per device, whether live views may take the audio. It is
keyed by device_api_id in a module-level registry rather than hass.data
because the RingOther methods patched in __init__ have no hass handle.

Per-session override: an offer flagged video-only (session attribute
"a=x-video-only", or every audio m-line inactive / port 0) never takes the
audio, whatever the switch says. That is what a go2rtc/WHEP consumer uses.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable

_LOGGER = logging.getLogger(__name__)

VIDEO_ONLY_ATTR = "a=x-video-only"

_states: dict[int, "AudioState"] = {}


def get_audio_state(device_api_id: int) -> "AudioState":
    """Return the AudioState for a device, creating it on first use."""
    return _states.setdefault(device_api_id, AudioState())


class AudioState:
    """Whether live-view sessions of one device may take the intercom audio."""

    def __init__(self) -> None:
        self.enabled: bool = True  # default: current behaviour
        self._listeners: list[Callable[[], None]] = []

    def add_listener(self, listener: Callable[[], None]) -> Callable[[], None]:
        self._listeners.append(listener)

        def _remove() -> None:
            if listener in self._listeners:
                self._listeners.remove(listener)

        return _remove

    def set(self, enabled: bool) -> None:
        if enabled == self.enabled:
            return
        self.enabled = enabled
        for listener in list(self._listeners):
            listener()


def offer_wants_audio(sdp_offer: str) -> bool:
    """False for video-only offers, True otherwise (browser offers)."""
    lines = sdp_offer.replace("\r\n", "\n").split("\n")
    if VIDEO_ONLY_ATTR in lines:
        return False
    in_audio = False
    for line in lines:
        if line.startswith("m="):
            if in_audio:
                return True  # previous audio section had a live direction
            parts = line.split(" ")
            in_audio = parts[0] == "m=audio" and parts[1] != "0"
        elif in_audio and line == "a=inactive":
            in_audio = False
    return in_audio


class AudioGate:
    """Websocket proxy that applies the audio policy to Ring's signaling.

    Rewrites exactly two outgoing messages:
    - live_view       -> stream_options.audio_enabled = audio
    - camera_options  -> stealth_mode = not audio
    Everything else passes through untouched; reads are delegated.
    """

    def __init__(self, ws, audio: bool) -> None:
        self._ws = ws
        self.audio = audio

    async def send(self, data):
        try:
            msg = json.loads(data)
            method = msg.get("method")
            if method == "live_view":
                msg["body"]["stream_options"]["audio_enabled"] = self.audio
                data = json.dumps(msg)
                _LOGGER.debug(
                    "live_view sent with stream_options=%s",
                    msg["body"]["stream_options"],
                )
            elif method == "camera_options":
                msg["body"]["stealth_mode"] = not self.audio
                data = json.dumps(msg)
                _LOGGER.debug("camera_options sent as %s", msg["body"])
        except (ValueError, KeyError, TypeError):
            pass
        return await self._ws.send(data)

    def __getattr__(self, name):
        return getattr(self._ws, name)

    def __aiter__(self):
        return self._ws.__aiter__()


async def apply_audio_live(stream, audio: bool) -> bool:
    """Switch audio on/off on an already running session, no renegotiation.

    ring-client-api sends stream_options and camera_options as session
    messages after activate_session, so the device accepts them while the
    session runs. The browser's audio transceiver is recvonly from the start;
    it simply plays whatever RTP arrives.
    """
    ws = stream.websocket
    if ws is None or not stream.is_alive or not stream.session_id:
        return False
    if isinstance(ws, AudioGate):
        ws.audio = audio
    msgs = [
        ("stream_options", {"audio_enabled": audio, "video_enabled": True}),
        ("camera_options", {"stealth_mode": not audio}),
    ]
    if not audio:
        # Disabling: release the device speaker path first, then stop the
        # RTP. The device honours stream_options reliably mid-session but
        # stealth_mode only sometimes; sending it first and once more after
        # a short delay raises the odds. Known limitation: occasionally the
        # handset only gets its audio back when the session ends.
        msgs.reverse()
    for method, body in msgs:
        await ws.send(json.dumps(stream.get_session_message(method, body)))
    if not audio:
        await asyncio.sleep(1)
        if stream.is_alive and stream.websocket is not None:
            await ws.send(json.dumps(
                stream.get_session_message("camera_options", {"stealth_mode": True})
            ))
    _LOGGER.debug("session %s: audio switched %s", stream.session_id, "on" if audio else "off")
    return True
