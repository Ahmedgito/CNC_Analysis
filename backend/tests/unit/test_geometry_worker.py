"""The isolated geometry worker: real subprocess, timeouts, crashes, recovery."""

from __future__ import annotations

import os

import pytest

from app.geometry.errors import ModelLimitError, UnreadableModelError
from app.geometry.worker import GeometryWorker
from tests.fixtures.models import sample


@pytest.fixture(scope="module")
def worker():
    w = GeometryWorker(timeout_s=60, inline=False)
    yield w
    w.shutdown()


def test_job_runs_in_a_separate_process(worker):
    result = worker.process(sample("2283_bushing.igs"), "2283_bushing.igs", "0" * 64)
    assert result.slice.feature("od_1").numbers["diameter_mm"] == pytest.approx(48)
    assert result.meshes[1][:4] == b"glTF"
    assert worker.run("pid", os.getpid) != os.getpid()


def test_kernel_errors_come_back_as_errors(worker):
    with pytest.raises(UnreadableModelError):
        worker.process(sample("2280_flange.igs")[:3000], "cut.igs", "0" * 64)


def test_a_crashed_worker_is_replaced(worker):
    with pytest.raises(UnreadableModelError, match="stopped while reading"):
        worker.run("crash.igs", os._exit, 3)
    # The next job gets a fresh worker.
    assert worker.process(sample("3001_gear_blank.igs"), "3001.igs", "0" * 64).slice.valid


def test_a_slow_job_is_stopped_and_the_pool_recovers():
    w = GeometryWorker(timeout_s=0.5, inline=False)
    try:
        import time

        with pytest.raises(ModelLimitError, match="longer than"):
            w.run("slow.igs", time.sleep, 30)
        w.timeout_s = 60
        assert w.process(sample("2283_bushing.igs"), "2283.igs", "0" * 64).slice.valid
    finally:
        w.shutdown()


def test_memory_cap_stops_a_runaway_job():
    w = GeometryWorker(timeout_s=60, memory_mb=400, inline=False)
    try:
        with pytest.raises(ModelLimitError, match="more than 400 MB"):
            w.run("huge.igs", bytearray, 900_000_000)
    finally:
        w.shutdown()
