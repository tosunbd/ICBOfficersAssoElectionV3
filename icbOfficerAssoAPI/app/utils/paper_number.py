"""Ballot paper number in the box at the top right of the paper: printed with the
form, or stamped into the box with an automatic numbering machine.

The number is read without an OCR engine: the box is found next to the title
(above the ballot table), the digits inside are cut apart and each one is
compared with digit shapes rendered from common Bengali and English fonts
(``paper_digits.npz``, made by ``scripts/make_digit_templates.py``).  The
whole number is read once as Bengali digits (০-৯) and once as English digits
(0-9) and the better fitting script wins, so ``৪`` is never confused with ``8``.

When the box or a digit cannot be read with confidence, ``read_paper_no``
returns None: the ballot then goes to the committee for review.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np

TEMPLATES = Path(__file__).with_name("paper_digits.npz")
GLYPH = 32                 # digit images are compared at GLYPH x GLYPH pixels
MIN_SCORE = 0.55           # weakest digit match accepted (correlation, 1 = identical)
MIN_MARGIN = 0.03          # best digit must beat the next other digit by this much

# scanned image named after its paper: img_0001.jpg, IMG_0001.JPEG, iMg_0001.Jpg ...
_FILE_NAME = re.compile(r"^img_(?P<paper>\d+)\.(?:jpg|jpeg)$")


def file_paper_no(file_name: str) -> str | None:
    """Paper number in a scanned file name (``img_0001.jpg`` -> ``0001``), any
    upper/lower case of ``img`` and of the jpg/jpeg extension; None for other names."""
    match = _FILE_NAME.match(file_name.strip().lower())
    return match["paper"] if match else None


def same_paper(file_no: str | None, paper_no: str | None) -> bool:
    """True when the number in the file name and the number on the paper are the same
    paper.  Leading zeros do not count: a numbering machine stamps 000001 on the paper
    the scanner saves as img_0001.jpg."""
    if not file_no or not paper_no or not file_no.isdigit() or not paper_no.isdigit():
        return False
    return int(file_no) == int(paper_no)


# ------------------------------------------------------------------ glyphs
def normalize_glyph(ink: np.ndarray) -> np.ndarray | None:
    """Ink mask of one digit -> GLYPH x GLYPH float image (ink = 1), centred, aspect kept."""
    ys, xs = np.nonzero(ink)
    if len(xs) == 0:
        return None
    crop = ink[ys.min(): ys.max() + 1, xs.min(): xs.max() + 1].astype(np.float32)
    h, w = crop.shape
    side = max(h, w)
    square = np.zeros((side, side), np.float32)
    square[(side - h) // 2: (side - h) // 2 + h, (side - w) // 2: (side - w) // 2 + w] = crop
    inner = GLYPH - 4
    glyph = cv2.resize(square, (inner, inner), interpolation=cv2.INTER_AREA)
    glyph = cv2.copyMakeBorder(glyph, 2, 2, 2, 2, cv2.BORDER_CONSTANT, value=0)
    return cv2.GaussianBlur(glyph, (3, 3), 0)


def _flat(glyph: np.ndarray) -> np.ndarray:
    v = glyph.reshape(-1).astype(np.float32)
    v = v - v.mean()
    return v / (np.linalg.norm(v) or 1.0)


@lru_cache(maxsize=1)
def _templates() -> dict[str, tuple[np.ndarray, np.ndarray]]:
    data = np.load(TEMPLATES)
    return {
        script: (np.stack([_flat(g) for g in data[script]]), data[f"{script}_labels"])
        for script in ("bn", "en")
    }


def _digit(mask: np.ndarray, script: str) -> tuple[str, float] | None:
    """The digit drawn in `mask` and its match, or None when no digit fits clearly."""
    glyph = normalize_glyph(mask)
    if glyph is None:
        return None
    vectors, labels = _templates()[script]
    best: dict[int, float] = {}
    for label, score in zip(labels, vectors @ _flat(glyph)):
        best[int(label)] = max(best.get(int(label), -1.0), float(score))
    ranked = sorted(best.items(), key=lambda kv: kv[1], reverse=True)
    (digit, score), (_, runner_up) = ranked[0], ranked[1]
    if score < MIN_SCORE or score - runner_up < MIN_MARGIN:
        return None
    return str(digit), score


def _touching(mask: np.ndarray, script: str) -> tuple[str, float] | None:
    """Two digits printed so close that they touch: cut at the thinnest column."""
    xs = np.flatnonzero(mask.any(axis=0))
    left, right = xs.min(), xs.max()
    width = right - left + 1
    if width < 0.6 * np.ptp(np.flatnonzero(mask.any(axis=1))):
        return None  # too narrow for two digits
    columns = mask[:, left + width // 4: right - width // 4 + 1].sum(axis=0)
    cut = left + width // 4 + int(np.argmin(columns))
    a, b = mask.copy(), mask.copy()
    a[:, cut:] = False
    b[:, :cut] = False
    first, second = _digit(a, script), _digit(b, script)
    if first is None or second is None:
        return None
    return first[0] + second[0], min(first[1], second[1])


def _classify(masks: list[np.ndarray], script: str) -> tuple[str, float] | None:
    """Digits for `masks` in one script and the weakest match, or None if any digit is unsure."""
    digits, weakest = [], 1.0
    for mask in masks:
        read = _digit(mask, script) or _touching(mask, script)
        if read is None:
            return None
        digits.append(read[0])
        weakest = min(weakest, read[1])
    return "".join(digits), weakest


# --------------------------------------------------------------------- box
def find_number_box(gray: np.ndarray) -> tuple[int, int, int, int] | None:
    """(x, y, w, h) of the printed ballot-number box: a small rectangle in the top
    right part of the page, above the ballot table."""
    page_h, page_w = gray.shape
    top = cv2.GaussianBlur(gray[: int(page_h * 0.2)], (3, 3), 0)
    _, binary = cv2.threshold(top, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    # the box may be printed in a thin, light (blue) line that is paler than the Otsu
    # level set by the black title text: a local threshold keeps its outline closed
    binary |= cv2.adaptiveThreshold(top, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 25, 12)
    # the table starts at the first line running across most of the page: look above it.
    # The title underline is about half the page wide, so a line must span 60% of it;
    # a vertical dilation keeps a slightly tilted table line in one pixel row.
    thick = cv2.dilate(binary, cv2.getStructuringElement(cv2.MORPH_RECT, (1, 9)))
    lines = cv2.morphologyEx(thick, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (int(page_w * 0.6), 1)))
    rows = np.flatnonzero(lines.max(axis=1))
    if len(rows):
        binary = binary[: rows[0]]
    contours, _ = cv2.findContours(binary, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    best = None
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        # 15 mm (form of 17-11-2026) to 32 mm wide (form of 19-11-2026, for the numbering machine)
        if not (0.05 * page_w <= w <= 0.22 * page_w) or not (1.3 <= w / max(h, 1) <= 3.6):
            continue
        if x + w / 2 < page_w * 0.55:
            continue
        # a printed rectangle: ink along most of each edge (text glyphs fail this)
        t = max(2, h // 12)
        edges = (binary[y: y + t, x: x + w], binary[y + h - t: y + h, x: x + w],
                 binary[y: y + h, x: x + t], binary[y: y + h, x + w - t: x + w])
        if min(float((e.max(axis=0 if i < 2 else 1) > 0).mean()) for i, e in enumerate(edges)) < 0.8:
            continue
        if best is None or x + w > best[0] + best[2]:  # the right-most one (outer edge of the border)
            best = (x, y, w, h)
    return best


def split_digits(box_gray: np.ndarray) -> list[np.ndarray]:
    """Ink masks of the digits inside the box, left to right."""
    h, w = box_gray.shape
    _, ink = cv2.threshold(cv2.GaussianBlur(box_gray, (3, 3), 0), 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    if float(ink.mean()) / 255 < 0.01:
        return []  # empty box
    count, labels, stats, _ = cv2.connectedComponentsWithStats(ink, connectivity=8)
    parts = []
    for i in range(1, count):
        x, y, cw, ch, area = stats[i]
        if ch < 0.2 * h or area < 0.0015 * h * w:
            continue  # dust, or what is left of the box border
        if x == 0 or y == 0 or x + cw >= w or y + ch >= h:
            if cw > 0.6 * w or ch > 0.9 * h:
                continue  # part of the border
        parts.append([x, x + cw, labels == i])
    parts.sort(key=lambda p: p[0])
    merged: list[list] = []
    for part in parts:  # pieces of one digit overlap horizontally
        if merged and part[0] < merged[-1][1] - 0.5 * (part[1] - part[0]):
            merged[-1][1] = max(merged[-1][1], part[1])
            merged[-1][2] = merged[-1][2] | part[2]
        else:
            merged.append(part)
    return [p[2] for p in merged]


def read_paper_no(gray: np.ndarray | None) -> str | None:
    """Digits printed in the ballot-number box (``"0001"``), or None when unreadable."""
    if gray is None:
        return None
    box = find_number_box(gray)
    if box is None:
        return None
    x, y, w, h = box
    m = max(3, h // 8)  # stay clear of the border lines
    masks = split_digits(gray[y + m: y + h - m, x + m: x + w - m])
    if not masks or len(masks) > 8:
        return None
    reads = [r for r in (_classify(masks, script) for script in ("bn", "en")) if r is not None]
    if not reads:
        return None
    return max(reads, key=lambda r: r[1])[0]
