#!/usr/bin/env python3
import os
import shutil
import subprocess
from PIL import Image, ImageDraw, ImageFont

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ICONSET = os.path.join(BASE, "BiliNotify.iconset")
ICNS = os.path.join(BASE, "BiliNotify.icns")
PNG = os.path.join(BASE, "BiliNotify.png")


def gen_iconset():
    if os.path.exists(ICONSET):
        shutil.rmtree(ICONSET)
    os.makedirs(ICONSET, exist_ok=True)

    sizes = [16, 32, 128, 256, 512]
    for s in sizes:
        img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        color = (0, 161, 214, 255)
        draw.ellipse((0, 0, s - 1, s - 1), fill=color)
        inner = int(s * 0.08)
        draw.ellipse(
            (inner, inner, s - inner - 1, s - inner - 1),
            outline=(255, 255, 255, 60),
            width=max(1, s // 32),
        )
        text = "B"
        try:
            font = ImageFont.truetype(
                "/System/Library/Fonts/Supplemental/Arial Bold.ttf", int(s * 0.6)
            )
        except Exception:
            font = ImageFont.load_default()
        bbox = draw.textbbox((0, 0), text, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        draw.text(
            ((s - tw) / 2, (s - th) / 2 - s * 0.02),
            text,
            fill=(255, 255, 255, 255),
            font=font,
        )
        out = os.path.join(ICONSET, f"icon_{s}x{s}.png")
        img.save(out)
        img2 = img.resize((s * 2, s * 2), Image.LANCZOS)
        out2 = os.path.join(ICONSET, f"icon_{s}x{s}@2x.png")
        img2.save(out2)

    # save a 1024 png for preview
    img2.save(PNG)


def build_icns():
    if shutil.which("iconutil") is None:
        raise RuntimeError("iconutil not found")
    subprocess.check_call(["iconutil", "-c", "icns", ICONSET, "-o", ICNS])


def main():
    gen_iconset()
    build_icns()
    print(ICNS)


if __name__ == "__main__":
    main()
