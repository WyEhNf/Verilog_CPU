const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];

const ui = {
  config: null,
  params: {},
  test: "join03:accumulate",
  lastEvent: 0,
  polling: false,
  registers: Array(32).fill("00000000"),
  latestState: {},
  eventCount: 0,
  testsExpanded: false,
  running: false,
};

const stageNames = ["IDLE", "READ RS1", "READ RS2", "ISSUE", "EXEC", "LOAD", "STORE", "COMMIT"];
const registerAliases = ["zero", "ra", "sp", "gp", "tp", "t0", "t1", "t2", "s0", "s1", "a0", "a1", "a2", "a3", "a4", "a5", "a6", "a7", "s2", "s3", "s4", "s5", "s6", "s7", "s8", "s9", "s10", "s11", "t3", "t4", "t5", "t6"];

function hex(value, width = 8) {
  if (value === undefined || value === null || value === "") return "0x" + "0".repeat(width);
  if (typeof value === "number") return "0x" + (value >>> 0).toString(16).toUpperCase().padStart(width, "0").slice(-width);
  const cleaned = String(value).replace(/^0x/i, "").toUpperCase();
  return "0x" + cleaned.padStart(width, "0").slice(-width);
}

function bitActive(value) {
  if (typeof value === "number") return value !== 0;
  return value && value !== "0" && !/^0+$/.test(value);
}

function showToast(message) {
  const toast = $("#toast");
  toast.textContent = message;
  toast.classList.add("show");
  clearTimeout(showToast.timer);
  showToast.timer = setTimeout(() => toast.classList.remove("show"), 2600);
}

function setStatus(status, message) {
  const pill = $("#runStatus");
  pill.className = "status-pill " + status;
  pill.querySelector("span").textContent = message || ({
    idle: "等待启动", building: "正在构建", running: "仿真运行中",
    passed: "测试通过", failed: "测试失败", stopping: "正在停止", stopped: "已停止",
  }[status] || status);
  ui.running = ["building", "running", "stopping"].includes(status);
  $("#runButton").disabled = ui.running;
  $("#stopButton").disabled = !ui.running || status === "stopping";
  $("#connection").innerHTML = `<i></i> ${ui.running ? "仿真已连接" : "GUI 就绪"}`;
  $("#datapath").classList.toggle("flowing", status === "running");
}

function renderProfiles() {
  const select = $("#profileSelect");
  select.innerHTML = Object.entries(ui.config.profiles).map(([key, profile]) =>
    `<option value="${key}">${profile.label}</option>`).join("");
  select.addEventListener("change", () => applyProfile(select.value));
  applyProfile("area");
}

function applyProfile(name) {
  const profile = ui.config.profiles[name];
  if (!profile) return;
  ui.params = { ...profile.params };
  $("#profileSelect").value = name;
  $("#profileDescription").textContent = profile.description;
  Object.entries(ui.params).forEach(([key, value]) => {
    const field = document.querySelector(`[data-param="${key}"]`);
    if (field) field.value = value;
  });
  const badge = $("#areaBadge");
  if (profile.area) {
    badge.classList.remove("unknown");
    badge.innerHTML = `<span>ASAP7 最终面积</span><strong>${profile.area.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}</strong><small>µm²</small>`;
  } else {
    badge.classList.add("unknown");
    badge.innerHTML = `<span>面积数据</span><strong>需重新综合</strong><small></small>`;
  }
  updateBackendStatic();
}

function restoreCurrentConfiguration(current) {
  if (!current?.params) return;
  const match = Object.entries(ui.config.profiles).find(([, profile]) =>
    Object.keys(profile.params).every(key => Number(profile.params[key]) === Number(current.params[key])));
  if (match) {
    applyProfile(match[0]);
  } else {
    ui.params = { ...current.params };
    $("#profileSelect").value = "";
    $("#profileDescription").textContent = "当前运行的自定义参数配置";
    Object.entries(ui.params).forEach(([key, value]) => {
      const field = document.querySelector(`[data-param="${key}"]`);
      if (field) field.value = value;
    });
    $("#areaBadge").classList.add("unknown");
    $("#areaBadge").innerHTML = `<span>面积数据</span><strong>需重新综合</strong><small></small>`;
    updateBackendStatic();
  }
  if (current.test) ui.test = current.test;
}

function renderParameters() {
  const container = $("#parameterGrid");
  container.innerHTML = Object.entries(ui.config.parameters).map(([name, spec]) => {
    const control = spec.values
      ? `<select class="select" data-param="${name}">${spec.values.map(value => `<option value="${value}">${value}</option>`).join("")}</select>`
      : `<input type="number" min="${spec.min}" max="${spec.max}" data-param="${name}">`;
    return `<div class="parameter-item"><label title="${name}">${spec.label}</label>${control}</div>`;
  }).join("");
  container.addEventListener("change", event => {
    const name = event.target.dataset.param;
    if (!name) return;
    ui.params[name] = Number(event.target.value);
    $("#profileSelect").value = "";
    $("#profileDescription").textContent = "自定义参数配置";
    $("#areaBadge").classList.add("unknown");
    $("#areaBadge").innerHTML = `<span>面积数据</span><strong>需重新综合</strong><small></small>`;
    updateBackendStatic();
  });
}

function renderTests() {
  const featured = ui.config.tests.filter(test => test.suite === "核心演示");
  const others = ui.config.tests.filter(test => test.suite !== "核心演示");
  $("#testList").innerHTML = [...featured, ...others].map(test => `
    <div class="test-card ${test.id === ui.test ? "selected" : ""} ${test.suite !== "核心演示" ? "hidden-test" : ""}" data-test="${test.id}">
      <div><strong>${test.name}</strong><b>${test.arch.toUpperCase()}${test.long ? " · LONG" : ""}</b></div>
      <p>${test.description} · 返回 ${test.expected}</p>
    </div>`).join("");
  $("#testList").addEventListener("click", event => {
    const card = event.target.closest(".test-card");
    if (!card) return;
    ui.test = card.dataset.test;
    $$(".test-card").forEach(item => item.classList.toggle("selected", item === card));
    const test = ui.config.tests.find(item => item.id === ui.test);
    $("#metricExpected").textContent = `expected ${test.expected}`;
    if (test.long) showToast("这是长测试；建议将采样周期调大");
  });
  const first = ui.config.tests.find(test => test.id === ui.test);
  $("#metricExpected").textContent = `expected ${first.expected}`;
}

function renderRegisters() {
  $("#registers").innerHTML = ui.registers.map((value, index) => `
    <div class="reg" id="reg${index}" title="${registerAliases[index]}">
      <span>x${index} · ${registerAliases[index]}</span><strong>${hex(value)}</strong>
    </div>`).join("");
}

function updateBackendStatic() {
  const serial = Number(ui.params.SERIAL_BACKEND) === 1;
  $("#backendTitle").textContent = serial ? "SERIAL" : `${ui.params.BE_WIDTH}-W OOO`;
  $("#backendMode").textContent = serial ? "SERIAL" : `OOO ×${ui.params.BE_WIDTH}`;
  $("#serialView").classList.toggle("hidden", !serial);
  $("#oooView").classList.toggle("hidden", serial);
  if (!serial) {
    setupQueue("rob", ui.params.ROB_ENTRIES);
    setupQueue("rs", ui.params.RS_ENTRIES);
    setupQueue("lsq", ui.params.LSQ_ENTRIES);
    setupQueue("completion", ui.params.COMPLETION_DEPTH);
  }
}

function setupQueue(name, max) {
  $(`#${name}Progress`).max = max;
  $(`#${name}Text`).textContent = `0 / ${max}`;
}

function resetRuntime() {
  ui.lastEvent = 0;
  ui.registers.fill("00000000");
  ui.latestState = {};
  ui.eventCount = 0;
  renderRegisters();
  $("#timeline").innerHTML = `<div class="empty-state">等待第一条退休指令</div>`;
  $("#eventCount").textContent = "0 EVENTS";
  $("#metricCycles").textContent = "0";
  $("#metricInstret").textContent = "0";
  $("#metricIpc").textContent = "0.000";
  $("#metricPc").textContent = "0x00000000";
  $("#metricEpoch").textContent = "epoch 0";
  $("#metricReturn").textContent = "—";
  $("#console").textContent = "";
  $$(".unit, .memory-unit").forEach(unit => unit.classList.remove("active"));
}

async function startRun() {
  resetRuntime();
  setStatus("building", "正在准备");
  try {
    const response = await fetch("/api/run", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ test: ui.test, params: ui.params,
        trace_interval: Number($("#traceInterval").value),
        delay_ms: Number($("#delayMs").value) }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "无法启动仿真");
    ui.lastEvent = 0;
    pollEvents();
  } catch (error) {
    setStatus("failed", "启动失败");
    showToast(error.message);
    appendLog(error.message, "error");
  }
}

async function stopRun() {
  try { await fetch("/api/stop", { method: "POST" }); }
  catch (error) { showToast(error.message); }
}

async function pollEvents() {
  if (ui.polling) return;
  ui.polling = true;
  try {
    while (ui.running || ui.lastEvent === 0) {
      const response = await fetch(`/api/events?since=${ui.lastEvent}`, { cache: "no-store" });
      const data = await response.json();
      for (const event of data.events) {
        ui.lastEvent = Math.max(ui.lastEvent, event.id);
        handleEvent(event);
      }
      if (data.status) setStatus(data.status.status, undefined);
      if (!["building", "running", "stopping"].includes(data.status.status)) break;
    }
  } catch (error) {
    appendLog("GUI 通信错误: " + error.message, "error");
    setStatus("failed", "连接中断");
  } finally {
    ui.polling = false;
  }
}

function handleEvent(event) {
  switch (event.type) {
    case "status": setStatus(event.status, event.message); appendLog(event.message, event.status); break;
    case "state": updateState(event); break;
    case "commit": updateCommit(event); break;
    case "memory": updateMemory(event); break;
    case "redirect": updateRedirect(event); break;
    case "result": updateResult(event); break;
    case "meta": appendLog(`配置: FE${event.fe} BE${event.be} P${event.phys} ROB${event.rob} · ${event.serial ? "串行" : "乱序"}`, "build"); break;
    case "error": appendLog(event.message, "error"); showToast(event.message); break;
    case "log": appendLog(event.message, event.level); break;
  }
}

function updateState(state) {
  ui.latestState = state;
  const cycles = Number(state.cycle || 0), instret = Number(state.instret || 0);
  $("#metricCycles").textContent = cycles.toLocaleString();
  $("#metricInstret").textContent = instret.toLocaleString();
  $("#metricIpc").textContent = cycles ? (instret / cycles).toFixed(3) : "0.000";
  $("#metricPc").textContent = hex(state.pc);
  $("#metricEpoch").textContent = `epoch ${state.epoch || 0}`;
  $("#fetchDetail").textContent = `PC ${hex(state.pc)} · E${state.epoch || 0}`;
  $("#decodeDetail").textContent = `valid ${state.trace_valid ?? "0"} · ready ${state.trace_ready ?? "0"}`;
  $("#commitDetail").textContent = `${instret.toLocaleString()} retired`;
  activateUnit("fetch", bitActive(state.fetch_valid) || bitActive(state.if_req));
  activateUnit("decode", bitActive(state.trace_valid));
  activateUnit("memory", bitActive(state.d_req) || bitActive(state.d_resp));

  if (state.mode === "serial") updateSerial(state);
  else updateOoo(state);
}

function updateSerial(state) {
  const stage = Number(state.stage || 0);
  $("#backendDetail").textContent = stageNames[stage] || `stage ${stage}`;
  $("#executeDetail").textContent = state.mdu_busy ? "MDU response" : (stage === 4 ? "ALU active" : "idle");
  activateUnit("backend", stage !== 0);
  activateUnit("execute", stage >= 3 && stage <= 6);
  $$("#stageRail .stage").forEach((item, index) => item.classList.toggle("active", index === stage));
  $("#serialInst").textContent = hex(state.inst);
  $("#serialOp").textContent = String(state.op ?? "—");
  $("#serialRs1").textContent = `x${state.rs1 ?? "—"} / ${hex(state.src1)}`;
  $("#serialRs2").textContent = `x${state.rs2 ?? "—"} / ${hex(state.src2)}`;
  $("#serialRd").textContent = `x${state.rd ?? "—"} / ${hex(state.result)}`;
  $("#serialMdu").textContent = state.mdu_busy ? "完成有效" : "空闲";
}

function updateOoo(state) {
  $("#backendDetail").textContent = `ROB ${state.rob_occ || 0} · RS ${state.rs_occ || 0} · LSQ ${state.lsq_occ || 0}`;
  $("#executeDetail").textContent = bitActive(state.issue) ? `issue ${state.issue}` : "idle";
  activateUnit("backend", bitActive(state.dispatch) || Number(state.rob_occ) > 0);
  activateUnit("execute", bitActive(state.issue) || bitActive(state.mdu_busy));
  updateQueue("rob", state.rob_occ, ui.params.ROB_ENTRIES);
  updateQueue("rs", state.rs_occ, ui.params.RS_ENTRIES);
  updateQueue("lsq", state.lsq_occ, ui.params.LSQ_ENTRIES);
  updateQueue("completion", state.completion_occ, ui.params.COMPLETION_DEPTH);
  $("#robPointers").textContent = `head ${state.rob_head || 0} · tail ${state.rob_tail || 0}`;
  $("#freePhys").textContent = `free physical ${state.free_phys ?? "—"}`;
  signal("dispatchSignal", state.dispatch);
  signal("issueSignal", state.issue);
  signal("cdbSignal", state.cdb);
  signal("branchSignal", state.branch_pending);
  signal("mduSignal", state.mdu_issue || state.mdu_busy);
}

function updateQueue(name, value, max) {
  const number = Number(value || 0);
  $(`#${name}Progress`).value = number;
  $(`#${name}Text`).textContent = `${number} / ${max}`;
}

function signal(id, value) { $("#" + id).classList.toggle("active", bitActive(value)); }
function activateUnit(name, value) { document.querySelector(`[data-unit="${name}"]`)?.classList.toggle("active", Boolean(value)); }

function updateCommit(event) {
  activateUnit("commit", true);
  setTimeout(() => activateUnit("commit", false), 180);
  ui.eventCount += 1;
  $("#eventCount").textContent = `${ui.eventCount} EVENTS`;
  if (event.we && Number(event.rd) !== 0) {
    ui.registers[Number(event.rd)] = String(event.value);
    const reg = $(`#reg${event.rd}`);
    reg.querySelector("strong").textContent = hex(event.value);
    reg.classList.remove("changed");
    void reg.offsetWidth;
    reg.classList.add("changed");
  }
  const timeline = $("#timeline");
  timeline.querySelector(".empty-state")?.remove();
  const row = document.createElement("div");
  row.className = "timeline-row" + (event.store ? " store" : "");
  const write = event.store ? `MEM ${hex(event.store_addr)}` : (event.we ? `x${event.rd} ← ${hex(event.value)}` : "—");
  row.innerHTML = `<span>${event.cycle}</span><span>${hex(event.pc)}</span><span>${hex(event.inst)}</span><span class="write">${write}</span>`;
  timeline.prepend(row);
  while (timeline.children.length > 80) timeline.lastElementChild.remove();
}

function updateMemory(event) {
  activateUnit("memory", true);
  setTimeout(() => activateUnit("memory", false), 260);
  const phase = event.phase === "request" ? (event.store ? "STORE" : "LOAD") : event.phase;
  $("#memoryDetail").textContent = `${phase} ${event.addr ? hex(event.addr) : ""}`;
  if (event.phase === "request") appendLog(`[${event.cycle}] MEM ${phase} ${hex(event.addr)}`, "sim");
}

function updateRedirect(event) {
  appendLog(`[${event.cycle}] REDIRECT → ${hex(event.pc)} epoch ${event.epoch}`, "sim");
  const unit = document.querySelector('[data-unit="fetch"]');
  unit.classList.add("active");
  setTimeout(() => unit.classList.remove("active"), 350);
}

function updateResult(event) {
  $("#metricCycles").textContent = Number(event.cycles || 0).toLocaleString();
  $("#metricInstret").textContent = Number(event.instret || 0).toLocaleString();
  $("#metricReturn").textContent = String(event.return ?? "—");
  $("#metricExpected").textContent = `expected ${event.expected}`;
  setStatus(event.status, event.status === "passed" ? "测试通过" : `失败 · ${event.reason}`);
  appendLog(`${event.status === "passed" ? "PASS" : "FAIL"}: return=${event.return}, expected=${event.expected}, cycles=${event.cycles}, instret=${event.instret}`, event.status === "passed" ? "pass" : "error");
  showToast(event.status === "passed" ? "测试通过 ✓" : `测试失败：${event.reason}`);
}

function appendLog(message, level = "") {
  if (!message) return;
  const consoleNode = $("#console");
  const line = document.createElement("span");
  line.className = level === "error" || level === "failed" ? "log-error" :
                   level === "pass" || level === "passed" ? "log-pass" :
                   level === "build" || level === "building" ? "log-build" : "";
  line.textContent = message + "\n";
  consoleNode.appendChild(line);
  while (consoleNode.childNodes.length > 260) consoleNode.removeChild(consoleNode.firstChild);
  consoleNode.scrollTop = consoleNode.scrollHeight;
}

async function initialize() {
  try {
    const response = await fetch("/api/config", { cache: "no-store" });
    ui.config = await response.json();
    renderParameters();
    renderProfiles();
    restoreCurrentConfiguration(ui.config.status.current);
    renderTests();
    renderRegisters();
    $("#stageRail").innerHTML = stageNames.map(name => `<div class="stage">${name}</div>`).join("");
    setStatus(ui.config.status.status || "idle");
    if (ui.config.status.last_event_id > 0) pollEvents();
  } catch (error) {
    setStatus("failed", "服务不可用");
    showToast("无法连接本地 GUI 服务");
  }
}

$("#runButton").addEventListener("click", startRun);
$("#stopButton").addEventListener("click", stopRun);
$("#clearLog").addEventListener("click", () => $("#console").textContent = "");
$("#resetView").addEventListener("click", () => applyProfile("area"));
$("#toggleParams").addEventListener("click", event => {
  const grid = $("#parameterGrid");
  grid.classList.toggle("collapsed");
  event.target.textContent = grid.classList.contains("collapsed") ? "展开" : "收起";
});
$("#toggleTests").addEventListener("click", event => {
  ui.testsExpanded = !ui.testsExpanded;
  $$(".hidden-test").forEach(card => card.style.display = ui.testsExpanded ? "block" : "none");
  event.target.textContent = ui.testsExpanded ? "仅核心" : "全部测试";
});

initialize();
