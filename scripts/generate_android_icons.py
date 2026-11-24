"""Generate Android launcher mipmap icons from static/icon.png."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
SRC_ICON = ROOT / "static" / "icon.png"
RES_DIR = ROOT / "android" / "app" / "src" / "main" / "res"

MIPMAP_SIZES = {
    "mipmap-mdpi": 48,
    "mipmap-hdpi": 72,
    "mipmap-xhdpi": 96,
    "mipmap-xxhdpi": 144,
    "mipmap-xxxhdpi": 192,
}


def generate_android_icons() -> None:
    if not SRC_ICON.is_file():
        raise FileNotFoundError(f"Source icon not found: {SRC_ICON}")

    base = Image.open(SRC_ICON).convert("RGBA")

    for folder, px in MIPMAP_SIZES.items():
        out_dir = RES_DIR / folder
        out_dir.mkdir(parents=True, exist_ok=True)

        square = base.resize((px, px), Image.Resampling.LANCZOS)
        square.save(out_dir / "ic_launcher.png", format="PNG")

        mask = Image.new("L", (px, px), 0)
        ImageDraw.Draw(mask).ellipse((2, 2, px - 3, px - 3), fill=255)
        round_icon = Image.new("RGBA", (px, px), (0, 0, 0, 0))
        round_icon.paste(square, (0, 0), mask)
        round_icon.save(out_dir / "ic_launcher_round.png", format="PNG")

    print(f"Generated Android launcher icons in {RES_DIR}")


if __name__ == "__main__":
    generate_android_icons()
