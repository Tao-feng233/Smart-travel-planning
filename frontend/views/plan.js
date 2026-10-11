/* Plan presentation. These helpers never change the saved itinerary. */
function planMinute(value) {
  const match = /^(\d{2}):(\d{2})$/.exec(String(value || ""));
  if (!match) return null;
  const hours = Number(match[1]),
    minutes = Number(match[2]);
  return (hours < 24 && minutes < 60) || (hours === 24 && minutes === 0)
    ? hours * 60 + minutes
    : null;
}

function planTimedEvents(day) {
  return (day.events || [])
    .map((event) => ({
      event,
      start: planMinute(event.start),
      end: planMinute(event.end),
    }))
    .filter(
      (row) => row.start !== null && row.end !== null && row.end > row.start,
    );
}

function dayTimelineHTML(day) {
  const rows = planTimedEvents(day);
  if (rows.length < 2) return "";
  const start = Math.min(...rows.map((row) => row.start)),
    end = Math.max(...rows.map((row) => row.end));
  const colors = {
    spot: "#4a68af",
    meal: "#a76196",
    hotel: "#b58528",
    route: "#8394b1",
    rest: "#6b9b82",
    free: "#6b9b82",
  };
  const clock = (value) =>
    String(Math.floor(value / 60)).padStart(2, "0") +
    ":" +
    String(value % 60).padStart(2, "0");
  const segments = rows
    .map(({ event, start: from, end: to }) => {
      const left = ((from - start) / (end - start)) * 100,
        width = ((to - from) / (end - start)) * 100;
      const title = `${clock(from)}–${clock(to)} ${event.name || ""}`;
      return `<div class="tl-seg" style="left:${left}%;width:${width}%;background:${colors[event.kind] || colors.route}" title="${esc(title)}">${width > 15 ? esc(event.name) : ""}</div>`;
    })
    .join("");
  return `<div class="timeline-bar" role="img" aria-label="${esc(day.date)}的安排时间分布"><span class="tl-start">${clock(start)}</span><div class="tl-track">${segments}</div><span class="tl-end">${clock(end)}</span></div>`;
}

function dayIntensityHTML(day) {
  const events = day.events || [],
    spots = events.filter((event) => event.poi).length;
  if (!spots) return "";
  const walking = events.reduce(
    (sum, event) =>
      sum +
      (event.route?.mode === "walking" ? Number(event.route.distance) || 0 : 0),
    0,
  );
  const activeMinutes = planTimedEvents(day)
    .filter((row) => row.event.poi || row.event.route)
    .reduce((sum, row) => sum + row.end - row.start, 0);
  const level =
    spots <= 2 && walking <= 3000 && activeMinutes <= 360
      ? "easy"
      : spots <= 4 && walking <= 6000 && activeMinutes <= 540
        ? "medium"
        : "hard";
  const title =
    "按景点数量、游玩与通行时长、步行距离作粗略参考；未包含景区内步行与个人体力差异。";
  return `<span class="intensity ${level}" title="${title}">节奏参考 · ${{ easy: "轻松", medium: "适中", hard: "紧凑" }[level]}</span>`;
}

function budgetSummaryHTML(budget, requirements) {
  const known = budget?.known_subtotal;
  if (typeof known !== "number" || !Number.isFinite(known) || known < 0)
    return "";
  const limit = Number(requirements.budget),
    pending = (budget.unknown || []).length;
  const label = `参考支出 ¥${known.toFixed(0)} · ${pending}项待核实`;
  if (!(limit > 0 && Number.isFinite(limit)))
    return `<p class="budget-summary">${esc(label)}</p>`;
  const percent = Math.min(100, (known / limit) * 100);
  return `<div class="budget-bar" title="仅比较已有费用参考与您填写的总预算；待核实项未计入"><div class="budget-bar-known" style="width:${percent}%"></div><div class="budget-bar-label">${esc(label)} / 预算 ¥${limit.toFixed(0)}</div></div>`;
}

function dayMapHTML(day) {
  return `<details class="day-map" data-day-map="${esc(day.date)}"><summary>查看当日地图</summary><div class="day-map-content"></div></details>`;
}

// Opening a map is the point at which its data and basemap are needed.
document.addEventListener(
  "toggle",
  (event) => {
    const details = event.target;
    if (details.matches?.("[data-day-map]") && details.open) {
      const body = details.querySelector(".day-map-content");
      if (!body.children.length)
        body.innerHTML = placeMapHTML(details.dataset.dayMap);
    }
  },
  true,
);

document.addEventListener("click", (event) => {
  const link = event.target.closest(".book-nav a");
  if (!link) return;
  const target = document.getElementById(link.getAttribute("href").slice(1));
  const details = target?.closest("details");
  if (details) details.open = true;
});

let planPrintDetails = [];
window.addEventListener("beforeprint", () => {
  planPrintDetails = [
    ...document.querySelectorAll(".book details:not(.day-map)"),
  ].map((details) => [details, details.open]);
  for (const [details] of planPrintDetails) details.open = true;
});
window.addEventListener("afterprint", () => {
  for (const [details, open] of planPrintDetails) details.open = open;
  planPrintDetails = [];
});

function bookHTML() {
  const w = workspace,
    p = w.plan;
  const toolbar = `<div class="toolbar"><p>一份可以继续完善、打印和带走的旅行计划。</p><div><button data-action="plan">${p ? "重新生成" : "生成计划书"}</button>${p || w.last_plan_conflict ? '<button class="ghost" data-action="optimize_plan">智能修订</button>' : ""}<button class="ghost" data-action="undo">撤销上一步</button>${p && !p.stale ? `<button class="ghost" id="print">打印 / PDF</button><a href="/api/workspaces/${w.id}/export">导出 Markdown ↗</a>` : ""}</div></div>`;
  if (!p)
    return (
      toolbar +
      empty(
        "04",
        "生成旅行计划书",
        "包含每日安排、交通方式、住宿、预算、天气、准备事项、来源与审核意见。先选景点；住宿未定也可生成带未知项的草稿。",
      )
    );
  if (p.stale)
    return (
      toolbar +
      `<div class="empty"><span class="number">↻</span><h3>选择已更新，计划需要重排</h3><p>上一版「${esc(p.title)}」已保留。当前景点、住宿或条件与上一版不同，请重新生成后查看和导出完整计划。</p><button data-action="plan">按当前选择重新整理 →</button></div>`
    );
  return (
    toolbar +
    `<article class="book">${p.stale ? '<div class="notice">选择或条件已经变化。这是上一版计划，请重新生成后再使用或导出。</div>' : ""}<div class="book-cover"><span class="eyebrow">YOUR TRAVEL BOOK / 旅行计划书</span><h2>${esc(w.requirements.city)}旅行计划书</h2><span class="badge">待完善草稿 · ${esc((p.created || "").replace("T", " "))}</span></div>
 <div class="book-stats"><div><strong>${p.days.length}</strong><span>天的旅行</span></div><div><strong>${w.selected_spots.length}</strong><span>个已选景点</span></div><div><strong>${p.days.reduce((n, d) => n + d.events.filter((e) => e.route).length, 0)}</strong><span>段已有路线数据</span></div><div><strong>待确认</strong><span>门票、接驳与完整预算</span></div></div>
 <nav class="book-nav" aria-label="计划书目录"><a href="#book-overview">旅行概览</a>${p.days.map((d, i) => `<a href="#day-${i}">第${i + 1}天</a>`).join("")}<a href="#book-budget">费用</a><a href="#book-todos">出发待办</a><a href="#book-review">审核意见</a></nav>
 <details class="book-overview"><summary>住宿与往返交通</summary><h3 id="book-overview">旅行信息</h3><p>${esc(w.requirements.city)} · ${esc(w.requirements.start_date)}起 · ${w.requirements.days || 2}天 · ${w.requirements.adults || "未明确"}位成人</p><p>${w.hotel ? `住宿：${esc(w.hotel.name)}（仅选定，尚未预订）<br>地址：${esc(w.hotel.address)}${w.selected_room ? `<br>房型：${esc(w.selected_room.name)} · ${w.selected_room.quantity}间 · 报价¥${esc(w.selected_room.price ?? "待核实")}<br>${esc(w.selected_room.meal || "餐食待核实")} · ${esc(w.selected_room.cancel || "退改待核实")}` : ""}${src(w.hotel.source)}` : "住宿未定，当前日程不含住宿往返。"}</p>${mapHTML(w.selected_spots.map((i) => w.catalog[i]))}
 <h3>往返交通</h3>${["selected_transport", "selected_return"].map((key, i) => (workspace[key] ? `<p>${i ? "返程" : "去程"}：${esc(workspace[key].name)} · ${esc(workspace[key].departure)} → ${esc(workspace[key].arrival)}（${workspace[key].selection_status === "recommended" ? "推荐待确认" : "选定"}，未预订）</p>` : `<p>${i ? "返程" : "去程"}：${w.requirements.intercity_mode === "self_drive" ? "自驾" : w.requirements.intercity_mode === "self_arranged" ? "自行安排" : "班次未选（可选）"}，实际抵达与离开时间待核实。</p>`)).join("")}</details><h3>每日安排</h3><p>以下时间为建议日程。班次、预约等固定条件未确认前，起止时间保留调整空间。</p>${p.days.map((d, i) => `<section class="day" id="day-${i}">${dayIntensityHTML(d)}<h4>${esc(d.date)} · ${esc(d.theme)}</h4>${d.note ? `<p>${esc(d.note)}</p>` : ""}${dayTimelineHTML(d)}${d.events.map((e) => `<div class="event ${e.kind === "route" ? "route" : ""}"><div class="time">${esc(e.start)}<br>— ${esc(e.end)}</div><div class="event-body"><strong>${esc(e.name)}</strong><p>${esc(e.note)}</p>${e.route ? `<p>${mode(e.route.mode)} · 高德预计 ${e.route.minutes} 分钟 / ${(e.route.distance / 1000).toFixed(1)}公里 · 另留${e.buffer}分钟缓冲</p><span class="confidence-badge ok">路线查询参考 · 出行前请复核</span>${src(e.route.source)}${routeCostsHTML(e.route)}<details><summary>比较其他方式</summary>${(e.options || []).map((o) => `<p>${mode(o.mode)}：${o.available ? o.minutes + " 分钟，" + (o.distance / 1000).toFixed(1) + "公里" : esc(o.reason || "无数据")}</p>`).join("")}</details>` : ""}${e.source ? src(e.source) : ""}${e.poi ? `<p>游玩 ${e.duration} 分钟是建议值；门票、预约及当天开放待核实。</p>${src(e.poi.source)}` : ""}</div></div>`).join("") || "<p>弹性休息与待补充安排。</p>"}${dayMapHTML(d)}</section>`).join("")}
 <h3 id="book-budget">03 · 预算与费用口径</h3>${budgetSummaryHTML(p.budget, w.requirements)}<table><tr><th>费用项</th><th>当前可确认程度</th></tr><tr><td>住宿起价参考</td><td>${p.budget.hotel_reference != null ? "¥" + p.budget.hotel_reference.toFixed(0) + (p.budget.nights_priced != null && p.budget.nights_priced < p.budget.nights ? "（已含 " + p.budget.nights_priced + "/" + p.budget.nights + " 晚，其余待核实）" : "") : "未确定"}</td></tr>${Object.entries(
   p.budget?.items || {},
 )
   .map(
     ([k, v]) =>
       `<tr><td>${esc(k)}</td><td>¥${esc((v.amount || 0).toFixed(0))}${(v.detail || []).length ? ` <small>（${v.detail.length} 项明细）</small>` : ""}</td></tr>`,
   )
   .join(
     "",
   )}${p.budget?.known_subtotal != null ? `<tr><td><strong>可确认小计</strong></td><td><strong>¥${esc(p.budget.known_subtotal.toFixed(0))}</strong><small>（未含待核实项）</small></td></tr>` : ""}${(p.budget?.unknown || []).map((x) => `<tr><td>${esc(x)}</td><td>待核实，尚未计入完整预算</td></tr>`).join("")}</table><p>${esc(p.budget.basis || "总费用尚无法准确计算。")}</p>
 <details class="book-section"><summary>04 · 天气与应对</summary>${w.weather ? weatherHTML().replace(/<div class="toolbar">[\s\S]*?<\/div>/, "") : "<p>天气尚未查询。超出预报范围的日期需要临近出发时再确认。</p>"}
 </details><details class="book-section"><summary id="book-todos">05 · 出发前要处理的事</summary><ul>${(p.todos || []).map((x) => `<li>${esc(x)}</li>`).join("")}</ul></details><details class="book-section"><summary>06 · 携带与节奏建议</summary><ul>${(p.packing || []).map((x) => `<li>${esc(x)}</li>`).join("")}</ul>
 </details><details class="book-section"><summary>07 · 风险与待确认条件</summary><ul>${(
   p.warnings || []
 )
   .map(
     (x) =>
       `<li>${esc(
         readable(x)
           .replace(/breakfast/g, "早餐")
           .replace(/lunch/g, "午餐")
           .replace(/dinner/g, "晚餐"),
       )}</li>`,
   )
   .join("")}</ul>
 </details><details class="book-section"><summary id="book-review">08 · 独立审核意见</summary><p>${esc(p.review?.summary || "尚未完成")}</p><ul>${(p.review?.issues || []).map((x) => `<li>${esc(x)}</li>`).join("")}</ul><p>审核意见为模型辅助检查，不能替代真实数据和程序检查。</p>
 </details><details class="book-section"><summary>09 · 资料来源</summary>${(p.guides || []).map((g) => `<p>${link(g.url, g.title)} · 采集 ${esc(g.fetched_at)}；适用日期需核实</p>`).join("") || "<p>本次未检索到相关官方片段。</p>"}</details></article>`
  );
}
