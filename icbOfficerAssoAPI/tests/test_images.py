"""Image ballots (JPG/PNG/TIFF) and the candidate CSV import."""

import io
import random

import numpy as np
import pytest
from PIL import Image

from app.config import settings
from app.services.ocr_service import ocr_service
from app.utils.sample_ballot import draw_ballot, random_choices
from tests.conftest import TMP, template_positions
from tests.test_ocr import build_layout

MARKED = {"101", "104", "105", "108", "109", "112", "113", "116", "117", "120", "121", "124", "125", "127", "130"}


def ballot_image(marked=MARKED, seed=3) -> Image.Image:
    return draw_ballot(template_positions(), marked, seed=seed)  # A4 at 200 DPI


def marked_voter_nos(result, layout) -> set[str]:
    by_id = {c["candidate_id"]: c["voter_no"] for c in layout}
    return {by_id[m.candidate_id] for m in result.marks if m.is_marked and not m.void_reason}


def save(image: Image.Image, name: str, **kwargs):
    path = TMP / "images" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, **kwargs)
    return path


@pytest.mark.parametrize("dpi", [72, 100, 150, 300, 600])
def test_jpg_at_any_resolution_is_read(dpi):
    """A 72 DPI export used to find no boxes at all: pages are now normalised."""
    image = ballot_image()
    scale = dpi / 200
    image = image.resize((round(image.width * scale), round(image.height * scale)), Image.LANCZOS)
    path = save(image, f"ballot_{dpi}.jpg", quality=80)
    layout = build_layout(template_positions())

    result = ocr_service.process_file(path, layout)[0]

    assert result.layout_ok, result.warnings
    assert marked_voter_nos(result, layout) == MARKED


@pytest.mark.parametrize("degrees", [90, 180, 270])
def test_rotated_scan_is_turned_upright(degrees):
    layout = build_layout(template_positions())
    path = save(ballot_image().rotate(degrees, expand=True, fillcolor="white"), f"rot_{degrees}.jpg", quality=85)

    result = ocr_service.process_file(path, layout)[0]

    assert result.layout_ok, result.warnings
    assert marked_voter_nos(result, layout) == MARKED
    assert any("turned by" in w for w in result.warnings)


def test_exif_orientation_is_respected():
    """Phone/scanner apps often store the page sideways plus an EXIF 'rotate' tag."""
    layout = build_layout(template_positions())
    sideways = ballot_image().rotate(90, expand=True, fillcolor="white")
    exif = Image.Exif()
    exif[0x0112] = 6  # page stored turned 90 deg anticlockwise; tag 6 = "rotate 90 clockwise to view"
    path = save(sideways, "exif.jpg", quality=85, exif=exif)

    result = ocr_service.process_file(path, layout)[0]

    assert result.layout_ok and not any("turned by" in w for w in result.warnings)
    assert marked_voter_nos(result, layout) == MARKED


def test_transparent_png_and_greyscale_png():
    layout = build_layout(template_positions())
    rgba = np.array(ballot_image().convert("RGBA"))
    rgba[(rgba[..., :3] > 200).all(-1)] = (0, 0, 0, 0)  # white paper -> transparent
    for path in (save(Image.fromarray(rgba), "transparent.png"), save(ballot_image().convert("L"), "grey.png")):
        result = ocr_service.process_file(path, layout)[0]
        assert result.layout_ok, (path.name, result.warnings)
        assert marked_voter_nos(result, layout) == MARKED


def test_multi_page_tiff_gives_one_result_per_page():
    positions = template_positions()
    layout = build_layout(positions)
    rng = random.Random(9)
    choices = [random_choices(positions, rng) for _ in range(3)]
    pages = [draw_ballot(positions, marked, seed=i) for i, marked in enumerate(choices)]
    path = TMP / "images" / "batch.tif"
    path.parent.mkdir(parents=True, exist_ok=True)
    pages[0].save(path, save_all=True, append_images=pages[1:], compression="tiff_lzw")

    results = ocr_service.process_file(path, layout)

    assert len(results) == 3
    for result, marked in zip(results, choices):
        assert marked_voter_nos(result, layout) == marked
    path.unlink()  # the file handle is released (moving files matters on Windows)


async def test_image_upload_counts_votes_and_keeps_extension(client, auth, election):
    buf = io.BytesIO()
    ballot_image().save(buf, "JPEG", quality=85)
    response = await client.post(
        f"/api/ballots/upload?election_id={election['id']}", headers=auth,
        files=[("files", ("scan.JPG", buf.getvalue(), "image/jpeg"))],
    )
    assert response.status_code == 200, response.text
    ballot = response.json()[0]
    assert ballot["status"] == "processed", ballot
    assert ballot["total_votes_extracted"] == 15
    assert ballot["pdf_filename"].startswith("Ballot_") and ballot["pdf_filename"].endswith(".jpg")
    assert (settings.completed_path / ballot["pdf_filename"]).exists()
    original = await client.get(f"/api/ballots/{ballot['id']}/file", headers=auth)
    assert original.status_code == 200 and original.headers["content-type"] == "image/jpeg"


# ---------------------------------------------------------------- CSV import
def candidates_csv() -> bytes:
    lines = ["voter_no,post_no,post_en,name_en,name_bn"]
    for post_no, pos in enumerate(template_positions(), start=1):
        for cand in pos["candidates"]:
            lines.append(f"{cand['voter_no']},{post_no},{pos['name']},Person {cand['voter_no']},নাম {cand['voter_no']}")
    return ("\n".join(lines) + "\n").encode("utf-8-sig")


async def new_election(client, auth) -> int:
    response = await client.post("/api/elections/", headers=auth, json={
        "title": f"Import {random.randint(1000, 99999)}", "year": 2026, "total_voters": 50,
    })
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def import_csv(client, auth, election_id, data: bytes, replace=False):
    return await client.post(
        f"/api/candidates/import?election_id={election_id}&replace={str(replace).lower()}", headers=auth,
        files={"file": ("candidates.csv", data, "text/csv")},
    )


async def test_csv_import_creates_positions_and_ballot_order(client, auth):
    election_id = await new_election(client, auth)
    response = await import_csv(client, auth, election_id, candidates_csv())
    assert response.status_code == 201, response.text
    assert len(response.json()) == 30

    detail = (await client.get(f"/api/elections/{election_id}")).json()
    assert len(detail["positions"]) == 13
    listed = (await client.get(f"/api/candidates/election/{election_id}")).json()
    assert [c["voter_no"] for c in listed] == [str(n) for n in range(101, 131)]
    exec_members = [c for c in listed if c["voter_no"] in {"125", "126", "127", "128", "129", "130"}]
    assert [c["display_order"] for c in exec_members] == [0, 1, 2, 3, 4, 5]
    assert listed[0]["name_bn"] == "নাম 101"


async def test_csv_import_validation_and_replace(client, auth):
    election_id = await new_election(client, auth)
    assert (await import_csv(client, auth, election_id, b"name,post\nA,1\n")).status_code == 400
    assert (await import_csv(client, auth, election_id, b"voter_no,post_no,name_en\n1,99,A\n")).status_code == 400
    assert (await import_csv(client, auth, election_id, candidates_csv())).status_code == 201
    # a second import would duplicate voter numbers -> rejected, nothing half-imported
    assert (await import_csv(client, auth, election_id, candidates_csv())).status_code == 400
    assert len((await client.get(f"/api/candidates/election/{election_id}")).json()) == 30
    response = await import_csv(client, auth, election_id, candidates_csv(), replace=True)
    assert response.status_code == 201 and len(response.json()) == 30


async def test_csv_replace_is_refused_once_ballots_exist(client, auth, election):
    buf = io.BytesIO()
    ballot_image().save(buf, "PNG")
    await client.post(f"/api/ballots/upload?election_id={election['id']}", headers=auth,
                      files=[("files", ("one.png", buf.getvalue(), "image/png"))])
    response = await import_csv(client, auth, election["id"], candidates_csv(), replace=True)
    assert response.status_code == 409


async def test_processing_is_refused_without_candidates_and_files_stay(client, auth):
    """Pressing 'Process Scanned folder now' before entering candidates must not
    send every scan to Failed."""
    election_id = await new_election(client, auth)
    path = save(ballot_image(), "waiting.jpg", quality=85)
    target = settings.scanned_path / "waiting_no_candidates.jpg"
    path.replace(target)
    try:
        response = await client.post(f"/api/ballots/scan-folder?election_id={election_id}", headers=auth)
        assert response.status_code == 400 and "no candidates" in response.json()["detail"]
        assert target.exists()
        assert not (settings.failed_path / target.name).exists()
        upload = await client.post(
            f"/api/ballots/upload?election_id={election_id}", headers=auth,
            files=[("files", ("x.jpg", target.read_bytes(), "image/jpeg"))],
        )
        assert upload.status_code == 400
    finally:
        target.unlink(missing_ok=True)
