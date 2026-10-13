// 旅行信息表单里的往返交通字段：出行方式 / 站点下拉 / 时间下拉（30 分钟一档）。
//
// 规则（见用户要求）：
//   * 出行方式四选一：火车 / 高铁 / 飞机 / 自驾
//   * 非自驾时，到达站、到达时间、返程站、返程时间必填
//   * 选自驾时，这几项在界面上置灰且不可填（保留可见，让用户知道它们存在）
//   * 时间按 30 分钟一档，共 48 档
//   * 站点选项按城市实时查询（火车站 / 机场），查询失败退化为可手动输入

const TRANSPORT_FIELDS = [
  "arrival_station",
  "arrival_time",
  "return_station",
  "return_time",
];

function isDriveVehicle(form) {
  return form.elements["intercity_vehicle"]?.value === "drive";
}

// 生成 00:00 / 00:30 / … / 23:30 共 48 档
function timeSlots() {
  const out = [];
  for (let h = 0; h < 24; h++)
    for (const m of [0, 30])
      out.push(
        String(h).padStart(2, "0") + ":" + String(m).padStart(2, "0"),
      );
  return out;
}

// 把某个 select 补全为时间下拉，并保留当前值（若不在档位内则加一项显示）
function fillTimes(form, name) {
  const el = form.elements[name];
  if (!el) return;
  const current = el.value;
  const head = el.querySelector("option[value='']");
  el.innerHTML = "";
  if (head) el.appendChild(head);
  else {
    const o = document.createElement("option");
    o.value = "";
    o.textContent = "请选择时间";
    el.appendChild(o);
  }
  for (const t of timeSlots()) {
    const o = document.createElement("option");
    o.value = t;
    o.textContent = t;
    el.appendChild(o);
  }
  setSelectValue(el, current);
}

// 设置 select 的值；若该值不在选项里（例如老数据的具体时刻），补一个选项
function setSelectValue(el, value) {
  const v = (value ?? "").toString();
  if (v && !Array.from(el.options).some((o) => o.value === v)) {
    const o = document.createElement("option");
    o.value = v;
    o.textContent = v + "（已填写）";
    el.appendChild(o);
  }
  el.value = v;
}

function stationKind(form) {
  const v = form.elements["intercity_vehicle"]?.value;
  if (v === "flight") return "flight";
  if (v === "train" || v === "highspeed") return "train";
  return null;
}

// 站点用 <input list=…> + <datalist>：既有下拉建议，又能自由输入，
// 查不到站点时不会把用户卡住。
async function loadStations(form, keepValues = true) {
  const kind = stationKind(form);
  const slots = [
    ["arrival_station", "arrival-station-options", "arrival"],
    ["return_station", "return-station-options", "return"],
  ];
  for (const [name, listId, which] of slots) {
    const input = form.elements[name];
    const list = document.getElementById(listId);
    if (!input || !list) continue;
    const kept = keepValues ? input.value : "";
    const city =
      which === "arrival"
        ? form.elements["city"]?.value?.trim()
        : form.elements["origin"]?.value?.trim() ||
          form.elements["city"]?.value?.trim();
    list.innerHTML = "";
    if (!kind || !city) {
      input.value = kept;
      continue;
    }
    let items = [];
    try {
      const r = await api(
        `/api/workspaces/${workspace.id}/stations?kind=${kind}&city=${encodeURIComponent(city)}`,
      );
      items = r.items || [];
    } catch {
      items = [];
    }
    for (const s of items) {
      const o = document.createElement("option");
      o.value = s.name;
      if (s.address) o.label = s.address;
      list.appendChild(o);
    }
    input.value = kept;
  }
}

// 自驾：置灰并禁用；非自驾：启用并标必填
function applyTransportState(form, { refreshStations = false } = {}) {
  const drive = isDriveVehicle(form);
  const kind = stationKind(form);
  for (const name of TRANSPORT_FIELDS) {
    const el = form.elements[name];
    if (!el) continue;
    el.disabled = drive;
    if (drive) {
      el.value = "";
      el.removeAttribute("required");
    } else {
      el.required = true;
    }
  }
  const note = form.querySelector("[data-transport-note]");
  if (note)
    note.textContent = drive
      ? "已选择自驾：到达站、返程站与时间无需填写，系统不按班次核对首尾日。"
      : "到达时间与返程时间为必填，系统据此核对抵达日与返程日的可用时间；选择自驾则无需填写。";
  // 站点清单在切换出行方式后必须重查（火车↔飞机是不同的清单）
  if (refreshStations) loadStations(form, true);
  return kind;
}

function initTransportFields() {
  const form = document.querySelector("#settings-form");
  if (!form) return;
  fillTimes(form, "arrival_time");
  fillTimes(form, "return_time");

  const vehicle = form.elements["intercity_vehicle"];
  if (vehicle)
    vehicle.addEventListener("change", () =>
      applyTransportState(form, { refreshStations: true }),
    );

  // 城市变化后站点清单要重查（目的地与出发城市都影响）
  for (const name of ["city", "origin"])
    form.elements[name]?.addEventListener("change", () =>
      applyTransportState(form, { refreshStations: true }),
    );
}

// 打开表单时按已有条件回填并同步启用状态
function syncTransportFields(form) {
  const r = (workspace && workspace.requirements) || {};
  const vehicle = form.elements["intercity_vehicle"];
  if (vehicle) {
    const fallback = r.intercity_mode === "self_drive" ? "drive" : "highspeed";
    vehicle.value = r.intercity_vehicle || fallback;
  }
  for (const name of TRANSPORT_FIELDS) {
    const el = form.elements[name];
    if (el && r[name] != null) el.value = r[name];
  }
  applyTransportState(form, { refreshStations: true });
}

// 提交前校验：非自驾时四项必填（用户选择的是强必填）
function transportProblem(form) {
  if (isDriveVehicle(form)) return "";
  const labels = {
    arrival_station: "到达站",
    arrival_time: "到达时间",
    return_station: "返程站",
    return_time: "返程时间",
  };
  const missing = TRANSPORT_FIELDS.filter(
    (n) => !String(form.elements[n]?.value || "").trim(),
  ).map((n) => labels[n]);
  return missing.length ? `请先填写：${missing.join("、")}` : "";
}
