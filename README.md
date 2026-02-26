# Ring Intercom Video Camera

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)

Home Assistant custom component that adds a **WebRTC live-stream camera** for the **Ring Intercom Handset Video** (2024/2025 model with camera).

The official Ring integration only exposes lock and ding entities for intercoms. This component adds the missing camera entity with native WebRTC live view — the same streaming technology Ring uses for its doorbell cameras.

## Why?

The Ring Intercom Video replaces analog intercoms (e.g. Fermax, Tegui, Comelit) and includes a camera that digitizes the analog CVBS video signal. However:

- The official HA Ring integration doesn't create camera entities for intercoms
- Standard Ring snapshot/recording APIs don't work for this device (they require Ring Protect)
- The device **does** support WebRTC live view, using the exact same protocol as Ring doorbells

This component bridges that gap.

## How it works

```
Lovelace (browser)  <-->  Camera Entity  <-->  Ring Signaling  <-->  Ring Intercom
   [WebRTC peer]         [SDP/ICE bridge]      [WebSocket]          [720x576 H.264]
```

1. You open the camera card in your dashboard
2. Your browser creates a WebRTC connection (SDP offer)
3. This component forwards it to Ring's signaling server via `python-ring-doorbell`
4. Ring returns the SDP answer and ICE candidates
5. Your browser connects directly to the Ring device — live video at ~25fps

**No server-side video processing.** No `aiortc`, no `ffmpeg`, no `Pillow`. The browser handles all the WebRTC decoding natively.

## Device compatibility

| Device | Kind | Supported |
|--------|------|-----------|
| Ring Intercom Handset Video (2024/2025) | `intercom_handset_video` | Yes |
| Ring Intercom (audio only) | `intercom_handset_audio` | No (no camera) |

Tested with Fermax 3304/99139 (5-wire) as the predecessor analog intercom.

## Important: camera behavior

The analog intercom camera (Fermax CVBS) only outputs video when activated:
- **During a ding** — someone presses the call button on the street panel
- **Manual activation** — pressing the camera button on the indoor handset

When the camera is not active, the stream shows a black image. This is normal — it's how analog intercoms work.

**Tip:** If you have a Zigbee/Z-Wave relay connected to the camera button on your indoor unit, you can trigger the camera via HA automation before viewing the stream.

## Installation

### HACS (recommended)

1. Open HACS in Home Assistant
2. Go to **Integrations** > click the **three dots menu** (top right) > **Custom repositories**
3. Add this URL: `https://github.com/cmos486/ring-intercom-video`
4. Category: **Integration**
5. Click **Add**, then search for "Ring Intercom Video Camera" and download it
6. Restart Home Assistant

### Manual

1. Copy the `custom_components/ring_intercom_camera/` folder to your HA `custom_components/` directory
2. Restart Home Assistant

## Configuration

Add to your `configuration.yaml`:

```yaml
ring_intercom_camera:
```

Restart Home Assistant. The component will auto-discover `intercom_handset_video` devices from your existing Ring integration.

A new camera entity will appear: `camera.<device_name>_camera`

## Prerequisites

- The official **[Ring](https://www.home-assistant.io/integrations/ring/)** integration must be configured and working in HA
- Your Ring account must have an Intercom Handset Video device
- HACS installed (for HACS installation method)

## Authentication

**You don't need to configure any credentials.** This component reuses the authentication from the official Ring integration that is already set up in your Home Assistant.

Under the hood:
- The official Ring integration handles all login/OAuth/2FA via its config flow (Settings > Integrations > Ring)
- This component declares `ring` as a dependency and accesses the already-authenticated Ring API client from `hass.data["ring"]`
- No tokens, passwords, or API keys are stored or managed by this component

If your Ring integration is working (you can see your intercom's lock and ding entities), this component will work too — no extra login needed.

## Dashboard setup

Add the camera to any dashboard using a Picture Entity card or the built-in camera card. When you click the live view button, WebRTC streaming will start automatically.

## Technical details

This component:
1. **Monkey-patches `RingOther`** (the intercom class in `python-ring-doorbell`) to add WebRTC streaming methods — the same methods that `RingDoorBell` has for doorbell cameras
2. **Creates a camera entity** with `CameraEntityFeature.STREAM` that implements the HA WebRTC signaling interface (`async_handle_async_webrtc_offer`, `async_on_webrtc_candidate`, `close_webrtc_session`)
3. Uses `python-ring-doorbell`'s `RingWebRtcStream` for all signaling — no custom WebSocket/HTTP code needed

## Troubleshooting

**No camera entity appears after restart**
- Check that the official Ring integration is working (Settings > Integrations > Ring)
- Verify your device is an `intercom_handset_video` (not `intercom_handset_audio`)
- Check HA logs for `ring_intercom_camera` entries

**Live view shows black/no video**
- This is expected when the Fermax camera is not active
- The analog camera only outputs video during a ding or manual activation
- Try pressing the call button on the street panel, then open the live view

**Live view button doesn't appear**
- Make sure you're using a browser that supports WebRTC (Chrome, Firefox, Safari)
- Check that `CameraEntityFeature.STREAM` is listed in the entity attributes

**Ring Protect subscription**
- **Not required.** This component uses WebRTC live view which works without any subscription
- Snapshots and recordings stored in the cloud do require Ring Protect, but this component doesn't use those APIs

## Attribution

This integration builds on top of:

- **[python-ring-doorbell](https://github.com/python-ring-doorbell/python-ring-doorbell)** (LGPL-3.0) — Python library for Ring devices. This component monkey-patches its `RingOther` class at runtime to add WebRTC stream support for intercom devices.
- **[Home Assistant Ring Integration](https://github.com/home-assistant/core/tree/dev/homeassistant/components/ring)** (Apache 2.0) — The camera entity's WebRTC signaling interface is modeled after the official Ring camera implementation in HA Core.

## License

[Apache License 2.0](LICENSE)

Copyright 2026 Kilian Ubeda Cano
