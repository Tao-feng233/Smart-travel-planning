"""Two-phase shutdown: stop accepting work, then decide what to do with what is running.

The first phase (refusing new work) already existed. These tests pin the second
one -- a bounded window in which in-flight actions may finish on their own, after
which whatever is left is cancelled. Without the window every restart loses turns;
with an unbounded one every restart hangs.
"""

import asyncio
import os

from app.application import jobs as job_runner


def _reset():
    job_runner.SHUTTING_DOWN = False
    job_runner.TASKS.clear()


def test_grace_window_defaults_and_parses_the_environment(monkeypatch):
    monkeypatch.delenv("SHUTDOWN_GRACE_SECONDS", raising=False)
    assert job_runner.grace_seconds() == 20.0
    monkeypatch.setenv("SHUTDOWN_GRACE_SECONDS", "0")
    assert job_runner.grace_seconds() == 0.0
    # A garbage value must not raise during shutdown.
    monkeypatch.setenv("SHUTDOWN_GRACE_SECONDS", "soon")
    assert job_runner.grace_seconds() == 20.0


def test_shutdown_stops_accepting_work():
    async def scenario():
        _reset()
        await job_runner.shutdown()
        return job_runner.SHUTTING_DOWN

    try:
        assert asyncio.run(scenario()) is True
    finally:
        _reset()


def test_an_action_that_finishes_in_time_is_not_cancelled(monkeypatch):
    monkeypatch.setenv("SHUTDOWN_GRACE_SECONDS", "5")
    finished = []

    async def scenario():
        _reset()

        async def quick():
            await asyncio.sleep(0.05)
            finished.append("done")

        task = asyncio.create_task(quick())
        job_runner.TASKS["t1"] = task
        await job_runner.shutdown()
        return task

    try:
        task = asyncio.run(scenario())
    finally:
        _reset()
    assert finished == ["done"]
    assert not task.cancelled()


def test_an_action_that_overruns_the_window_is_cancelled(monkeypatch):
    monkeypatch.setenv("SHUTDOWN_GRACE_SECONDS", "0.05")

    async def scenario():
        _reset()

        async def slow():
            await asyncio.sleep(30)

        task = asyncio.create_task(slow())
        job_runner.TASKS["t1"] = task
        # SHUTDOWN_GRACE_SECONDS is read at shutdown time, not import time.
        assert os.environ["SHUTDOWN_GRACE_SECONDS"] == "0.05"
        await job_runner.shutdown()
        return task

    try:
        task = asyncio.run(scenario())
    finally:
        _reset()
    assert task.cancelled()
