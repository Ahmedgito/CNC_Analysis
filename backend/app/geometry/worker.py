"""Run the geometry kernel in a separate process, so a bad file cannot take the API down.

OpenCascade is C++: a hostile or broken IGES file can segfault it, loop while sewing, or allocate
gigabytes. Every job runs in a ``spawn``-ed worker with a wall-clock timeout and a memory cap
(``RLIMIT_AS`` on Linux and macOS, a Job Object on Windows). A timeout or a crash kills the pool,
a fresh pool replaces it, and the caller gets a plain error naming the file.

``inline=True`` runs jobs in this process (tests of the measurement rules, the CLI on a trusted
machine). The API always uses the process pool.
"""

from __future__ import annotations

import atexit
import contextlib
import importlib.util
import multiprocessing
import sys
import threading
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from concurrent.futures.process import BrokenProcessPool

import structlog

from app.geometry.errors import GeometryUnavailableError, ModelLimitError, UnreadableModelError

log = structlog.get_logger(__name__)


def kernel_installed() -> bool:
    return importlib.util.find_spec("OCP") is not None


def _limit_memory(memory_mb: int) -> None:
    limit = memory_mb * 1024 * 1024
    if sys.platform == "win32":
        _windows_job_limit(limit)
        return
    try:
        import resource

        resource.setrlimit(resource.RLIMIT_AS, (limit, limit))
    except (ImportError, ValueError, OSError):  # pragma: no cover - platform dependent
        pass


def _windows_job_limit(limit: int) -> None:  # pragma: no cover - Windows only
    """Put this worker process in a Job Object whose process memory is capped."""
    import ctypes
    from ctypes import wintypes

    class IO_COUNTERS(ctypes.Structure):
        _fields_ = [(n, ctypes.c_ulonglong) for n in (
            "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
            "ReadTransferCount", "WriteTransferCount", "OtherTransferCount",
        )]  # fmt: skip

    class BASIC(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_longlong),
            ("PerJobUserTimeLimit", ctypes.c_longlong),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class EXTENDED(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", BASIC),
            ("IoInfo", IO_COUNTERS),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    JOB_OBJECT_LIMIT_PROCESS_MEMORY = 0x100
    JobObjectExtendedLimitInformation = 9
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateJobObjectW.restype = wintypes.HANDLE
    k32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    k32.GetCurrentProcess.restype = wintypes.HANDLE
    k32.SetInformationJobObject.argtypes = [
        wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD,
    ]  # fmt: skip
    k32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    job = k32.CreateJobObjectW(None, None)
    if not job:
        return
    info = EXTENDED()
    info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_PROCESS_MEMORY
    info.ProcessMemoryLimit = limit
    k32.SetInformationJobObject(
        job, JobObjectExtendedLimitInformation, ctypes.byref(info), ctypes.sizeof(info)
    )
    k32.AssignProcessToJobObject(job, k32.GetCurrentProcess())


def _init(memory_mb: int) -> None:
    try:
        _limit_memory(memory_mb)
    except Exception as exc:
        print(f"geometry worker: memory limit not applied ({exc})", file=sys.stderr)
    import OCP  # noqa: F401  # warm the kernel so the first job does not pay the import


def _job(data: bytes, file_name: str, sha256: str, max_bytes: int):
    from app.geometry.kernel import process_model

    result = process_model(data, file_name, sha256, max_bytes=max_bytes)
    return result.slice.model_dump(mode="json"), result.meshes, result.views


class GeometryWorker:
    def __init__(
        self,
        timeout_s: float = 30.0,
        memory_mb: int = 1536,
        max_bytes: int = 25 * 1024 * 1024,
        inline: bool = False,
    ) -> None:
        self.timeout_s = timeout_s
        self.memory_mb = memory_mb
        self.max_bytes = max_bytes
        self.inline = inline
        self._pool: ProcessPoolExecutor | None = None
        self._lock = threading.Lock()

    # -- pool lifecycle ------------------------------------------------------------------------
    def _ensure_pool(self) -> ProcessPoolExecutor:
        with self._lock:
            if self._pool is None:
                self._pool = ProcessPoolExecutor(
                    max_workers=1,
                    mp_context=multiprocessing.get_context("spawn"),
                    initializer=_init,
                    initargs=(self.memory_mb,),
                    max_tasks_per_child=50,
                )
            return self._pool

    def _kill_pool(self) -> None:
        with self._lock:
            pool, self._pool = self._pool, None
        if pool is None:
            return
        # ProcessPoolExecutor has no public kill; a hung or runaway worker must not linger.
        for proc in list(getattr(pool, "_processes", {}).values()):
            with contextlib.suppress(Exception):
                proc.kill()
        pool.shutdown(wait=False, cancel_futures=True)

    def shutdown(self) -> None:
        self._kill_pool()

    # -- jobs ----------------------------------------------------------------------------------
    def process(self, data: bytes, file_name: str, sha256: str):
        """Return a GeometryResult; raise UnreadableModelError, ModelLimitError or
        GeometryUnavailableError."""
        from app.domain.model import ModelSlice
        from app.geometry.kernel import GeometryResult

        if not kernel_installed():
            raise GeometryUnavailableError(
                "the 3D geometry kernel (cadquery-ocp-novtk) is not installed; IGES files "
                "cannot be read"
            )
        if self.inline:
            from app.geometry.kernel import process_model

            return process_model(data, file_name, sha256, max_bytes=self.max_bytes)
        slice_json, meshes, views = self.run(
            file_name, _job, data, file_name, sha256, self.max_bytes
        )
        return GeometryResult(
            slice=ModelSlice.model_validate(slice_json), meshes=meshes, views=views
        )

    def run(self, file_name: str, fn, *args):
        """Run ``fn(*args)`` in the pool under the limits; map timeouts and crashes to errors.
        (Public so tests can submit a job that crashes the worker.)"""
        pool = self._ensure_pool()
        future = pool.submit(fn, *args)
        try:
            return future.result(timeout=self.timeout_s)
        except FutureTimeout as exc:
            log.warning("geometry.timeout", file=file_name, timeout_s=self.timeout_s)
            self._kill_pool()
            raise ModelLimitError(
                f"{file_name} took longer than {self.timeout_s:g} s to process; the job was stopped"
            ) from exc
        except BrokenProcessPool as exc:
            log.warning("geometry.crash", file=file_name)
            self._kill_pool()
            raise UnreadableModelError(
                "the geometry kernel stopped while reading this file (crashed or ran out of memory)"
            ) from exc
        except MemoryError as exc:
            self._kill_pool()
            raise ModelLimitError(
                f"{file_name} needs more than {self.memory_mb} MB to process"
            ) from exc


_WORKERS: dict[tuple, GeometryWorker] = {}
_WORKERS_LOCK = threading.Lock()


def get_worker(timeout_s: float, memory_mb: int, max_bytes: int, inline: bool) -> GeometryWorker:
    """One worker per configuration per process, shared by every app (tests create many)."""
    key = (timeout_s, memory_mb, max_bytes, inline)
    with _WORKERS_LOCK:
        worker = _WORKERS.get(key)
        if worker is None:
            worker = _WORKERS[key] = GeometryWorker(timeout_s, memory_mb, max_bytes, inline)
        return worker


@atexit.register
def _shutdown_all() -> None:  # pragma: no cover - interpreter exit
    for w in list(_WORKERS.values()):
        w.shutdown()
