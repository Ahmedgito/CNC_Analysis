"""Content-addressed store for original drawing and model bytes and what is rendered from them.

Files are kept by SHA-256 so a re-upload of the same bytes reuses everything. Drawing page images
are rendered on first request with PDFium (a rasteriser only; PDF JavaScript never runs). Model
meshes (binary glTF) and hidden-line projections (SVG) are written once, at ingest, by the
geometry worker. Everything is immutable, so it can be cached by clients forever.
"""

from __future__ import annotations

import io
import os
import re
import threading
from pathlib import Path

_SHA_RE = re.compile(r"^[0-9a-f]{64}$")
_RENDER_LOCK = threading.Lock()  # PDFium is not thread-safe
MAX_DPI = 200
_VIEW_RE = re.compile(r"^[a-z]{2,12}$")


class FileStore:
    def __init__(self, root: Path) -> None:
        self.root = root

    def _pdf_path(self, sha: str) -> Path:
        if not _SHA_RE.match(sha):
            raise ValueError("invalid content hash")
        return self.root / "files" / f"{sha}.pdf"

    @staticmethod
    def _write(path: Path, data: bytes) -> Path:
        if path.exists():
            return path
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(f".{os.getpid()}.tmp")
        tmp.write_bytes(data)
        tmp.replace(path)  # atomic on the same filesystem
        return path

    def put(self, sha: str, data: bytes) -> Path:
        return self._write(self._pdf_path(sha), data)

    # -- IGES models -----------------------------------------------------------------------------
    def _check(self, sha: str) -> str:
        if not _SHA_RE.match(sha):
            raise ValueError("invalid content hash")
        return sha

    def put_model(
        self, sha: str, data: bytes, meshes: dict[int, bytes], views: dict[str, str]
    ) -> None:
        self._check(sha)
        self._write(self.root / "files" / f"{sha}.igs", data)
        for lod, glb in meshes.items():
            self._write(self.root / "meshes" / f"{sha}_{int(lod)}.glb", glb)
        for name, svg in views.items():
            if _VIEW_RE.match(name):
                self._write(self.root / "views" / f"{sha}_{name}.svg", svg.encode("utf-8"))

    def model_bytes(self, sha: str) -> bytes | None:
        path = self.root / "files" / f"{self._check(sha)}.igs"
        return path.read_bytes() if path.exists() else None

    def mesh(self, sha: str, lod: int) -> bytes | None:
        path = self.root / "meshes" / f"{self._check(sha)}_{int(lod)}.glb"
        return path.read_bytes() if path.exists() else None

    def view(self, sha: str, name: str) -> bytes | None:
        if not _VIEW_RE.match(name):
            return None
        path = self.root / "views" / f"{self._check(sha)}_{name}.svg"
        return path.read_bytes() if path.exists() else None

    def get(self, sha: str) -> bytes | None:
        path = self._pdf_path(sha)
        return path.read_bytes() if path.exists() else None

    def page_png(self, sha: str, page: int, dpi: int = 110, rotation: int = 0) -> bytes | None:
        """PNG of one page (1-based), rendered once and cached. None if the file is unknown.

        ``rotation`` is an extra clockwise turn (the drawing parser's orientation correction), so
        the image matches the coordinates of the facts read from it.
        """
        dpi = max(36, min(dpi, MAX_DPI))
        rotation = rotation % 360 if rotation % 90 == 0 else 0
        source = self._pdf_path(sha)
        if not source.exists():
            return None
        cached = self.root / "pages" / sha / f"p{page}_{dpi}_r{rotation}.png"
        if cached.exists():
            return cached.read_bytes()
        import pypdfium2 as pdfium

        with _RENDER_LOCK:
            pdf = pdfium.PdfDocument(str(source))
            try:
                if not 1 <= page <= len(pdf):
                    return None
                bitmap = pdf[page - 1].render(
                    scale=dpi / 72,  # type: ignore[arg-type]
                    rotation=rotation,
                )
                image = bitmap.to_pil()
                buf = io.BytesIO()
                image.save(buf, format="PNG", optimize=True)
            finally:
                pdf.close()
        cached.parent.mkdir(parents=True, exist_ok=True)
        cached.write_bytes(buf.getvalue())
        return buf.getvalue()
