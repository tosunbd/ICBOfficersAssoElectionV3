"""Mark detection for scanned ballot papers.

The ballot is a printed table.  Each row holds up to `BALLOT_COLUMNS`
(normally 2) candidates, and every candidate has a small square box that the
voter marks with an X.  Nothing has to be *read* as text: we only need to know
which boxes contain ink, so the whole pipeline is plain OpenCV.

Pipeline
--------
1. Render the PDF page (pypdfium2) or load an image file.
2. Grey-scale + adaptive threshold  ->  binary image (ink = white).
3. Find the outer border of the ballot table and deskew the page with it.
4. Find small rectangular outlines inside the table = candidate boxes.
   The left-most part of the table never holds a box (candidate numbers and
   names on the 11-11-2026 paper) and is ignored.
5. Group the boxes into rows (by y) and columns (by x).
6. Map row/column to the candidate layout that comes from the database
   (positions in ballot order, candidates in display order, 2 per row).
7. Measure every box: ink inside (marked?), ink around it (rule kha: X must be
   inside the box), fully inked boxes (rule ga: rubbed/scribbled marks are void).

The result carries warnings (e.g. "expected 30 boxes, found 29") so that the
processor can flag the ballot for manual review instead of silently trusting
a mis-aligned read.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from statistics import median
from typing import Any

import cv2
import numpy as np
from PIL import Image, ImageOps, ImageSequence

from app.config import settings

logger = logging.getLogger(__name__)

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".jfif", ".tif", ".tiff", ".bmp", ".webp"}
A4_WIDTH_INCHES = 8.27  # the ballot is printed on A4 portrait
SUPPORTED_SUFFIXES = IMAGE_SUFFIXES | {".pdf"}


# --------------------------------------------------------------------------
# Data structures
# --------------------------------------------------------------------------
@dataclass
class Box:
    x: int
    y: int
    w: int
    h: int

    @property
    def cx(self) -> float:
        return self.x + self.w / 2

    @property
    def cy(self) -> float:
        return self.y + self.h / 2

    def as_dict(self) -> dict[str, int]:
        return {"x": self.x, "y": self.y, "w": self.w, "h": self.h}


@dataclass
class MarkResult:
    candidate_id: int
    position_id: int
    row_index: int
    col_index: int
    is_marked: bool
    confidence: float
    density: float
    box: Box | None
    kind: str = "none"                # none | x | mark | outside | smudged
    void_reason: str | None = None     # set when the ballot rules make this vote invalid
    outside_ink: float = 0.0           # ink ratio in the ring around the box


@dataclass
class PageResult:
    marks: list[MarkResult]
    boxes_expected: int
    boxes_detected: int
    layout_ok: bool
    warnings: list[str] = field(default_factory=list)
    image: np.ndarray | None = None  # deskewed grey page, used for previews


# --------------------------------------------------------------------------
# Service
# --------------------------------------------------------------------------
class OCRService:
    """Detects marked boxes on a ballot page."""

    # Geometry filters, relative to the page width.  The printed box is about
    # 7.5% of the page width and roughly 1.5x wider than tall.
    MIN_BOX_RATIO = 0.035
    MAX_BOX_RATIO = 0.10
    MIN_ASPECT = 0.6
    MAX_ASPECT = 2.2
    # Fraction of each edge of a candidate box that must contain ink for the
    # contour to count as a printed rectangle (filters out text glyphs).
    MIN_EDGE_COVERAGE = 0.7
    # No candidate box lies in the left-most part of the table (it holds the
    # candidate numbers and names), so anything box-shaped there is ignored.
    TABLE_LEFT_IGNORE = 0.15
    # Rule (kha): ring around the box that must stay clean, as a fraction of the box height
    OUTSIDE_RING = 0.25
    # A box whose bounding rectangle is this much larger than the typical box has a
    # mark crossing its border (the contour of box + mark merged)
    OVERSIZE_RATIO = 1.3
    # Rule (ka): an X should put ink on both diagonals of the box
    DIAGONAL_MIN_COVERAGE = 0.3
    # Ink ratio of a typical pen X (~18% of the box): at or above this the
    # confidence is 1.0; between MARK_THRESHOLD and this it ramps from 0.5.
    STRONG_MARK = 0.18

    # ---------------------------------------------------------------- input
    @classmethod
    def render_pages(cls, path: str | Path, dpi: int | None = None) -> list[Image.Image]:
        """Return every page of a PDF or image file as a normalised RGB image.

        Images may be JPG/PNG/TIFF (multi-page TIFFs give one page per frame).
        Every page is scaled to the same working resolution (see `normalize`),
        so a 72 DPI phone picture and a 600 DPI scan are read the same way.
        """
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")
        dpi = dpi or settings.OCR_DPI

        if path.suffix.lower() in IMAGE_SUFFIXES:
            # `with` releases the file handle, so the file can be moved afterwards (Windows)
            with Image.open(path) as img:
                return [cls.normalize(frame.copy(), dpi) for frame in ImageSequence.Iterator(img)]

        import pypdfium2 as pdfium  # imported lazily: keeps unit tests light

        pdf = pdfium.PdfDocument(str(path))
        try:
            pages = []
            for page in pdf:
                bitmap = page.render(scale=dpi / 72)
                pages.append(cls.normalize(bitmap.to_pil(), dpi))
                page.close()
            return pages
        finally:
            pdf.close()

    @staticmethod
    def normalize(img: Image.Image, dpi: int | None = None) -> Image.Image:
        """Upright RGB page with its short side = A4 width at `dpi`.

        * applies the EXIF orientation written by cameras / phone scanner apps;
        * flattens transparency onto white paper (a transparent PNG would
          otherwise turn black);
        * rescales, because the detector's filters and kernels are tuned for
          an A4 page at OCR_DPI.  Without this a low-resolution image (e.g. a
          PDF exported to JPG at 72 DPI) finds no boxes at all.
        """
        dpi = dpi or settings.OCR_DPI
        img = ImageOps.exif_transpose(img)
        if img.mode in ("RGBA", "LA", "PA") or (img.mode == "P" and "transparency" in img.info):
            rgba = img.convert("RGBA")
            paper = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
            img = Image.alpha_composite(paper, rgba)
        elif img.mode in ("I", "I;16", "I;16B", "I;16L", "F"):  # 16-bit / float greyscale scans
            arr = np.asarray(img, dtype=np.float64)
            span = max(float(arr.max() - arr.min()), 1e-6)
            img = Image.fromarray(((arr - arr.min()) / span * 255).astype(np.uint8))
        img = img.convert("RGB")

        target = round(A4_WIDTH_INCHES * dpi)
        short = min(img.size)
        if short and abs(short - target) / target > 0.02:
            scale = target / short
            size = (max(1, round(img.width * scale)), max(1, round(img.height * scale)))
            img = img.resize(size, Image.LANCZOS if scale < 1 else Image.BICUBIC)
        return img

    # -------------------------------------------------------- preprocessing
    @staticmethod
    def to_gray(pil_image: Image.Image) -> np.ndarray:
        arr = np.array(pil_image)
        if arr.ndim == 3:
            return cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
        return arr

    @staticmethod
    def binarize(gray: np.ndarray) -> np.ndarray:
        """Ink -> 255, paper -> 0.

        Adaptive thresholding handles uneven lighting but hollows out large
        solid areas (a scribbled-out box would look empty), so it is combined
        with a global Otsu threshold that keeps solid ink solid.
        """
        blurred = cv2.GaussianBlur(gray, (3, 3), 0)
        adaptive = cv2.adaptiveThreshold(
            blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 25, 12
        )
        _, solid = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        return cv2.bitwise_or(adaptive, solid)

    @staticmethod
    def largest_component(binary: np.ndarray):
        """Contour of the largest connected ink component (normally the table grid)."""
        h, w = binary.shape
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        closed = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)
        contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        best, best_area = None, 0
        for contour in contours:
            _, _, cw, ch = cv2.boundingRect(contour)
            if cw < 0.5 * w or ch < 0.35 * h:
                continue
            if cw * ch > best_area:
                best, best_area = contour, cw * ch
        return best

    @staticmethod
    def grid_lines(binary: np.ndarray) -> np.ndarray:
        """Mask of the long horizontal/vertical printed lines (the table grid)."""
        h, w = binary.shape
        horizontal = cv2.morphologyEx(
            binary, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (max(w // 10, 10), 1))
        )
        vertical = cv2.morphologyEx(
            binary, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(h // 10, 10)))
        )
        return cv2.dilate(
            cv2.bitwise_or(horizontal, vertical), cv2.getStructuringElement(cv2.MORPH_RECT, (11, 11))
        )

    def find_table(self, binary: np.ndarray) -> Box | None:
        """Bounding box of the ballot table, found from its long grid lines.

        Text and small boxes never form long straight lines, so this is a
        reliable way to exclude the title and the ballot-number box.
        """
        h, w = binary.shape
        lines = self.grid_lines(binary)
        contours, _ = cv2.findContours(lines, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        best = None
        for contour in contours:
            x, y, cw, ch = cv2.boundingRect(contour)
            if cw < 0.5 * w or ch < 0.35 * h:
                continue
            if best is None or cw * ch > best.w * best.h:
                best = Box(x, y, cw, ch)
        if best is None:
            contour = self.largest_component(binary)
            if contour is not None:
                best = Box(*cv2.boundingRect(contour))
        return best

    @staticmethod
    def deskew(gray: np.ndarray, contour) -> tuple[np.ndarray, float]:
        """Rotate the page so the table border is horizontal."""
        (_, _), (_, _), angle = cv2.minAreaRect(contour)
        # OpenCV reports the angle in [-90, 0) or (0, 90] depending on the version:
        # bring it to (-45, 45] so a page tilted either way is straightened
        if angle > 45:
            angle -= 90
        elif angle <= -45:
            angle += 90
        if abs(angle) < 0.2 or abs(angle) > 10:
            return gray, 0.0
        h, w = gray.shape
        matrix = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
        rotated = cv2.warpAffine(
            gray, matrix, (w, h), flags=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_CONSTANT, borderValue=255,
        )
        return rotated, angle

    # ------------------------------------------------------------ detection
    def detect_boxes(self, binary: np.ndarray, table: Box | None) -> list[Box]:
        """Find the square candidate boxes inside the table."""
        page_h, page_w = binary.shape
        region = table or Box(0, 0, page_w, page_h)
        min_size = int(page_w * self.MIN_BOX_RATIO)
        max_size = int(page_w * self.MAX_BOX_RATIO)
        left_limit = region.x + region.w * self.TABLE_LEFT_IGNORE

        # RETR_CCOMP: level 0 = outer boundary of an ink component, level 1 = holes.
        # A printed box is its own component (level 0); a table cell is a hole
        # in the big grid component (level 1) and is therefore skipped.
        contours, hierarchy = cv2.findContours(binary, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
        boxes: list[Box] = []
        parents = hierarchy[0][:, 3] if hierarchy is not None else []
        for contour, parent in zip(contours, parents):
            if parent != -1:
                continue
            x, y, w, h = cv2.boundingRect(contour)
            if not (min_size <= w <= max_size and min_size <= h <= max_size):
                continue
            aspect = w / h
            if not (self.MIN_ASPECT <= aspect <= self.MAX_ASPECT):
                continue
            box = Box(x, y, w, h)
            inside = (
                region.x <= box.cx <= region.x + region.w
                and region.y <= box.cy <= region.y + region.h
            )
            if not inside or box.cx < left_limit:
                continue
            if not self._is_outline(binary, box):
                continue
            boxes.append(box)

        # Merge duplicates (outer + inner edge of the same printed square)
        boxes.sort(key=lambda b: b.w * b.h, reverse=True)
        merged: list[Box] = []
        for box in boxes:
            if any(abs(box.cx - m.cx) < min_size and abs(box.cy - m.cy) < min_size for m in merged):
                continue
            merged.append(box)
        merged.sort(key=lambda b: (b.cy, b.cx))
        return merged

    def _is_outline(self, binary: np.ndarray, box: Box) -> bool:
        """True when ink runs along all four edges of the bounding box."""
        t = max(2, int(min(box.w, box.h) * 0.1))
        top = binary[box.y: box.y + t, box.x: box.x + box.w]
        bottom = binary[box.y + box.h - t: box.y + box.h, box.x: box.x + box.w]
        left = binary[box.y: box.y + box.h, box.x: box.x + t]
        right = binary[box.y: box.y + box.h, box.x + box.w - t: box.x + box.w]
        if not all(e.size for e in (top, bottom, left, right)):
            return False
        coverage = (
            np.count_nonzero(top.max(axis=0)) / top.shape[1],
            np.count_nonzero(bottom.max(axis=0)) / bottom.shape[1],
            np.count_nonzero(left.max(axis=1)) / left.shape[0],
            np.count_nonzero(right.max(axis=1)) / right.shape[0],
        )
        return min(coverage) >= self.MIN_EDGE_COVERAGE

    @staticmethod
    def group_rows(boxes: list[Box]) -> list[list[Box]]:
        if not boxes:
            return []
        tolerance = median(b.h for b in boxes) * 0.6
        rows: list[list[Box]] = []
        for box in sorted(boxes, key=lambda b: b.cy):
            if rows and abs(box.cy - median(b.cy for b in rows[-1])) <= tolerance:
                rows[-1].append(box)
            else:
                rows.append([box])
        for row in rows:
            row.sort(key=lambda b: b.cx)
        return rows

    @staticmethod
    def column_centres(boxes: list[Box], n_cols: int, table: Box | None) -> list[float]:
        """Estimate the x centre of each box column."""
        xs = sorted(b.cx for b in boxes)
        if not xs:
            return []
        if n_cols <= 1 or len(xs) < 2:
            return [median(xs)]
        # Split at the largest gaps between consecutive x positions
        gaps = sorted(
            ((xs[i + 1] - xs[i], i) for i in range(len(xs) - 1)), reverse=True
        )[: n_cols - 1]
        min_gap = (table.w if table else max(xs)) * 0.08
        cut_points = sorted(i for gap, i in gaps if gap >= min_gap)
        clusters, start = [], 0
        for cut in cut_points:
            clusters.append(xs[start: cut + 1])
            start = cut + 1
        clusters.append(xs[start:])
        return [median(c) for c in clusters if c]

    def build_grid(
        self, boxes: list[Box], n_cols: int, table: Box | None
    ) -> tuple[list[list[Box | None]], list[str], list[float]]:
        """Arrange detected boxes into rows x columns (also returns the column centres)."""
        warnings: list[str] = []
        rows = self.group_rows(boxes)
        centres = self.column_centres(boxes, n_cols, table)
        if len(centres) < n_cols:
            warnings.append(f"Only {len(centres)} box column(s) found, expected {n_cols}")
        grid: list[list[Box | None]] = []
        for row in rows:
            slots: list[Box | None] = [None] * n_cols
            for box in row:
                if centres:
                    col = min(range(len(centres)), key=lambda i: abs(box.cx - centres[i]))
                else:
                    col = 0
                col = min(col, n_cols - 1)
                if slots[col] is None:
                    slots[col] = box
                else:
                    warnings.append(f"Two boxes competed for the same cell near y={int(box.cy)}")
            grid.append(slots)
        return grid, warnings, centres

    def recover_lost_box(
        self, clean: np.ndarray, row: list[Box | None], col: int, centres: list[float], typical: tuple[float, float]
    ) -> Box | None:
        """A box that was not detected although its row was.

        When an X is drawn across the printed border, the contour of box and
        mark merge into one big blob and the box is lost.  If there is ink
        where the box should be, we know a mark was made outside the box
        (rule kha).  Returns the estimated box, or None if the area is blank.
        """
        present = [b for b in row if b is not None]
        if not present or col >= len(centres):
            return None
        w, h = typical
        cx, cy = centres[col], median(b.cy for b in present)
        grow = 1.6
        x0, y0 = int(cx - w * grow / 2), int(cy - h * grow / 2)
        x1, y1 = int(cx + w * grow / 2), int(cy + h * grow / 2)
        ih, iw = clean.shape
        region = clean[max(0, y0): min(ih, y1), max(0, x0): min(iw, x1)]
        if region.size == 0:
            return None
        if float(np.count_nonzero(region)) / region.size < settings.MARK_THRESHOLD / 2:
            return None
        return Box(int(cx - w / 2), int(cy - h / 2), int(w), int(h))

    # ------------------------------------------------------------- measure
    @staticmethod
    def _diagonal_coverage(roi: np.ndarray) -> tuple[float, float]:
        """Share of each diagonal band of the box interior that carries ink."""
        h, w = roi.shape
        if h < 4 or w < 4:
            return 0.0, 0.0
        ys, xs = np.mgrid[0:h, 0:w]
        ny, nx = ys / (h - 1), xs / (w - 1)
        band = 0.12
        d1 = np.abs(ny - nx) < band
        d2 = np.abs(ny - (1 - nx)) < band
        ink = roi > 0
        c1 = float(np.count_nonzero(ink & d1)) / max(1, np.count_nonzero(d1))
        c2 = float(np.count_nonzero(ink & d2)) / max(1, np.count_nonzero(d2))
        return c1, c2

    def _ring_ink(self, clean: np.ndarray, box: Box) -> float:
        """Ink ratio in the ring just outside the box (grid lines removed)."""
        h, w = clean.shape
        ring = max(4, int(box.h * self.OUTSIDE_RING))
        x0, y0 = max(0, box.x - ring), max(0, box.y - ring)
        x1, y1 = min(w, box.x + box.w + ring), min(h, box.y + box.h + ring)
        outer = clean[y0:y1, x0:x1]
        if outer.size == 0:
            return 0.0
        inner_area = box.w * box.h
        # ink inside the box (with a small border allowance) does not count
        pad = max(2, int(min(box.w, box.h) * 0.06))
        inner = clean[max(0, box.y - pad): box.y + box.h + pad, max(0, box.x - pad): box.x + box.w + pad]
        ring_pixels = outer.size - inner.size
        ring_ink = int(np.count_nonzero(outer)) - int(np.count_nonzero(inner))
        return round(max(0, ring_ink) / max(1, ring_pixels), 4) if inner_area else 0.0

    def measure(
        self, binary: np.ndarray, clean: np.ndarray, box: Box, typical: tuple[float, float], baseline: float = 0.0
    ) -> dict:
        """Classify one box according to the printed ballot rules.

        Returns dict(is_marked, confidence, density, outside_ink, kind, void_reason).
        kinds: none | x | mark (ink but not X-shaped) | outside (rule kha) | smudged (rule ga)
        """
        margin = max(3, int(min(box.w, box.h) * 0.15))
        roi = binary[box.y + margin: box.y + box.h - margin, box.x + margin: box.x + box.w - margin]
        result = {"is_marked": False, "confidence": 0.0, "density": 0.0, "outside_ink": 0.0, "kind": "none", "void_reason": None}
        if roi.size == 0:
            return result

        density = float(np.count_nonzero(roi)) / roi.size
        outside = self._ring_ink(clean, box)
        oversized = box.w > self.OVERSIZE_RATIO * typical[0] or box.h > self.OVERSIZE_RATIO * typical[1]
        threshold = settings.MARK_THRESHOLD
        result.update(density=round(density, 4), outside_ink=outside)

        marked = density >= threshold
        if marked:
            span = max(self.STRONG_MARK - threshold, 1e-6)
            confidence = 0.5 + 0.5 * min((density - threshold) / span, 1.0)
        else:
            confidence = 1.0 - 0.5 * (density / threshold)

        if density >= settings.SMUDGE_THRESHOLD:
            result.update(is_marked=True, kind="smudged", confidence=1.0,
                          void_reason="Rule (ga): mark is rubbed / scribbled over (box mostly ink)")
            return result
        outside_excess = outside - baseline
        if (outside_excess >= settings.OUTSIDE_INK_THRESHOLD and outside > 2 * baseline) or (marked and oversized):
            result.update(is_marked=True, kind="outside", confidence=round(max(confidence, 0.7), 3),
                          void_reason="Rule (kha): mark is not inside the box")
            return result
        if marked:
            c1, c2 = self._diagonal_coverage(roi)
            x_like = min(c1, c2) >= self.DIAGONAL_MIN_COVERAGE
            if not x_like:
                confidence *= 0.85  # a tick or a dot: counted, but the committee should glance at it
            result.update(is_marked=True, kind="x" if x_like else "mark", confidence=round(min(confidence, 1.0), 3))
            return result
        result.update(confidence=round(confidence, 3))
        return result

    # ------------------------------------------------------------ pipeline
    def extract(self, pil_image: Image.Image, layout: list[dict]) -> PageResult:
        """Detect marks for every candidate in `layout`.

        `layout` items: {candidate_id, position_id, row_index, col_index}
        """
        n_cols = max(1, settings.BALLOT_COLUMNS)
        expected_rows = max((c["row_index"] for c in layout), default=-1) + 1

        gray = self.to_gray(pil_image)
        binary = self.binarize(gray)
        warnings: list[str] = []

        contour = self.largest_component(binary)
        if contour is not None:
            gray, angle = self.deskew(gray, contour)
            if angle:
                logger.info("Deskewed page by %.2f degrees", angle)
                binary = self.binarize(gray)

        table = self.find_table(binary)
        if table is None:
            warnings.append("Ballot table border not found; using the whole page")

        boxes = self.detect_boxes(binary, table)
        grid, grid_warnings, centres = self.build_grid(boxes, n_cols, table)
        warnings.extend(grid_warnings)
        typical = (median(b.w for b in boxes), median(b.h for b in boxes)) if boxes else (1.0, 1.0)
        clean = cv2.bitwise_and(binary, cv2.bitwise_not(self.grid_lines(binary)))
        baseline = median(self._ring_ink(clean, b) for b in boxes) if boxes else 0.0

        # Boxes lost because a mark crosses their border (rule kha)
        recovered = 0
        for r, row in enumerate(grid):
            for c, slot in enumerate(row):
                if slot is None:
                    box = self.recover_lost_box(clean, row, c, centres, typical)
                    if box is not None:
                        grid[r][c] = box
                        recovered += 1

        resolved = len(boxes) + recovered
        layout_ok = resolved == len(layout) and len(grid) == expected_rows
        if resolved != len(layout):
            warnings.append(f"Expected {len(layout)} boxes, detected {len(boxes)}")
        if len(grid) != expected_rows:
            warnings.append(f"Expected {expected_rows} rows, detected {len(grid)}")

        marks: list[MarkResult] = []
        for cand in layout:
            r, c = cand["row_index"], cand["col_index"]
            box = grid[r][c] if r < len(grid) and c < len(grid[r]) else None
            if box is None:
                marks.append(MarkResult(cand["candidate_id"], cand["position_id"], r, c, False, 0.0, 0.0, None))
                continue
            if box not in boxes:  # recovered: the mark merged with the border
                marks.append(MarkResult(
                    cand["candidate_id"], cand["position_id"], r, c, True, 0.8, 0.0, box,
                    kind="outside", void_reason="Rule (kha): mark is not inside the box (crosses the border)",
                ))
                continue
            m = self.measure(binary, clean, box, typical, baseline)
            confidence = round(m["confidence"] * 0.6, 3) if not layout_ok else m["confidence"]
            marks.append(MarkResult(
                cand["candidate_id"], cand["position_id"], r, c, m["is_marked"], confidence, m["density"], box,
                kind=m["kind"], void_reason=m["void_reason"], outside_ink=m["outside_ink"],
            ))

        logger.info(
            "Detected %d/%d boxes, %d marked, layout_ok=%s",
            len(boxes), len(layout), sum(m.is_marked for m in marks), layout_ok,
        )
        return PageResult(marks, len(layout), len(boxes), layout_ok, warnings, gray)

    def extract_oriented(self, pil_image: Image.Image, layout: list[dict]) -> PageResult:
        """`extract`, correcting a page fed upside down or sideways.

        The page is read as it is (portrait) or turned upright (landscape).
        Only if the box grid does not match is the opposite orientation tried.
        A wrong orientation can never match by accident: the box columns would
        sit on the left of each candidate and fall into the ignored left
        column, so the box count comes out wrong.
        """
        first, second = (0, 180) if pil_image.height >= pil_image.width else (90, 270)
        rotate = lambda deg: pil_image.rotate(deg, expand=True, fillcolor="white") if deg else pil_image  # noqa: E731
        result = self.extract(rotate(first), layout)
        if result.layout_ok:
            if first:
                result.warnings.append(f"Page was scanned sideways; turned by {first} degrees")
            return result
        retry = self.extract(rotate(second), layout)
        if retry.layout_ok:
            retry.warnings.append(f"Page was scanned upside down / sideways; turned by {second} degrees")
            logger.info("Corrected page orientation by %d degrees", second)
            return retry
        return result

    def process_file(self, path: str | Path, layout: list[dict]) -> list[PageResult]:
        """Process every page of a scanned file (PDF or image)."""
        return [self.extract_oriented(img, layout) for img in self.render_pages(path)]

    # -------------------------------------------------------------- preview
    @classmethod
    def render_raw_preview(cls, path: str | Path, dest: Path, max_width: int = 1400) -> bool:
        """Save the first page as it was scanned (no marks read).  False if it cannot be rendered."""
        pages = cls.render_pages(path)
        if not pages:
            return False
        page = pages[0].convert("RGB")
        if page.width > max_width:
            page = page.resize((max_width, int(page.height * max_width / page.width)))
        dest.parent.mkdir(parents=True, exist_ok=True)
        page.save(dest, format="PNG")
        return True

    @staticmethod
    def render_preview(result: PageResult, dest: Path, max_width: int = 1400) -> None:
        """Save an annotated PNG: green = marked, grey = empty, red = missing."""
        if result.image is None:
            return
        canvas = cv2.cvtColor(result.image, cv2.COLOR_GRAY2BGR)
        for mark in result.marks:
            if mark.box is None:
                continue
            b = mark.box
            if mark.void_reason:
                colour = (40, 40, 220)  # BGR red: void by the ballot rules
            else:
                colour = (40, 170, 40) if mark.is_marked else (160, 160, 160)
            cv2.rectangle(canvas, (b.x - 4, b.y - 4), (b.x + b.w + 4, b.y + b.h + 4), colour, 3)
            if mark.is_marked:
                label = mark.kind.upper() if mark.void_reason else f"{mark.confidence:.2f}"
                cv2.putText(
                    canvas, label, (b.x, max(b.y - 8, 12)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, colour, 1, cv2.LINE_AA,
                )
        h, w = canvas.shape[:2]
        if w > max_width:
            scale = max_width / w
            canvas = cv2.resize(canvas, (max_width, int(h * scale)), interpolation=cv2.INTER_AREA)
        dest.parent.mkdir(parents=True, exist_ok=True)
        ok, encoded = cv2.imencode(".png", canvas)
        if ok:
            dest.write_bytes(encoded.tobytes())


ocr_service = OCRService()
