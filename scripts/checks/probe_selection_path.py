"""Trace the real UI selection job with isolated storage and a controlled preview gate.

No suppliers, models or user records are accessed. --assert-immediate is a
red-capable check for whether selection completion waits for preview work.
"""

# ruff: noqa: E402 -- these scripts bootstrap the workspace import path.

import argparse
import asyncio
from contextlib import ExitStack, nullcontext
import copy
import json
from pathlib import Path
import sys
import time
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.agents import planner
from app.application import jobs, guidance, job_results
from app.persistence import storage
from app.planning import travel_preview, timeline_review


async def probe(assert_immediate=False):
    with patch.object(storage, "save"):
        workspace = storage.new_workspace("probe-owner")
    workspace["requirements"] = {"city": "青岛", "days": 2, "adults": 2}
    workspace["catalog"] = {"s": {"id": "s", "kind": "spot", "name": "栈桥"}}
    workspace["ui"] = {}
    entered, release = asyncio.Event(), asyncio.Event()
    phases, model_calls = [], []

    class Progress:
        def __init__(self, w, *args):
            self.workspace, self.trace = w, []

        def __call__(self, text):
            self.trace.append({"text": text})

        def stream(self):
            return nullcontext()

    async def model(*args, **kwargs):
        model_calls.append(kwargs.get("label"))
        raise AssertionError("Direct card selection invoked a model")

    async def preview(w, *args, **kwargs):
        phases.append("preview")
        assert w["selected_spots"] == ["s"]
        entered.set()
        await release.wait()

    async def review(*args, **kwargs):
        phases.append("audit")

    def complete(w, body, jid, result, *args):
        phases.append("completed:" + result.status)

    with ExitStack() as stack:
        for owner, name, value in [
            (storage, "get", lambda *args: copy.deepcopy(workspace)),
            (storage, "save", lambda w: None),
            (storage, "update_job", lambda *args, **kwargs: None),
            (jobs, "JobProgress", Progress),
            (
                guidance,
                "describe",
                lambda *args, **kwargs: {"title": "选择景点", "status": "loading"},
            ),
            (planner, "llm", model),
            (travel_preview, "refresh", preview),
            (timeline_review, "refresh", review),
            (job_results, "complete", complete),
        ]:
            stack.enter_context(patch.object(owner, name, value))
        body = SimpleNamespace(action="select", args={"id": "s"}, revision=0)
        started = time.perf_counter()
        task = asyncio.create_task(
            jobs.perform(workspace["id"], body, "probe-job", "probe-owner")
        )
        try:
            await asyncio.wait_for(entered.wait(), 2)
            result = {
                "real_path": "jobs.perform -> actions.run -> do_select -> post_processing.refresh",
                "selection_applied_before_preview": True,
                "model_calls": model_calls,
                "task_waits_for_preview": not task.done(),
                "ms_until_preview": round((time.perf_counter() - started) * 1000, 2),
                "measurement": "isolated control-flow probe; not live API latency",
            }
            if assert_immediate:
                assert task.done(), (
                    "Card selection completion is blocked on preview refresh"
                )
        finally:
            release.set()
            await task
        result["phases"] = phases
        return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--assert-immediate", action="store_true")
    arguments = parser.parse_args()
    print(
        json.dumps(
            asyncio.run(probe(arguments.assert_immediate)), ensure_ascii=False, indent=2
        )
    )
