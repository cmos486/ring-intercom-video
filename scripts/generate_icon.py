"""Generate brand icons for the Ring Intercom Video integration.

Design: a camera lens (concentric circles) wrapped by a Ring-blue outer ring,
on a white rounded-square background. Produces icon.png (256) and icon@2x.png (512).

Usage:
    python3 scripts/generate_icon.py
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

RING_BLUE = (25, 152, 213, 255)
RING_BLUE_DARK = (15, 110, 160, 255)
LENS_DARK = (20, 28, 40, 255)
LENS_MID = (45, 65, 90, 255)
LENS_HIGHLIGHT = (200, 230, 255, 230)
WHITE = (255, 255, 255, 255)

OUT_DIR = Path(__file__).resolve().parent.parent / "custom_components" / "ring_intercom_camera" / "brand"


def _rounded_square(size: int, radius_ratio: float = 0.22, fill=WHITE) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    r = int(size * radius_ratio)
    d.rounded_rectangle((0, 0, size - 1, size - 1), radius=r, fill=fill)
    return img


def _circle(draw: ImageDraw.ImageDraw, cx: int, cy: int, r: int, fill, outline=None, width: int = 0) -> None:
    draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=fill, outline=outline, width=width)


def build_icon(size: int) -> Image.Image:
    # Transparent background — HA brand icons should not have a white square baked in.
    bg = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(bg)

    cx = cy = size // 2

    # Outer Ring-blue ring
    outer_r = int(size * 0.46)
    ring_thickness = max(2, int(size * 0.07))
    d.ellipse(
        (cx - outer_r, cy - outer_r, cx + outer_r, cy + outer_r),
        outline=RING_BLUE,
        width=ring_thickness,
    )

    # Inner subtle darker ring (depth)
    inner_ring_r = outer_r - ring_thickness
    d.ellipse(
        (cx - inner_ring_r, cy - inner_ring_r, cx + inner_ring_r, cy + inner_ring_r),
        outline=RING_BLUE_DARK,
        width=max(1, int(size * 0.008)),
    )

    # Lens body
    lens_outer_r = int(size * 0.34)
    _circle(d, cx, cy, lens_outer_r, fill=LENS_MID)

    lens_mid_r = int(size * 0.27)
    _circle(d, cx, cy, lens_mid_r, fill=LENS_DARK)

    lens_inner_r = int(size * 0.18)
    _circle(d, cx, cy, lens_inner_r, fill=(10, 14, 22, 255))

    # Aperture reflection (Ring blue accent inside lens)
    accent_r = int(size * 0.10)
    _circle(d, cx, cy, accent_r, fill=RING_BLUE)

    # Highlight (top-left specular)
    hl_layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    hl_draw = ImageDraw.Draw(hl_layer)
    hl_r = int(size * 0.055)
    hl_cx = cx - int(size * 0.07)
    hl_cy = cy - int(size * 0.07)
    hl_draw.ellipse(
        (hl_cx - hl_r, hl_cy - hl_r, hl_cx + hl_r, hl_cy + hl_r),
        fill=LENS_HIGHLIGHT,
    )
    hl_layer = hl_layer.filter(ImageFilter.GaussianBlur(radius=max(1, size * 0.004)))
    bg.alpha_composite(hl_layer)

    # Tiny "REC" dot at top — subtle indicator of video
    rec_r = max(2, int(size * 0.022))
    rec_cx = cx + int(outer_r * 0.62)
    rec_cy = cy - int(outer_r * 0.62)
    d.ellipse(
        (rec_cx - rec_r, rec_cy - rec_r, rec_cx + rec_r, rec_cy + rec_r),
        fill=(220, 50, 50, 255),
    )

    return bg


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    icon_256 = build_icon(256)
    icon_512 = build_icon(512)

    p1 = OUT_DIR / "icon.png"
    p2 = OUT_DIR / "icon@2x.png"
    icon_256.save(p1, "PNG", optimize=True)
    icon_512.save(p2, "PNG", optimize=True)

    print(f"Wrote {p1} ({p1.stat().st_size} bytes)")
    print(f"Wrote {p2} ({p2.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
