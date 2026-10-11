"""Daily arrival, visits, dining, lodging and departure in explicit order."""

from app.core.errors import DataError
from app.travel import foods, stay_plan
from app.planning import pacing, transport_links
from app.planning.time_values import minute, round_up, clock
from app.planning import meal_events


class DailySchedule:
    def __init__(self, ctx, group):
        self.ctx = ctx
        self.group = group

    async def meal(self, *args):
        return await meal_events.schedule(self.ctx, *args)

    async def build(self):
        await self.setup()
        if await self.arrival():
            return
        if await self.return_only():
            return
        await self.breakfast()
        for self.index, self.item in enumerate(self.group["items"]):
            await self.before_visit()
            self.visit_checkpoint = {
                "time": self.time,
                "events": len(self.events),
                "warnings": len(self.ctx.warnings),
                "offered": len(self.ctx.offered),
                "meal_unplaced": len(self.ctx.meal_unplaced),
            }
            await self.approach()
            self.duration = self.item["duration"]
            self.fit_return_day()
            await self.visit_start()
            if await self.opening():
                self.discard_visit()
                continue
            await self.inside_dining()
            if self.meal_minutes and await self.opening(self.meal_minutes):
                self.discard_visit()
                continue
            if await self.visit_end():
                break
            await self.add_visit()
        await self.after_lunch()
        await self.dinner()
        await self.hotel_transfer()
        await self.free_time()
        await self.return_trip()
        self.publish()

    def discard_visit(self):
        """Withdraw the uncommitted road/wait segment; preserve preceding meals."""
        mark = self.visit_checkpoint
        self.time = mark["time"]
        del self.events[mark["events"] :]
        del self.ctx.warnings[mark["warnings"] :]
        del self.ctx.offered[mark["offered"] :]
        del self.ctx.meal_unplaced[mark["meal_unplaced"] :]

    def latest_end(self):
        """Latest acceptable day end: the requirement, extended for evening visits and
        pulled earlier on the return day so接驳准备 still fits."""
        limit = minute(self.ctx.requirements.get("day_end", "18:30"))
        if any((x.get("period") == "evening" for x in self.group["items"])):
            limit = max(limit, 22 * 60)
        if (
            self.ctx.return_time
            and self.group["date"] == self.ctx.return_time.date().isoformat()
        ):
            deadline = (
                (
                    self.ctx.return_time.hour * 60
                    + self.ctx.return_time.minute
                    - transport_links.offset(self.ctx.workspace, "return")
                )
                // 5
                * 5
            )
            limit = min(limit, max(0, deadline))
        return limit

    def fit_return_day(self):
        """On the return day, narrow a visit so it still fits before the deadline.

        Hard-scheduling to the point of raising would abort the whole plan, leaving the
        user with nothing to adjust. Narrowing and reporting it keeps the plan usable.
        """
        if not (
            self.ctx.return_time
            and self.group["date"] == self.ctx.return_time.date().isoformat()
        ):
            return
        limit = self.latest_end()
        available = limit - self.time
        if available >= self.duration:
            return
        if available < 0:
            raise DataError(
                self.group["date"]
                + " 已没有可安排时间："
                + clock(self.time)
                + " 时已超过需在 "
                + clock(limit)
                + " 前开始接驳准备的要求（返程 "
                + self.ctx.return_time.strftime("%H:%M")
                + "）。请减少当天安排或改乘更晚的班次。",
                {
                    "date": self.group["date"],
                    "view": "spot",
                    "direction": "return",
                    "candidate_ids": [self.item["candidate_id"]],
                },
            )
        original = self.duration
        self.duration = max(0, available)
        self.ctx.offered.append(
            {
                "code": "return_day_trim",
                "level": "warning",
                "view": "spot",
                "date": self.group["date"],
                "candidate_ids": [self.item["candidate_id"]],
                "overrun_minutes": original - self.duration,
                "available_minutes": available,
                "message": self.group["date"]
                + " 当天需在 "
                + clock(limit)
                + " 前开始接驳准备（返程 "
                + self.ctx.return_time.strftime("%H:%M")
                + "），"
                + self.item["name"]
                + "已由"
                + str(original)
                + "分钟调整为约"
                + str(self.duration)
                + "分钟。若希望玩满，可减少当天景点、提前返回，或改乘更晚的班次。",
            }
        )

    async def setup(self):
        self.group["items"].sort(
            key=lambda item: {"morning": 0, "any": 1, "afternoon": 2, "evening": 3}.get(
                item.get("period", "any"), 1
            )
        )
        self.origin = stay_plan.anchor(
            self.ctx.workspace, self.group["date"], morning=True
        )
        self.ctx.base = stay_plan.anchor(self.ctx.workspace, self.group["date"])
        if (
            self.ctx.return_time
            and self.group["date"] == self.ctx.return_time.date().isoformat()
        ):
            self.ctx.base = self.origin
        self.time = round_up(minute(self.ctx.requirements.get("day_start", "09:00")))
        self.events = []
        self.last = self.origin
        self.lunch = False
        self.inside_periods = set()
        if (
            "stay_hotels" in self.ctx.workspace
            and (not self.ctx.base)
            and (self.group["date"] in stay_plan.nights(self.ctx.workspace))
        ):
            self.ctx.warnings.append(
                self.group["date"]
                + "当晚尚未指定可用于算路的住宿，未假设沿用最近选定酒店。"
            )
        self.changing_hotel = bool(
            self.origin
            and self.ctx.base
            and (not stay_plan.same_hotel(self.origin, self.ctx.base))
        )
        if self.changing_hotel:
            self.ctx.warnings.append(
                self.group["date"]
                + "更换住宿，需要携带行李转场；退房暂预留15分钟，寄存与入住条件待核实。"
            )
        if (
            self.ctx.transport
            and self.ctx.transport.get("departure", "")[:10] == self.group["date"]
            and (self.ctx.transport.get("arrival", "")[:10] == self.group["date"])
        ):
            self.events.append(
                {
                    "kind": "transport",
                    "name": "乘坐"
                    + self.ctx.transport["name"]
                    + "前往"
                    + self.ctx.requirements["city"],
                    "start": self.ctx.transport["departure"][-5:],
                    "end": self.ctx.transport["arrival"][-5:],
                    "note": "请注意核实出发时刻、车站或机场及席别；请携带并保管好身份证件。",
                    "source": self.ctx.transport.get("source"),
                }
            )

    async def arrival(self):
        if self.ctx.arrival:
            if self.group["date"] < self.ctx.arrival.date().isoformat():
                if self.group["items"]:
                    raise DataError(
                        f"{self.group['date']} 的游览早于所选班次到达，草稿未通过校验，请调整班次或重新生成。",
                        {
                            "date": self.group["date"],
                            "direction": "outbound",
                            "candidate_ids": [
                                x["candidate_id"] for x in self.group["items"]
                            ],
                            "view": "spot",
                        },
                    )
                self.ctx.computed.append(
                    {
                        "date": self.group["date"],
                        "theme": "在途，尚未抵达目的地",
                        "events": self.events,
                        "end": clock(self.time),
                        "note": "当天在途，尚未抵达目的地，不安排游览。",
                    }
                )
                return True
            elif self.group["date"] == self.ctx.arrival.date().isoformat():
                self.last = self.ctx.base
                arrival_buffer = transport_links.offset(self.ctx.workspace, "outbound")
                self.time = round_up(
                    max(
                        self.time,
                        self.ctx.arrival.hour * 60
                        + self.ctx.arrival.minute
                        + arrival_buffer,
                    )
                )
                arrival_links = transport_links.events(
                    self.ctx.workspace,
                    "outbound",
                    self.ctx.arrival.hour * 60 + self.ctx.arrival.minute,
                )
                if self.time >= minute(
                    self.ctx.requirements.get("day_end", "18:30")
                ) and (not self.group["items"]):
                    if arrival_links:
                        self.events += arrival_links
                    self.events.append(
                        {
                            "kind": "arrival",
                            "name": "抵达后先前往"
                            + (self.ctx.base["name"] if self.ctx.base else "住宿地点")
                            + "，核对入住并休息",
                            "start": arrival_links[-1]["end"]
                            if arrival_links
                            else self.ctx.arrival.strftime("%H:%M"),
                            "end": "23:59",
                            "candidate_id": self.ctx.base["id"]
                            if self.ctx.base
                            else None,
                            "note": "抵达时间较晚，当天不安排景点。先前往已选酒店；接驳路线及当晚入住条件尚需核实，不代表已预订或可立即入住。",
                        }
                    )
                    if self.time >= 1440:
                        self.ctx.warnings.append(
                            self.group["date"]
                            + "抵达后出站与前往酒店的接驳可能跨至次日；不能假设当晚已办理入住，请确认夜间交通及入住条件。"
                        )
                    self.ctx.computed.append(
                        {
                            "date": self.group["date"],
                            "theme": "抵达与休息",
                            "events": self.events,
                            "end": "23:59",
                            "note": "到达较晚，优先办理入住和休息。",
                        }
                    )
                    return True
                self.ctx.warnings.append(
                    f"{self.group['date']} 到达后预留{arrival_buffer}分钟出站与前往住宿；道路部分以查询结果为参考，出站、入住与等待仍是建议预留。"
                )
                if arrival_links:
                    self.events += arrival_links
                    if minute(arrival_links[-1]["end"]) < self.time:
                        self.events.append(
                            {
                                "kind": "arrival",
                                "candidate_id": self.ctx.base["id"],
                                "name": "寄存行李、核对入住与机动时间",
                                "start": arrival_links[-1]["end"],
                                "end": clock(self.time),
                                "note": "入住和寄存条件需确认，不代表已预订。",
                            }
                        )
                elif self.ctx.base:
                    self.events.append(
                        {
                            "kind": "arrival",
                            "name": "抵达后先前往"
                            + self.ctx.base["name"]
                            + "，寄存行李或核对入住",
                            "start": self.ctx.arrival.strftime("%H:%M"),
                            "end": clock(self.time),
                            "candidate_id": self.ctx.base["id"],
                            "note": "默认先前往已选酒店，再开始用餐或游览。接驳路线尚未核实，暂按建议预留；入住和寄存条件需确认。",
                        }
                    )

    async def return_only(self):
        if (
            self.ctx.return_time
            and self.group["date"] == self.ctx.return_time.date().isoformat()
            and (not self.group["items"])
        ):
            depart = self.ctx.return_time.hour * 60 + self.ctx.return_time.minute
            preparation = max(
                0, depart - transport_links.offset(self.ctx.workspace, "return")
            )
            if (
                self.ctx.arrival
                and self.ctx.arrival.date() == self.ctx.return_time.date()
                and (self.ctx.arrival.hour * 60 + self.ctx.arrival.minute > preparation)
            ):
                raise DataError(
                    "到达时间与返程接驳准备时间冲突，请调整往返班次。",
                    {
                        "date": self.group["date"],
                        "direction": "return",
                        "candidate_ids": [],
                        "view": "transport",
                    },
                )
            if (
                foods.choice(self.ctx.workspace, self.group["date"], "breakfast")
                and preparation >= 8 * 60 + 30
            ):
                breakfast, bt, self.last = await self.meal(
                    self.group["date"], "breakfast", 7 * 60 + 30, self.last, 45
                )
                if bt > preparation:
                    raise DataError(
                        "返程当天已选早餐与接驳准备时间冲突，请调整早餐地点或返程班次。",
                        {
                            "date": self.group["date"],
                            "direction": "return",
                            "view": "food",
                            "meal_period": "breakfast",
                            "candidate_ids": [],
                        },
                    )
                self.events += breakfast
            back_links = transport_links.events(self.ctx.workspace, "return", depart)
            if back_links:
                self.events += back_links
            else:
                self.events.append(
                    {
                        "kind": "transfer_plan",
                        "name": "退房与前往车站或机场，预留候车和安检时间",
                        "start": clock(preparation),
                        "end": self.ctx.return_time.strftime("%H:%M"),
                        "note": "接驳道路尚未核实，暂按建议准备；实际路线、退房及候车耗时请核对。",
                    }
                )
            back = self.ctx.workspace["selected_return"]
            finish = (
                back.get("arrival", "")[-5:]
                if back.get("arrival", "")[:10] == self.group["date"]
                else "23:59"
            )
            self.events.append(
                {
                    "kind": "transport",
                    "name": "乘坐" + back.get("name", "返程班次") + "返程",
                    "start": self.ctx.return_time.strftime("%H:%M"),
                    "end": finish,
                    "source": back.get("source"),
                    "note": "请核实班次最终时刻、车站或机场及席别。",
                }
            )
            self.ctx.computed.append(
                {
                    "date": self.group["date"],
                    "theme": "退房与返程",
                    "events": self.events,
                    "end": clock(preparation),
                }
            )
            return True

    async def breakfast(self):
        if (
            not self.ctx.arrival
            or self.group["date"] > self.ctx.arrival.date().isoformat()
        ) and (not self.events or minute(self.events[0]["start"]) >= 9 * 60):
            breakfast_at = pacing.meal_time(
                self.ctx.workspace, self.group["date"], "breakfast"
            )
            if self.changing_hotel:
                self.events.append(
                    {
                        "kind": "arrival",
                        "name": "退房（当天 12 点前；在早餐前办妥）并寄存行李",
                        "start": clock(breakfast_at - 15),
                        "end": clock(breakfast_at),
                        "candidate_id": self.origin["id"],
                        "note": "多数酒店要求当天 12 点前退房（具体以酒店为准），提前办理即可；退房后把行李寄存在酒店，再前往用餐与游览。",
                    }
                )
            breakfast, bt, self.last = await self.meal(
                self.group["date"],
                "breakfast",
                breakfast_at,
                self.last,
                pacing.meal_duration(
                    self.ctx.workspace, self.group["date"], "breakfast"
                ),
            )
            self.events += breakfast
            self.time = max(self.time, round_up(bt))

    async def before_visit(self):
        self.point = self.ctx.catalog[self.item["candidate_id"]]
        if (
            self.item.get("period") in ("afternoon", "evening")
            and self.time
            < pacing.meal_time(self.ctx.workspace, self.group["date"], "lunch")
            and (not self.lunch)
            and ("lunch" not in self.inside_periods)
        ):
            self.events.append(
                {
                    "kind": "free",
                    "name": "自由活动与休息",
                    "start": clock(self.time),
                    "end": clock(
                        pacing.meal_time(
                            self.ctx.workspace, self.group["date"], "lunch"
                        )
                    ),
                    "note": "为午餐及后续游玩时段保留弹性时间。",
                }
            )
            lunch_events, self.time, self.last = await self.meal(
                self.group["date"],
                "lunch",
                pacing.meal_time(self.ctx.workspace, self.group["date"], "lunch"),
                self.last,
                pacing.meal_duration(self.ctx.workspace, self.group["date"], "lunch"),
            )
            self.events += lunch_events
            self.lunch = True
        if (
            self.time
            >= pacing.meal_time(self.ctx.workspace, self.group["date"], "lunch")
            and (not self.lunch)
            and ("lunch" not in self.inside_periods)
        ):
            lunch_events, self.time, self.last = await self.meal(
                self.group["date"],
                "lunch",
                self.time,
                self.last,
                pacing.meal_duration(self.ctx.workspace, self.group["date"], "lunch"),
            )
            self.events += lunch_events
            self.lunch = True

    async def approach(self):
        if self.last:
            pair = (self.last["id"], self.point["id"])
            opts = self.ctx.routes.get(pair)
            if opts is None:
                opts = await self.ctx.services.route_options(self.last, self.point)
                self.ctx.routes[pair] = opts
            chosen = self.ctx.services.choose_route(opts, self.ctx.requirements)
            if chosen:
                base_buffer = (
                    15 if self.ctx.requirements.get("pace") == "relaxed" else 10
                )
                allocation = round_up(chosen["minutes"] + base_buffer)
                buffer = allocation - chosen["minutes"]
                self.events.append(
                    {
                        "kind": "route",
                        "name": "从" + self.last["name"] + "前往" + self.point["name"],
                        "start": clock(self.time),
                        "end": clock(self.time + chosen["minutes"] + buffer),
                        "route": chosen,
                        "options": opts,
                        "buffer": buffer,
                        "note": f"另留{buffer}分钟规划缓冲，非实测等待",
                    }
                )
                self.time += chosen["minutes"] + buffer
            else:
                self.ctx.warnings.append(
                    self.last["name"]
                    + "到"
                    + self.point["name"]
                    + "路线未知，时间衔接未验证"
                )
                self.events.append(
                    {
                        "kind": "unknown_route",
                        "name": "从" + self.last["name"] + "前往" + self.point["name"],
                        "start": clock(self.time),
                        "end": clock(self.time + 30),
                        "note": "路线查询失败，暂留30分钟占位；实际是否足够待核实",
                    }
                )
                self.time += 30

    async def opening(self, meal_minutes=0):
        """Validate the actual start and total stay, including in-venue meals."""
        from app.planning import opening_hours as _oh

        _ok, _why, _limit = _oh.check(
            self.point.get("opening"),
            self.point.get("name"),
            self.time,
            self.duration + meal_minutes,
        )
        if not _ok:
            _opens, _closes, _last = _oh.parse(self.point.get("opening"))
            _shift = _opens or 0
            if self.time < _shift and _shift + self.duration + meal_minutes <= (
                _limit if _limit is not None else 24 * 60
            ):
                self.events.append(
                    {
                        "kind": "free",
                        "name": "等候开放",
                        "start": clock(self.time),
                        "end": clock(_shift),
                        "note": "该地点按其开放资料尚未开始接待，先作机动安排。",
                    }
                )
                self.time = _shift
                _ok, _why, _limit = _oh.check(
                    self.point.get("opening"),
                    self.point.get("name"),
                    self.time,
                    self.duration + meal_minutes,
                )
        if not _ok:
            _cap = _limit if _limit is not None else 24 * 60
            _, _, last_entry = _oh.parse(self.point.get("opening"))
            _usable = max(0, _cap - self.time - meal_minutes)
            if last_entry is not None and self.time > last_entry:
                _usable = 0
            self.ctx.boundary_issues.append(
                {
                    "code": "opening_hours",
                    "level": "warning",
                    "view": "spot",
                    "date": self.group["date"],
                    "candidate_ids": [self.point["id"]],
                    "overrun_minutes": max(0, self.duration - _usable),
                    "available_minutes": _usable,
                    "message": self.group["date"]
                    + " "
                    + self.point["name"]
                    + "："
                    + _why
                    + "。该时段可用游玩时间约 "
                    + str(_usable)
                    + " 分钟；不足15分钟的景点未放入日程，选择仍保留，请改到开放时段或调整顺序。",
                }
            )
            self.duration = max(0, _usable)
            if self.duration < 15:
                return True

    async def visit_start(self):
        self.period = self.item.get("period", "any")
        self.floor = max(
            {"afternoon": 13 * 60, "evening": 18 * 60}.get(self.period, 0),
            minute(self.item.get("not_before") or "00:00"),
        )
        if self.time < self.floor:
            self.events.append(
                {
                    "kind": "free",
                    "name": "自由活动与休息",
                    "start": clock(self.time),
                    "end": clock(self.floor),
                    "note": "为后续指定游玩时段保留弹性时间。",
                }
            )
            self.time = self.floor

    async def visit_end(self):
        """Check hard end boundaries after opening waits and meals are known."""
        self.pin = self.ctx.workspace.get("visit_requests", {}).get(
            self.point["id"], {}
        )
        self.limit = {"morning": 720, "afternoon": 1080}.get(self.pin.get("period"))
        total_duration = self.duration + self.meal_minutes
        if self.limit and self.time + total_duration > self.limit:
            raise DataError(
                self.point["name"]
                + "的当前建议时长超出指定"
                + ("上午" if self.limit == 720 else "下午")
                + "窗口，正在核对可调整的顺序与游览范围。",
                {
                    "phase": "schedule",
                    "code": "visit_window",
                    "date": self.group["date"],
                    "candidate_ids": [self.point["id"]],
                    "view": "spot",
                    "available_minutes": max(0, self.limit - self.time),
                    "suggested_minutes": total_duration,
                    "events": [
                        {
                            "kind": e["kind"],
                            "name": e.get("name"),
                            "start": e["start"],
                            "end": e["end"],
                            "route": {
                                k: (e.get("route") or {}).get(k)
                                for k in ("mode", "minutes", "source")
                            },
                        }
                        for e in self.events
                    ],
                },
            )
        if self.time + total_duration > 24 * 60:
            over = max(0, self.time + total_duration - 24 * 60)
            self.ctx.boundary_issues.append(
                {
                    "code": "day_boundary",
                    "level": "warning",
                    "view": "spot",
                    "date": self.group["date"],
                    "candidate_ids": [self.point["id"]],
                    "overrun_minutes": over,
                    "available_minutes": max(0, 24 * 60 - self.time),
                    "message": self.group["date"]
                    + "按当前路线与游览时长计算，"
                    + self.point["name"]
                    + "前后已排到 24:00 之后（约超出 "
                    + str(over)
                    + " 分钟）。已按当天 24:00 截断，建议减少当日景点、换更早的班次或调整顺序。",
                }
            )
            self.duration = max(0, 24 * 60 - self.time - self.meal_minutes)
            if self.duration < 15:
                return True

    async def inside_dining(self):
        self.evidence = [
            x for x in self.ctx.guides if x["id"] in self.item.get("evidence_ids", [])
        ]
        self.note = str(self.item.get("note", ""))[:500]
        self.lunch_at = pacing.meal_time(
            self.ctx.workspace, self.group["date"], "lunch"
        )
        self.before_lunch = self.lunch_at - self.time
        self.inside_meals = []
        from app.planning.schedule import meal_inside as _meal_inside

        for _period in ("lunch", "dinner"):
            if _period == "lunch" and self.lunch:
                continue
            if foods.choice(self.ctx.workspace, self.group["date"], _period):
                from app.planning.schedule import meal_too_late as _mtl

                _late, _over, _wend = _mtl(
                    self.ctx.workspace,
                    self.group["date"],
                    _period,
                    self.time + self.duration,
                )
                if _late:
                    _label = "午餐" if _period == "lunch" else "晚餐"
                    _selected = foods.choice(
                        self.ctx.workspace, self.group["date"], _period
                    )
                    _sel_name = _selected.get("name") if _selected else "所选餐厅"
                    self.ctx.offered.append(
                        {
                            "code": "meal_not_placed",
                            "level": "warning",
                            "view": "food",
                            "date": self.group["date"],
                            "meal_period": _period,
                            "candidate_ids": [_selected["id"]]
                            if _selected and _selected.get("id")
                            else [],
                            "message": self.group["date"]
                            + " 的"
                            + _label
                            + "（"
                            + _sel_name
                            + "）未能放入日程：当天游玩到 "
                            + clock(self.time + self.duration)
                            + " 才结束，已超出"
                            + _label
                            + "可用时段（至"
                            + clock(_wend)
                            + "）约 "
                            + str(_over)
                            + " 分钟。建议该餐自行安排，或调整当天顺序、缩短游览、改到其他日期；您的餐厅选择仍保留。",
                        }
                    )
                    self.ctx.meal_unplaced.append(self.group["date"] + "|" + _period)
                continue
            _in, _at = _meal_inside(
                self.ctx.workspace,
                self.group["date"],
                self.time,
                self.duration,
                _period,
                self.lunch,
            )
            if _in:
                self.inside_meals.append((_period, _at))
        self.meal_minutes = sum(
            (
                pacing.meal_duration(self.ctx.workspace, self.group["date"], _p)
                for _p, _a in self.inside_meals
            )
        )
        if self.inside_meals:
            _names = ", ".join(
                ("午餐" if _p == "lunch" else "晚餐" for _p, _a in self.inside_meals)
            )
            self.note = (
                self.note
                + "；"
                + _names
                + "安排在游玩过程中（游玩时长不缩短，游程相应延长）。"
            )

    async def add_visit(self):
        self.inside_periods.update(period for period, _ in self.inside_meals)
        self.events.append(
            {
                "kind": "spot",
                "candidate_id": self.point["id"],
                "name": self.point["name"],
                "start": clock(self.time),
                "end": clock(self.time + self.duration + self.meal_minutes),
                "duration": self.duration,
                "note": self.note,
                "poi": self.point,
                "evidence": self.evidence,
            }
        )
        self.time += self.duration + self.meal_minutes
        if self.index < len(self.group["items"]) - 1:
            leisure = pacing.for_day(self.ctx.workspace, self.group["date"])[
                "break_minutes"
            ]
            self.events.append(
                {
                    "kind": "rest",
                    "name": "休息与机动时间",
                    "start": clock(self.time),
                    "end": clock(self.time + leisure),
                    "note": pacing.for_day(self.ctx.workspace, self.group["date"])[
                        "reason"
                    ],
                }
            )
            self.time += leisure
        self.last = self.point

    async def after_lunch(self):
        if (
            self.group["items"]
            and (not self.lunch)
            and ("lunch" not in self.inside_periods)
        ):
            from app.planning.schedule import meal_window as _mw

            _w0, _w1 = _mw(self.ctx.workspace, self.group["date"], "lunch")
            _dur = pacing.meal_duration(self.ctx.workspace, self.group["date"], "lunch")
            if self.time + _dur <= _w1 and self.time < _w1:
                meal_start = max(
                    self.time,
                    pacing.meal_time(self.ctx.workspace, self.group["date"], "lunch"),
                )
                lunch_events, self.time, self.last = await self.meal(
                    self.group["date"], "lunch", meal_start, self.last, _dur
                )
                self.events += lunch_events
                self.lunch = True

    async def dinner(self):
        self.end_limit = self.latest_end()
        if any((x.get("period") == "evening" for x in self.group["items"])):
            self.ctx.warnings.append(
                self.group["date"]
                + "包含晚间游览建议，当日结束按22:00预留；请核实出游当天夜间开放并确认体力。"
            )
        if (
            self.ctx.return_time
            and self.group["date"] == self.ctx.return_time.date().isoformat()
        ):
            self.ctx.warnings.append(
                f"{self.group['date']} 所选返程 {self.ctx.return_time.strftime('%H:%M')}，预留{transport_links.offset(self.ctx.workspace, 'return')}分钟接驳准备；实际出入口、候车或安检等待仍需确认。"
            )
            if self.time > self.end_limit:
                raise DataError(
                    self.group["date"]
                    + "的活动与返程冲突：预计结束于"
                    + clock(self.time)
                    + "，返程"
                    + self.ctx.return_time.strftime("%H:%M")
                    + "需暂按"
                    + clock(self.end_limit)
                    + "开始接驳准备。请调整这一天的顺序、游玩日期或返程班次后重排。",
                    {
                        "date": self.group["date"],
                        "direction": "return",
                        "candidate_ids": [
                            x["candidate_id"] for x in self.group["items"]
                        ],
                        "view": "spot",
                        "deadline": clock(self.end_limit),
                    },
                )
        if (
            self.end_limit >= 18 * 60
            and self.time <= self.end_limit - 60
            and ("dinner" not in self.inside_periods)
        ):
            dinner_start = max(
                self.time,
                pacing.meal_time(self.ctx.workspace, self.group["date"], "dinner"),
            )
            if self.time < dinner_start:
                self.events.append(
                    {
                        "kind": "free",
                        "name": "自由活动与机动时间",
                        "start": clock(self.time),
                        "end": clock(dinner_start),
                        "note": "可休息或自行安排活动。",
                    }
                )
            dinner_events, self.time, self.last = await self.meal(
                self.group["date"],
                "dinner",
                dinner_start,
                self.last,
                pacing.meal_duration(self.ctx.workspace, self.group["date"], "dinner"),
            )
            self.events += dinner_events
            if (
                self.ctx.return_time
                and self.group["date"] == self.ctx.return_time.date().isoformat()
                and (self.time > self.end_limit)
            ):
                raise DataError("已选晚餐与返程接驳冲突，请调整餐厅或班次。")

    async def hotel_transfer(self):
        if self.ctx.base and self.last and (self.last["id"] != self.ctx.base["id"]):
            opts = await self.ctx.services.route_options(self.last, self.ctx.base)
            chosen = self.ctx.services.choose_route(opts, self.ctx.requirements)
            if not chosen:
                raise DataError(
                    "从"
                    + self.last["name"]
                    + "返回"
                    + self.ctx.base["name"]
                    + "的路线尚未核实，请更新位置或重试，也可调整用餐安排。",
                    {
                        "date": self.group["date"],
                        "candidate_ids": [self.last["id"], self.ctx.base["id"]],
                        "view": "food",
                        "phase": "route",
                        "route_options": opts,
                    },
                )
            allocation = round_up(chosen["minutes"] + 15)
            if (
                self.ctx.return_time
                and self.group["date"] == self.ctx.return_time.date().isoformat()
                and (self.time + allocation > self.end_limit)
            ):
                _need = self.time + allocation - self.end_limit
                raise DataError(
                    self.group["date"]
                    + " "
                    + self.last["name"]
                    + "游览到"
                    + clock(self.time)
                    + "结束，返回"
                    + self.ctx.base["name"]
                    + "还需"
                    + str(allocation)
                    + "分钟（约"
                    + clock(self.time + allocation)
                    + "到），但为赶"
                    + self.ctx.return_time.strftime("%H:%M")
                    + "的返程，最晚需在"
                    + clock(self.end_limit)
                    + "前开始接驳准备，相差约"
                    + str(_need)
                    + "分钟。这一段回住宿的路程本身就占了大部分时间，"
                    + "单纯缩短游览通常补不回来；建议减少当天的景点或活动、提前返回住宿，"
                    + "或改乘更晚的班次。",
                    {
                        "date": self.group["date"],
                        "view": "spot",
                        "direction": "return",
                        "candidate_ids": [self.last["id"], self.ctx.base["id"]],
                        "deadline": clock(self.end_limit),
                        "overrun_minutes": _need,
                        "available_minutes": max(0, self.end_limit - self.time),
                        "needed_minutes": allocation,
                    },
                )
            self.events.append(
                {
                    "kind": "route",
                    "name": "从" + self.last["name"] + "返回" + self.ctx.base["name"],
                    "start": clock(self.time),
                    "end": clock(self.time + allocation),
                    "route": chosen,
                    "options": opts,
                    "buffer": allocation - chosen["minutes"],
                    "note": "活动后前往当晚住宿或返程前的行李寄存地点，含规划缓冲；寄存及入住条件待核实。",
                }
            )
            self.time += allocation
            self.last = self.ctx.base
            _cap = 23 * 60 + 30
            if self.time > _cap:
                _cut = self.time - _cap
                for _e in reversed(
                    [
                        x
                        for x in self.events
                        if x.get("kind") == "free" and (not x.get("poi"))
                    ]
                ):
                    if _cut <= 0:
                        break
                    _len = max(0, minute(_e.get("end")) - minute(_e.get("start")))
                    if _len <= 0:
                        continue
                    _take = min(_len, _cut)
                    _e["end"] = clock(minute(_e.get("end")) - _take)
                    _e["note"] = (
                        _e.get("note") or ""
                    ) + "（为满足最晚 23:30 到达住宿已压缩）"
                    _cut -= _take
                if _cut > 0:
                    self.ctx.boundary_issues.append(
                        {
                            "code": "late_checkin",
                            "level": "warning",
                            "view": "hotel",
                            "date": self.group["date"],
                            "candidate_ids": [self.ctx.base["id"]]
                            if self.ctx.base.get("id")
                            else [],
                            "overrun_minutes": _cut,
                            "available_minutes": _cap,
                            "message": self.group["date"]
                            + " 按当前安排约 "
                            + clock(self.time - _cut)
                            + " 才到达住宿，已超过最晚 23:30 约 "
                            + str(_cut)
                            + " 分钟。建议减少当天景点、提前返回或调整班次，以免行程跨到次日。",
                        }
                    )
                self.time = self.time - _cut

    async def free_time(self):
        if self.time + 30 < self.end_limit:
            self.events.append(
                {
                    "kind": "free",
                    "name": "自由活动与机动时间",
                    "start": clock(self.time),
                    "end": clock(self.end_limit),
                    "note": "尚未安排具体活动，可休息或继续挑选体验；返程未确定时不能视为全部可用",
                }
            )
            self.time = self.end_limit

    async def return_trip(self):
        if (
            self.ctx.return_time
            and self.group["date"] == self.ctx.return_time.date().isoformat()
        ):
            back_links = transport_links.events(
                self.ctx.workspace,
                "return",
                self.ctx.return_time.hour * 60 + self.ctx.return_time.minute,
            )
            if back_links:
                self.events += back_links
            else:
                self.events.append(
                    {
                        "kind": "transfer_plan",
                        "name": "前往车站或机场，预留候车与安检时间",
                        "start": clock(self.end_limit),
                        "end": self.ctx.return_time.strftime("%H:%M"),
                        "note": "接驳道路尚未核实，具体路线、候车与安检耗时请确认。",
                    }
                )
            back = self.ctx.workspace["selected_return"]
            finish = (
                back.get("arrival", "")[-5:]
                if back.get("arrival", "")[:10] == self.group["date"]
                else "23:59"
            )
            self.events.append(
                {
                    "kind": "transport",
                    "name": "乘坐" + back.get("name", "返程班次") + "返程",
                    "start": self.ctx.return_time.strftime("%H:%M"),
                    "end": finish,
                    "note": "请注意核实返程最终时刻、车站或机场及席别，提前准备身份证件。",
                    "source": back.get("source"),
                }
            )

    def publish(self):
        self.ctx.computed.append(
            {
                "date": self.group["date"],
                "theme": self.group.get("theme", "当日行程"),
                "events": self.events,
                "end": clock(self.time),
            }
        )
