// views/workspace.js
function setWorkbenchLayout(value) {
  workbenchExpanded = value;
  $("#application").classList.toggle("workbench-expanded", value);
  $("#workbench-shade").hidden = !value;
  $("#expand-workbench").setAttribute("aria-expanded", String(value));
  $("#expand-workbench").textContent = value ? "›" : "‹";
}

function hintText(text) {
  return String(text || "").replaceAll(
    "{位置}",
    innerWidth <= 700 ? "下方" : "右侧",
  );
}

function guideButton(cta) {
  if (!cta) return "";
  const attr =
    cta.view && sceneNames[cta.view]
      ? `data-tab="${cta.view}"`
      : cta.settings
        ? "data-open-settings"
        : Object.hasOwn(actionViews, cta.action)
          ? `data-action="${cta.action}"`
          : "";
  return attr ? `<button ${attr}>${esc(cta.label)} →</button>` : "";
}

function guidanceHTML(ui, reply = false) {
  if (!ui) return "";
  if (reply) return "";
  return ui.status === "loading"
    ? `<div class="scene-guide"><span>${esc(ui.title)}</span><span class="spinner" aria-hidden="true"></span></div>`
    : "";
}

function initialView(w) {
  const view = w.ui?.view;
  return sceneNames[view] ? view : w.plan ? "plan" : w.hotel ? "hotel" : "spot";
}

function centerStayHTML() {
  const w = workspace,
    hq = w.hotel_query || {};
  const ids = (hq.center_matches || []).length
    ? hq.center_matches
    : Object.keys(w.center_hotel_quotes || {});
  const found = ids.map((id) => w.catalog[id]).filter((p) => p && !p.stale);
  const basis = hq.center_basis || "全部已选景点的中心";
  const head = `<div class="stay-head"><strong>住宿候选（以全部景点中心为参照）</strong><small>以${esc(basis)}为参照，位置对整天行程都方便。选哪一家就点它上面的“住这一晚”，逐晚指定，没选就是还没选。</small></div>`;
  if (!found.length)
    return `<div class="stay-plan center-stay">${head}<p class="panel-footnote">还没有以全部景点中心查过主住宿。点上面的“查询住宿”会同时给出这一组候选；也可以直接在住宿编排里逐晚挑。</p></div>`;
  return `<div class="stay-plan center-stay">${head}<div class="cards">${found.map((p) => card(p)).join("")}</div><p class="panel-footnote">想让某一晚单独换一家，在下面“住宿编排”里点那一晚的候选即可，不会影响其它夜晚。</p></div>`;
}

function stayPlanHTML() {
  const w = workspace,
    stay = w.stay_plan;
  if (!stay || !(stay.rows || []).length) return "";
  const assignedRows = stay.assignments || {};
  const rows = (stay.rows || [])
    .map((row) => {
      const found = (row.candidate_ids || [])
        .map((id) => w.catalog[id])
        .filter((p) => p && !p.stale);
      const assigned = assignedRows[row.date];
      const rowHotelId = assigned
        ? assigned.hotel_id
        : row.hotel_source === "explicit"
          ? row.hotel_id
          : null;
      const picked = rowHotelId ? w.catalog[rowHotelId] : null;
      const chosen = !!rowHotelId;
      const pickedName = (picked || {}).name || "已选住宿";
      const label = chosen
        ? esc(pickedName) + "（这一晚已选）"
        : esc(row.anchor_name || "待定") + " 周边";
      const sub = chosen
        ? "这一晚单独指定"
        : "尚未选这一晚的住宿" +
          (row.anchor_is_station ? "（次日赶车，建议靠近出发站）" : "");
      const onway = (row.dinner_hint || [])
        .filter((x) => x.on_the_way)
        .map((x) => x.name);
      // 已选好住宿的那一晚折叠候选，避免整页一直是长列表；要换再点开。
      const expanded =
        (!chosen || stayOpenDate === row.date) && settledNight !== row.date;
      const body = found.length
        ? `<details class="stay-candidates"${expanded ? " open" : ""}><summary>${chosen ? "想换这一晚的住宿" : "这一晚的候选"}（${found.length} 家）</summary><div class="cards stay-cards">${found.map(card).join("")}</div></details>`
        : "";
      return `<div class="stay-row${chosen ? "" : " needs-hotel"}" data-stay-date="${esc(row.date)}"><div class="stay-date"><strong>${esc(row.date)}</strong><small>住 1 晚</small></div><div class="stay-anchor"><span>${label}</span><small>${sub}</small>${onway.length ? `<small>晚餐顺路：${esc(onway.join("、"))}</small>` : ""}</div><div class="stay-actions">${found.length ? `<small>${found.length} 家候选</small>` : `<small class="stay-unqueried">尚未查询</small><button class="ghost" data-action="search_hotels" data-stay-date="${esc(row.date)}">查这晚</button>`}</div>${body}</div>`;
    })
    .join("");
  const pending = (stay.unassigned || []).length;
  return `<div class="stay-plan"><div class="stay-head"><strong>住宿编排</strong><small>${esc(stay.note || "")}</small></div>${rows}${pending ? `<p class="panel-footnote">还有 ${pending} 晚没有选住宿（${esc((stay.unassigned || []).join("、"))}）：没选就是还没选，在对应夜晚点候选卡片即可。</p>` : `<p class="panel-footnote">${(stay.rows || []).length} 晚都已选定。要换某一晚，点那一晚的候选卡片即可，不影响其它夜晚。</p>`}</div>`;
}

function empty(n, title, text, button = "", actionName = "") {
  return `<div class="empty"><span class="number">${n}</span><h3>${title}</h3><p>${text}</p>${button ? `<button data-action="${actionName}">${button}</button>` : ""}</div>`;
}

function workflowHTML() {
  return planningNavigation();
}

function selectedStayUsable() {
  const h = workspace?.hotel;
  if (!h || h.selection_stale || h.location_stale) return false;
  const key = (value) =>
    String(value || "")
      .trim()
      .replace(/市$/, "");
  const city = h.query_conditions?.cityName || h.city;
  return (
    !city ||
    !workspace.requirements.city ||
    key(city) === key(workspace.requirements.city)
  );
}

function selectionHTML() {
  const w = workspace;
  return `<div class="selected-section"><h3>景点 · ${w.selected_spots.length}个</h3><div class="selection-spots">${w.selected_spots.map((id) => `<button data-select="${esc(id)}">${esc(w.catalog[id]?.name || id)} ×</button>`).join("") || "<p>未选择景点</p>"}</div></div><div class="selected-section"><h3>住宿与房型</h3>${w.hotel ? `<p>${esc(w.hotel.name)}${w.hotel.stale || w.hotel.quote_stale ? " · 报价待更新，位置已保留" : ""}</p>${w.selected_room ? `<p>${esc(w.selected_room.name)} · ${w.selected_room.quantity}间 · ¥${esc(w.selected_room.price ?? "待核实")}</p><p>${esc(w.selected_room.meal || "餐食待核实")} · ${esc(w.selected_room.cancel || "退改待核实")}</p>` : "<p>房型可选 · 尚未选择</p>"}` : "<p>未选择住宿</p>"}</div><div class="selected-section"><h3>用餐选择（可选）</h3>${
    Object.entries(w.meal_choices || {})
      .map(
        ([key, c]) =>
          `<p>${esc(key.replace("|", " · ").replace("breakfast", "早餐").replace("lunch", "午餐").replace("dinner", "晚餐"))}：${c.mode === "chosen" ? esc(w.catalog[c.food_id]?.name) : "自行安排"}</p>`,
      )
      .join("") || "<p>自行安排</p>"
  }</div><div class="selected-section"><h3>往返交通</h3>${["selected_transport", "selected_return"].map((key, i) => `<p>${i ? "返程" : "去程"}：${w[key] ? `${esc(w[key].name)} · ${esc(w[key].departure)}<br>${w[key].selection_status === "recommended" ? "推荐 · 待确认" : "已选定"}，尚未购票` : "未选择"}</p>`).join("")}</div>`;
}

function renderWorkspace() {
  const w = workspace,
    r = jobUI?.requirements || w.requirements;
  $("#conversation-title").textContent = w.title || "旅行规划";
  $("#conversation-title").title = w.title || "";
  $("#workspace-title").textContent =
    tab === "spot" && (!r.city || w.discovery_mode)
      ? "目的地推荐"
      : r.city
        ? `${r.city} · ${sceneNames[tab]}`
        : sceneNames[tab];
  const values = [
    ["city", "目的地", r.city],
    ["origin", "出发地", r.origin],
    ["start_date", "出游日期", r.start_date],
    ["days", "天数", r.days ? `${r.days} 天` : null],
    [
      "adults",
      "同行人数",
      r.adults
        ? `${r.adults} 成人${r.children ? ` / ${r.children} 儿童` : ""}`
        : null,
    ],
    ["budget", "总预算", r.budget ? `¥${r.budget}` : null],
  ];
  $("#requirements").innerHTML = values
    .map(
      ([key, label, v]) =>
        `<button class="info-field ${v ? "" : "unknown"}" data-edit-field="${key}"><small>${label}</small><strong>${esc(v || "未确定")}</strong></button>`,
    )
    .join("");
  $("#workflow").innerHTML = workflowHTML();
  $("#selected-content").innerHTML = selectionHTML();
  $("#selection").hidden = !w.archived;
  $("#selection").innerHTML = w.archived
    ? '<div class="archive-notice">已归档，仅供查看。<button id="restore-trip" class="ghost">恢复规划</button></div>'
    : "";
  const ui = jobUI || w.ui;
  $("#scene-feedback").hidden =
    ui?.status !== "loading" ||
    !ui ||
    !!w.archived ||
    (!!ui.view && ui.view !== tab);
  $("#scene-feedback").innerHTML = guidanceHTML(ui);
  $("#scene-feedback").classList.toggle("loading", ui?.status === "loading");
  $("#mission").hidden =
    !w.archived &&
    ((!!ui?.view && ui.view === tab) ||
      (tab === "plan" && w.plan && !w.plan.stale));
  $("#mission").classList.toggle(
    "compact",
    !!w.plan && !w.plan.stale && !w.archived,
  );
  $("#trip-state").textContent = w.plan?.stale
    ? "计划待更新"
    : w.plan
      ? "计划已生成"
      : w.title || "新旅行";
  const displayMessages = w.messages.filter(
    (m) =>
      !(
        m.role === "assistant" &&
        /^已(?:选择|取消选择)：.*当前已选\d+个景点/.test(readable(m.content))
      ),
  );
  const welcome = {
    role: "assistant",
    type: "welcome",
    content:
      "欢迎使用识途。\n\n**您想去哪里？目的地是否已经确定？**\n也可以先告诉我大致预算、出游时间和旅行偏好，我会帮您比较目的地，再逐步安排景点、住宿、交通与餐饮。",
  };
  const messages = displayMessages.some(
    (m) =>
      m.type === "welcome" ||
      (m.role === "assistant" && m.content.startsWith("欢迎使用识途。")),
  )
    ? displayMessages
    : [welcome, ...displayMessages];
  const lastAssistant = messages.findLastIndex((m) => m.role === "assistant");
  const messageSignature = w.id + JSON.stringify(messages) + innerWidth;
  if (messageSignature !== renderedMessages) {
    $("#messages").innerHTML = messages
      .map(
        (m, i) =>
          `<div class="message ${m.role === "user" ? "user" : ""}"><span class="speaker">${m.role === "user" ? "用户" : "识途"}</span><div class="bubble">${processHTML(m.process_steps)}${messageHTML(m.content, { ...m.ui, role: m.role })}${!busy && !w.archived && i === lastAssistant ? guidanceHTML(m.ui || w.ui, true) : ""}</div></div>`,
      )
      .join("");
    $("#messages").scrollTop = $("#messages").scrollHeight;
    renderedMessages = messageSignature;
  }
  document
    .querySelectorAll(".tabs [data-tab]")
    .forEach((b) => b.classList.toggle("active", b.dataset.tab === tab));
  $("#content").innerHTML = prerequisitesHTML() + content();
  const count = w.selected_spots.length;
  $("#selection-indicator").hidden = !count;
  $("#selection-indicator").innerHTML = count
    ? `<span>已选 <strong>${count}</strong> 个景点</span><button class="text-button" data-action="complete_spots">${w.spots_confirmed ? "重新确认景点" : "完成景点选择"}</button>`
    : "";
  setBusy(busy);
  renderLive();
}

function renderWorkspaceContent() {
  const w = workspace;
  if (tab === "food") return foodHTML();
  if (tab === "spot") {
    return !w.requirements.city || w.discovery_mode
      ? destinationHTML()
      : spotsHTML();
  }
  if (tab === "hotel") {
    const chosen = w.hotel
      ? `<div class="current-stay"><small>已选住宿</small><strong>${esc(w.hotel.name)}</strong><span>${w.selected_room ? esc(w.selected_room.name) + " · " + w.selected_room.quantity + "间" : "房型可选 · 未选择"}</span>${w.hotel.stale || w.hotel.quote_stale ? "<small>住宿位置已保留，房型与价格需重新查询。</small>" : ""}</div>`
      : "";
    const items = w.hotel_query
      ? (w.hotel_query.ids || [])
          .map((id) => w.catalog[id])
          .filter((p) => p && !p.stale)
      : Object.values(w.catalog || {}).filter(
          (p) => p.kind === "hotel" && !p.stale,
        );
    const missing = [
      ["start_date", "出游日期"],
      ["days", "旅行天数"],
      ["adults", "成人数"],
    ].filter(([k]) => !w.requirements[k]);
    return (
      chosen +
      `<div class="candidate-head"><div><h3>住宿推荐</h3><p>选定酒店即可继续 · 具体房型可选</p></div><button data-action="complete_hotel" ${selectedStayUsable() ? "" : "disabled"}>完成住宿选择</button></div>` +
      (missing.length
        ? `<div class="inline-requirements"><strong>查询住宿需要补充信息</strong><p>${missing.map((x) => x[1]).join("、")}尚未确定。可以直接在对话中提供，或编辑右侧旅行信息。</p><button data-open-settings>补充旅行信息</button></div>`
        : "") +
      stayPlanHTML() +
      centerStayHTML() +
      `<div class="toolbar"><p>${items.length} 家候选${w.hotel_query?.keyword ? " · " + esc(w.hotel_query.keyword) : ""} · 结合游览区域比较</p><button class="ghost" data-action="search_hotels">查询住宿</button></div>` +
      ((items.length || (w.hotel_query?.center_matches || []).length) &&
      !w.stay_plan
        ? `<div class="cards">${
            (w.hotel_query?.center_matches || [])
              .map((id) => w.catalog[id])
              .filter((p) => p && !p.stale)
              .map(card)
              .join("") +
            items
              .sort(
                (a, b) =>
                  (a.recommendation_rank ?? 99) - (b.recommendation_rank ?? 99),
              )
              .map(card)
              .join("")
          }</div>`
        : items.length
          ? ""
          : empty(
              "02",
              "住宿安排",
              Number(w.requirements.days) === 1
                ? "本次为一日游，可以跳过住宿。"
                : "确认景点与日期后查询住宿。已有住宿或暂未决定时，可以先继续规划。",
            )) +
      `<div class="panel-footer-actions"><button class="ghost" data-action="skip_hotel">暂不安排住宿，继续</button></div>`
    );
  }
  if (tab === "weather") return weatherHTML();
  if (tab === "transport") return transportHTML();
  if (tab === "plan") return bookHTML();
  const guides = w.web_guides || w.plan?.guides || [];
  return (
    `<div class="toolbar"><p>联网旅游资料，优先采用官方信息；平台文章须核实点赞数至少一万。资料保留来源与查询时间，运营信息需核对出游日。</p></div>` +
    (guides.length
      ? guides
          .map(
            (g) =>
              `<article class="knowledge"><h4>${esc(g.title)}</h4><p>${esc(g.text)}</p>${link(g.url, "查看原文 ↗")}<div class="source">查询 ${esc(g.fetched_at)} · ${esc(g.source_kind === "popular_article" ? `平台文章 · 点赞 ${g.likes} · 评论 ${g.comments ?? "未提供"}` : "官方资料")} · ${esc(g.retrieval || "页面快照")}</div></article>`,
          )
          .join("")
      : empty(
          "资料",
          "介绍也需要有依据",
          "查询景点时，助手会联网收集旅游资料。尚无可核实来源时保留未知。",
        )) +
    `<details><summary>最近的执行记录</summary>${w.trace.map((x) => `<p>${esc(x.time)} · ${esc(x.text)}</p>`).join("")}</details>`
  );
}

function weatherHTML() {
  const w = workspace.weather,
    r = workspace.requirements;
  let top =
    '<div class="toolbar"><p>和风真实预报，仅覆盖返回的日期。</p><button data-action="weather">更新天气</button></div>';
  if (!w)
    return (
      top +
      empty(
        "☀",
        "天气信息",
        "选一个景点后，用它的坐标查询天气。超出预报窗口的日期不提供伪造预报。",
      )
    );
  const relevant = w.days.filter(
    (d) =>
      !r.start_date ||
      (d.date >= r.start_date &&
        d.date < addDate(r.start_date, Number(r.days || 2))),
  );
  return (
    top +
    (!relevant.length
      ? '<div class="notice">旅行日期超出当前预报范围，天气待确认。下面展示当前可查询窗口。</div>'
      : "") +
    `<div class="weather-days">${(relevant.length ? relevant : w.days).map((d) => `<div class="weather-day"><small>${esc(d.date)}</small><h4>${esc(d.text)}</h4><div class="temp">${Math.round(d.low)}° — ${Math.round(d.high)}°</div><p>降水概率 ${d.rain != null ? Math.round(d.rain * 100) + "%" : "未知"}</p><p>风力 ${esc(d.wind ?? "未知")} 级</p></div>`).join("")}</div><p>${esc(w.alert_status)} · 当前预警，不等于出游日预警</p>${w.alerts.length ? `<pre>${esc(JSON.stringify(w.alerts, null, 2))}</pre>` : ""}${src(w.source)}${w.attributions.map((u) => link(u, "天气数据署名")).join(" · ")}`
  );
}

function addDate(s, n) {
  let d = new Date(s + "T12:00:00");
  d.setDate(d.getDate() + n);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}
