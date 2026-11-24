SAMPLE BALLOTS 24-11-2026 - Bengali ballot with QR code, bar code and large number box
(Blank ballot\Blank_ballot_form.docx)
====================================================================================

25 scanned ballot images (JPG), A4, made from the Word form itself (exported by Word):
QR code and Bengali title, ballot paper number box (38 x 14 mm), then one row
per post with the post name in the middle column and its two candidates on either side:
  voter no + candidate name | box | post name | voter no + candidate name | box
Executive Member (6 candidates, up to 3 votes) takes 3 rows with one merged post-name cell.
Footer: the instructions (ka/kha/ga), Election Commissioner and seal; bar code bottom centre.
Same form as 17-11-2026 (same names, same table, same place on the page) plus:
  - QR code (top left) and bar code (bottom centre, under the candidate table; it was at the
    bottom left on the form of 19-11-2026), both reading ICBOA-20-2026 on every paper;
    the counting system does not need them, they mark the paper as a ballot of this election.
  - a larger number box (38 x 14 mm; it was 32 x 12 mm on the form of 21-11-2026): the form is
    printed WITHOUT a number and the 6 digit ballot paper number (০০০০০১ ... ০০০৪৫৫)
    is stamped into the box by hand with the automatic numbering machine.
Both halves are the same: equal candidate columns, equal boxes, one font size.
Candidates: candidates.csv of this folder = the names and the left / right places of the
Word form (first candidate of a row = left side). Voter number on the first line, name below.

FILE NAME MUST MATCH THE BALLOT NUMBER
  Images named img_<number>.jpg are checked: the number in the file name must be the ballot
  paper number stamped in the box at the top right (read from the scan). 'img' and the
  extension may be any upper/lower case (IMG_0001.JPG, iMg_0001.Jpeg); jpg and jpeg are both
  accepted. Leading zeros do not count: img_0001 = paper 000001 = paper 1.
  A mismatch, or a paper whose number cannot be read, goes to 'Needs review'.
  So does a number that was never issued (above 000455 = Total voters of the election).
  Bengali (০-৯) and English (0-9) digits are both read; the system shows them as 000001.
  Stamp the number INSIDE the box, clear of its border, in dark ink (black or blue).
  Here: 0019 is saved as ..._0091 (typing error), 0021 is a photocopy of paper 0002, 0022 is
  paper 0026, and 0023 has an empty number box.

FILES
  img_0001.jpg ... IMG_0025.JPEG  (mixed case on purpose)
  candidates.csv      the 30 candidates  <-- IMPORT THIS FIRST (Admin -> Candidates -> Import CSV)
  answer_key.csv      every mark on every ballot and what the system must do with it
  expected_tally.csv  votes_counted_by_system = what Admin -> Results must show
  Total valid votes: 315.
  Blank ballot\Blank_ballot_form.docx          the form (Word) - the source of everything here
  Blank ballot\Blank_ballot_form.png / .pdf   the unmarked form (no X, no number) - PRINT THIS
                      (455 copies), then stamp the numbers. Do NOT copy it into the Scanned folder.

WHAT EACH BALLOT TESTS                                                         expected status
--------------------------------------------------------------------------------------------------------------
  IMG_0001.jpeg     paper 000001  Correct ballot: one X in every post, 3 Executive Members
        scan: 200 DPI;  -> Processed
  Img_0002.JPG      paper 000002  Correct ballot (this paper is photocopied as file no 0021)
        scan: 200 DPI;  -> Processed
  iMg_0003.JPEG     paper 000003  Some posts left blank on purpose (allowed)
        scan: 200 DPI;  -> Processed
  imG_0004.Jpg      paper 000004  Rule (ka): two X for President -> both President marks void
        scan: 200 DPI;  -> Needs review: over-vote
  IMg_0005.jPeg     paper 000005  Rule (kha): Vice President X crosses the box border -> void
        scan: 200 DPI;  -> Needs review: void mark
  iMG_0006.jpg      paper 000006  Rule (ga): General Secretary box scribbled over -> void
        scan: 200 DPI;  -> Needs review: void mark
  ImG_0007.jpeg     paper 000007  Treasurer box 1 scribbled out, X in box 2 -> both boxes touched, no vote for the post
        scan: 200 DPI;  -> Needs review: void mark
  img_0008.JPG      paper 000008  Tick marks instead of X (President, Office Secretary, Sports Secretary) -> counted
        scan: 200 DPI;  -> Processed (a tick / slash counts; a light one lowers the confidence and may also ask for review)
  IMG_0009.JPEG     paper 000009  Single slash '/' instead of X (Asst. Gen. Secretary, Drama Secretary) -> counted
        scan: 200 DPI;  -> Processed (a tick / slash counts; a light one lowers the confidence and may also ask for review)
  Img_0010.Jpg      paper 000010  Only a small dot in the Cultural Secretary box, the other box empty -> the dot counts
        scan: 200 DPI;  -> Processed
  iMg_0011.jPeg     paper 000011  Rule (ka): 4 Executive Members marked (3 allowed) -> all 4 void
        scan: 200 DPI;  -> Needs review: over-vote
  imG_0012.jpg      paper 000012  Only 1 Executive Member marked (fewer than 3 is allowed) -> counted
        scan: 200 DPI;  -> Processed
  IMg_0013.jpeg     paper 000013  Rule (kha): Publication Secretary X drawn beside the box, box empty -> void
        scan: 200 DPI;  -> Needs review: void mark
  iMG_0014.JPG      paper 000014  X on the candidate's NAME (Organizing Secretary) and a circled name (Hospitality) -> no vote
        scan: 200 DPI;  -> Processed
  ImG_0015.JPEG     paper 000015  Faint pencil X marks everywhere -> counted
        scan: 200 DPI;  -> Processed
  img_0016.Jpg      paper 000016  Stray pen line across the names (not through a box) -> ignored; votes counted
        scan: 200 DPI;  -> Processed
  IMG_0017.jPeg     paper 000017  Completely blank ballot -> 0 votes
        scan: 200 DPI;  -> Processed
  Img_0018.jpg      paper 000018  Every box marked -> every post over-voted, all void (rule ka)
        scan: 200 DPI;  -> Needs review: over-vote
  iMg_0091.jpeg     paper 000019  Scanned crooked (2.5 degrees) at 150 DPI; scanner operator typed the file number wrong (0091) -> mismatch
        scan: 150 DPI, skewed +2.5 deg;  -> Needs review: file number 0091 does not match paper 000019
  imG_0020.JPG      paper 000020  Scanned upside down -> turned upright, counted
        scan: 200 DPI, upside down;  -> Processed
  IMg_0021.JPEG     paper 000002  PHOTOCOPY of paper 0002 saved as file 0021 -> the file number 0021 does not match paper 0002
        scan: 200 DPI, photocopy;  -> Needs review: file number 0021 does not match paper 000002
  iMG_0022.Jpg      paper 000026  Paper 0026 saved as file 0022 -> the file number does not match the printed number
        scan: 200 DPI;  -> Needs review: file number 0022 does not match paper 000026
  ImG_0023.jPeg     paper ------  Ballot paper number box left empty -> the paper number cannot be read, needs review
        scan: 200 DPI;  -> Needs review: file number 0023: paper number cannot be read
  img_0024.jpg      paper 000024  Scanned sideways at 300 DPI -> turned upright, counted
        scan: 300 DPI, sideways;  -> Processed
  IMG_0025.jpeg     paper 000025  Mixed: two X Treasurer (ka), X across border Sports (kha), tick Drama, dark noisy scan
        scan: 200 DPI, skewed -1.2 deg, dark noisy scan;  -> Needs review: void mark, over-vote (a tick / slash counts; a light one lowers the confidence and may also ask for review)

TEST PROCEDURE
1. Start the system, open Admin (admin / admin123).
2. Elections: create the election, set it Active.
3. Candidates: Import CSV -> this folder's candidates.csv (30 candidates, 13 posts).
4. Copy all 25 image files into the Scanned folder (Admin -> Overview) and process them.
5. Compare Admin -> Results with expected_tally.csv (votes_counted_by_system).
   Ballots -> filter 'Needs review': open 0019, 0021, 0022 and 0023 - the warning list states
   'File number: ...' (mismatch / number not readable).

To rebuild this folder (same ballots, fixed seed):
  cd icbOfficerAssoAPI
  .venv\Scripts\python scripts\make_bn_ballots.py        (needs Microsoft Word)
The form itself (QR code, bar code, number box) is built by scripts\make_ballot_form.py.
