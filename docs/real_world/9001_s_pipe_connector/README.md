# 9001 — S-Shaped Flanged Pipe Connector (real-world validation part)

Source: GrabCAD, "S-Shaped Flanged Pipe Connector" by Mehdi Jalali
(`s-shaped-flanged-pipe-connector-1.snapshot.6.zip`). Exported from SolidWorks.

## Files
| File | Status |
|---|---|
| `Part1.STEP` | Original, STEP AP203, units **mm** |
| `Part1.igs` | Converted from the STEP with `tools/inspect_cad.py --to-iges` (BRep solids). Re-reads with identical geometry. |
| `Part1.SLDDRW` | SolidWorks drawing. **Not readable from Python**; also the `.SLDPRT` it references is NOT in the zip, so views may be blank. Needs SolidWorks / eDrawings → PDF. |
| `*.png` | Renders only (not drawings) |

## Geometry facts (from `python tools/inspect_cad.py Part1.STEP`)
| Fact | Value | Reliability |
|---|---|---|
| Units | mm | High (STEP header) |
| Bodies | **2 separate solids**, touching, zero overlap (vol 537,540 + 805,803 mm³) | High — real-world multi-body gotcha |
| Overall bbox (axis aligned) | 435 x 235 x 140 mm | High |
| Oriented bbox | 140 x 194.8 x 488.0 mm | Medium (depends on OBB algorithm) |
| Flange OD | D140 (2 flanges) | High |
| Bore | D80 (at both flanges) | High |
| Bolt holes | **12 x D15** total (6 per flange, assumed — verify against renders) | Medium |
| Volume | 1,343,343 mm³ (≈ 10.5 kg in steel, ≈ 3.6 kg in Al) | Medium — only valid because solids don't overlap |

## Why it's a useful test
- Multi-body STEP (app must not assume one solid).
- Two flanges facing different directions (hole counting off-axis).
- Free-form S-bend → axis-aligned bbox ≠ true envelope.
- No usable drawing PDF → app must say the drawing is unavailable/unreadable.

## TODO for the team
- Write an Excel record row for part **9001** (material, stock, machine, ops, cycle time).
  Suggested planted mismatch: Excel says `8 x D15 holes` → app must flag vs IGES 12.
- Produce a PDF from `Part1.SLDDRW` if someone has SolidWorks/eDrawings.
