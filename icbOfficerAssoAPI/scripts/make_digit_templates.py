r"""Build app/utils/paper_digits.npz: the digit shapes used to read the ballot paper number.

    .venv\Scripts\python scripts\make_digit_templates.py

Every digit 0-9 is drawn in Bengali (০-৯) and English with the fonts below, in
a thin, normal and heavy stroke, and stored as normalised glyph images (see
app/utils/paper_number.py).  Only needed again when a font is added; the
counting PC does not need the fonts.
"""

from __future__ import annotations

import sys
from pathlib import Path

API_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(API_DIR))

import cv2  # noqa: E402
import numpy as np  # noqa: E402
from PIL import Image, ImageDraw, ImageFont  # noqa: E402

from app.utils.paper_number import TEMPLATES, normalize_glyph  # noqa: E402

FONTS_DIR = Path("C:/Windows/Fonts")
FONTS = {
    "bn": [("kalpurush.ttf", 0), ("Nirmala.ttc", 0), ("Nirmala.ttc", 1), ("Nirmala.ttc", 2), ("Siyamrupali.ttf", 0)],
    "en": [("arial.ttf", 0), ("arialbd.ttf", 0), ("times.ttf", 0), ("timesbd.ttf", 0),
           ("calibri.ttf", 0), ("calibrib.ttf", 0), ("consola.ttf", 0), ("segoeui.ttf", 0),
           # faces close to the wheels of a numbering machine (gothic and roman styles)
           ("bahnschrift.ttf", 0), ("ARIALNB.TTF", 0), ("courbd.ttf", 0), ("consolab.ttf", 0),
           ("OCRAEXT.TTF", 0), ("GOTHICB.TTF", 0), ("SCHLBKB.TTF", 0), ("BOD_B.TTF", 0), ("ROCKB.TTF", 0)],
}
DIGITS = {"bn": "০১২৩৪৫৬৭৮৯", "en": "0123456789"}


def render(char: str, font: ImageFont.FreeTypeFont) -> np.ndarray:
    img = Image.new("L", (160, 160), 0)
    ImageDraw.Draw(img).text((30, 10), char, fill=255, font=font)
    return (np.asarray(img) > 127).astype(np.uint8)


def main() -> None:
    out: dict[str, np.ndarray] = {}
    for script, fonts in FONTS.items():
        glyphs, labels = [], []
        for name, index in fonts:
            path = FONTS_DIR / name
            if not path.exists():
                print(f"  skipped {name} (not installed)")
                continue
            font = ImageFont.truetype(str(path), 96, index=index)
            for value, char in enumerate(DIGITS[script]):
                ink = render(char, font)
                for stroke in (ink, cv2.erode(ink, np.ones((3, 3), np.uint8)), cv2.dilate(ink, np.ones((5, 5), np.uint8))):
                    glyph = normalize_glyph(stroke)
                    if glyph is not None:
                        glyphs.append(glyph)
                        labels.append(value)
        out[script] = np.stack(glyphs).astype(np.float32)
        out[f"{script}_labels"] = np.array(labels, np.uint8)
        print(f"  {script}: {len(glyphs)} digit shapes")
    np.savez_compressed(TEMPLATES, **out)
    print(f"Wrote {TEMPLATES}")


if __name__ == "__main__":
    main()
