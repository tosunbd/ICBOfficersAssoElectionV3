"""Ballot paper number printed in the box at the top right, and the img_<no>.jpg file-name check."""

from pathlib import Path

import numpy as np
import pytest
from PIL import ImageDraw, ImageFont

from app.utils import paper_number
from app.utils.paper_number import file_paper_no, read_paper_no
from app.utils.sample_ballot import draw_ballot
from tests.conftest import TMP, template_positions
from tests.test_api import upload

NIRMALA = Path("C:/Windows/Fonts/Nirmala.ttc")


def _gray(image) -> np.ndarray:
    return np.asarray(image.convert("L"))


def test_file_paper_no_accepts_any_case_of_img_and_jpg():
    assert file_paper_no("img_0001.jpg") == "0001"
    assert file_paper_no("IMG_0001.JPG") == "0001"
    assert file_paper_no("iMg_0007.Jpeg") == "0007"
    assert file_paper_no("ImG_0012.jPeg") == "0012"
    for other in ("Ballot_0001.jpg", "img_0001.png", "img0001.jpg", "img_.jpg", "img_00a1.jpg", "scan_0001.jpg"):
        assert file_paper_no(other) is None


@pytest.mark.parametrize("number", ["0001", "2345", "6789", "1190"])
def test_reads_english_digits_in_the_box(number):
    assert read_paper_no(_gray(draw_ballot(template_positions(), set(), ballot_no=number, seed=1))) == number


@pytest.mark.skipif(not NIRMALA.exists(), reason="needs a Bengali font")
@pytest.mark.parametrize("number", ["0001", "2345", "6789", "1190"])
def test_reads_bengali_digits_in_the_box(number):
    image = draw_ballot(template_positions(), set(), seed=2)
    font = ImageFont.truetype(str(NIRMALA), 34, index=1)
    ImageDraw.Draw(image).text((1352, 120), number.translate(str.maketrans("0123456789", "০১২৩৪৫৬৭৮৯")), fill="black", font=font)
    assert read_paper_no(_gray(image)) == number


def test_empty_box_or_page_reads_nothing():
    assert read_paper_no(_gray(draw_ballot(template_positions(), set(), seed=3))) is None
    assert read_paper_no(None) is None


def _image(name: str, number: str | None, seed: int):
    image = draw_ballot(template_positions(), {"101"}, ballot_no=number, seed=seed)
    path = TMP / "generated" / name
    image.save(path, "JPEG", quality=90)
    return path


async def test_file_number_must_be_the_ballot_number(client, auth, election):
    same = (await upload(client, auth, election["id"], _image("IMG_0005.JPEG", "0005", 21)))[0]
    assert same["status"] == "processed", same["ocr_warnings"]
    assert same["printed_paper_no"] == "0005"

    other = (await upload(client, auth, election["id"], _image("iMg_0060.Jpg", "0006", 22)))[0]
    assert other["status"] == "needs_review"
    assert any("MISMATCH" in w and "0060" in w and "0006" in w for w in other["ocr_warnings"])

    short = (await upload(client, auth, election["id"], _image("img_7.jpg", "0007", 23)))[0]
    # leading zeros do not count: a numbering machine stamps 000007 on the paper saved as img_7 / img_0007
    assert short["status"] == "processed", short["ocr_warnings"]
    assert paper_number.same_paper("0001", "000001") and paper_number.same_paper("460", "0460")
    assert not paper_number.same_paper("0010", "0001") and not paper_number.same_paper("0001", None)

    unread = (await upload(client, auth, election["id"], _image("img_0008.jpeg", None, 24)))[0]
    assert unread["status"] == "needs_review"
    assert any("could not be read" in w for w in unread["ocr_warnings"])

    plain = (await upload(client, auth, election["id"], _image("scan_0009.jpg", None, 25)))[0]
    assert plain["status"] == "processed"  # other file names are not checked
