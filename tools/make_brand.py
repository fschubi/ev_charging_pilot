"""Render the integration icon (brand/icon.png, icon@2x.png) – battery with a bolt.

Usage: .venv/bin/python tools/make_brand.py custom_components/smart_eq_charging/brand
"""

import sys
from pathlib import Path

from PIL import Image, ImageDraw


def render(size: int) -> Image.Image:
    scale = 4  # supersampling for smooth edges
    s = size * scale
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, s - 1, s - 1), radius=int(s * 0.22), fill=(14, 30, 46, 255))
    # battery body and terminal
    bx0, by0, bx1, by1 = s * 0.16, s * 0.30, s * 0.78, s * 0.70
    line = int(s * 0.045)
    d.rounded_rectangle((bx0, by0, bx1, by1), radius=int(s * 0.07), outline=(255, 255, 255, 255),
                        width=line)
    d.rounded_rectangle((bx1 + s * 0.015, s * 0.42, s * 0.86, s * 0.58), radius=int(s * 0.03),
                        fill=(255, 255, 255, 255))
    # charge level
    pad = line + s * 0.025
    d.rounded_rectangle((bx0 + pad, by0 + pad, bx0 + (bx1 - bx0) * 0.72, by1 - pad),
                        radius=int(s * 0.035), fill=(67, 160, 71, 255))
    # lightning bolt
    bolt = [(0.50, 0.18), (0.33, 0.53), (0.47, 0.53), (0.41, 0.82), (0.63, 0.43), (0.49, 0.43),
            (0.57, 0.18)]
    d.polygon([(x * s, y * s) for x, y in bolt], fill=(255, 214, 0, 255),
              outline=(14, 30, 46, 255), width=int(s * 0.02))
    return img.resize((size, size), Image.LANCZOS)


if __name__ == "__main__":
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    render(256).save(out / "icon.png")
    render(512).save(out / "icon@2x.png")
    print("ok")
