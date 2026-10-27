#!/usr/bin/env python3
"""docs/images/collage.jpg: a collage of the painted aircraft on the cream ground, for the README. Best effort, needs Pillow."""
import random, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def build(n=14, seed=7):
    from PIL import Image
    files = sorted((ROOT / "planes").glob("*.webp")) + sorted((ROOT / "planes" / "liveries").glob("*/*/*.webp"))
    files = [f for f in files if not f.stem.endswith("-2")] or files
    if not files:
        print("collage: nothing painted yet"); return
    rnd = random.Random(seed)
    rnd.shuffle(files)
    W, H = 1600, 760
    canvas = Image.new("RGB", (W, H), (240, 232, 214))
    cols = 5
    cell_w, cell_h = W // cols, H // 3
    for i, f in enumerate(files[:cols * 3 if len(files) >= cols * 3 else len(files)]):
        im = Image.open(f).convert("RGBA")
        im.thumbnail((cell_w - 30, cell_h - 30))
        x = (i % cols) * cell_w + (cell_w - im.width) // 2 + rnd.randint(-12, 12)
        y = (i // cols) * cell_h + (cell_h - im.height) // 2 + rnd.randint(-8, 8)
        canvas.paste(im, (x, y), im)
    out = ROOT / "docs" / "images"
    out.mkdir(parents=True, exist_ok=True)
    canvas.save(out / "collage.jpg", quality=88)
    print("collage: docs/images/collage.jpg")


if __name__ == "__main__":
    build()
