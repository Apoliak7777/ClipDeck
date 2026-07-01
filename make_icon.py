"""Generate assets/icon.ico for ClipDeck (window / tray / exe icon)."""
import os
from PIL import Image, ImageDraw

ACCENT = (108, 99, 255)      # indigo
ACCENT2 = (88, 200, 250)     # cyan
REC = (255, 76, 76)          # record red
DARK = (22, 24, 34)


def render(size: int) -> Image.Image:
    s = size * 4  # supersample for clean edges
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # rounded-square badge with a vertical gradient
    r = int(s * 0.22)
    badge = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    bd = ImageDraw.Draw(badge)
    for y in range(s):
        t = y / s
        col = tuple(int(ACCENT[i] * (1 - t) + ACCENT2[i] * t) for i in range(3))
        bd.line([(0, y), (s, y)], fill=col + (255,))
    mask = Image.new("L", (s, s), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, s, s], radius=r, fill=255)
    img.paste(badge, (0, 0), mask)

    # film-strip perforations down both sides
    hole_w, hole_h = int(s * 0.07), int(s * 0.05)
    gap = int(s * 0.14)
    y = int(s * 0.16)
    while y < s - hole_h - int(s * 0.10):
        for x in (int(s * 0.12), s - int(s * 0.12) - hole_w):
            d.rounded_rectangle([x, y, x + hole_w, y + hole_h],
                                radius=int(hole_h * 0.3), fill=DARK + (235,))
        y += gap

    # central record dot
    cx, cy = s // 2, s // 2
    rad = int(s * 0.17)
    d.ellipse([cx - rad, cy - rad, cx + rad, cy + rad], fill=REC + (255,))
    d.ellipse([cx - rad, cy - rad, cx + rad, cy + rad],
              outline=(255, 255, 255, 230), width=max(2, s // 90))

    return img.resize((size, size), Image.LANCZOS)


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    out = os.path.join(here, "assets", "icon.ico")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    sizes = [16, 24, 32, 48, 64, 128, 256]
    imgs = [render(n) for n in sizes]
    imgs[0].save(out, format="ICO", sizes=[(n, n) for n in sizes],
                 append_images=imgs[1:])
    # also a PNG for the tray icon
    render(256).save(os.path.join(here, "assets", "icon.png"))
    print("wrote", out)


if __name__ == "__main__":
    main()
