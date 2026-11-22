SAMPLE BALLOTS - manual test for PDF and image scanning
=======================================================

pdfs/     Ballot_0001.pdf ... Ballot_0015.pdf   (scanned PDFs, 200 DPI)
images/   Ballot_0016.jpg ... Ballot_0030.jpg   (images, deliberately varied)
            0018, 0024        300 DPI
            0019, 0026        150 DPI
            0020              72 DPI (like a PDF exported to JPG)
            0021              scanned upside down  -> turned upright automatically
            0022              scanned sideways     -> turned upright automatically
            all others        200 DPI
candidates.csv       the 30 candidates printed on these ballots  <-- IMPORT THIS FIRST
answer_key.csv       every mark on every ballot and whether it counts
expected_tally.csv   correct totals: PDFs only, images only, both together

Rule checks (the last three ballots of each set):
  0013 / 0028  rule (ka)  two X for President             -> both President marks VOID
  0014 / 0029  rule (kha) Vice President X crosses border  -> that mark VOID
  0015 / 0030  rule (ga)  General Secretary box scribbled  -> that mark VOID
These six ballots show "Needs review"; all their other marks are counted.

TEST PROCEDURE
1. Start.bat, open http://localhost:3000/admin (admin / admin123).
2. Elections: create the election, set it Active, and press "Publish results"
   so the live screen shows the count.
3. Candidates: "Import CSV" (top right) -> choose Sample Ballots\candidates.csv
   -> Import. The page must then show 30 candidates in 13 positions.
   IMPORTANT: without candidates the system cannot read any ballot. The Ballots
   page then shows a red warning and "Process Scanned folder now" is disabled;
   files in the Scanned folder simply wait.
4. Copy all files from pdfs\ and images\ into the Scanned folder shown in
   Admin -> Overview (data\Scanned). Open http://localhost:3000/dashboard on a
   second screen.
5. Ballots: press "Process Scanned folder now". The ballots are counted in
   file-name order, one after another, and each appears on the live screen.
6. Compare Admin -> Results with expected_tally.csv:
     PDFs only   -> column votes_pdfs
     images only -> column votes_images
     both        -> column votes_total   (401 valid votes in total)
   Counted files move to Completed as Ballot_0001.pdf ... Ballot_0030.jpg.
   Ballots 0013-0015 and 0028-0030 are "Needs review"; nothing goes to Failed.

Afterwards, clear the test data (DBCLEAR.bat, or Ballots -> Select all ->
Delete selected) before the real election.

To rebuild this folder (same ballots, fixed seed):
  cd icbOfficerAssoAPI
  .venv\Scripts\python scripts\make_test_ballots.py
