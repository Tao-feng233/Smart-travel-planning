"""Reuse road queries within one plan, including trial schedules."""


async def options(ctx, start, end):
    pair = (start["id"], end["id"])
    if pair not in ctx.routes:
        ctx.routes[pair] = await ctx.services.route_options(start, end)
    return ctx.routes[pair]
