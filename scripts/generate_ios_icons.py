"""Generate opaque 1024x1024 AppIcon for iOS/iPhone from static/icon.png."""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SRC_ICON = ROOT / "static" / "icon.png"
ASSETS_DIR = ROOT / "ios" / "App" / "Assets.xcassets"
APPICON_DIR = ASSETS_DIR / "AppIcon.appiconset"


def generate_ios_icons() -> None:
    if not SRC_ICON.is_file():
        raise FileNotFoundError(f"Source icon not found: {SRC_ICON}")

    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    APPICON_DIR.mkdir(parents=True, exist_ok=True)

    fg = Image.open(SRC_ICON).convert("RGBA").resize((1024, 1024), Image.Resampling.LANCZOS)
    bg = Image.new("RGBA", (1024, 1024), (7, 9, 14, 255))
    bg.alpha_composite(fg)
    bg.convert("RGB").save(APPICON_DIR / "AppIcon-1024.png", format="PNG")

    (ASSETS_DIR / "Contents.json").write_text(
        json.dumps({"info": {"author": "xcode", "version": 1}}, indent=2) + "\n",
        encoding="utf-8",
    )
    (APPICON_DIR / "Contents.json").write_text(
        json.dumps(
            {
                "images": [
                    {
                        "filename": "AppIcon-1024.png",
                        "idiom": "universal",
                        "platform": "ios",
                        "size": "1024x1024",
                    }
                ],
                "info": {"author": "xcode", "version": 1},
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"Generated iOS AppIcon in {APPICON_DIR}")


if __name__ == "__main__":
    generate_ios_icons()
