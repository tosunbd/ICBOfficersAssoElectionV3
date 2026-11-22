r"""Build the ballot form of 21-11-2026 from the form approved on 17-11-2026.

    .venv\Scripts\python scripts\make_ballot_form.py [--force]

Source (read only):  <project>/Sample Ballots/17-11-2026/Blank ballot/Blank_ballot_form.docx
Written:             <project>/Sample Ballots/21-11-2026/Blank ballot/Blank_ballot_form.docx

Three changes, nothing else on the form is touched:

1. QR code at the top left, beside the title            (floating picture)
2. bar code (Code 128) at the bottom, below the instructions, centred under the
   candidate table (floating picture; it was at the bottom left on the form of 19-11-2026)
3. a larger ballot paper number box (32 x 12 mm instead of 15 x 10 mm): the number
   is stamped with an automatic numbering machine and must fit inside the box.

The pictures float over the page, so the candidate table does not move: the taller
title row is taken out of the top margin.  Both codes hold BALLOT_CODE, the same
on every paper (the papers are identical when printed; the number comes later
from the numbering machine).

An existing form is only replaced with --force (it may have been edited in Word).
"""

from __future__ import annotations

import io
import re
import sys
import zipfile
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "Sample Ballots" / "17-11-2026" / "Blank ballot" / "Blank_ballot_form.docx"
DEST = ROOT / "Sample Ballots" / "21-11-2026" / "Blank ballot" / "Blank_ballot_form.docx"

BALLOT_CODE = "ICBOA-20-2026"   # ICB Officers' Association, 20th council, election 2026

EMU = 36000                      # per mm
QR_MM = (15.1, 9.5, 12.5)        # left, top (from the page corner), side
TABLE_MM = (15.1, 184.9)         # candidate table: left edge (= left margin), width
BARCODE_MM = (276.0, 9.0)        # top, height; left/right: centred under the candidate table
BARCODE_MODULE_MM = 0.33         # width of the narrowest bar

# title table: title | "ballot paper no" | gap | number box | spacer   (twips, 1 mm = 56.7)
OLD_COLS = {"title": 7063, "box": 867, "spacer": 576}
NEW_COLS = {"title": 6572, "box": 1814, "spacer": 120}
OLD_ROW_H, NEW_ROW_H = 547, 680
OLD_TOP_MARGIN = 781


# ------------------------------------------------------------------ codes
def qr_image(text: str = BALLOT_CODE, module_px: int = 16) -> Image.Image:
    """QR code (version 1, error correction M) without a white border."""
    params = cv2.QRCodeEncoder_Params()
    params.version = 1
    params.correction_level = cv2.QRCodeEncoder_CORRECT_LEVEL_M
    params.mode = cv2.QRCodeEncoder_MODE_ALPHANUMERIC
    code = cv2.QRCodeEncoder_create(params).encode(text)
    ys, xs = np.nonzero(code < 128)
    code = code[ys.min(): ys.max() + 1, xs.min(): xs.max() + 1]
    code = cv2.resize(code, None, fx=module_px, fy=module_px, interpolation=cv2.INTER_NEAREST)
    return Image.fromarray(code).convert("L")


_CODE128 = (
    "212222 222122 222221 121223 121322 131222 122213 122312 132212 221213 "
    "221312 231212 112232 122132 122231 113222 123122 123221 223211 221132 "
    "221231 213212 223112 312131 311222 321122 321221 312212 322112 322211 "
    "212123 212321 232121 111323 131123 131321 112313 132113 132311 211313 "
    "231113 231311 112133 112331 132131 113123 113321 133121 313121 211331 "
    "231131 213113 213311 213131 311123 311321 331121 312113 312311 332111 "
    "314111 221411 431111 111224 111422 121124 121421 141122 141221 112214 "
    "112412 122114 122411 142112 142211 241211 221114 413111 241112 134111 "
    "111242 121142 121241 114212 124112 124211 411212 421112 421211 212141 "
    "214121 412121 111143 111341 131141 114113 114311 411113 411311 113141 "
    "114131 311141 411131 211412 211214 211232 2331112"
).split()
assert len(_CODE128) == 107 and all(sum(map(int, p)) == 11 for p in _CODE128[:106])


def code128_modules(text: str = BALLOT_CODE) -> list[int]:
    """Bars of a Code 128 (set B) symbol as 1 (black) / 0 (white) modules."""
    values = [104] + [ord(ch) - 32 for ch in text]              # start B, then the characters
    values.append(sum(v * max(i, 1) for i, v in enumerate(values)) % 103)
    values.append(106)                                           # stop
    modules: list[int] = []
    for value in values:
        for i, width in enumerate(_CODE128[value]):
            modules += [1 - i % 2] * int(width)
    return modules


def barcode_image(text: str = BALLOT_CODE, module_px: int = 6, height_px: int = 160) -> Image.Image:
    row = np.array([0 if m else 255 for m in code128_modules(text)], np.uint8)
    return Image.fromarray(np.tile(np.repeat(row, module_px), (height_px, 1))).convert("L")


def _png(image: Image.Image) -> bytes:
    data = io.BytesIO()
    image.convert("1").save(data, "PNG")
    return data.getvalue()


# ------------------------------------------------------------------- docx
def _picture(rel_id: str, pic_id: int, name: str, x_mm: float, y_mm: float, w_mm: float, h_mm: float) -> str:
    """A run with a picture floating in front of the page at a fixed place."""
    x, y, cx, cy = (round(v * EMU) for v in (x_mm, y_mm, w_mm, h_mm))
    return (
        '<w:r><w:drawing><wp:anchor distT="0" distB="0" distL="0" distR="0" simplePos="0" relativeHeight="251659264" '
        'behindDoc="0" locked="1" layoutInCell="0" allowOverlap="1"><wp:simplePos x="0" y="0"/>'
        f'<wp:positionH relativeFrom="page"><wp:posOffset>{x}</wp:posOffset></wp:positionH>'
        f'<wp:positionV relativeFrom="page"><wp:posOffset>{y}</wp:posOffset></wp:positionV>'
        f'<wp:extent cx="{cx}" cy="{cy}"/><wp:effectExtent l="0" t="0" r="0" b="0"/><wp:wrapNone/>'
        f'<wp:docPr id="{pic_id}" name="{name}"/><wp:cNvGraphicFramePr/>'
        '<a:graphic xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">'
        '<a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">'
        '<pic:pic xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture">'
        f'<pic:nvPicPr><pic:cNvPr id="{pic_id}" name="{name}"/><pic:cNvPicPr/></pic:nvPicPr>'
        f'<pic:blipFill><a:blip r:embed="{rel_id}"/><a:stretch><a:fillRect/></a:stretch></pic:blipFill>'
        f'<pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm>'
        '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr>'
        '</pic:pic></a:graphicData></a:graphic></wp:anchor></w:drawing></w:r>'
    )


def _swap(text: str, old: str, new: str, count: int | None = None) -> str:
    found = text.count(old)
    if found == 0 or (count is not None and found != count):
        raise SystemExit(f"{SOURCE.name} is not the 17-11-2026 form: {old!r} found {found} time(s)")
    return text.replace(old, new)


def build_document(xml: str, barcode_w_mm: float) -> str:
    start = xml.index("<w:tbl>")
    end = xml.index("</w:tbl>") + len("</w:tbl>")
    table = xml[start:end]

    # 3. the larger number box: wider (space taken from the title cell and the spacer), taller row
    for key in OLD_COLS:
        table = _swap(table, f'w:w="{OLD_COLS[key]}"', f'w:w="{NEW_COLS[key]}"', 2)   # grid column + cell
    table = _swap(table, f'<w:trHeight w:hRule="exact" w:val="{OLD_ROW_H}"/>', f'<w:trHeight w:hRule="exact" w:val="{NEW_ROW_H}"/>', 1)
    # title and label stay level with the middle of the taller row
    for width in (NEW_COLS["title"], 1876):
        table = _swap(table, f'<w:tcW w:w="{width}" w:type="dxa"/></w:tcPr>',
                      f'<w:tcW w:w="{width}" w:type="dxa"/><w:vAlign w:val="center"/></w:tcPr>', 1)
    table = _swap(table, '</w:tcBorders></w:tcPr>', '</w:tcBorders><w:vAlign w:val="center"/></w:tcPr>', 1)
    table = _swap(table, 'w:before="115" w:line="302"', 'w:before="0" w:line="302"', 1)
    xml = xml[:start] + table + xml[end:]
    # the candidate table keeps its place on the page
    xml = _swap(xml, f'<w:pgMar w:top="{OLD_TOP_MARGIN}"', f'<w:pgMar w:top="{OLD_TOP_MARGIN - (NEW_ROW_H - OLD_ROW_H)}"', 1)

    # 1 + 2. the two pictures hang on the empty paragraph after the title table
    host = xml.index("</w:p>", xml.index("</w:tbl>"))
    pictures = (
        _picture("rId101", 101, "Ballot QR code", QR_MM[0], QR_MM[1], QR_MM[2], QR_MM[2])
        + _picture("rId102", 102, "Ballot bar code", TABLE_MM[0] + (TABLE_MM[1] - barcode_w_mm) / 2, BARCODE_MM[0],
                   barcode_w_mm, BARCODE_MM[1])
    )
    return xml[:host] + pictures + xml[host:]


def build(source: Path = SOURCE, dest: Path = DEST) -> Path:
    barcode_w_mm = len(code128_modules()) * BARCODE_MODULE_MM
    media = {"word/media/ballot_qr.png": _png(qr_image()), "word/media/ballot_barcode.png": _png(barcode_image())}
    relationship = ('<Relationship Id="%s" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" '
                    'Target="media/%s"/>')
    dest.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(source) as src, zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as dst:
        for item in src.infolist():
            data = src.read(item.filename)
            if item.filename == "word/document.xml":
                data = build_document(data.decode("utf-8"), barcode_w_mm).encode("utf-8")
            elif item.filename == "word/_rels/document.xml.rels":
                extra = relationship % ("rId101", "ballot_qr.png") + relationship % ("rId102", "ballot_barcode.png")
                data = re.sub(r"</Relationships>\s*$", extra + "</Relationships>", data.decode("utf-8")).encode("utf-8")
            elif item.filename == "[Content_Types].xml":
                data = data.decode("utf-8").replace(
                    '<Default Extension="xml"', '<Default Extension="png" ContentType="image/png"/><Default Extension="xml"', 1
                ).encode("utf-8")
            dst.writestr(item, data)
        for name, data in media.items():
            dst.writestr(name, data)
    return dest


def main() -> None:
    if DEST.exists() and "--force" not in sys.argv:
        raise SystemExit(f"{DEST} already exists (it may have been edited in Word). Run with --force to replace it.")
    print(f"Wrote {build()}")


if __name__ == "__main__":
    main()
