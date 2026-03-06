#!/usr/bin/env python3
"""
Generate app icons for File Organizer desktop app (Tauri).

Produces all required icon formats:
  - icon.png          : 512x512 master PNG
  - icon.ico          : Windows (multi-size: 256, 64, 48, 32, 16)
  - icon.icns         : macOS (via iconutil if available, else PNG set)
  - icon_256x256.png  : Linux
  - icon_128x128.png  : Linux
  - icon_64x64.png    : Linux
  - icon_32x32.png    : Linux
"""

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    from PIL import Image, ImageDraw
except ImportError:
    print("ERROR: Pillow is required. Install with: pip install Pillow")
    sys.exit(1)


# ── Design constants ──────────────────────────────────────────────────────────
BG_COLOR = (37, 99, 235)  # #2563EB  Tailwind blue-600
BG_COLOR_DARK = (29, 78, 216)  # #1D4ED8  slightly darker for depth
FOLDER_COLOR = (255, 255, 255)  # white folder body
FOLDER_TAB_COLOR = (191, 219, 254)  # light blue folder tab
ARROW_COLOR = (16, 185, 129)  # #10B981 green accent arrow

OUTPUT_DIR = Path(__file__).parent.parent / "desktop" / "icons"


def draw_icon(size: int) -> Image.Image:
    """
    Draw a stylised folder-with-arrow icon at the given square pixel size.

    Layout (all values relative to `size`):
      • Rounded-rectangle blue background
      • White folder body with a small tab
      • Green downward-arrow inside folder (represents organisation / sorting)
    """
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    s = size  # alias for brevity
    pad = s * 0.06  # outer padding

    # ── Background rounded rect ───────────────────────────────────────────────
    r = s * 0.18  # corner radius
    draw.rounded_rectangle(
        [pad, pad, s - pad, s - pad],
        radius=r,
        fill=BG_COLOR,
    )

    # Subtle gradient effect: draw a slightly lighter strip at the top
    draw.rounded_rectangle(
        [pad, pad, s - pad, s * 0.52],
        radius=r,
        fill=BG_COLOR_DARK,
    )
    # Re-draw bottom to restore full bg (simple two-tone approach)
    draw.rectangle(
        [pad, s * 0.38, s - pad, s - pad],
        fill=BG_COLOR,
    )

    # ── Folder tab (small rounded rect above folder body) ─────────────────────
    fx1 = s * 0.20  # folder left
    fx2 = s * 0.80  # folder right
    fy1 = s * 0.30  # folder top (body)
    fy2 = s * 0.76  # folder bottom

    tab_w = (fx2 - fx1) * 0.42
    tab_h = s * 0.07
    tab_r = tab_h * 0.5
    draw.rounded_rectangle(
        [fx1, fy1 - tab_h, fx1 + tab_w, fy1 + tab_r],
        radius=tab_r,
        fill=FOLDER_TAB_COLOR,
    )

    # ── Folder body ───────────────────────────────────────────────────────────
    folder_r = s * 0.04
    draw.rounded_rectangle(
        [fx1, fy1, fx2, fy2],
        radius=folder_r,
        fill=FOLDER_COLOR,
    )

    # ── Arrow (pointing down = organise / sort) ───────────────────────────────
    # Arrow shaft
    cx = s * 0.50  # center x
    shaft_w = s * 0.08
    shaft_top = fy1 + (fy2 - fy1) * 0.14
    shaft_bot = fy1 + (fy2 - fy1) * 0.60
    draw.rectangle(
        [cx - shaft_w / 2, shaft_top, cx + shaft_w / 2, shaft_bot],
        fill=ARROW_COLOR,
    )
    # Arrow head (triangle pointing down)
    head_w = s * 0.22
    head_h = s * 0.16
    head_top = shaft_bot - s * 0.01  # slight overlap
    head_bot = head_top + head_h
    draw.polygon(
        [
            (cx, head_bot),
            (cx - head_w / 2, head_top),
            (cx + head_w / 2, head_top),
        ],
        fill=ARROW_COLOR,
    )

    return img


def save_png(img: Image.Image, path: Path) -> None:
    img.save(str(path), "PNG")
    print(f"  Saved: {path.relative_to(OUTPUT_DIR.parent.parent)}")


def generate_master(size: int = 512) -> Image.Image:
    return draw_icon(size)


def generate_all_pngs(master: Image.Image) -> dict[int, Image.Image]:
    """Return dict of {size: Image} for all required sizes."""
    sizes = [1024, 512, 256, 128, 64, 48, 32, 16]
    images: dict[int, Image.Image] = {512: master}
    for sz in sizes:
        if sz == 512:
            continue
        if sz > 512:
            # Draw natively at larger sizes for crisp Retina icons
            images[sz] = draw_icon(sz)
        else:
            images[sz] = master.resize((sz, sz), Image.LANCZOS)
    return images


def build_ico(images: dict[int, Image.Image], out: Path) -> None:
    """Create Windows .ico with multiple embedded sizes."""
    ico_sizes = [256, 64, 48, 32, 16]
    ico_imgs = [images[sz].convert("RGBA") for sz in ico_sizes if sz in images]
    ico_imgs[0].save(
        str(out),
        format="ICO",
        sizes=[(sz, sz) for sz in ico_sizes if sz in images],
        append_images=ico_imgs[1:],
    )
    print(f"  Saved: {out.relative_to(OUTPUT_DIR.parent.parent)}")


def build_icns(images: dict[int, Image.Image], out: Path) -> None:
    """
    Create macOS .icns using iconutil (macOS-only).
    Falls back to saving the 512px PNG as icon.icns if iconutil unavailable.
    """
    if shutil.which("iconutil") is None:
        # Not on macOS – save a placeholder PNG named .icns so the build
        # can substitute it later on a Mac CI runner.
        images[512].save(str(out), "PNG")
        print(
            f"  Saved (PNG fallback, iconutil not available): {out.relative_to(OUTPUT_DIR.parent.parent)}"
        )
        return

    # Build an .iconset directory then convert
    with tempfile.TemporaryDirectory() as tmpdir:
        iconset = Path(tmpdir) / "AppIcon.iconset"
        iconset.mkdir()

        # Required iconset filenames per Apple spec
        iconset_map = {
            "icon_16x16.png": 16,
            "icon_16x16@2x.png": 32,
            "icon_32x32.png": 32,
            "icon_32x32@2x.png": 64,
            "icon_128x128.png": 128,
            "icon_128x128@2x.png": 256,
            "icon_256x256.png": 256,
            "icon_256x256@2x.png": 512,
            "icon_512x512.png": 512,
            "icon_512x512@2x.png": 1024,
        }

        for filename, sz in iconset_map.items():
            img = images.get(sz)
            if img is None:
                img = draw_icon(sz)
            img.save(str(iconset / filename), "PNG")

        result = subprocess.run(
            ["iconutil", "-c", "icns", str(iconset), "-o", str(out)],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            print(f"  WARNING: iconutil failed: {result.stderr.strip()}")
            images[512].save(str(out), "PNG")
            print(f"  Saved (PNG fallback): {out.relative_to(OUTPUT_DIR.parent.parent)}")
        else:
            print(f"  Saved: {out.relative_to(OUTPUT_DIR.parent.parent)}")


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Generating icons in {OUTPUT_DIR} ...\n")

    # 1. Master 512x512 PNG
    master = generate_master(512)
    images = generate_all_pngs(master)

    # 2. Master icon.png
    save_png(master, OUTPUT_DIR / "icon.png")

    # 3. Linux PNGs
    for sz in [256, 128, 64, 32]:
        save_png(images[sz], OUTPUT_DIR / f"icon_{sz}x{sz}.png")

    # 4. Windows .ico
    build_ico(images, OUTPUT_DIR / "icon.ico")

    # 5. macOS .icns
    build_icns(images, OUTPUT_DIR / "icon.icns")

    print("\nDone! Icon files generated:")
    for f in sorted(OUTPUT_DIR.iterdir()):
        size_kb = f.stat().st_size / 1024
        print(f"  {f.name:30s}  {size_kb:6.1f} KB")


if __name__ == "__main__":
    main()
