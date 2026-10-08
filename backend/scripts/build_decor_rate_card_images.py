"""
Builds the decor photos shown to decorators on vendor-onboarding.html
(2026-10-08, per Shruti: "show him a gallery of all classic decors ... all
images to have our logo and number in a significant way").

Reads every decor photo the website's party builder shows for each tier
(builder.html -> THEMES -> tierPhotos / tierExtraPhotos), plus the four
standard reference photos, and writes watermarked copies to
img/Decor/rate-card/ (logo in the middle + "WONDERSHOP +91 97422 40477"
repeated diagonally; the whole photo is kept, nothing is cropped or covered)
and the list the form reads to js/decor-rate-card-designs.js.

Run it again whenever a decor photo is added to or removed from builder.html:

    cd Website
    python3 backend/scripts/build_decor_rate_card_images.py

Needs Pillow (pip install pillow). Only reads the originals; never changes them.
"""
import json
import os
import re
import sys

from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
OUT_DIR = os.path.join(ROOT, "img", "Decor", "rate-card")
OUT_JS = os.path.join(ROOT, "js", "decor-rate-card-designs.js")
PHONE = "+91 97422 40477"
TIERS = ["Classic", "Premium", "Luxury", "Signature"]
REFERENCE = {
    "Classic": "img/Decor/Standard Classic Balloon Arch.jpg",
    "Premium": "img/Decor/Standard - Premium 1 panel decor.jpg",
    "Luxury": "img/Decor/Standard - Luxury 2 panel decor.jpg",
    "Signature": "img/Decor/Standard Signature 3 Panel Decor.jpg",
}
FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/Library/Fonts/Arial Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
]


def font(size):
    for f in FONT_CANDIDATES:
        if os.path.exists(f):
            return ImageFont.truetype(f, size)
    return ImageFont.load_default(size)


def themes_from_builder():
    """[(theme name, tier, photo path), ...] in builder.html order."""
    src = open(os.path.join(ROOT, "builder.html"), encoding="utf-8").read()
    out = []
    for chunk in re.split(r"\{id:'", src)[1:]:
        if "tierPhotos" not in chunk[:4000]:
            continue
        chunk = chunk[:4000]
        m = re.search(r"n:'([^']*)'", chunk)
        name = m.group(1) if m else chunk.split("'")[0]
        tp = re.search(r"tierPhotos:\{([^}]*)\}", chunk)
        if tp:
            for tier, path in re.findall(r"(\w+):'([^']*)'", tp.group(1)):
                out.append((name, tier, path))
        ex = re.search(r"tierExtraPhotos:\{(.*?)\}\}", chunk, re.S)
        if ex:
            for tier, arr in re.findall(r"(\w+):\[([^\]]*)\]", ex.group(1)):
                for path in re.findall(r"'([^']*)'", arr):
                    out.append((name, tier, path))
    return out


def _alpha(img, a):
    r, g, b, al = img.split()
    return Image.merge("RGBA", (r, g, b, al.point(lambda v: int(v * a))))


def watermark(path, width):
    logo_b = Image.open(os.path.join(ROOT, "logo-horizontal.png")).convert("RGBA")
    logo_w = Image.open(os.path.join(ROOT, "logo-horizontal-dark.png")).convert("RGBA")
    im = Image.open(os.path.join(ROOT, path))
    h = int(width * im.height / im.width)
    im = im.resize((width, h), Image.LANCZOS).convert("RGBA")
    ov = Image.new("RGBA", (width, h), (0, 0, 0, 0))
    tf = font(int(width * 0.045))
    tile = Image.new("RGBA", (width * 3, h * 3), (0, 0, 0, 0))
    td = ImageDraw.Draw(tile)
    txt = ("WONDERSHOP  " + PHONE + "     ") * 6
    y, k = 0, 0
    while y < h * 3:
        td.text(((k % 2) * width * 0.25 - width * 0.2, y), txt, font=tf,
                fill=(255, 255, 255, 85), stroke_width=1, stroke_fill=(0, 0, 0, 40))
        y += int(width * 0.16)
        k += 1
    tile = tile.rotate(28, resample=Image.BICUBIC)
    ov.alpha_composite(tile.crop((width, h, width * 2, h * 2)))
    lw = int(width * 0.62)
    lg = logo_w.resize((lw, int(lw * logo_w.height / logo_w.width)), Image.LANCZOS)
    sh = logo_b.resize(lg.size, Image.LANCZOS)
    cx, cy = (width - lw) // 2, int(h * 0.5 - lg.height / 2)
    ov.alpha_composite(_alpha(sh, 0.25), (cx + 2, cy + 2))
    ov.alpha_composite(_alpha(lg, 0.6), (cx, cy))
    return Image.alpha_composite(im, ov).convert("RGB")


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    designs = {t: [] for t in TIERS}
    seen = {t: {} for t in TIERS}
    for name, tier, path in themes_from_builder():
        if tier not in designs or not os.path.exists(os.path.join(ROOT, path)):
            continue
        n = seen[tier].get(name, 0) + 1
        seen[tier][name] = n
        stem = os.path.splitext(os.path.basename(path))[0]
        out_name = stem + ".jpg"
        watermark(path, 480).save(os.path.join(OUT_DIR, out_name), quality=80, optimize=True)
        designs[tier].append({
            "id": stem,
            "name": name if n == 1 else f"{name} – option {n}",
            "img": "img/Decor/rate-card/" + out_name,
        })
    refs = {}
    for tier, path in REFERENCE.items():
        if os.path.exists(os.path.join(ROOT, path)):
            out_name = "ref-" + tier.lower() + ".jpg"
            watermark(path, 1024).save(os.path.join(OUT_DIR, out_name), quality=80, optimize=True)
            refs[tier] = "img/Decor/rate-card/" + out_name
    with open(OUT_JS, "w", encoding="utf-8") as fh:
        fh.write("// Generated by backend/scripts/build_decor_rate_card_images.py - do not edit by hand.\n")
        fh.write("window.WS_DECOR_DESIGNS = " + json.dumps({"designs": designs, "reference": refs}, ensure_ascii=False, indent=1) + ";\n")
    print({t: len(v) for t, v in designs.items()}, "reference:", sorted(refs))


if __name__ == "__main__":
    sys.exit(main())
