SPEC'26 - HARD MODE test batch (synthetic). Use AFTER your app works on the clean batch.

excel/messy_workshop_export.xlsx  one workbook, 5 sheets: Summary (noise), Master List (header on row 6),
                                  Part Card 3003 (vertical layout), Archive_2025 (obsolete data).
pdf/3001_gear_blank_scan.pdf      SCANNED, image only. Text extraction returns nothing.
pdf/3002_coupling_hub_RevB.pdf    2 pages, revision history + drawing.
pdf/3003_base_plate.pdf           1:2 scale, material only in a note.
pdf/3004_shaft_collar.pdf         mm drawing; Excel is in inches.
ground_truth_batch2.json          answer key for you.

Good questions to ask the app
  3001: what is the bore? (needs OCR/vision; if the app cannot read the scan it must say so, not guess)
  3002: what is the bore diameter? (must say 20 mm, Rev B; ideally mention Rev A was 18 and superseded)
  3003: what material? how many holes? (holes: expect a flagged disagreement)
  3004: what is the outer diameter? (50.8 mm = 2.000 in; no mismatch)
  any:  what is the unit price / delivery date? -> "Not found in the provided files"
