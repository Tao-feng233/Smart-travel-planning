"""Read-only review; failures preserve the executable program checks."""

from app import prompts
import json
from app.core.errors import DataError
from app.integrations.enrichment import model_facts


async def review(ctx, plan):
    ctx.progress("审核助手正在复核用户要求、来源和计划书遗漏")
    try:
        review_prompt = prompts.system("plan_review")
        review_plan = {
            k: v for k, v in plan.items() if k not in ("usage", "guides", "days")
        }
        review_plan["guides"] = [
            {
                "id": g.get("id"),
                "text": g.get("text"),
                "date_scope": g.get("date_scope") or g.get("scope") or "",
            }
            for g in ctx.guides
        ]
        review_plan["days"] = [
            {
                **d,
                "events": [
                    {
                        k: v
                        for k, v in e.items()
                        if k not in ("options", "poi", "evidence")
                    }
                    for e in d["events"]
                ],
            }
            for d in ctx.computed
        ]
        review_messages = [
            {"role": "system", "content": review_prompt},
            {
                "role": "user",
                "content": json.dumps(
                    model_facts(
                        {
                            "requirements": ctx.requirements,
                            "plan": review_plan,
                            "transport": ctx.transport,
                            "return_transport": ctx.workspace.get("selected_return"),
                        }
                    ),
                    ensure_ascii=False,
                ),
            },
        ]
        for attempt in range(2):
            m, u = await ctx.services.model(
                review_messages, json_mode=True, max_tokens=1800, label="review"
            )
            (ctx.services.runtime / "last-review-response.txt").write_text(
                m.get("content") or "", encoding="utf-8"
            )
            try:
                review = ctx.services.parse_review(m.get("content"))
                break
            except (ValueError, TypeError, IndexError):
                if attempt:
                    raise ValueError("审核响应结构无效") from None
                review_messages.append(
                    {
                        "role": "user",
                        "content": "上次响应不是完整有效的JSON。请重新独立检查同一份草稿，只返回issues字符串数组与summary字符串，最多6条简短问题。",
                    }
                )
        plan["review"] = {**review, "usage": u, "status": "completed"}
    except (DataError, ValueError, KeyError, TypeError) as e:
        plan["review"] = {
            "status": "failed",
            "error_type": type(e).__name__,
            "issues": ["模型审核未完成，请人工复核"],
            "summary": "程序检查已保留，模型审核失败。",
        }
