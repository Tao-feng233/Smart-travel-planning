"""Build completion messages and persist a finished job once."""

import json

from app.application import guidance
from app.application.action_policy import QUERY_ACTIONS, quiet
from app.application.turn_state import transport_ready
from app.core.text import readable
from app.persistence import storage
from app.travel.journey import next_step


def finish_ui(workspace, body, result, baseline):
    ui = guidance.finish(
        workspace,
        "ready" if result.status == "completed" else result.status,
        result.error,
    )
    if result.error:
        from app.planning.diagnostics import from_error

        result.error_context = from_error(workspace, result.error_context, result.error)
    if result.error_context:
        ui["conflict"] = result.error_context
    newly_ready = (
        result.status == "completed"
        and not baseline.ready
        and transport_ready(workspace)
    )
    if newly_ready:
        ui["suggested_view"] = next_step(workspace)["view"]
    if (
        result.status == "completed"
        and body.action in ("complete_hotel", "skip_hotel")
        and next_step(workspace)["view"] == "food"
    ):
        ui["suggested_view"] = "food"
    return ui, newly_ready


def feedback(workspace, body, job_id, answer):
    action = body.action
    kind = workspace["catalog"].get(body.args.get("id"), {}).get("kind")
    text = "推荐列表已更新"
    if action == "select" and kind == "spot":
        text = f"已选{len(workspace['selected_spots'])}个景点"
    elif action == "requirements":
        text = "旅行信息已更新"
    elif action in ("select", "select_room"):
        text = "选择已更新"
    if (
        action in ("select_room", "meal_choice")
        or action == "select"
        and kind != "spot"
    ):
        text = readable(answer).split("\n")[0]
    if action in QUERY_ACTIONS:
        text = "查询结果已更新，请在右侧查看。"
    workspace["feedback"] = {"id": job_id, "text": text}


def announce_adjustment(workspace, result, baseline):
    adjustment = workspace.get("timeline_adjustment") or {}
    if adjustment.get("status") != "applied" or baseline.adjustment == json.dumps(
        adjustment, sort_keys=True
    ):
        return
    names = [
        workspace["catalog"].get(cid, {}).get("name", "景点")
        for cid in adjustment.get("changed_ids", [])
    ]
    text = "**时间轴已自动优化**\n" + adjustment.get(
        "reason", "已调整可移动活动的日期、顺序与建议时间。"
    )
    if names:
        text += "\n涉及：" + "、".join(names[:12]) + "。"
    if not adjustment.get("roads_checked"):
        text += " 部分交通仍待核对，显示时间为建议。"
    workspace["messages"].append(
        {"role": "assistant", "content": text, "time": storage.now()}
    )
    if result.performed in ("complete_spots", "analyze_visits", "visit_schedule"):
        from app.planning.visit_analysis import summary

        result.answer = (
            summary(workspace, workspace["visit_analysis"])
            + "\n"
            + next_step(workspace)["message"]
        )


def announce_audit(workspace, result):
    if not result:
        return
    from app.planning.timeline_review import message, fresh_issues, issue_key

    fresh = fresh_issues(workspace, result)
    # During selection, material estimates already appear on the rail. Avoid
    # adding a diagnostic conversation block until a book exists.
    if fresh and not workspace.get("plan"):
        return
    keys = sorted(issue_key(row) for row in fresh)
    if keys and keys == list(workspace.get("last_audit_message_keys") or []):
        return
    text = message({**result, "issues": fresh})
    if text:
        workspace["last_audit_message_keys"] = keys
        workspace["messages"].append(
            {
                "role": "assistant",
                "content": text,
                "time": storage.now(),
                "ui": {"conflict": {"issues": fresh, "view": "spot"}},
            }
        )


def complete(workspace, body, job_id, result, baseline, trace):
    ui, newly_ready = finish_ui(workspace, body, result, baseline)
    silent = quiet(body.action, result.status)
    if silent:
        feedback(workspace, body, job_id, result.answer)
    announce_adjustment(workspace, result, baseline)
    announce_audit(workspace, result.audit)
    if silent and newly_ready:
        workspace["messages"].append(
            {
                "role": "assistant",
                "content": "**往返班次已确认。**\n" + next_step(workspace)["message"],
                "time": storage.now(),
            }
        )
    elif not silent:
        workspace["messages"].append(
            {
                "role": "assistant",
                "content": readable(result.answer),
                "time": storage.now(),
                "ui": ui,
                "process_steps": [row["text"] for row in trace],
            }
        )
    if body.action != "undo":
        workspace["revision"] += 1
    workspace["trace"] = (workspace.get("trace", []) + trace)[-30:]
    storage.save(workspace)
    storage.update_job(
        job_id,
        status=result.status,
        progress="已停止"
        if result.status == "cancelled"
        else "任务已中断"
        if result.status == "interrupted"
        else "完成",
        error=result.error,
        ui={
            **ui,
            "reply_text": "" if silent else readable(result.answer),
            "process_steps": [row["text"] for row in trace],
        },
    )
