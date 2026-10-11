// core/api.js
async function api(url, opts = {}) {
  const method = (opts.method || "GET").toUpperCase(),
    headers = { ...(opts.headers || {}) };
  if (method !== "GET") {
    headers["Content-Type"] = "application/json";
    if (csrfToken) headers["X-CSRF-Token"] = csrfToken;
  }
  const r = await fetch(url, { ...opts, headers, credentials: "same-origin" });
  if (!r.ok) {
    let d;
    try {
      d = await r.json();
    } catch {}
    if (r.status === 401 && currentUser)
      showGate("登录已过期，请重新登录后继续。");
    const e = new Error(d?.detail || `请求失败 ${r.status}`);
    e.code = r.status;
    throw e;
  }
  return r.json();
}

function error(msg) {
  $("#error").hidden = !msg;
  $("#error").textContent = msg || "";
}

function switchTab(next, focusId = null) {
  if (!sceneNames[next]) return;
  tab = next;
  render();
  const card = focusId
    ? [...document.querySelectorAll("[data-candidate]")].find(
        (x) => x.dataset.candidate === focusId,
      )
    : null;
  $("#content").scrollTo({
    top: card ? Math.max(0, card.offsetTop - $("#content").offsetTop) : 0,
    behavior: "smooth",
  });
  const active = $(`.tabs [data-tab="${next}"]`);
  active?.scrollIntoView({
    behavior: "smooth",
    block: "nearest",
    inline: "nearest",
  });
  if (innerWidth <= 900)
    $(".workspace").scrollIntoView({ behavior: "smooth", block: "start" });
  if (card) {
    card.classList.add("just-updated");
    setTimeout(() => card.classList.remove("just-updated"), 2400);
  }
}

async function action(name, args = {}, text = "") {
  // 记录动作前最早未选的宿夜：选定酒店后后端会把它从 unassigned 移除，
  // 事后再取首位会指向下一晚，导致折叠到错的那一晚。
  pendingSettledNight = (workspace?.stay_plan?.unassigned || [])[0] || null;
  // 每次动作都重置：只有刚选定/刚查询的那一晚保持展开，已选的其它夜晚不该一直展开。
  stayOpenDate = "";
  if (busy || !workspace || workspace.archived) return;
  const wid = workspace.id,
    epoch = tripEpoch;
  liveReply = "";
  liveSteps = [];
  const p = workspace.catalog?.[args.id],
    view =
      name === "complete_spots" && Number(workspace.requirements.days) === 1
        ? "transport"
        : (name === "place_detail" ? args.view || tab : actionViews[name]) ||
          (name === "select"
            ? {
                spot: "spot",
                hotel: "hotel",
                train: "transport",
                flight: "transport",
                food: "food",
              }[p?.kind]
            : null);
  jobUI = {
    action: name,
    view,
    status: "loading",
    title:
      name === "chat"
        ? "正在理解你的想法"
        : name === "select"
          ? "正在保存你的选择"
          : `正在处理${sceneNames[view] || "旅行条件"}`,
    message:
      name === "chat"
        ? "识别需求后，工作台会切换到对应内容。"
        : "结果更新后，可查看推荐与安排建议。",
  };
  if (name === "train" || name === "flight") {
    transportMode = name;
    transportDirection = args.direction || "outbound";
    args = {
      ...args,
      train_type: trainType,
      time_start: timeStart || undefined,
      time_end: timeEnd || undefined,
      departure_date:
        transportDates[transportDirection] || transportDate(transportDirection),
    };
  }
  if (view) tab = view;
  setBusy(true);
  render();
  error("");
  $("#reconnect-task").hidden = true;
  $("#progress-text").textContent = jobUI.title;
  try {
    const { job_id } = await api(`/api/workspaces/${wid}/actions`, {
      method: "POST",
      body: JSON.stringify({
        revision: workspace.revision,
        action: name,
        args,
        text,
        request_id: crypto.randomUUID(),
      }),
    });
    if (epoch !== tripEpoch) return;
    if (text) {
      workspace.messages.push({ role: "user", content: text });
      render();
    }
    await pollJob(wid, job_id, epoch, name, args);
  } catch (e) {
    if (epoch === tripEpoch) {
      error(e.message);
      $("#reconnect-task").hidden = false;
      if (text) $("#message").value = text;
    }
  } finally {
    if (epoch === tripEpoch) {
      jobUI = null;
      liveReply = "";
      liveSteps = [];
      setBusy(false);
      render();
    }
  }
}

async function pollJob(wid, jid, epoch = tripEpoch, name = "", args = {}) {
  runningJobId = jid;
  setBusy(true);
  let followedView = jobUI?.view || null;
  try {
    const streamed = await readEvents(jid, epoch);
    if (streamed) {
      finishJob(streamed, name, args);
      return;
    }
    for (let i = 0; i < 360; i++) {
      await new Promise((r) => setTimeout(r, 750));
      if (epoch !== tripEpoch || workspace?.id !== wid) return;
      const j = await api("/api/jobs/" + jid);
      if (epoch !== tripEpoch) return;
      $("#progress-text").textContent = j.progress;
      if (j.status === "running" && j.ui?.status) {
        applyWorkspacePreview(j.ui?.workspace_preview);
        jobUI = { ...j.ui, message: j.progress };
        if (sceneNames[j.ui.view] && j.ui.view !== followedView) {
          followedView = j.ui.view;
          switchTab(j.ui.view);
        } else render();
      }
      if (j.status !== "running") {
        finishJob(j, name, args);
        return;
      }
    }
    error("任务等待较长，请点击恢复任务进度查看最新状态。");
    $("#reconnect-task").hidden = false;
  } catch (e) {
    if (epoch === tripEpoch) {
      error(e.message);
      $("#reconnect-task").hidden = false;
    }
  } finally {
    if (epoch === tripEpoch) {
      jobUI = null;
      liveReply = "";
      liveSteps = [];
      setBusy(false);
      render();
    }
  }
}

async function readEvents(jid, epoch) {
  const controller = new AbortController();
  const r = await fetch("/api/jobs/" + jid + "/events", {
    credentials: "same-origin",
    signal: controller.signal,
  });
  if (!r.ok || !r.headers.get("content-type")?.includes("text/event-stream")) {
    controller.abort();
    return null;
  }
  const reader = r.body.getReader(),
    decoder = new TextDecoder();
  let buffer = "";
  try {
    while (true) {
      if (epoch !== tripEpoch) {
        controller.abort();
        return null;
      }
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder
        .decode(value, { stream: true })
        .replaceAll("\r\n", "\n");
      let pos;
      while ((pos = buffer.indexOf("\n\n")) >= 0) {
        const frame = buffer.slice(0, pos);
        buffer = buffer.slice(pos + 2);
        const type = frame
          .split("\n")
          .find((l) => l.startsWith("event:"))
          ?.slice(6)
          .trim();
        const raw = frame
          .split("\n")
          .filter((l) => l.startsWith("data:"))
          .map((l) => l.slice(5).trim())
          .join("\n");
        if (!raw) continue;
        const data = JSON.parse(raw);
        if (epoch !== tripEpoch) return null;
        if (type === "delta") {
          liveReply += data.text;
          renderLive();
        }
        if (type === "replace") {
          liveReply = data.text;
          renderLive();
        }
        if (type === "progress") {
          applyWorkspacePreview(data.ui?.workspace_preview);
          await applyQueryControls(data.ui?.controls, true, epoch);
          liveSteps = data.ui?.process_steps || [];
          jobUI = data.ui;
          $("#progress-text").textContent = "正在处理";
          if (sceneNames[data.ui?.view] && tab !== data.ui.view) {
            tab = data.ui.view;
            render();
          }
          renderLive();
        }
        if (type === "done") return data;
      }
    }
    return null;
  } finally {
    reader.cancel().catch(() => {});
    controller.abort();
  }
}

function applyWorkspacePreview(preview) {
  if (!preview || !busy || preview.id !== workspace?.id) return;
  workspace.catalog = { ...workspace.catalog, ...(preview.catalog || {}) };
  for (const key of ["spot_search", "spot_page", "hotel_query", "food_query"])
    if (preview[key]) workspace[key] = preview[key];
  if (typeof preview.discovery_mode === "boolean")
    workspace.discovery_mode = preview.discovery_mode;
  render();
}

function applyJobResult(j, name, args) {
  applyQueryControls(j.ui?.controls, false);
  runningJobId = null;
  jobUI = null;
  liveReply = "";
  liveSteps = [];
  setBusy(false);
  if (!j.workspace) return;
  workspace = j.workspace;
  const performed =
    (name || j.action) === "chat" ? workspace.last_action : name || j.action;
  if (["train", "flight"].includes(performed) && workspace.transport) {
    transportMode = performed;
    transportDirection = workspace.transport.direction || "outbound";
  }
  const pickedHotel =
    performed === "select" && workspace.catalog[args.id]?.kind === "hotel"
      ? args.id
      : null;
  // 刚选定的那一晚：逐晚点选时带 stay_date；从主列表点选时，后端会落到最早未选的那一晚，因此用 unassigned 的首位反推。
  const justSettled = !pickedHotel
    ? ""
    : args.stay_date || pendingSettledNight || "";
  if (performed === "hotel_detail" || pickedHotel)
    detailOpenId = pickedHotel || args.id || j.ui?.focus_id;
  // 折叠状态必须在 render() 之前定好：选好某一晚就收起该晚，刚查过某一晚则保持展开。
  // 放到 render() 之后再改，等于改了状态却没重画。选房型（select_room）之后也会重画，
  // 所以按"这次是否真的给某晚定好了酒店"来判断，而不是只看动作名。
  // 折叠只影响对应那一晚：未选夜晚展开、已选夜晚折叠、刚选定那一晚强制折叠，
  // 不把其它夜晚一起收起（此前清空 stayOpenDate 会连带折叠所有夜晚）。
  settledNight = pickedHotel ? justSettled : "";
  if (settledNight) stayOpenDate = settledNight;
  else if (performed === "search_hotels" && args.stay_date)
    stayOpenDate = args.stay_date;
  const view = j.ui?.view || actionViews[performed];
  if (sceneNames[view] && tab !== view) switchTab(view);
  else render();
  if (j.status === "completed" && workspace.feedback?.id === j.id)
    toast(workspace.feedback.text);
  else if (
    j.status === "completed" &&
    ["search_spots", "search_hotels", "weather", "train", "flight"].includes(
      performed,
    )
  )
    toast("查询结果已更新，可在右侧查看");
  if (j.status === "completed" && performed === "select") {
    const picked = workspace.catalog[args.id];
    if (
      picked &&
      ["train", "flight"].includes(picked.kind) &&
      picked.direction !== "return" &&
      (!workspace.selected_return ||
        workspace.selected_return.selection_status === "recommended")
    )
      $("#return-dialog").showModal();
  }
  if (j.ui?.suggested_view && j.status === "completed") {
    switchTab(j.ui.suggested_view);
    toast(workspace.next_step?.message || "往返班次已确认。");
    if (j.ui.suggested_view === "food") {
      const slot = nextMealSlot();
      if (slot) {
        mealDate = slot.date;
        mealPeriod = slot.period;
        render();
        const epoch = tripEpoch,
          wid = workspace.id;
        setTimeout(() => {
          if (epoch === tripEpoch && workspace.id === wid && !busy)
            action("search_foods", {
              meal_date: slot.date,
              meal_period: slot.period,
            });
        }, 120);
      }
    }
  } else if (
    ["train", "flight"].includes(performed) &&
    j.status === "completed"
  ) {
    scrollToResults();
  }
  pickedHotelOpen = null;
  if (j.error) error(j.error);
}
