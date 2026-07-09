"""Ring Intercom Video Camera integration.

Adds a WebRTC live-stream camera entity for Ring Intercom Video
(intercom_handset_video) devices. The official Ring integration only creates
lock/ding entities for intercoms; this component adds the missing camera.

Architecture:
- Hooks into the existing Ring integration's data/auth
- Monkey-patches RingOther to add WebRTC stream methods (same as RingDoorBell)
- Exposes a native HA WebRTC camera entity (browser does the WebRTC, no aiortc needed)
- When user opens the camera in Lovelace, the browser establishes WebRTC directly
"""

from __future__ import annotations

import asyncio
import importlib
import logging
import sys

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import discovery

_LOGGER = logging.getLogger(__name__)

DOMAIN = "ring_intercom_camera"
PLATFORMS = [Platform.CAMERA]

# Packages needed for server-side snapshots (async_camera_image /
# camera.snapshot). aiortc is NOT a manifest requirement and is never
# installed with dependency resolution — see _async_ensure_aiortc.
AIORTC_PACKAGES = ["aiortc", "aioice", "pylibsrtp", "pyee", "google-crc32c", "av"]


def _patch_ring_other() -> None:
    """Add WebRTC stream methods to RingOther (intercom) class.

    RingOther doesn't inherit from RingDoorBell so it lacks WebRTC methods,
    even though the intercom_handset_video hardware supports WebRTC live view
    via the exact same signaling protocol.
    """
    from ring_doorbell.other import RingOther
    from ring_doorbell.webrtcstream import RingWebRtcStream

    if hasattr(RingOther, "generate_async_webrtc_stream"):
        return  # Already patched

    def _get_streams(self):
        """Lazy-init _webrtc_streams for already-instantiated objects."""
        if not hasattr(self, "_webrtc_streams"):
            self._webrtc_streams = {}
        return self._webrtc_streams

    async def generate_async_webrtc_stream(self, sdp_offer, session_id,
                                            on_message_callback, *,
                                            keep_alive_timeout=60 * 5):
        streams = _get_streams(self)

        async def _close_callback():
            await self.close_webrtc_stream(session_id)

        stream = RingWebRtcStream(
            self._ring,
            self.device_api_id,
            on_message_callback=on_message_callback,
            keep_alive_timeout=keep_alive_timeout,
            on_close_callback=_close_callback,
        )
        streams[session_id] = stream
        await stream.generate(sdp_offer)

    async def on_webrtc_candidate(self, session_id, candidate, multi_line_index):
        streams = _get_streams(self)
        if stream := streams.get(session_id):
            await stream.on_ice_candidate(candidate, multi_line_index)

    async def close_webrtc_stream(self, session_id):
        streams = _get_streams(self)
        stream = streams.pop(session_id, None)
        if stream:
            await stream.close()

    def sync_close_webrtc_stream(self, session_id):
        streams = _get_streams(self)
        stream = streams.pop(session_id, None)
        if stream:
            stream.sync_close()
    RingOther.generate_async_webrtc_stream = generate_async_webrtc_stream
    RingOther.on_webrtc_candidate = on_webrtc_candidate
    RingOther.close_webrtc_stream = close_webrtc_stream
    RingOther.sync_close_webrtc_stream = sync_close_webrtc_stream

    _LOGGER.info("Patched RingOther with WebRTC stream methods")


async def _async_ensure_aiortc(hass: HomeAssistant) -> None:
    """Ensure aiortc is installed for server-side snapshots, SAFELY.

    aiortc pulls native deps (av/PyAV, pylibsrtp) plus cryptography/cffi.
    We must NEVER let pip resolve dependencies here: on some HA OS images
    that upgrades the shared `cffi`/`cryptography` baked into the image and
    breaks every integration using native crypto (this actually happened in
    v0.4.4). So we install ONLY aiortc's own packages with `--no-deps` —
    pip cannot touch cffi, cryptography, pyopenssl or av; it reuses HA's
    existing shared libraries.

    Runs on every startup: a fast no-op once installed, and a self-heal
    after an HA Core update recreates the container (snapshots survive
    updates with no manual reinstall). Failure only disables snapshots;
    native WebRTC live streaming is unaffected.
    """
    def _installed() -> bool:
        try:
            import aiortc  # noqa: F401
            return True
        except ImportError:
            return False

    if await hass.async_add_executor_job(_installed):
        return

    _LOGGER.info(
        "aiortc not present — installing for server-side snapshots "
        "(--no-deps; will not touch HA's shared libraries)"
    )

    for runner in (["-m", "pip"], ["-m", "uv", "pip"]):
        cmd = [sys.executable, *runner, "install", "--no-deps", *AIORTC_PACKAGES]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            out, _ = await proc.communicate()
        except FileNotFoundError:
            continue  # this installer isn't available, try the next
        except Exception:
            _LOGGER.debug("aiortc install error via %s", runner[-1], exc_info=True)
            continue

        if proc.returncode == 0:
            await hass.async_add_executor_job(importlib.invalidate_caches)
            if await hass.async_add_executor_job(_installed):
                _LOGGER.info("aiortc installed — snapshot capture enabled")
                return
        else:
            _LOGGER.debug(
                "aiortc install via %s failed (rc=%s): %s",
                runner[-1], proc.returncode,
                (out or b"").decode(errors="replace")[-500:],
            )

    _LOGGER.warning(
        "Could not install aiortc automatically — server-side snapshots are "
        "disabled (native WebRTC live streaming is unaffected). To enable "
        "them, install it manually in the HA environment: "
        "pip install --no-deps %s",
        " ".join(AIORTC_PACKAGES),
    )


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the Ring Intercom Camera component from configuration.yaml."""
    hass.data.setdefault(DOMAIN, {})

    _patch_ring_other()

    # Ensure aiortc for snapshots in the background — never blocks setup, so
    # the camera (live stream) loads immediately even if the install is slow
    # or fails.
    hass.async_create_background_task(
        _async_ensure_aiortc(hass), "ring_intercom_camera_ensure_aiortc"
    )

    hass.async_create_task(
        discovery.async_load_platform(hass, Platform.CAMERA, DOMAIN, {}, config)
    )
    return True
