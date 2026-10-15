"""Render the integration icon (brand/icon.png, icon@2x.png, logo.png, logo@2x.png):
a battery with charge level and bolt above a car silhouette.

Usage: .venv/bin/python tools/make_brand.py custom_components/ev_charging_pilot/brand
"""

import sys
from pathlib import Path

from PIL import Image, ImageDraw

BG = (14, 30, 46, 255)
WHITE = (255, 255, 255, 255)
GREEN = (67, 160, 71, 255)
YELLOW = (255, 214, 0, 255)
SUPERSAMPLE = 4


def bezier(p0, p1, p2, p3, n=24):
    """Points along a cubic Bézier curve (PIL has no curves)."""
    points = []
    for i in range(n + 1):
        t = i / n
        a, b = (1 - t) ** 3, 3 * (1 - t) ** 2 * t
        c, d = 3 * (1 - t) * t ** 2, t ** 3
        points.append((a * p0[0] + b * p1[0] + c * p2[0] + d * p3[0],
                       a * p0[1] + b * p1[1] + c * p2[1] + d * p3[1]))
    return points


def box(x0, y0, w, h):
    """Map relative coordinates of a box to canvas coordinates."""
    def point(x, y):
        return (x0 + x * w, y0 + y * h)
    return point


def draw_car(d, x0, y0, w, h, s):
    """Compact car, side view facing left, with windows and wheels."""
    p = box(x0, y0, w, h)
    body = (bezier(p(0.02, 0.92), p(0.00, 0.80), p(0.00, 0.66), p(0.06, 0.58))      # front
            + bezier(p(0.06, 0.58), p(0.14, 0.52), p(0.26, 0.48), p(0.32, 0.46))    # bonnet
            + bezier(p(0.32, 0.46), p(0.38, 0.30), p(0.44, 0.10), p(0.54, 0.06))    # windscreen
            + bezier(p(0.54, 0.06), p(0.66, 0.02), p(0.84, 0.02), p(0.92, 0.10))    # roof
            + bezier(p(0.92, 0.10), p(0.99, 0.24), p(1.00, 0.60), p(0.99, 0.92)))   # rear
    d.polygon(body, fill=WHITE)
    windows = (bezier(p(0.36, 0.44), p(0.41, 0.30), p(0.46, 0.16), p(0.54, 0.14))
               + [p(0.86, 0.14), p(0.90, 0.44)])
    d.polygon(windows, fill=BG)
    d.line([p(0.62, 0.12), p(0.62, 0.46)], fill=WHITE, width=int(s * 0.02))
    for cx in (0.22, 0.79):
        c = p(cx, 0.92)
        r = 0.17 * h
        for radius, colour in ((r * 1.25, BG), (r, WHITE), (r * 0.45, BG)):
            d.ellipse((c[0] - radius, c[1] - radius, c[0] + radius, c[1] + radius), fill=colour)


def draw_bolt(d, s, cx, cy, size):
    shape = [(0.50, 0.00), (0.17, 0.62), (0.44, 0.62), (0.34, 1.00), (0.80, 0.36),
             (0.52, 0.36), (0.66, 0.00)]
    d.polygon([(cx + (x - 0.5) * size * 0.6, cy + (y - 0.5) * size) for x, y in shape],
              fill=YELLOW, outline=BG, width=int(s * 0.018))


def render(size: int) -> Image.Image:
    s = size * SUPERSAMPLE
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, s - 1, s - 1), radius=int(s * 0.22), fill=BG)
    # battery with 70 % charge
    bx0, by0, bx1, by1 = s * 0.27, s * 0.10, s * 0.69, s * 0.37
    line = int(s * 0.035)
    d.rounded_rectangle((bx0, by0, bx1, by1), radius=int(s * 0.05), outline=WHITE, width=line)
    d.rounded_rectangle((bx1 + s * 0.01, s * 0.19, s * 0.75, s * 0.28), radius=int(s * 0.02),
                        fill=WHITE)
    pad = line + s * 0.02
    d.rounded_rectangle((bx0 + pad, by0 + pad, bx0 + (bx1 - bx0) * 0.72, by1 - pad),
                        radius=int(s * 0.025), fill=GREEN)
    draw_bolt(d, s, s * 0.48, s * 0.235, s * 0.38)
    draw_car(d, s * 0.09, s * 0.47, s * 0.82, s * 0.33, s)
    return img.resize((size, size), Image.LANCZOS)


if __name__ == "__main__":
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    for name, size in (("icon.png", 256), ("icon@2x.png", 512), ("logo.png", 256),
                       ("logo@2x.png", 512)):
        render(size).save(out / name)
    print("ok")
