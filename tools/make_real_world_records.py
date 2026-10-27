"""Build docs/real_world/real_world_records.xlsx - Excel records for real-world validation parts.

Same layout as data/mfg_record_A.xlsx (sheets "Parts" + "Operations", header on row 1)
so the existing schema-agnostic ingester can read it. Kept OUT of data/ so it does not
change the synthetic eval suite; ingest explicitly with:

    uv run cnc ingest ../docs/real_world/real_world_records.xlsx

Add new parts to PARTS / OPERATIONS and re-run:

    python tools/make_real_world_records.py

Planted issues are documented in backend/evals/answer_keys/ground_truth_real_world.json.
"""
from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter

OUT = Path(__file__).resolve().parents[1] / "docs" / "real_world" / "real_world_records.xlsx"

PARTS_HEADER = [
    "Part No", "Description", "Material", "Stock Size (mm)", "Finished Size (mm)", "Holes",
    "Machine", "Cycle Time (min)", "General Tolerance", "Surface Finish", "Heat Treatment",
    "Batch Qty",
]

PARTS = [
    [
        "9001",
        "S-Shaped Flanged Pipe Connector",
        "ASTM A216 WCB cast steel",
        "2-piece casting (elbow + S-taper), welded at seam; approx. 440 x 240 x 145 envelope",
        "435 x 235 x 140 envelope; 2 x flange \u00d8140, bore \u00d880",
        # PLANTED MISMATCH: IGES/STEP has 12 x D15 (6 per flange on D120 PCD)
        "8 x \u00d815 through on \u00d8120 PCD (4 per flange)",
        "Haas VF-2 mill, Mazak QT-200 lathe",
        55,
        "\u00b10.2 mm (ISO 2768-c)",
        "Ra 3.2 on flange faces",
        "Normalized",
        20,
    ],
    [
        "9002",
        "Wider Air Gripper HFT Series (HFT32)",
        "Aluminum 6061-T6",
        "255 x 110 x 90 (billet block)",
        "245 x 100 x 82 envelope; Bore \u00d832, Stroke 60 mm",
        "Mounting holes M8x1.25, 4 x \u00d84.2, 4 x \u00d812 c-bore",
        "Haas VF-2 mill",
        42,
        "\u00b10.05 mm",
        "Ra 0.8",
        "Hard Anodize",
        50,
    ],
    [
        "9003",
        "Clamp Cylinder MCK Series (MCK80)",
        "Aluminum 7075-T6",
        "260 x 125 x 100 (billet block)",
        # PLANTED MISMATCH: Excel claims Stroke 75 mm; PDF technical data & 3D model are Stroke 50 mm (MCK80x50)
        "253 x 115 x 93 envelope; Bore \u00d880, Stroke 75 mm",
        "Port threads PT 3/8, mounting M6x1",
        "Mazak Integrex e-420H",
        65,
        "\u00b10.05 mm",
        "Ra 0.8",
        "None",
        30,
    ],
]

OPS_HEADER = ["Part No", "Op No", "Operation", "Machine", "Tool", "Setup (min)", "Run (min)"]

OPERATIONS = [
    ["9001", 10, "Face flange A and turn OD \u00d8140", "Mazak QT-200", "CNMG 120408 insert", 15, 6],
    ["9001", 20, "Face flange B and turn OD \u00d8140", "Mazak QT-200", "CNMG 120408 insert", 15, 6],
    ["9001", 30, "Finish bore \u00d880 both ends", "Mazak QT-200", "\u00d840 boring bar", 5, 8],
    ["9001", 40, "Drill 4 holes \u00d815 flange A", "Haas VF-2", "\u00d815 drill", 10, 4],
    ["9001", 50, "Drill 4 holes \u00d815 flange B", "Haas VF-2", "\u00d815 drill", 10, 4],
    ["9002", 10, "Face 6 sides to envelope 245 x 100 x 82", "Haas VF-2", "\u00d850 face mill", 12, 10],
    ["9002", 20, "Bore \u00d832 cylinder chamber", "Haas VF-2", "\u00d820 boring head", 6, 8],
    ["9002", 30, "Mill guide tracks and pockets", "Haas VF-2", "\u00d812 end mill", 8, 12],
    ["9002", 40, "Drill and tap M8x1.25 / M10x1.5 mounting holes", "Haas VF-2", "\u00d86.8 drill, M8 tap", 5, 6],
    ["9003", 10, "Rough turn OD and face cylinder body", "Mazak Integrex", "CNMG 120408 insert", 15, 12],
    ["9003", 20, "Finish bore \u00d880 cylinder cavity", "Mazak Integrex", "\u00d850 boring bar", 10, 15],
    ["9003", 30, "Thread port holes PT 3/8", "Mazak Integrex", "PT 3/8 tap", 8, 6],
    ["9003", 40, "Mill clamp mounting brackets and pockets", "Mazak Integrex", "\u00d816 end mill", 12, 14],
]


def write_sheet(ws, header, rows) -> None:
    ws.append(header)
    for cell in ws[1]:
        cell.font = Font(bold=True)
    for row in rows:
        ws.append(row)
    for i, col in enumerate(ws.columns, start=1):
        width = max(len(str(c.value)) for c in col if c.value is not None)
        ws.column_dimensions[get_column_letter(i)].width = min(width + 2, 60)
    ws.freeze_panes = "A2"


def main() -> None:
    wb = Workbook()
    write_sheet(wb.active, PARTS_HEADER, PARTS)
    wb.active.title = "Parts"
    write_sheet(wb.create_sheet("Operations"), OPS_HEADER, OPERATIONS)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    wb.save(OUT)
    print(f"wrote {OUT}  ({len(PARTS)} parts, {len(OPERATIONS)} operations)")


if __name__ == "__main__":
    main()

