"""End-to-end smoke test against a running API. Exits non-zero on the first failure.

    uv run python scripts/smoke.py                       # http://127.0.0.1:8000
    uv run python scripts/smoke.py http://localhost:3000/api/backend   # through the web proxy

Stdlib only, so it runs anywhere Python does.
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000").rstrip("/")
if not BASE.startswith(("http://", "https://")):
    sys.exit(f"base URL must be http(s): {BASE}")
API = BASE if BASE.endswith("/api/backend") else f"{BASE}/api/v1"


def call(method: str, path: str, body: dict | None = None) -> tuple[int, dict]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(  # noqa: S310 - scheme validated as http(s) above
        f"{API}{path}", data=data, method=method, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:  # noqa: S310 - validated above
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read() or b"{}")


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"{'PASS' if ok else 'FAIL'}  {name}{f'  ({detail})' if detail else ''}")
    if not ok:
        sys.exit(1)


def main() -> None:
    status, parts = call("GET", "/parts")
    keys = [p["part_key"] for p in parts.get("parts", [])]
    check("parts listed", status == 200 and "2280" in keys, ", ".join(keys))

    status, ans = call("POST", "/parts/2280/ask", {"question": "What material is it made of?"})
    cells = [e["cell_id"] for e in ans.get("evidence", [])]
    check(
        "material answered with evidence",
        status == 200 and ans.get("status") == "answered" and "SS304" in ans.get("answer", ""),
        f"{ans.get('status')}: {cells}",
    )
    check("evidence names the Parts!C2 cell", "mfg_record_A!Parts!C2" in cells)

    status, ans = call("POST", "/parts/2280/ask", {"question": "What is the unit price?"})
    check("price is not invented", ans.get("status") == "not_found", ans.get("answer", "")[:80])

    status, ans = call("POST", "/parts/9999/ask", {"question": "What material is it?"})
    check("unknown part handled", ans.get("status") == "part_not_found")
    print(f"smoke OK against {API} (provider: {ans.get('provider') or 'n/a'})")


if __name__ == "__main__":
    main()
