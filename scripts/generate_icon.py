"""Generate iOS Liquid Glass rounded-square icons (.png and .ico) for !Download."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


def _rounded_mask(size: int, radius: int) -> Image.Image:
    mask = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle((0, 0, size - 1, size - 1), radius=radius, fill=255)
    return mask


def generate_icons() -> None:
    STATIC_DIR.mkdir(parents=True, exist_ok=True)
    size = 512
    pad = 24
    tile = size - pad * 2
    radius = 112

    # Base transparent canvas
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))

    # Subtle ambient drop shadow under the glass tile
    shadow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow)
    shadow_draw.rounded_rectangle(
        (pad, pad + 10, size - pad, size - pad + 10),
        radius=radius,
        fill=(4, 10, 24, 150),
    )
    shadow = shadow.filter(ImageFilter.GaussianBlur(14))
    canvas.alpha_composite(shadow)

    # Glass tile gradient (deep obsidian slate with cool steel-blue top tint)
    tile_img = Image.new("RGBA", (tile, tile), (0, 0, 0, 0))
    tile_px = tile_img.load()
    for y in range(tile):
        t = y / max(1, tile - 1)
        r = int(28 * (1 - t) + 11 * t)
        g = int(38 * (1 - t) + 16 * t)
        b = int(58 * (1 - t) + 28 * t)
        for x in range(tile):
            # Subtle radial sheen near upper-left
            dx = (x / tile) - 0.32
            dy = (y / tile) - 0.20
            glow = max(0.0, 1.0 - (dx * dx + dy * dy) * 2.2)
            rr = min(255, int(r + glow * 34))
            gg = min(255, int(g + glow * 52))
            bb = min(255, int(b + glow * 86))
            tile_px[x, y] = (rr, gg, bb, 255)

    mask = _rounded_mask(tile, radius)
    tile_masked = Image.new("RGBA", (tile, tile), (0, 0, 0, 0))
    tile_masked.paste(tile_img, (0, 0), mask)
    canvas.alpha_composite(tile_masked, (pad, pad))

    # Top inner liquid specular rim & glass refraction arc
    specular = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    spec_draw = ImageDraw.Draw(specular)
    spec_draw.rounded_rectangle(
        (pad + 2, pad + 2, size - pad - 2, size - pad - 2),
        radius=radius - 2,
        outline=(255, 255, 255, 95),
        width=4,
    )
    spec_draw.arc(
        (pad - 40, pad - 120, size - pad + 40, pad + 185),
        start=15,
        end=165,
        fill=(210, 235, 255, 52),
        width=36,
    )
    tile_only_mask = Image.new("L", (size, size), 0)
    tile_only_mask.paste(mask, (pad, pad))
    specular_clipped = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    specular_clipped.paste(specular, (0, 0), tile_only_mask)
    canvas.alpha_composite(specular_clipped)

    # Crisp silver-blue exclamation + download arrow glyph
    glyph = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    g_draw = ImageDraw.Draw(glyph)

    # Soft blue glow behind glyph
    glow_layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow_layer)
    cx = size // 2
    glow_draw.ellipse((cx - 110, 120, cx + 110, 390), fill=(42, 148, 255, 95))
    glow_layer = glow_layer.filter(ImageFilter.GaussianBlur(28))
    canvas.alpha_composite(glow_layer)

    # Exclamation-styled arrow shaft (wide rounded pill tapering slightly)
    shaft_color = (242, 247, 255, 255)
    accent_color = (96, 178, 255, 255)

    # Upper "!" bar + arrow shaft
    g_draw.rounded_rectangle((cx - 26, 118, cx + 26, 294), radius=26, fill=shaft_color)

    # Smooth chevron head forming arrow tip
    chevron = [
        (cx - 88, 248),
        (cx - 56, 218),
        (cx, 274),
        (cx + 56, 218),
        (cx + 88, 248),
        (cx, 336),
    ]
    g_draw.polygon(chevron, fill=shaft_color)

    # Luminous base dot / tray bar (reminiscent of "!" dot + download tray)
    g_draw.rounded_rectangle((cx - 94, 360, cx + 94, 394), radius=17, fill=accent_color)
    # Center bright highlight inside base bar
    g_draw.rounded_rectangle((cx - 22, 363, cx + 22, 391), radius=14, fill=shaft_color)

    canvas.alpha_composite(glyph)

    png_path = STATIC_DIR / "icon.png"
    ico_path = STATIC_DIR / "icon.ico"

    canvas.save(png_path, format="PNG")
    canvas.save(
        ico_path,
        format="ICO",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    print(f"Generated {png_path} and {ico_path}")


if __name__ == "__main__":
    generate_icons()
