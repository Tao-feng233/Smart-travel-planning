// views/candidates.js
function mapHTML(items) {
  const ps = items
    .filter((x) => x.location)
    .map((p) => ({ ...p, xy: p.location.split(",").map(Number) }));
  if (ps.length < 2) return "";
  const xs = ps.map((p) => p.xy[0]),
    ys = ps.map((p) => p.xy[1]);
  const xmin = Math.min(...xs),
    ymin = Math.min(...ys),
    dx = Math.max(...xs) - xmin || 0.01,
    dy = Math.max(...ys) - ymin || 0.01;
  return `<div class="map"><small>地点分布 · 真实坐标示意，连线不代表道路或导航路线</small><svg viewBox="0 0 650 220" role="img" aria-label="已选地点位置示意"><path d="M0 180 Q150 150 300 195 T650 170" fill="none" stroke="#d2dfd5" stroke-width="30"/>${ps
    .map((p, i) => {
      const x = 45 + ((p.xy[0] - xmin) / dx) * 520,
        y = 180 - ((p.xy[1] - ymin) / dy) * 135;
      return `<circle cx="${x}" cy="${y}" r="6"/><text x="${Math.min(x + 9, 530)}" y="${y - 9}">${esc(p.name.slice(0, 15))}</text>`;
    })
    .join("")}</svg></div>`;
}

function renderCandidateCard(p) {
  if (p.kind === "spot") return spotCard(p);
  if (p.kind === "food") return foodCard(p);
  const noTicket =
    ["train", "flight"].includes(p.kind) && String(p.seats) === "0";
  const currentTransport =
    p.direction === "return"
      ? workspace.selected_return
      : workspace.selected_transport;
  const sel =
    p.kind === "spot"
      ? workspace.selected_spots.includes(p.id)
      : p.kind === "hotel"
        ? workspace.hotel?.id === p.id
        : (p.direction === "return"
            ? workspace.selected_return
            : workspace.selected_transport
          )?.id === p.id;
  const h = p.kind === "hotel",
    t = p.kind === "train" || p.kind === "flight";
  return `<article class="card ${sel ? "selected" : ""}" data-candidate="${esc(p.id)}"><div class="card-top"><div><span class="kind">${h ? "住宿候选" : t ? "交通候选" : "景点候选"}</span><h3>${esc(p.name)}</h3></div>${p.rating ? `<span class="badge">${esc(p.rating)} 分</span>` : ""}</div>
 ${p.price != null ? `<div class="price">¥${esc(p.price)} <small>${h ? "起" : "参考"}</small></div>` : ""}
 ${t ? `<p>${esc(p.departure)} → ${esc(p.arrival)}</p><p>${esc(p.departure_station || "")} → ${esc(p.arrival_station || "")}</p><p>${p.kind === "train" ? esc(p.seat_type || "席别待核实") + " / " : ""}当前可售状态：${esc(p.seat_label)}${p.tax != null ? " · 税费 " + esc(p.tax) : ""}</p>` : `<p>${esc(p.address || "地址未知")}</p>`}
 ${h ? `<p>${esc(p.area || "")} · ${esc(p.room || "房型待核实")}</p><p>${esc(p.window || "")} · ${esc(p.meal || "")} · ${esc(p.refund || "")}</p><p>${esc(p.review_summary || "")}</p><p>${esc(p.match_status || "")}</p>${p.anchor_route ? `<p>到${esc(p.anchor_name)}：${mode(p.anchor_route.mode)}约 ${p.anchor_route.minutes} 分钟</p>` : ""}` : !t ? `<p>地图营业资料：${esc(p.opening || "未提供")}</p><p>票价 / 预约：待核实，不能据此认定免费或无需预约</p>` : ""}
 ${p.price_basis ? `<p>${esc(p.price_basis)}</p>` : ""}${p.recommendation ? `<div class="reason">助手建议 · ${esc(p.recommendation)}</div>` : ""}
 ${noTicket ? '<div class="sold-out">无票 · 请选择其他班次</div>' : ""}<div class="card-actions"><button data-select="${esc(p.id)}" ${noTicket ? 'disabled aria-disabled="true"' : ""}>${noTicket ? "无票" : sel ? (t && currentTransport?.selection_status === "recommended" ? "确认推荐" : p.kind === "spot" ? "已选择 · 移除" : "已选定") : h ? "选择住宿" : t ? "选择班次" : "想去这里"}</button>${h ? `<button class="ghost" data-detail="${esc(p.id)}">房型详情</button>` : !t ? `<button class="ghost" data-ticket="${esc(p.id)}">查门票</button>` : ""}${p.location ? link(`https://uri.amap.com/marker?position=${p.location}&name=${encodeURIComponent(p.name)}`, "地图查看 ↗") : ""}</div>
 ${p.detail ? roomHTML(p.detail, p.id) : ""}
 ${workspace.tickets[p.id] ? ticketsHTML(workspace.tickets[p.id]) : ""}${src(p.source)}${p.detail_source ? src(p.detail_source) : ""}${p.map_source ? src(p.map_source) : ""}${p.evidence?.length ? `<details><summary>推荐依据 · ${p.evidence.length} 条资料</summary>${p.evidence.map((g) => `<p>${esc(g.text)}</p>${link(g.url, g.title)}`).join("")}</details>` : ""}</article>`;
}

function pager(page, pages, more = false, destination = false) {
  const attr = destination ? "data-destination-page" : "data-spots-page",
    start = Math.max(1, Math.min(page - 1, pages - 3));
  return `<nav class="candidate-pager" aria-label="${destination ? "目的地" : "景点"}分页"><button class="ghost" ${attr}="${page - 1}" ${page <= 1 ? "disabled" : ""}>上一页</button>${Array.from(
    { length: Math.min(4, pages) },
    (_, i) => start + i,
  )
    .map(
      (n) =>
        `<button ${attr}="${n}" class="${page === n ? "active" : "ghost"}" aria-current="${page === n ? "page" : "false"}">${n}</button>`,
    )
    .join(
      "",
    )}<button class="ghost" ${attr}="${page + 1}" ${page >= pages && !more ? "disabled" : ""}>下一页</button></nav>`;
}

function renderSpotResults() {
  const w = workspace,
    all = Object.values(w.catalog || {}).filter(
      (p) => p.kind === "spot" && !w.rejected_spots?.includes(p.id),
    );
  const info = w.spot_page || {
    page: 1,
    pages: Math.max(1, Math.ceil(all.length / 4)),
    ids: all.slice(0, 4).map((p) => p.id),
    has_more: false,
  };
  const items = info.ids.map((id) => w.catalog[id]).filter(Boolean);
  const top = `<div class="candidate-head"><div><h3>景点推荐</h3><p>${w.requirements.preferences?.length ? "按偏好与已知条件推荐" : "按城市代表景点资料、地图评分与位置推荐"} · 已选 ${w.selected_spots.length} 个</p><small>地图评分不代表实时热度排行</small>${w.spot_search?.ids ? `<small>本轮 ${w.spot_search.ids.length} 个候选${w.spot_search.minimum ? ` · 本次目标至少 ${w.spot_search.minimum} 个` : ""}，按兴趣取舍，不需要全部选择。</small>` : ""}</div><button data-action="complete_spots" ${w.selected_spots.length ? "" : "disabled"}>完成景点选择</button></div>`;
  const nav = `<div class="browse-tools">${info.pages > 1 ? pager(info.page, info.pages, false) : '<span class="panel-footnote">本轮推荐</span>'}<button class="text-button" data-more-spots>继续推荐相关景点</button><button class="text-button" data-replace-spots>重新筛选推荐</button></div>`;
  if (
    w.spot_preference?.city === w.requirements.city &&
    w.spot_preference.status === "awaiting" &&
    !w.requirements.preferences?.length
  )
    return (
      top +
      `<div class="panel-intro preference-prompt"><h3>按旅行偏好推荐</h3><p>请在对话中提供海滨、人文、自然风光、亲子游或少走路等偏好。暂无偏好也可以直接查看代表景点。</p><button data-action="search_spots" data-preference-mode="default">暂无偏好，查看代表景点</button></div>`
    );
  if (!all.length)
    return (
      top +
      `<div class="panel-intro"><h3>${esc(w.requirements.city)}景点选择</h3><p>根据旅行偏好查询景点，选择完成后再比较住宿。可以在对话中指定兴趣或景点名称。</p><button data-action="search_spots">查询景点推荐</button><button class="ghost" data-action="discover_destinations">比较其他目的地</button></div>`
    );
  return (
    top +
    nav +
    `<div class="cards">${groupedSpotsHTML(items)}</div><div class="panel-footer-actions"><button class="ghost" data-action="discover_destinations">比较其他目的地</button><button class="ghost" data-action="search_spots">按当前偏好重新查询</button></div>`
  );
}

function roomHTML(d, id) {
  const h = workspace.catalog[id],
    choices = h.room_choices || [],
    policy = d.policies || {};
  return `<details class="room-details" ${detailOpenId === id || workspace.hotel?.id === id ? "open" : ""}><summary>房型与报价（可选） · ${(d.roomTypes || []).length}种</summary><p>入住 ${esc(policy.checkInTime || d.checkInTime || "待核实")} / 退房 ${esc(policy.checkOutTime || d.checkOutTime || "待核实")}</p>${policy.cancelPolicy ? `<p>酒店退改概览：${esc(policy.cancelPolicy)}</p>` : ""}${(
    d.roomTypes || []
  )
    .map(
      (r, i) =>
        `<div class="room" data-room-group="${esc(id)}:${i}"><strong>${esc(r.roomTypeName)}</strong><p>${[r.bedType, r.maxOccupancy ? `最多${r.maxOccupancy}人` : "人数待核实", r.roomSize ? String(r.roomSize) + (String(r.roomSize).match(/^\d+(\.\d+)?$/) ? "㎡" : "") : "", r.floor ? "楼层 " + r.floor : ""].filter(Boolean).map(esc).join(" · ")}</p>${r.images?.length ? photoHTML({ name: r.roomTypeName, photos: r.images, source: h.detail_source }) : ""}${(
          r.ratePlans || []
        )
          .map((v, j) => {
            const c = choices.find(
                (c) => c.room_index === i && c.rate_index === j,
              ),
              soldOut = String(v.count) === "0";
            return `<div class="rate"><strong>¥${esc(v.rmbPrices ?? "待核实")}</strong><small>参考报价</small>${v.ratePlanName ? `<p>${esc(v.ratePlanName)}</p>` : ""}<p>${esc(v.mealText || "餐食待核实")} · ${esc(v.cancelText || v.cancelDesc || "退改待核实")}</p>${soldOut ? '<p class="sold-out">无房 · 请更换报价或更新详情</p>' : v.count != null ? `<small>可售数量 ${esc(v.count)}（查询时）</small>` : "<small>可售状态待确认</small>"}${c ? `<button data-room="${esc(c.id)}" ${soldOut ? "disabled" : ""} class="${workspace.selected_room?.id === c.id ? "ghost" : ""}">${soldOut ? "无房" : workspace.selected_room?.id === c.id ? "已选此房型" : "选择此房型"}</button>` : "<p>请更新房型详情后选择</p>"}</div>`;
          })
          .join("")}</div>`,
    )
    .join(
      "",
    )}<p class="panel-footnote">报价、入住资格及整段住宿总价需预订前确认。</p></details>`;
}

function transportDate(direction) {
  const r = jobUI?.requirements || workspace.requirements;
  return direction === "outbound"
    ? r.outbound_date || r.start_date
    : r.return_date ||
        (r.start_date ? addDate(r.start_date, Number(r.days || 2)) : null);
}

function prerequisitesHTML() {
  const w = workspace,
    r = w.requirements;
  let need = [];
  if (tab === "hotel")
    need = [
      ["start_date", "出游日期"],
      ["days", "游玩天数"],
      ["adults", "成人数"],
    ];
  if (tab === "transport")
    need = [
      ["origin", "出发城市"],
      ["city", "目的地"],
      ["start_date", "出游日期"],
      ["days", "游玩天数"],
    ];
  if (tab === "food")
    need = [
      ["start_date", "出游日期"],
      ["days", "游玩天数"],
    ];
  const missing = need.filter(([k]) => !r[k]).map(([, n]) => n);
  if (missing.length)
    return `<div class="missing-banner" role="status"><div><strong>请补充一下${missing.map(esc).join("、")}</strong><p>便于按实际条件查询与安排行程；可在对话中提供或手动编辑旅行信息。</p></div><button class="ghost" data-open-settings>填写信息</button></div>`;
  const next = w.next_step;
  if (next?.action && ["transport", "hotel", "food", "plan"].includes(tab))
    return `<div class="next-banner"><strong>${esc(next.message)}</strong><button data-action="${esc(next.action)}">${esc(next.label)}</button></div>`;
  return "";
}

function includedBreakfast() {
  if (mealPeriod !== "breakfast") return "";
  const slot = (workspace?.timeline?.meal_slots || []).find(
    (x) =>
      x.date === mealDate && x.period === "breakfast" && x.included_in_room,
  );
  if (!slot) return "";
  const m = String(slot.name || "").match(/（([^）]*)）/);
  return m ? m[1] : "房型含早";
}

function renderFoodResultsBase() {
  const w = workspace,
    r = w.requirements;
  const slots = (typeof mealSlots === "function" ? mealSlots() : []) || []; // 有槽位时以其为准；无槽位就不列出日期——回退到游玩日会把抵达日又列回来，
  // 造成"选了却排不下"的死循环。
  const dates = slots.length
    ? [...new Set(slots.map((x) => x.date))].sort()
    : [];
  if (!dates.includes(mealDate)) mealDate = dates[0] || "";
  if (!slots.some((x) => x.date === mealDate && x.period === mealPeriod)) {
    const nxt = typeof nextMealSlot === "function" ? nextMealSlot("") : null;
    if (nxt) {
      mealDate = nxt.date;
      mealPeriod = nxt.period;
    }
  }
  const q =
      w.food_query?.meal_date &&
      (w.food_query.meal_date !== mealDate ||
        w.food_query.meal_period !== mealPeriod)
        ? null
        : w.food_query,
    items = (q?.ids || []).map((i) => w.catalog[i]).filter(Boolean),
    key = mealDate + "|" + mealPeriod,
    ch = w.meal_choices?.[key];
  return `<div class="candidate-head"><div><h3>餐饮安排（可选）</h3><p>按日期和餐次选择，也可以出行时自行决定。</p></div><button class="ghost" data-search-foods>查询餐厅</button></div><div class="meal-picker"><label>日期<select id="meal-date">${dates.map((d) => `<option ${mealDate === d ? "selected" : ""}>${esc(d)}</option>`).join("")}</select></label><label>参照地点<select id="food-anchor"><option value="">按当日行程自动选择</option>${[
    ...w.selected_spots.map((id) => w.catalog[id]),
    w.hotel,
  ]
    .filter((p) => p?.location)
    .map(
      (p) =>
        `<option value="${esc(p.id)}" ${foodAnchor === p.id ? "selected" : ""}>${esc(p.name)}</option>`,
    )
    .join("")}</select></label><label>餐次<select id="meal-period">${[
    ["breakfast", "早餐"],
    ["lunch", "午餐"],
    ["dinner", "晚餐"],
  ]
    .map(
      ([v, n]) =>
        `<option value="${v}" ${mealPeriod === v ? "selected" : ""}>${n}</option>`,
    )
    .join(
      "",
    )}</select></label><button class="ghost" data-self-meal ${!dates.length ? "disabled" : ""}>本餐自行安排</button></div>${w.meal_removed_notice ? `<p class="meal-removed-notice">${esc(w.meal_removed_notice)}</p>` : ""}<p class="meal-status">${includedBreakfast() ? "房型已含早（" + esc(includedBreakfast()) + "），无需另选；如想出去吃，可在下方自行选择餐厅。" : ch?.mode === "chosen" ? "本餐已选：" + esc(w.catalog[ch.food_id]?.name) + ' <button class="text-button" data-meal-remove>取消这一餐</button>' : "本餐尚未选定，可选下方餐厅或自行安排。"}</p>${q ? `<p>${esc(q.meal_date || "未指定餐日")} ${esc({ breakfast: "早餐", lunch: "午餐", dinner: "晚餐" }[q.meal_period] || "")} · ${esc(q.anchor)} · ${esc(q.scope || "城市范围")} · ${items.length}家候选</p>` : ""}<div class="cards">${items.map(foodCard).join("")}</div>${
    q?.markets?.length
      ? "<h3>海鲜采购场所（非用餐预订）</h3>" +
        q.markets
          .map((id) => {
            const p = w.catalog[id];
            return p
              ? `<article class="card"><h3>${esc(p.name)}</h3><p>${esc(p.address)}</p>${src(p.source)}</article>`
              : "";
          })
          .join("")
      : ""
  }${!items.length ? "<p>尚无餐厅候选：系统已先按当日景点周边、再按城市范围查询过。可以换一个日期或餐次、在参照地点里指定别的景点、或直接告诉我具体菜系（例如“水席”“面食”）或店名，我再查一次；也可以点“本餐自行安排”。</p>" : ""}<div class="panel-footer-actions"><button class="ghost" data-self-all-meals>全部用餐自行安排</button><button data-action="complete_food">完成餐饮安排，继续</button></div>`;
}

function transportHTML() {
  const w = workspace;
  const own = w.requirements.intercity_mode === "self_drive",
    arranged = w.requirements.intercity_mode === "self_arranged";
  // 往返交通改为用户填写：不再提供"选班次"。班次查询保留，仅作时刻参考，
  // 但不存在"把某趟车选进行程"这一步——本项目不出票。
  const optional = `<div class="panel-intro"><h3>往返交通（可选）</h3><p>城际交通由你自行安排：在「旅行信息」里填到达站与到达时间、返程站与返程时间。自驾可跳过。市内通行仍会按地点计算。</p><div class="panel-footer-actions"><button data-trip-transport="self_drive" class="${own ? "" : "ghost"}">自驾游，继续规划</button><button data-trip-transport="self_arranged" class="${arranged ? "" : "ghost"}">往返自行安排</button></div></div>`;
  if (own || arranged)
    return (
      optional +
      "<p>已设为" +
      (own ? "自驾游，市内优先驾车" : "往返自行安排") +
      '。抵达和离开时间未明确时，首尾日保持弹性。</p><button data-tab="food">查看餐饮安排</button>'
    );
  if (w.local_trip)
    return (
      optional +
      '<div class="panel-intro"><h3>本地出游</h3><p>出发地与游玩地在同一区域，无需选择外地往返班次。市内步行、公交或打车方案会在计划书中比较。</p><button data-tab="food">查看餐饮安排</button></div>'
    );
  const key = transportMode + ":" + transportDirection,
    q =
      w.transport_queries?.[key] ||
      (w.transport?.kind === transportMode &&
      w.transport?.direction === transportDirection
        ? w.transport
        : null),
    items = q?.items || [];
  return (
    optional +
    `<div class="transport-picker"><div class="segmented"><button data-transport-mode="train" class="${transportMode === "train" ? "active" : "ghost"}">火车／高铁</button><button data-transport-mode="flight" class="${transportMode === "flight" ? "active" : "ghost"}">飞机</button></div><div class="segmented"><button data-transport-direction="outbound" class="${transportDirection === "outbound" ? "active" : "ghost"}">去程</button><button data-transport-direction="return" class="${transportDirection === "return" ? "active" : "ghost"}">返程</button></div><div class="transport-filter-row"><div class="transport-date"><label>${transportDirection === "return" ? "返程" : "去程"}日期<input id="transport-date" type="date" value="${esc(transportDates[transportDirection] || transportDate(transportDirection) || "")}"></label></div><div class="transport-time"><label>出发时段<input id="time-start" type="time" value="${esc(timeStart)}"></label><span>至</span><input id="time-end" type="time" value="${esc(timeEnd)}" aria-label="出发时段结束"></div></div>${transportMode === "train" ? `<label class="train-type-label">车型选择<select id="train-type" aria-label="车次类型"><option value="all" ${trainType === "all" ? "selected" : ""}>全部列车</option><option value="highspeed" ${trainType === "highspeed" ? "selected" : ""}>高铁</option><option value="regular" ${trainType === "regular" ? "selected" : ""}>动车／火车</option></select></label>` : ""}<div class="toolbar"><p>${transportDirection === "return" ? "返程" : "去程"} · ${esc(transportDirection === "return" ? w.requirements.city : w.requirements.origin || "出发地待定")} → ${esc(transportDirection === "return" ? w.requirements.origin || "出发地待定" : w.requirements.city || "目的地待定")}</p><button data-query-transport>查询班次</button></div></div><div class="transport-summary">${["selected_transport", "selected_return"].map((k, i) => `<div><small>${i ? "返程" : "去程"}</small>${w[k] ? `<strong>${esc(w[k].name)}</strong><span>${esc(w[k].departure)} · ${w[k].selection_status === "recommended" ? "推荐待确认" : "已选定"}</span>${candidateConflicts(w[k].id).map(conflictHTML).join("")}${w[k].selection_status === "recommended" ? `<button data-select="${esc(w[k].id)}">确认推荐</button>` : ""}` : "<span>待选择</span>"}</div>`).join("")}</div>${q ? `<div class="cards transport-results">${items.map(card).join("")}</div>${!items.length ? "<p>本次查询没有符合条件的结果，可调整时段或交通类型。</p>" : ""}<p class="panel-footnote">当前展示接口返回的一批结果。车次类型按返回车次筛选；余票为查询时快照。</p>` : "<p>选择类型与方向后查询班次，已选另一方向会保留。</p>"}${w.selected_transport && w.selected_return ? `<div class="panel-footer-actions"><button data-tab="food">查看餐饮安排</button>${w.dining_reviewed || w.meal_mode === "self" ? '<button class="ghost" data-action="plan">生成旅行计划书</button>' : ""}</div>` : ""}`
  );
}

function ticketsHTML(t) {
  const rows = t.items || [],
    groups = [
      ["admission", "含门票产品"],
      ["other", "其他产品 · 入园范围需核对"],
      ["addon", "附加体验、餐食与商品"],
    ];
  function row(x) {
    const hasDays = x.advanceBookDay != null && x.advanceBookDay !== "",
      hasHours = x.advanceBookHour != null && x.advanceBookHour !== "";
    const advance = [
      hasDays ? esc(x.advanceBookDay) + "天" : "",
      hasHours ? esc(x.advanceBookHour) + "小时" : "",
    ]
      .filter(Boolean)
      .join(" / ");
    const zeroAdvance =
      advance &&
      Number(x.advanceBookDay || 0) === 0 &&
      Number(x.advanceBookHour || 0) === 0;
    return `<article class="ticket-product"><small class="ticket-origin">${esc(t.source?.name || "来源未记录")}返回的产品资料</small><strong>${esc(x.resName || "未命名产品")}</strong>${x.scenicName ? `<p>产品所属景区：${esc(x.scenicName)}${t.candidate_name && t.candidate_name !== x.scenicName ? "；请核对是否覆盖所选景点“" + esc(t.candidate_name) + "”" : ""}</p>` : ""}<p><b>${x.startPrice != null ? "¥" + esc(x.startPrice) + " 起" : "价格未提供"}</b><span class="ticket-price-scope">供应商区间起价</span> · ${esc(x.personTypeName || "适用人群待核实")} · ${esc(x.ticketTypeName || "")}</p><p>最低价日期：${esc(x.departsDate || "未提供")}；${t.requested_date === String(x.departsDate || "").slice(0, 10) ? "仍需确认当天报价" : "不作为所选游玩日期的报价"}</p><p>销售区间：${esc(x.startDate || "未提供")}—${esc(x.endDate || "未提供")}${x.date_status === "outside_sales_window" ? '<strong class="sold-out"> · 所选日期不在销售区间内</strong>' : ""}</p>${x.lossName ? `<p>退改：${esc(x.lossName)}（具体规则待确认）</p>` : ""}${x.admissionVoucherDesc ? `<p>来源提供的入园凭证：${esc(x.admissionVoucherDesc)}</p>` : ""}${x.enterTypeName ? `<p>来源提供的入园方式：${esc(x.enterTypeName)}</p>` : ""}${advance ? `<p>供应商提前量字段：${advance}；${zeroAdvance ? "是否支持当天预订及截止时间仍需确认" : "具体截止时间需核对"}</p>` : ""}${x.commonAgeLimit ? `<p>年龄资料：${esc(x.commonAgeLimit.minAge ?? "未提供")}—${esc(x.commonAgeLimit.maxAge ?? "未提供")}岁，边界与证件要求需确认</p>` : ""}<small>预约名额：未提供${x.productId ? " · 产品 " + esc(x.productId) : ""}${x.resId ? " / 资源 " + esc(x.resId) : ""}</small></article>`;
  }
  return `<details open class="ticket-results"><summary>门票产品 · 游玩日期 ${esc(t.requested_date || "未确定")}</summary>${t.status === "query_failed" ? `<p class="sold-out">${esc(t.attempted_date || "本次日期")}查询失败，下列内容为之前的查询快照。</p>` : ""}${rows.length ? `<p class="ticket-price-status"><strong>${esc(t.requested_date || "当前")}所选日期报价尚未确认</strong> · 预约库存未提供。以下为${esc(t.source?.name || "查询来源")}返回的产品与区间起价，销售区间不代表当天可预订。</p>` : ""}${t.query_name && t.query_name !== t.candidate_name ? `<p>使用名称“${esc(t.query_name)}”查询；请核对产品是否覆盖所选景点。</p>` : ""}<p class="data-scope">${esc(t.note || "供应商返回区间起价，具体日期报价与预约名额待确认。")}</p>${
    rows.length
      ? groups
          .map(([key, title]) => {
            const items = rows.filter(
              (x) => (x.product_group || "other") === key,
            );
            return items.length
              ? key === "addon"
                ? `<details><summary>${title} · ${items.length}项</summary>${items.map(row).join("")}</details>`
                : `<h4>${title} · ${items.length}项</h4>${items.map(row).join("")}`
              : "";
          })
          .join("")
      : "未查到产品，不能据此断定免费、无票或关闭。"
  }${src(t.source)}</details>`;
}

function routeCostsHTML(r) {
  const own = workspace?.requirements.intercity_mode === "self_drive";
  const fare =
    r.mode === "driving"
      ? own
        ? `道路收费：${r.tolls != null ? "预估 ¥" + esc(r.tolls) : "待核实"}；油费与停车费待核实`
        : `打车预估：${r.taxi_cost != null ? "¥" + esc(r.taxi_cost) : "费用待查询"}；非实时叫车报价`
      : r.mode === "transit"
        ? `公交／地铁票价：${r.fare != null ? "参考 ¥" + esc(r.fare) : "待核实"}`
        : "步行无需车费";
  return `<p class="route-cost">${fare}</p>`;
}

function destinationHTML() {
  const items = workspace.destinations || [];

  if (!items.length)
    return `<div class="panel-intro"><h3>确定旅行方向</h3><p>推荐范围以已入库资料为准。可提供旅行偏好，或查看已有数据的目的地。</p><button data-action="discover_destinations">查看已有目的地</button></div>`;

  const detail = items.slice(0, 4);

  return `<div class="candidate-head"><div><h3>目的地推荐</h3><p>已有资料覆盖 ${items.length} 个城市 · 以下列出本轮比较的方向</p></div><button class="ghost" data-action="discover_destinations">更新推荐</button></div><p class="data-coverage-notice">未入库地区暂不提供推荐，请从已有资料的地区中选择。</p><div class="destination-cards">${detail.map((d) => `<article class="card destination-card" data-open-candidate="${esc(d.id)}" tabindex="0"><h3>${esc(d.name)}</h3><div class="destination-tags">${(d.tags || []).map((t) => `<span>${esc(t)}</span>`).join("")}</div><p>${esc(d.summary)}</p><p>已有代表景点：${(d.highlights || []).map(esc).join(" · ")}</p><button data-destination="${esc(d.id)}">选择目的地：${esc(d.name)}</button>${src(d.source)}</article>`).join("")}</div>${
    items.length > 4
      ? `<details class="covered-destinations"><summary>查看其他已有资料的地区（${items.length - 4} 个）</summary><div class="panel-footer-actions">${items
          .slice(4)
          .map(
            (d) =>
              `<button class="ghost" data-destination="${esc(d.id)}">${esc(d.name)}</button>`,
          )
          .join("")}</div></details>`
      : ""
  }`;
}
