SPEC'26 CNC analyzer - SYNTHETIC TEST DATA
===========================================
excel/mfg_record_A.xlsx   parts 2280, 2281, 2282. Sheets: Parts, Operations.
                          Headers in row 1. Part No is numeric for 2280/2281 and TEXT for 2282.
excel/job_cards_B.xlsx    parts 2283, 2284. Sheets: Job Cards, Tooling.
                          Banner rows above the header (header is on row 4). Different column names
                          (Item Code, Mat. Grade, Raw Stock, Final Dims...). Part numbers are text.
pdf/2280_flange.pdf  2281_shaft.pdf  2282_bracket.pdf  2283_bushing.pdf
                          Text-based drawings (not scanned). Title block + dimension text are extractable.
                          2281 uses different title-block labels and position. 2282 is in INCHES.
ground_truth.json         true dimensions + planted issues (for YOU; do not feed to the app).

NOT INCLUDED: IGES files. Model each part in FreeCAD from ground_truth.json and export .igs.

What each part tests
  2280  happy path, all sources agree
  2281  different title-block layout/labels
  2282  unit conversion (inch PDF vs mm Excel) - must NOT be flagged as a mismatch
  2283  planted mismatch: OD 50 vs 48, material brass vs bronze - MUST be flagged
  2284  missing PDF and IGES - must say NOT AVAILABLE, not guess

Questions that should return "Not found in the provided files"
  unit price / cost, customer name, delivery date, weight (if IGES is surfaces only)
Questions that should be answerable
  material, stock size, machine, cycle time, tolerance, number of holes, hole diameter, operations, tools

Notes
  - No Excel column holds price, on purpose.
  - Company name "ACME PRECISION MACHINING" is fictional.
