"""Generate binary .glb models for all parts in the catalog.

Uses build123d and OpenCascade to export accurate 3D meshes for:
- Synthetic parts: 2280, 2281, 2282, 2283, 3001, 3002, 3003, 3004
- Real-world parts: 9001, 9004, 9006, 9007, 9008
"""

from pathlib import Path
import build123d as b3d

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "data" / "rendered_models"
OUT_DIR.mkdir(parents=True, exist_ok=True)

def _base():
    return (b3d.Align.CENTER, b3d.Align.CENTER, b3d.Align.MIN)

# --- Synthetic Parts ---
def make_2280():
    with b3d.BuildPart() as p:
        b3d.Cylinder(radius=60, height=20, align=_base())
        b3d.Cylinder(radius=20, height=20, align=_base(), mode=b3d.Mode.SUBTRACT)
        with b3d.PolarLocations(radius=45, count=6):
            b3d.Cylinder(radius=5, height=20, align=_base(), mode=b3d.Mode.SUBTRACT)
    return p.part

def make_2281():
    with b3d.BuildPart() as p:
        b3d.Cylinder(radius=15, height=160, align=_base())
        with b3d.Locations((0, 0, 160)):
            b3d.Cylinder(radius=12.5, height=40, align=_base())
    return p.part

def make_2282():
    with b3d.BuildPart() as p:
        b3d.Box(101.6, 63.5, 9.525, align=_base())
        dx, dy = 101.6 / 2 - 12.7, 63.5 / 2 - 12.7
        with b3d.Locations((dx, dy, 0), (-dx, dy, 0), (dx, -dy, 0), (-dx, -dy, 0)):
            b3d.Cylinder(radius=3.175, height=9.525, align=_base(), mode=b3d.Mode.SUBTRACT)
    return p.part

def make_2283():
    with b3d.BuildPart() as p:
        b3d.Cylinder(radius=24, height=40, align=_base())
        b3d.Cylinder(radius=15, height=40, align=_base(), mode=b3d.Mode.SUBTRACT)
    return p.part

def make_3001():
    with b3d.BuildPart() as p:
        b3d.Box(80, 50, 12, align=_base())
        with b3d.Locations((25, 15, 0), (-25, 15, 0), (25, -15, 0), (-25, -15, 0)):
            b3d.Cylinder(radius=4, height=12, align=_base(), mode=b3d.Mode.SUBTRACT)
    return p.part

def make_3002():
    with b3d.BuildPart() as p:
        b3d.Cylinder(radius=35, height=50, align=_base())
        b3d.Cylinder(radius=10, height=50, align=_base(), mode=b3d.Mode.SUBTRACT)
    return p.part

def make_3003():
    with b3d.BuildPart() as p:
        b3d.Cylinder(radius=32.5, height=25, align=_base())
        b3d.Cylinder(radius=17.5, height=25, align=_base(), mode=b3d.Mode.SUBTRACT)
        with b3d.PolarLocations(radius=25, count=4):
            b3d.Cylinder(radius=3.5, height=25, align=_base(), mode=b3d.Mode.SUBTRACT)
    return p.part

def make_3004():
    with b3d.BuildPart() as p:
        b3d.Box(50, 40, 30, align=_base())
        b3d.Cylinder(radius=8, height=30, align=_base(), mode=b3d.Mode.SUBTRACT)
    return p.part

def main():
    generators = {
        "2280": make_2280,
        "2281": make_2281,
        "2282": make_2282,
        "2283": make_2283,
        "3001": make_3001,
        "3002": make_3002,
        "3003": make_3003,
        "3004": make_3004,
    }

    for key, fn in generators.items():
        out_file = OUT_DIR / f"{key}.glb"
        print(f"Generating {key} -> {out_file.name}...")
        part = fn()
        b3d.export_gltf(part, str(out_file), binary=True)

    # Real world parts
    real_parts = {
        "9001": ROOT / "docs" / "real_world" / "9001_s_pipe_connector" / "Part1.STEP",
        "9004": ROOT / "docs" / "real_world" / "9004_helical_bevel_gear" / "Helical Bevel Gear.STEP",
        "9006": ROOT / "docs" / "real_world" / "9006_wind_turbine_components" / "Main_Shaft.STEP",
        "9007": ROOT / "docs" / "real_world" / "9007_servo_bracket" / "Servo_Bracket_MG996.STEP",
        "9008": ROOT / "docs" / "real_world" / "9008_pivot_support_bracket" / "Pivot Support.STEP",
    }

    for key, step_path in real_parts.items():
        if step_path.exists():
            out_file = OUT_DIR / f"{key}.glb"
            print(f"Importing {step_path.name} -> {out_file.name}...")
            try:
                shape = b3d.import_step(str(step_path))
                b3d.export_gltf(shape, str(out_file), binary=True)
                print(f"Exported {key}: {out_file.stat().st_size} bytes")
            except Exception as e:
                print(f"Failed {key}: {e}")

    print("All GLBs generated successfully!")

if __name__ == "__main__":
    main()

