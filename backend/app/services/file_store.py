"""Content-addressed store for original drawing bytes and their rendered page images.

Drawings are kept by SHA-256 so a re-upload of the same bytes reuses everything, and page images
(rendered on first request with PDFium) are cached next to them. Rendering never executes PDF
JavaScript; PDFium is used here as a rasteriser only.
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


class FileStore:
    def __init__(self, root: Path) -> None:
        self.root = root

    def _pdf_path(self, sha: str) -> Path:
        if not _SHA_RE.match(sha):
            raise ValueError("invalid content hash")
        return self.root / "files" / f"{sha}.pdf"

    def put(self, sha: str, data: bytes) -> Path:
        path = self._pdf_path(sha)
        if path.exists():
            return path
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(f".{os.getpid()}.tmp")
        tmp.write_bytes(data)
        tmp.replace(path)  # atomic on the same filesystem
        return path

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
