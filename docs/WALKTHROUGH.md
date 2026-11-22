# Election-day walkthrough

This is the full sequence from an empty system to published results.
Screens are in the admin panel at `http://<server>:3000/admin`.

## Before the election

1. **Log in** with the admin account and change the password (Settings).
2. **Elections → New election.** Enter the title (English and Bengali), the year
   and the number of eligible voters (used for the turnout percentage).
3. **Seed the 13 ICB positions** (button on the Elections page). Check the
   "Elect" column: Executive Member elects 3, all others 1. Edit if the ballot
   design changes; the order must match the printed ballot from top to bottom.
4. **Candidates.** For every position add the candidates **in the order they are
   printed on the ballot** (left box first, then right box, next row, …).
   The ballot number / voter number and the Bengali name are shown on the dashboard.
   Faster: **Import CSV** (top right of the Candidates page) loads the whole list
   from a CSV file with the columns `voter_no, post_no, name_en, name_bn`, one row
   per candidate in ballot order (`Sample Ballots/candidates.csv` is an example;
   in Excel use *Save As → CSV UTF-8* so Bengali names survive). If the election
   has no positions yet, the 13 standard posts are created automatically.
   *For a rehearsal you can instead use "Seed with template candidates (rehearsal)",
   which creates the 30 placeholder candidates of the sample ballot.*
5. **Rehearsal with sample ballots.** The quickest way is the ready-made rehearsal
   (`scripts/seed_rehearsal.py`, see [RUN_WITHOUT_DOCKER.md](RUN_WITHOUT_DOCKER.md)):
   it creates a "Rehearsal Election" with anonymous candidates and 10 PDFs in
   `data/Scanned`, which you count by pressing **Process Scanned folder now**.
   The folder `Sample Ballots` holds a ready-made manual test: 10 PDFs and
   10 JPG images with an answer key, see `Sample Ballots/README.txt`.
   For your real election, `scripts/make_sample_ballots.py --count 10 --overvote 1`
   writes sample PDFs that match *its* candidates (API must be running).
   Afterwards delete the test ballots (Ballots → open → Delete) or create the
   real election as a new election.
   Before election day set `AUTO_PROCESS_ENABLED=true` and
   `PROCESS_DELAY_SECONDS=0` in `.env` so scans are counted automatically.
6. **Set the election to Active** (Elections page). Only the active election
   receives files from the Scanned folder. Other active elections are closed.
7. **Scanner setup.** Configure the scanner to save PDF or image files (JPG, PNG,
   TIFF, BMP, WebP) into the Scanned folder shown in Admin → Overview. 200 dpi
   grey-scale or black/white is ideal; colour and any resolution from 72 to 600 dpi
   also work (every page is scaled to the same working size). One page per ballot;
   multi-page PDFs or TIFFs from a document feeder are fine (each page becomes one
   ballot). A page fed upside down or sideways is turned upright automatically.

## During counting

1. Scan a ballot (or a batch). The file appears in the Scanned folder and is
   processed within a few seconds; Admin → Overview shows "Files waiting" and
   the counters, and the public dashboard updates immediately.
2. The **public live screen** (`/dashboard`) is meant for a projector or TV
   (press **⛶ Full screen**). Every counted ballot is shown for
   the election's **Seconds per ballot** (Admin → Elections, 20 s unless you
   change it): the scanned paper with the detected
   marks, the votes on it, and the totals growing by one so voters and
   candidates can follow the count. Until you press **Publish results** it
   only shows the progress (ballots counted), not the numbers. **Pause live
   updates** freezes the screen at any moment.

   When you press **Publish results**, the screen starts from zero and counts
   again ballot by ballot, from the first file scanned, one every
   **Seconds per ballot**. The standings below grow with each ballot
   (a candidate marked on ballots 1 and 3 shows 1, 1, 2) and the header shows
   **COUNTING 12 / 230**. Ballots scanned meanwhile join the end of the queue.
   Results & controls shows the progress, with **Skip to totals** and
   **Count again**. Admin pages always show the real totals.
3. **Needs review.** A ballot is flagged when:
   * a position has more marks than allowed (over-vote) → those marks are stored but **not counted**;
   * the number of boxes found on the page does not match the ballot layout (bad scan, skewed page);
   * a mark is faint (confidence below the threshold).

   Open Ballots → filter **Needs review** → **Review**. The scanned page is shown
   with the detected boxes; tick the correct candidates on the right, enter the
   ballot paper number if you want, and **Save as manual file**. The Election
   Commission's selection replaces the automatic one and counts in the totals
   (Reports show it as a **Manual file**). A ballot is never rejected as a
   whole: a mark that breaks the rules is simply not counted. You can also
   **re-read** the scan.
4. **Errors.** Unreadable files are moved to `data/Failed` and listed with status
   *error*; they are not in the totals yet. Re-scan the paper, or open the file,
   tick the candidates marked on the paper and **Save as manual file**: it then
   counts like every other ballot.

## After counting

1. **Results & Controls** shows every position ranked; the gold rank badges are
   the candidates currently within the elected seats. Press **Recount from
   records** if you ever doubt the counters (it rebuilds them from the stored votes).
2. **Export CSV** for the minutes.
3. Set the election to **Completed**. The dashboard keeps showing the final
   result (the newest election is shown when none is active).
4. Keep a copy of the `data/` folder (database + all scanned files + previews).
5. The **Audit Log** lists every publish/pause, review, recount and status change
   with the user and time.

## The three printed rules and how the system applies them

| Rule on the ballot | What the reader does |
|---|---|
| **ক** প্রতিটি পদের প্রার্থীর নামের পাশের বক্সে X দিয়ে ভোট দিন | One mark per candidate box; a post with **more marks than seats** (1, or 3 for Executive Member) is an over-vote: those marks are stored but **not counted**. A mark that does not look like an X (a tick, a dot) is counted but lowers the confidence so the ballot is reviewed. |
| **খ** X চিহ্ন যেন বক্সের মধ্যে থাকে। অন্যথায় ভোট বাতিল বলে গণ্য হবে। | Ink **around** the box (X drawn beside it, or an X so large it crosses the printed border) makes that vote **void**. |
| **গ** X চিহ্ন ঘষা-মাজা করলে ভোট বাতিল বলে গণ্য হবে। | A box that is mostly ink (scribbled over, blacked out, rubbed) is a **void** mark. A faint, half-erased mark lowers the confidence and is sent for review. |

Void marks are shown in **red** on the review preview and on the live screen
("outside box · খ", "rubbed · গ", "extra mark · ক"); the reason is stored with
the vote (`invalid_reason`) and listed on the review page. Any ballot with a
void mark is flagged **Needs review** so the committee has the final word: on
the review page the committee can confirm the automatic decision or tick the
candidate the voter intended. Only the rule-abiding marks on such a ballot are
counted; the rest of the ballot still counts (the system voids the *vote*, not
the whole paper; to void a paper, tick "Void this ballot" on the review page).

## Ballot paper numbers and file names

Every counted ballot receives the next **ballot paper number** of the election
(0001, 0002, …). The scanned file is moved to `data/Completed` renamed to
`Ballot_0001.pdf` (a multi-page scan becomes `Ballot_0011-0020.pdf`). If the
committee changes the number on the review page, the file is renamed to match.
The number is shown on the live screen ("Paper no. 0007") and in Admin → Ballots.

## What the automatic reader does (so you know what to look out for)

* It finds the ballot table by its printed grid lines, straightens the page if
  it was scanned slightly rotated, and looks for the small rectangular boxes
  inside the table (two per row: candidate | box | post name | candidate | box).
* A box counts as **marked** when more than 6% of its inside is ink. A normal
  pen X covers 15–25%, an empty box 0–1%. A tick, a scribble or a filled box
  all count as marks.
* Marks that touch or cross the box border are still detected; a mark drawn
  completely **outside** the box is not, which is consistent with the printed
  instruction "put an X inside the box".
* Ballots where a voter crossed out a mark (rule গ on the ballot) cannot be
  told apart automatically; they typically show up as an over-vote and are
  flagged for review.
