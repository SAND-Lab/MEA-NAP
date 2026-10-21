"""Make the app icons (.ico for Windows, .icns for macOS) from the GUI logo.

The logo is wide; an icon is square and mostly seen at 16-64 px, where the
wordmark would be unreadable. So the icon is the logo's network-drawn "N" on a
white rounded square. Run by the build (see ``build_app.py``); writes into
``packaging/build/``.
"""

from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
LOGO = ROOT / "src" / "meanap" / "gui" / "assets" / "mea-nap-logo.png"
OUT = Path(__file__).resolve().parent / "build"

#: The "N" and its network, in the logo's pixel coordinates.
N_BOX = (465, 415, 705, 655)
SIZE = 1024


def _glyph() -> Image.Image:
    """The "N" alone: its yellow and green, without the neighbouring letters' blue
    and the cartoon neurons' grey that overlap the crop."""
    import numpy as np

    px = np.asarray(Image.open(LOGO).convert("RGBA").crop(N_BOX)).copy()
    r, g, b = (px[..., i].astype(int) for i in range(3))
    keep = (r - b > 60) | (g - b > 60)   # yellow and green; not blue, not grey
    px[~keep, 3] = 0
    return Image.fromarray(px)


def icon_image() -> Image.Image:
    glyph = _glyph()
    canvas = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    # macOS icons sit inside ~80% of their canvas with a rounded-square body.
    margin = SIZE // 10
    ImageDraw.Draw(canvas).rounded_rectangle(
        (margin, margin, SIZE - margin, SIZE - margin),
        radius=SIZE // 5, fill=(255, 255, 255, 255),
        outline=(210, 214, 220, 255), width=SIZE // 128)
    inner = SIZE - 2 * margin - SIZE // 8
    glyph = glyph.resize((inner, inner), Image.LANCZOS)
    offset = (SIZE - inner) // 2
    canvas.alpha_composite(glyph, (offset, offset))
    return canvas


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    img = icon_image()
    img.save(OUT / "icon.png")
    img.save(OUT / "icon.ico", sizes=[(s, s) for s in (16, 24, 32, 48, 64, 128, 256)])
    img.save(OUT / "icon.icns")
    print(f"icons -> {OUT}")


if __name__ == "__main__":
    main()
