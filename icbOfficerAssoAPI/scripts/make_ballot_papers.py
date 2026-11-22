r"""Print-ready ballot papers from the approved Word form (needs Microsoft Word).

Run from the icbOfficerAssoAPI folder:

    .venv\Scripts\python scripts\make_ballot_papers.py                 the empty form only
    .venv\Scripts\python scripts\make_ballot_papers.py 1 460           and numbered papers

The form is <project>/Sample Ballots/21-11-2026/Blank ballot/Blank_ballot_form.docx
(QR code, bar code and the large number box: scripts/make_ballot_form.py; read
only here).  Written next to it:

    Blank_ballot_form.pdf / .png          the empty form (no ballot number): print this
                                          one and stamp the numbers with the numbering machine
    Ballot_papers_0001_to_0460.pdf        only when first / last are given: one ballot per
                                          page with the number printed (০০০১ ... ০৪৬০), for an
                                          election without a numbering machine
"""

from __future__ import annotations

import re
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path

import pypdfium2 as pdfium
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
FOLDER = ROOT / "Sample Ballots" / "21-11-2026"
TEMPLATE = FOLDER / "Blank ballot" / "Blank_ballot_form.docx"
DPI = 200

BN_DIGITS = str.maketrans("0123456789", "০১২৩৪৫৬৭৮৯")
EN_DIGITS = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")
TITLE_PREFIX = "জনাব "

_TBL = re.compile(r"<w:tbl>.*?</w:tbl>", re.S)
_ROW = re.compile(r"<w:tr[ >].*?</w:tr>", re.S)
_CELL = re.compile(r"<w:tc>.*?</w:tc>", re.S)
_PARA = re.compile(r"<w:p[ >].*?</w:p>", re.S)
_TEXT = re.compile(r"<w:t(?: [^>]*)?>([^<]*)</w:t>")


def bn(value) -> str:
    return str(value).translate(BN_DIGITS)


def _document_xml(template: Path) -> str:
    with zipfile.ZipFile(template) as z:
        return z.read("word/document.xml").decode("utf-8")


def template_candidates(template: Path = TEMPLATE) -> list[tuple[str, str]]:
    """(voter no, Bengali name) of every candidate printed on the form, row by row,
    left candidate before the right one."""
    table = _TBL.findall(_document_xml(template))[1]
    out = []
    for row in _ROW.findall(table)[1:]:
        for cell in _CELL.findall(row):
            lines = ["".join(_TEXT.findall(p)).strip() for p in _PARA.findall(cell)]
            if len(lines) == 2 and lines[1].startswith(TITLE_PREFIX):
                out.append((lines[0].translate(EN_DIGITS), lines[1][len(TITLE_PREFIX):].strip()))
    return out


def numbered_docx(numbers: list[str | None], out: Path, template: Path = TEMPLATE) -> None:
    """Copy of the form with one page per entry of `numbers`; each page has that
    number (None = empty box) in the ballot paper number box, nothing else changed."""
    xml = _document_xml(template)
    start = xml.index("<w:body>") + len("<w:body>")
    end = xml.rindex("<w:sectPr")
    body, sect = xml[start:end], xml[end: xml.rindex("</w:body>")]
    body = re.sub(r' w14:(?:paraId|textId)="[^"]*"', "", body)  # ids must not repeat

    # the number box = 4th cell of the first (title) table
    table = _TBL.search(body)
    box = list(_CELL.finditer(table.group(0)))[3]
    if _TEXT.search(box.group(0)):
        raise SystemExit(f"{template.name}: the ballot paper number box must be empty")
    at = table.start() + box.start() + box.group(0).rindex("</w:p>")
    # digits 1.2 pt apart: bold Bengali digits set tight (৮৩, ৫২ ...) touch and are then misread from the scan
    run = '<w:r><w:rPr><w:b/><w:bCs/><w:spacing w:val="24"/><w:sz w:val="24"/><w:szCs w:val="24"/></w:rPr><w:t>%s</w:t></w:r>'
    # a next-page section break after every page but the last
    page_end = ('<w:p><w:pPr><w:spacing w:line="20" w:lineRule="exact"/><w:rPr><w:sz w:val="2"/><w:szCs w:val="2"/></w:rPr>'
                f"{sect}</w:pPr></w:p>")
    pages = [body[:at] + (run % bn(n) if n else "") + body[at:] for n in numbers]
    # picture ids (QR code, bar code) must not repeat from page to page
    pages = [re.sub(r'(<(?:wp:docPr|pic:cNvPr) id=")(\d+)"', lambda m, k=k: f'{m[1]}{int(m[2]) + 10 * k}"', page)
             for k, page in enumerate(pages)]
    xml = xml[:start] + page_end.join(pages) + xml[end:]
    with zipfile.ZipFile(template) as src, zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as dst:
        for item in src.infolist():
            dst.writestr(item, xml.encode("utf-8") if item.filename == "word/document.xml" else src.read(item.filename))


def docx_to_pdf(docx: Path, pdf: Path) -> None:
    """Export with Microsoft Word (own hidden instance; the file is opened read only)."""
    quote = lambda p: "'" + str(p.resolve()).replace("'", "''") + "'"  # noqa: E731
    script = (
        "$ErrorActionPreference = 'Stop'; $w = New-Object -ComObject Word.Application; $w.Visible = $false; $w.DisplayAlerts = 0; "
        f"try {{ $d = $w.Documents.Open({quote(docx)}, $false, $true); $d.ExportAsFixedFormat({quote(pdf)}, 17); $d.Close(0) }} "
        "catch { 'ERROR: ' + $_.Exception.Message; exit 3 } finally { if ($w.Documents.Count -eq 0) { $w.Quit() } }"
    )
    message = ""
    for attempt in range(3):
        # a Word instance that is still closing from the export before makes the next one fail: wait and retry
        time.sleep(3 if attempt == 0 else 15)
        pdf.unlink(missing_ok=True)
        done = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
                              capture_output=True, text=True, timeout=1800)
        if done.returncode == 0 and pdf.exists():
            return
        message = (done.stdout.strip() or done.stderr.strip() or f"exit code {done.returncode}")
    raise SystemExit(f"Microsoft Word could not export {docx.name}: {message}")


def ballot_pdf(numbers: list[str | None], pdf: Path, template: Path = TEMPLATE) -> None:
    """PDF with one ballot per entry of `numbers` (None = empty number box)."""
    with tempfile.TemporaryDirectory(prefix="icb-ballot-papers-") as work:
        docx = Path(work) / "ballots.docx"
        numbered_docx(numbers, docx, template)
        docx_to_pdf(docx, pdf)
    with_pages = pdfium.PdfDocument(pdf)
    count = len(with_pages)
    with_pages.close()
    if count != len(numbers):
        raise SystemExit(f"{pdf.name}: {count} pages for {len(numbers)} ballots - the form no longer fits on one page")


def render_pages(pdf: Path, dpi: int = DPI) -> list[Image.Image]:
    doc = pdfium.PdfDocument(pdf)
    try:
        return [page.render(scale=dpi / 72).to_pil().convert("RGB") for page in doc]
    finally:
        doc.close()


def write_blank(folder: Path, template: Path = TEMPLATE) -> Image.Image:
    """Blank_ballot_form.pdf + .png (the empty form) in `folder`; returns the page image."""
    pdf = folder / "Blank_ballot_form.pdf"
    ballot_pdf([None], pdf, template)
    image = render_pages(pdf)[0]
    image.save(folder / "Blank_ballot_form.png", dpi=(DPI, DPI))
    return image


def main() -> None:
    folder = TEMPLATE.parent
    write_blank(folder)
    print(f"Wrote {folder / 'Blank_ballot_form.pdf'} and .png")
    if len(sys.argv) < 3:
        return
    first, last = int(sys.argv[1]), int(sys.argv[2])
    out = folder / f"Ballot_papers_{first:04d}_to_{last:04d}.pdf"
    ballot_pdf([f"{n:04d}" for n in range(first, last + 1)], out)
    print(f"Wrote {out} ({last - first + 1} pages)")


if __name__ == "__main__":
    main()
