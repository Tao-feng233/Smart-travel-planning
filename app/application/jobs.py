"""One authoritative registry for running actions, cancellation and shutdown."""

import asyncio
import logging
import os

from app.travel import actions as travel_actions
from app.application import guidance, post_processing, job_results
from app.application.action_policy import NO_COMPOSE_ACTIONS
from app.application.job_progress import JobProgress
from app.application.turn_state import TurnSnapshot, TurnResult
from app.agents import planner, replies
from app.agents.planner import handle, run_chat
from app.core.errors import DataError
from app.persistence import storage

LOCKS = {}
TASKS = {}
CANCELLED = set()
SHUTTING_DOWN = False


def grace_seconds():
    """How long an in-flight action may finish on its own before it is cancelled.

    Two-phase on purpose: `SHUTTING_DOWN` already stops *new* work, so the only
    question is what to do with work already running. Cutting it immediately
    turns a restart into lost turns; waiting forever turns a restart into a hang.
    """
    try:
        return max(0.0, float(os.environ.get("SHUTDOWN_GRACE_SECONDS", "20")))
    except ValueError:
        return 20.0


def initialize():
    global SHUTTING_DOWN
    SHUTTING_DOWN = False
    storage.interrupt_jobs()


def start(wid, body, jid, owner_id):
    def finished(task):
        TASKS.pop(jid, None)
        if task.cancelled():
            storage.update_job(jid, status="cancelled", progress="已停止")

    task = asyncio.create_task(perform(wid, body, jid, owner_id))
    TASKS[jid] = task
    task.add_done_callback(finished)


def cancel_running(jid):
    task = TASKS.get(jid)
    if task:
        CANCELLED.add(jid)
        task.cancel()
    else:
        storage.update_job(jid, status="interrupted", error="任务已中断，请重新发起")


async def shutdown():
    """Stop accepting work, let in-flight actions finish, then cancel the rest."""
    global SHUTTING_DOWN
    SHUTTING_DOWN = True
    tasks = list(TASKS.values())
    if not tasks:
        return
    pending = set(tasks)
    grace = grace_seconds()
    if grace:
        _, pending = await asyncio.wait(tasks, timeout=grace)
    for task in pending:
        task.cancel()
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)


async def dispatch(workspace, action, args, progress):
    answer = await handle(workspace, action, args, progress)
    if action == "requirements":
        from app.agents.planner import ensure_weather

        await ensure_weather(workspace, progress)
    return answer


async def perform(wid, body, jid, owner_id):
    async with LOCKS.setdefault(wid, asyncio.Lock()):
        w = storage.get(wid, owner_id)
        if not w or w["revision"] != body.revision:
            storage.update_job(jid, status="failed", error="旅行已被更新，请刷新后重试")
            return
        progress = JobProgress(w, body.action, jid)
        if w.get("ui", {}).get("conflict"):
            w["last_plan_conflict"] = w["ui"]["conflict"]
        w["ui"] = guidance.describe(w, body.action, body.args, status="loading")
        progress(w["ui"]["title"])
        if body.action == "chat":
            w["turn_base_revision"] = w["revision"]
            w["messages"].append(
                {"role": "user", "content": body.text.strip(), "time": storage.now()}
            )
            w["revision"] += 1
            storage.save(w)
        baseline = TurnSnapshot.capture(w)
        result = TurnResult(performed=body.action)
        with progress.stream():
            try:
                async with asyncio.timeout(600):
                    if body.action == "undo":
                        w = storage.previous(w)
                        progress.workspace = w
                        result.answer = "已恢复上一版选择和安排。"
                    elif body.action == "chat":
                        result.answer = await run_chat(w, body.text, progress)
                    else:
                        w.update(
                            turn_action=body.action,
                            turn_is_chat=False,
                            turn_weather_updated=False,
                            turn_food_updated=False,
                        )
                        result.answer = await travel_actions.run(
                            w, body.action, body.args, progress, dispatch
                        )
                        if body.action not in NO_COMPOSE_ACTIONS:
                            result.answer = await replies.compose(w, result.answer)
                    result.performed = (
                        w.get("turn_action") if body.action == "chat" else body.action
                    )
                    selected_kind = (
                        w.get("catalog", {}).get(body.args.get("id"), {}).get("kind")
                        if body.action == "select"
                        else None
                    )
                    result.audit = await post_processing.refresh(
                        w,
                        baseline,
                        result.performed,
                        selected_kind,
                        progress,
                        planner.llm,
                    )
            except asyncio.CancelledError:
                w.pop("auto_selection_run", None)
                result.status = "interrupted" if SHUTTING_DOWN else "cancelled"
                if w.get("assistant_goal"):
                    w["assistant_goal"]["status"] = result.status
                result.answer = (
                    "任务已中断，已保存的对话和选择可以继续。"
                    if SHUTTING_DOWN
                    else "已停止本轮处理，当前选择已保留。"
                )
            except DataError as error:
                result.error = result.answer = str(error)
                result.status = "failed"
                result.error_context = error.context
            except ValueError:
                result.error = result.answer = (
                    "没有可撤销的版本"
                    if body.action == "undo"
                    else "本轮处理数据不完整，请检查条件后重试"
                )
                result.status = "failed"
            except TimeoutError:
                result.error = result.answer = (
                    "本轮处理超时，已保存当前选择，请稍后重试。"
                )
                result.status = "failed"
            except Exception as error:
                logging.getLogger(__name__).error(
                    "Action failed: %s", type(error).__name__
                )
                result.error = result.answer = (
                    "本轮处理出现异常，已有选择已保留，请重试。"
                )
                result.status = "failed"
            finally:
                CANCELLED.discard(jid)
        job_results.complete(w, body, jid, result, baseline, progress.trace)
