// app.js
function link(url, label) {
  try {
    const u = new URL(url);
    if (u.protocol !== "https:" && u.protocol !== "http:") return esc(label);
    return `<a href="${esc(u.href)}" target="_blank" rel="noopener noreferrer">${esc(label)}</a>`;
  } catch {
    return esc(label);
  }
}

function src(s) {
  return s
    ? `<details class="source"><summary>${esc(s.name)} · 查询依据</summary>${link(s.url, "查看数据来源 ↗")}<br>查询时间：${esc(s.queried_at?.replace("T", " "))}<br>${esc(s.kind || "查询事实")}</details>`
    : "";
}

function setTaskBusy(v) {
  busy = v;
  $("#progress").hidden = !v;
  document
    .querySelectorAll(
      "#application button:not([data-tab]):not(#history-toggle):not(#conversation-history):not(#cancel-task):not(#auto-selection-stop):not(#restore-trip):not([data-info]):not(#feedback-button):not(#selected-button):not(#expand-workbench):not(#sources-button):not(#map-button)",
    )
    .forEach((b) => {
      if (!disabledBeforeBusy.has(b)) disabledBeforeBusy.set(b, b.disabled);
      b.disabled = v || !!workspace?.archived || disabledBeforeBusy.get(b);
    });
  $("#message").disabled = !!workspace?.archived;
  $("#cancel-task").disabled = !v;
}

document.addEventListener("click", async (e) => {
  const b = e.target.closest("button");
  if (!b) return;
  if (b.dataset.tripTransport) {
    await action("transport_arrangement", { mode: b.dataset.tripTransport });
    return;
  }
  if (b.dataset.transportMode) {
    transportMode = b.dataset.transportMode;
    render();
    return;
  }
  if (b.dataset.transportDirection) {
    transportDirection = b.dataset.transportDirection;
    render();
    return;
  }
  if (b.dataset.returnMode) {
    $("#return-dialog").close();
    transportMode = b.dataset.returnMode;
    transportDirection = "return";
    switchTab("transport");
    if (!workspace.transport_queries?.[transportMode + ":return"])
      await action(transportMode, { direction: "return" });
    return;
  }
  if (b.hasAttribute("data-query-transport")) {
    await action(transportMode, { direction: transportDirection });
    return;
  }
  if (b.dataset.room) {
    await action("select_room", { id: b.dataset.room });
    return;
  }
  if (b.dataset.editField) {
    $("#conditions").click();
    $("#settings-form").elements[b.dataset.editField]?.focus();
    return;
  }
  if (b.dataset.destination) {
    await action("choose_destination", { id: b.dataset.destination });
    return;
  }
  if (b.dataset.destinationPage) {
    destinationPage = Number(b.dataset.destinationPage);
    render();
    $("#content").scrollTo({ top: 0, behavior: "smooth" });
    return;
  }
  if (b.dataset.spotsPage) {
    await action("spots_page", { page: Number(b.dataset.spotsPage) });
    return;
  }
  if (b.hasAttribute("data-more-spots")) {
    await action("search_spots", { expand_spots: true });
    return;
  }
  if (b.hasAttribute("data-replace-spots")) {
    await action("search_spots", { reject_current: true });
    return;
  }
  if (b.dataset.dismiss) {
    await action("dismiss_spot", { id: b.dataset.dismiss });
    return;
  }
  if (b.hasAttribute("data-open-settings")) {
    $("#conditions").click();
    return;
  }
  if (b.dataset.tab) {
    switchTab(b.dataset.tab);
    return;
  }
  if (b.dataset.action) {
    const row = b.closest(".stay-row");
    // 按钮自己可以带 data-stay-date（逐晚的"查这晚"），它比所在行更精确，
    // 因此优先取它；否则退回所在"住宿晚"行。
    // 此前只从行上取，导致点了某一晚的"查这晚"却按行日期去查，
    // 界面看起来就是"这一晚点了没反应"。
    const stayDate = b.dataset.stayDate || row?.dataset.stayDate;
    const stayArgs = stayDate ? { stay_date: stayDate } : {};
    if (stayArgs.stay_date && b.dataset.action === "search_hotels")
      stayOpenDate = stayArgs.stay_date;
    await action(b.dataset.action, {
      ...stayArgs,
      ...(b.dataset.direction ? { direction: b.dataset.direction } : {}),
      ...(b.dataset.preferenceMode
        ? { preference_mode: b.dataset.preferenceMode }
        : {}),
    });
    return;
  }
  if (b.hasAttribute("data-search-foods")) {
    await action("search_foods", {
      meal_date: mealDate || workspace.requirements.start_date,
      meal_period: mealPeriod,
      anchor_id: document.querySelector("#food-anchor")?.value || undefined,
    });
    return;
  }
  if (b.dataset.food) {
    await action("meal_choice", {
      food_id: b.dataset.food,
      meal_date: mealDate || workspace.requirements.start_date,
      meal_period: mealPeriod,
      meal_mode: "chosen",
    });
    return;
  }
  if (b.hasAttribute("data-meal-remove")) {
    await action("meal_choice", {
      meal_date: mealDate || workspace.requirements.start_date,
      meal_period: mealPeriod,
      mode: "remove",
    });
    return;
  }
  if (b.hasAttribute("data-self-meal")) {
    await action("meal_choice", {
      meal_date: mealDate || workspace.requirements.start_date,
      meal_period: mealPeriod,
      meal_mode: "self",
    });
    return;
  }
  if (b.hasAttribute("data-self-all-meals")) {
    await action("meal_choice", { meal_mode: "self" });
    return;
  }
  if (b.dataset.select) {
    const picked = workspace.catalog[b.dataset.select],
      old =
        picked && ["train", "flight"].includes(picked.kind)
          ? workspace[
              picked.direction === "return"
                ? "selected_return"
                : "selected_transport"
            ]
          : null;
    if (old && old.id !== picked.id) {
      replaceTarget = picked.id;
      $("#replace-text").textContent =
        `该方向已选 ${old.name}，是否替换为 ${picked.name}？将只保留一个班次。`;
      $("#replace-dialog").showModal();
      return;
    }
    // 住宿候选若位于某个"住宿晚"行内，点选只改那一晚；否则作为主住宿覆盖未指定的夜晚。
    const stayRow = b.closest && b.closest(".stay-row");
    const stayArg =
      picked && picked.kind === "hotel" && stayRow && stayRow.dataset.stayDate
        ? { stay_date: stayRow.dataset.stayDate }
        : {};
    await action("select", { id: b.dataset.select, ...stayArg });
    return;
  }
  if (b.dataset.detail) {
    await action("hotel_detail", { id: b.dataset.detail });
    return;
  }
  if (b.dataset.ticket) {
    const input = $("#candidate-dialog [data-ticket-date]");
    await action("ticket", {
      id: b.dataset.ticket,
      visit_date: input?.value || undefined,
    });
    return;
  }
  if (b.dataset.placeDetail) {
    await action("place_detail", { id: b.dataset.placeDetail, view: tab });
    return;
  }
  if (b.id === "print") {
    tab = "plan";
    render();
    window.print();
  }
});

$("#chat-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const t = $("#message").value.trim();
  if (!t || busy) return;
  $("#message").value = "";
  sessionStorage.removeItem(draftKey(workspace.id));
  await action("chat", {}, t);
});

$("#message").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {
    e.preventDefault();
    $("#chat-form").requestSubmit();
  }
});

$("#quick-setup").onclick = () => $("#conditions").click();

$("#conditions").onclick = () => {
  $("#settings-form").reset();
  for (const [k, v] of Object.entries(workspace.requirements)) {
    const el = $("#settings-form").elements[k];
    if (el) el.value = Array.isArray(v) ? v.join(",") : (v ?? "");
  }
  $("#settings").showModal();
};

$("#close-settings").onclick = () => $("#settings").close();

$("#settings-form").onsubmit = async (e) => {
  e.preventDefault();
  const patch = {};
  for (const [k, v] of new FormData(e.target))
    if (v.trim()) {
      patch[k] = [
        "days",
        "adults",
        "children",
        "rooms",
        "budget",
        "intercity_ticket_cost",
      ].includes(k)
        ? Number(v)
        : k === "child_ages"
          ? v.split(/[,，]/).map((x) => Number(x.trim()))
          : v;
    }
  $("#settings").close();
  await action("requirements", { patch });
};

$("#new").onclick = newTrip;

$("#expand-workbench").onclick = () => setWorkbenchExpanded(!workbenchExpanded);

$("#workbench-shade").onclick = () => setWorkbenchExpanded(false);

document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && workbenchExpanded) setWorkbenchExpanded(false);
});

$("#selected-button").onclick = () => {
  $("#selected-content").innerHTML = selectionHTML();
  $("#selected-dialog").showModal();
};

$("#confirm-replace").onclick = async () => {
  const id = replaceTarget;
  replaceTarget = null;
  $("#replace-dialog").close();
  await action("select", { id, replace: true });
};

document.addEventListener("change", (e) => {
  if (e.target.id === "transport-date")
    transportDates[transportDirection] = e.target.value;
  if (e.target.id === "food-anchor") foodAnchor = e.target.value;
  if (e.target.id === "meal-date") {
    mealDate = e.target.value;
    render();
  }
  if (e.target.id === "meal-period") {
    mealPeriod = e.target.value;
    render();
  }
  if (e.target.id === "time-start") timeStart = e.target.value;
  if (e.target.id === "time-end") timeEnd = e.target.value;
  if (e.target.id === "train-type") {
    trainType = e.target.value;
    if (!busy) action(transportMode, { direction: transportDirection });
  }
});

for (const id of [
  "selected-dialog",
  "replace-dialog",
  "return-dialog",
  "settings",
])
  $("#" + id).addEventListener("click", (e) => {
    const d = e.currentTarget,
      r = d.getBoundingClientRect();
    if (
      e.target === d &&
      (e.clientX < r.left ||
        e.clientX > r.right ||
        e.clientY < r.top ||
        e.clientY > r.bottom)
    )
      d.close();
  });

// 返程出发站默认同到达站：只是【减少输入】，不替用户做决定。
// 用户若从别处返程，改这一栏即可；这里只在用户从未动过它时才预填。
(() => {
  const form = $("#settings-form");
  if (!form) return;
  const arrival = form.elements["arrival_station"];
  const back = form.elements["return_station"];
  if (!arrival || !back) return;
  back.addEventListener("input", () => {
    back.dataset.touched = "1";
  });
  arrival.addEventListener("blur", () => {
    const value = (arrival.value || "").trim();
    if (value && !back.dataset.touched && !(back.value || "").trim())
      back.value = value;
  });
})();

document.addEventListener("DOMContentLoaded", bootAccount);

window.addEventListener("beforeprint", () => {
  printSources = [...document.querySelectorAll(".book details.source")].filter(
    (d) => !d.open,
  );
  printSources.forEach((d) => (d.open = true));
});

window.addEventListener("afterprint", () => {
  printSources.forEach((d) => (d.open = false));
  printSources = [];
});
