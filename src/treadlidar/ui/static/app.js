/* TreadLidar desktop UI - core: DOM helpers, API, state, shell (rail / top bar / status bar), shared widgets. */
"use strict";
(function (G) {
  const SVG = (d, extra) => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${d}</svg>`;
  const ICON = {
    folder: SVG('<path d="M3 7a2 2 0 0 1 2-2h4l2 2.5h8a2 2 0 0 1 2 2V17a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>'),
    file: SVG('<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/>'),
    cloud: SVG('<circle cx="6" cy="8" r="1.3"/><circle cx="12" cy="6" r="1.3"/><circle cx="18" cy="9" r="1.3"/><circle cx="9" cy="13" r="1.3"/><circle cx="15" cy="14" r="1.3"/><circle cx="7" cy="18" r="1.3"/><circle cx="13" cy="19" r="1.3"/><circle cx="19" cy="18" r="1.3"/>'),
    play: SVG('<path d="M7 4.5v15l12-7.5z" fill="currentColor"/>'),
    check: SVG('<path d="M5 12.5l4.5 4.5L19 7.5"/>'),
    alert: SVG('<path d="M12 3.5l9.5 16.5h-19z"/><path d="M12 10v4.5M12 17.4v.1"/>'),
    info: SVG('<circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 7.6v.1"/>'),
    cube: SVG('<path d="M12 3l8 4.5v9L12 21l-8-4.5v-9z"/><path d="M12 12l8-4.5M12 12L4 7.5M12 12v9"/>'),
    layers: SVG('<path d="M12 3l9 5-9 5-9-5z"/><path d="M3 12.5l9 5 9-5M3 16.5l9 5 9-5"/>'),
    ruler: SVG('<path d="M3 17L17 3l4 4L7 21z"/><path d="M7.5 12.5l2 2M10.5 9.5l2 2M13.5 6.5l2 2"/>'),
    target: SVG('<circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3"/>'),
    region: SVG('<rect x="4" y="5" width="16" height="14" rx="1.5" stroke-dasharray="3 2.5"/>'),
    pan: SVG('<path d="M12 3v18M3 12h18M12 3l-2.5 2.5M12 3l2.5 2.5M12 21l-2.5-2.5M12 21l2.5-2.5M3 12l2.5-2.5M3 12l2.5 2.5M21 12l-2.5-2.5M21 12l-2.5 2.5"/>'),
    gauge: SVG('<path d="M4 17a8 8 0 1 1 16 0"/><path d="M12 17l4-6"/>'),
    download: SVG('<path d="M12 4v11M7.5 11l4.5 4.5 4.5-4.5M5 19.5h14"/>'),
    upload: SVG('<path d="M12 15V4M7.5 8L12 3.5 16.5 8M5 19.5h14"/>'),
    trash: SVG('<path d="M4 7h16M9 7V4.5h6V7M6.5 7l1 13h9l1-13"/>'),
    plus: SVG('<path d="M12 5v14M5 12h14"/>'),
    sun: SVG('<circle cx="12" cy="12" r="4"/><path d="M12 2.5v2.5M12 19v2.5M2.5 12H5M19 12h2.5M5.3 5.3l1.8 1.8M16.9 16.9l1.8 1.8M5.3 18.7l1.8-1.8M16.9 7.1l1.8-1.8"/>'),
    moon: SVG('<path d="M20 14.5A8 8 0 0 1 9.5 4 8 8 0 1 0 20 14.5z"/>'),
    help: SVG('<circle cx="12" cy="12" r="9"/><path d="M9.5 9.5a2.5 2.5 0 1 1 3.6 2.2c-.7.4-1.1.9-1.1 1.8M12 16.8v.1"/>'),
    lock: SVG('<rect x="5" y="11" width="14" height="9" rx="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/>'),
    ring: SVG('<circle cx="12" cy="12" r="8.5"/><circle cx="12" cy="12" r="4.5"/>'),
    refresh: SVG('<path d="M20 11a8 8 0 0 0-14-4.5L4 9M4 5v4h4M4 13a8 8 0 0 0 14 4.5L20 15M20 19v-4h-4"/>'),
    focus: SVG('<path d="M4 9V5h4M20 9V5h-4M4 15v4h4M20 15v4h-4"/>'),
    link: SVG('<path d="M10 14a4.5 4.5 0 0 0 6.4 0l3-3a4.5 4.5 0 0 0-6.4-6.4l-1 1M14 10a4.5 4.5 0 0 0-6.4 0l-3 3a4.5 4.5 0 0 0 6.4 6.4l1-1"/>'),
    x: SVG('<path d="M6 6l12 12M18 6L6 18"/>'),
    chevron: SVG('<path d="M9 6l6 6-6 6"/>'),
    up: SVG('<path d="M12 19V6M6.5 11.5L12 6l5.5 5.5"/>'),
    sliders: SVG('<path d="M4 7h9M17 7h3M4 17h3M11 17h9"/><circle cx="15" cy="7" r="2"/><circle cx="9" cy="17" r="2"/>'),
    copy: SVG('<rect x="8" y="8" width="11" height="12" rx="2"/><path d="M5 15V6a2 2 0 0 1 2-2h8"/>'),
    zip: SVG('<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5M10 11h2M10 14h2M10 17h2"/>'),
  };

  /* ---------- tiny DOM helper ---------- */
  function h(tag, attrs, ...kids) {
    const el = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (v == null || v === false) continue;
      if (k === "class") el.className = v; else if (k === "style" && typeof v === "object") Object.assign(el.style, v);
      else if (k.startsWith("on") && typeof v === "function") el.addEventListener(k.slice(2).toLowerCase(), v);
      else if (k === "html") el.innerHTML = v; else if (k === "value") el.value = v; else if (k === "checked") el.checked = !!v;
      else if (k === "disabled") el.disabled = !!v; else el.setAttribute(k, v === true ? "" : v);
    }
    const add = (c) => { if (c == null || c === false) return; if (Array.isArray(c)) c.forEach(add); else el.append(c.nodeType ? c : document.createTextNode(String(c))); };
    kids.forEach(add); return el;
  }
  const ico = (n, cls) => h("span", { class: cls || "", html: ICON[n] || "", style: { display: "inline-flex" } });
  const $ = (sel, root) => (root || document).querySelector(sel);
  const fmt = (v, d = 2) => (v == null || !isFinite(v) ? "–" : (+v).toFixed(d));
  const fmtInt = (v) => (v == null ? "–" : Number(v).toLocaleString("en-US"));
  const fmtSize = (b) => (b < 1024 ? b + " B" : b < 1048576 ? (b / 1024).toFixed(0) + " KB" : (b / 1048576).toFixed(1) + " MB");
  const lsGet = (k, d) => { try { const v = localStorage.getItem("treadlidar." + k); return v == null ? d : JSON.parse(v); } catch (e) { return d; } };
  const lsSet = (k, v) => { try { localStorage.setItem("treadlidar." + k, JSON.stringify(v)); } catch (e) { /* storage unavailable: fine */ } };

  /* ---------- API ---------- */
  const token = new URLSearchParams(location.search).get("t") || "";
  async function api(method, path, body) {
    let r;
    try { r = await fetch(path, { method, headers: { "X-Token": token, ...(body ? { "Content-Type": "application/json" } : {}) }, body: body ? JSON.stringify(body) : undefined }); }
    catch (e) { throw new Error("The local TreadLidar service is not reachable. Is the app still running?"); }
    const ct = r.headers.get("Content-Type") || "";
    const data = ct.includes("json") ? await r.json() : await r.arrayBuffer();
    if (!r.ok) throw new Error((data && data.error) || `HTTP ${r.status}`);
    return data;
  }
  async function apiBin(path) {
    const r = await fetch(path, { headers: { "X-Token": token } });
    if (!r.ok) { let m = `HTTP ${r.status}`; try { m = (await r.json()).error || m; } catch (e) { /* binary */ } throw new Error(m); }
    return { buf: await r.arrayBuffer(), meta: JSON.parse(r.headers.get("X-Meta") || "{}") };
  }
  async function runJob(startReq, onProgress) {
    const { job } = await startReq; App.setBusy(job);
    for (;;) {
      const j = await api("GET", "/api/jobs/" + job.id); App.setBusy(j); if (onProgress) onProgress(j);
      if (j.status === "done") { App.setBusy(null); return j.result; }
      if (j.status === "error") { App.setBusy(null); throw new Error(j.error || "failed"); }
      await new Promise((r) => setTimeout(r, 250));
    }
  }

  /* ---------- state ---------- */
  const DEFAULT_PARAMS = {
    tire: { axis_hint: "", tread_half_width_mm: 120, radius_min_mm: 250, radius_max_mm: 500, expected_grooves: "" },
    filter: { outlier_enabled: false, outlier_k: 16, outlier_std: 3 },
    recon: { cell_mm: "auto", smoothing_sigma: 0, edge_jump_mm: 30 },
    detect: { threshold_mm: 1.6, min_threshold_sigma: 3, ref_method: "global_poly", poly_degree: 2 },
  };
  const State = {
    info: null, scans: [], sel: null, results: {}, resultId: null, params: JSON.parse(JSON.stringify(DEFAULT_PARAMS)),
    view: "data", tab: { data: "preview", tread: "seg" }, previewed: {}, merged: false, validated: false, exported: false, cmap: "tread", vmax: 10, tireId: "TIRE_001",
    pins: [], accuracy: { rows: [{ groove_index: 1, ref_depth_mm: "" }], origin: "unknown", picks: {}, out: null }, fulltire: { out: null, picks: {}, angles: {}, circumference: "" },
    busy: null, theme: lsGet("theme", null), dir: lsGet("dir", null),
  };
  const saved = lsGet("params", null);
  if (saved) for (const k of Object.keys(DEFAULT_PARAMS)) Object.assign(State.params[k], saved[k] || {});
  const App = { h, ico, $, fmt, fmtInt, fmtSize, api, apiBin, runJob, State, ICON, views: {}, lsGet, lsSet };
  G.App = App;
  const scanById = (id) => State.scans.find((s) => s.id === id);
  App.scan = scanById;
  App.curScan = () => scanById(State.sel);
  App.curResult = () => (State.resultId ? State.results[State.resultId] : null);
  App.anySim = () => State.scans.some((s) => s.simulated);
  App.savePrm = () => lsSet("params", State.params);

  /* ---------- toasts / modal / banners ---------- */
  App.toast = (msg, kind) => {
    const t = h("div", { class: "toast " + (kind || "") }, ico(kind === "bad" ? "alert" : kind === "ok" ? "check" : "info"), h("div", null, msg));
    $("#toast-root").append(t); setTimeout(() => t.remove(), kind === "bad" ? 7000 : 3800);
  };
  App.fail = (e) => { console.error(e); App.toast(e.message || String(e), "bad"); };
  App.modal = ({ title, body, footer, onClose, wide }) => {
    const root = $("#modal-root"); root.innerHTML = "";
    const close = () => { root.innerHTML = ""; document.removeEventListener("keydown", esc); if (onClose) onClose(); };
    const esc = (e) => { if (e.key === "Escape") close(); };
    document.addEventListener("keydown", esc);
    const m = h("div", { class: "modal", role: "dialog", "aria-modal": "true", "aria-label": title, style: wide ? { width: "min(860px,94vw)" } : {} },
      h("div", { class: "modal-h" }, h("h2", null, title), h("button", { class: "btn ghost icon sm", "aria-label": "Close", onclick: close }, ico("x"))),
      h("div", { class: "modal-b" }, body), footer ? h("div", { class: "modal-f" }, footer) : null);
    root.append(m); root.onclick = (e) => { if (e.target === root) close(); }; return { close, el: m };
  };
  App.banner = (kind, title, text) => h("div", { class: "banner " + kind, role: kind === "bad" ? "alert" : "note" }, ico(kind === "ok" ? "check" : kind === "info" ? "info" : "alert"), h("div", null, title ? h("b", null, title + " ") : null, text));

  /* ---------- steps ---------- */
  const STEPS = [
    { n: 1, label: "Load scan", sub: "Files or demo data", view: "data", tab: "load" },
    { n: 2, label: "Preview", sub: "Raw point cloud", view: "data", tab: "preview" },
    { n: 3, label: "Register", sub: "Merge scans (optional)", view: "data", tab: "register", optional: true },
    { n: 4, label: "Segment tire", sub: "Isolate tread points", view: "tread", tab: "seg" },
    { n: 5, label: "Reconstruct", sub: "Surface without smoothing", view: "tread", tab: "surface" },
    { n: 6, label: "Analyze tread", sub: "Grooves and reference", view: "tread", tab: "grooves" },
    { n: 7, label: "Select area", sub: "Pin or box a region", view: "measure" },
    { n: 8, label: "Calculate depth", sub: "Per location, in 3D", view: "measure" },
    { n: 9, label: "Accuracy", sub: "Against gauge readings", view: "accuracy" },
    { n: 10, label: "Export", sub: "PLY · STL · OBJ · reports", view: "export" },
  ];
  const TOOLS = [
    { id: "fulltire", label: "Full tire", sub: "Rotating wheel, 360°", icon: "ring" },
    { id: "sensor", label: "Sensor check", sub: "Noise and step tests", icon: "gauge" },
  ];
  const done = (n) => ({ 1: State.scans.length > 0, 2: Object.keys(State.previewed).length > 0, 3: State.merged, 4: !!App.curResult(), 5: !!App.curResult(), 6: !!App.curResult(),
    7: State.pins.length > 0, 8: State.pins.length > 0, 9: State.validated, 10: State.exported }[n]);

  const dataTab = () => (State.scans.length ? State.tab.data : "load");
  App.go = (view, tab) => { State.view = view; if (tab) State.tab[view] = tab; App.render(); };
  function renderRail() {
    const rail = $("#rail"); rail.innerHTML = "";
    rail.append(h("div", { class: "brand" }, h("div", { class: "logo", html: '<svg viewBox="0 0 32 32"><path d="M7 22L11 10H15L13 22ZM17 22L19 10H23L25 22Z" fill="#fff"/><rect x="6" y="23.5" width="20" height="2" rx="1" fill="#fff" opacity=".6"/></svg>' }),
      h("div", null, h("b", null, "TreadLidar"), h("span", null, "Unitree L2 tread lab"))));
    const sc = h("nav", { class: "rail-scroll", "aria-label": "Workflow steps" });
    sc.append(h("div", { class: "rail-group" }, "Workflow"));
    STEPS.forEach((s) => {
      const active = State.view === s.view && (!s.tab || State.tab[s.view] === s.tab || (s.view === "measure"));
      const tt = State.tab.tread === "density" ? "grooves" : State.tab.tread;
      const isCur = (s.view === State.view) && (s.view === "measure" ? s.n === (State.pins.length ? 8 : 7) : s.view === "data" ? dataTab() === s.tab : s.view === "tread" ? tt === s.tab : true);
      const el = h("button", { class: "step" + (done(s.n) ? " done" : "") + (s.optional ? " optional" : ""), "aria-current": isCur ? "step" : null, onclick: () => App.go(s.view, s.tab) },
        h("span", { class: "dot" }, done(s.n) ? ico("check") : String(s.n)), h("span", null, h("span", { class: "lbl" }, s.label), h("span", { class: "sub" }, s.sub)));
      if (done(s.n)) $(".dot svg", el).style.cssText = "width:13px;height:13px"; sc.append(el);
    });
    sc.append(h("div", { class: "rail-group" }, "Tools"));
    TOOLS.forEach((t) => sc.append(h("button", { class: "step", "aria-current": State.view === t.id ? "step" : null, onclick: () => App.go(t.id) },
      h("span", { class: "dot", style: { border: "none", background: "var(--surface-3)" } }, ico(t.icon)), h("span", null, h("span", { class: "lbl" }, t.label), h("span", { class: "sub" }, t.sub)))));
    rail.append(sc);
    rail.append(h("div", { class: "rail-foot" }, ico("lock"), h("span", null, "Runs locally · v" + (State.info ? State.info.version : "")), h("span", { class: "grow" }), h("button", { class: "btn ghost icon sm", "aria-label": "Toggle light/dark theme", onclick: toggleTheme, title: "Toggle theme" }, ico(isDark() ? "sun" : "moon"))));
  }
  const isDark = () => document.documentElement.dataset.theme === "dark" || (!document.documentElement.dataset.theme && matchMedia("(prefers-color-scheme: dark)").matches);
  function applyTheme() { if (State.theme) document.documentElement.dataset.theme = State.theme; else delete document.documentElement.dataset.theme; }
  function toggleTheme() { State.theme = isDark() ? "light" : "dark"; lsSet("theme", State.theme); applyTheme(); App.render(); }
  App.isDark = isDark;

  function renderTop() {
    const top = $("#topbar"); top.innerHTML = "";
    const cur = STEPS.find((s) => s.view === State.view && (!s.tab || (State.view === "data" ? dataTab() : State.tab[s.view] === "density" ? "grooves" : State.tab[s.view]) === s.tab)) || STEPS.find((s) => s.view === State.view && (s.view !== "measure" || s.n === (State.pins.length ? 8 : 7)));
    const tool = TOOLS.find((t) => t.id === State.view);
    top.append(h("div", null, h("div", { class: "faint", style: { fontSize: "11px" } }, tool ? "Tool" : cur ? `Step ${cur.n} of 10` : ""), h("b", { style: { fontSize: "15px" } }, tool ? tool.label : cur ? cur.label : "")));
    top.append(h("div", { class: "grow" }));
    if (State.scans.length) {
      const sel = h("select", { class: "input", style: { width: "260px" }, "aria-label": "Active scan", onchange: (e) => { State.sel = e.target.value; State.resultId = App.resultIdFor(State.sel); App.render(); } },
        State.scans.map((s) => h("option", { value: s.id, selected: s.id === State.sel }, `${s.name}  ·  ${fmtInt(s.n_points)} pts`)));
      top.append(h("span", { class: "faint" }, "Scan"), sel);
    }
    const sim = App.anySim();
    if (State.scans.length) top.append(h("span", { class: "badge " + (sim ? "warn" : "info"), title: sim ? "Loaded data is marked simulated: it says nothing about the real Unitree L2." : "Real recorded data. Accuracy is unvalidated until you run the Accuracy step with reference readings." },
      ico(sim ? "alert" : "info"), sim ? "SIMULATED DATA" : "Real data · unvalidated"));
    top.append(h("button", { class: "btn ghost icon", "aria-label": "Help and shortcuts", onclick: showHelp }, ico("help")));
  }
  App.resultIdFor = (sid) => { const r = Object.values(State.results).filter((x) => x.scan_id === sid); return r.length ? r[r.length - 1].id : null; };
  function showHelp() {
    const rows = [["Ctrl / ⌘ + Enter", "Run the analysis (Tread view)"], ["Mouse wheel", "Zoom 3D views and the depth map"], ["Drag", "Rotate (3D) · pan (depth map, Pan tool)"], ["Shift + drag / right-drag", "Pan the 3D view"], ["Double-click 3D", "Reset the view"], ["Esc", "Close dialogs"]];
    App.modal({ title: "Help", body: h("div", { class: "stack" },
      h("p", null, "TreadLidar measures tire tread depth from LiDAR point clouds. Work down the steps on the left; every step can be revisited."),
      App.banner("info", "Honest by design.", "Accuracy is never assumed: only the Accuracy step (real scans + real gauge readings) can produce a verdict about the Unitree L2. Simulated demo data is labelled everywhere."),
      h("table", { class: "tbl" }, h("tbody", null, rows.map((r) => h("tr", null, h("td", null, h("span", { class: "kbd" }, r[0])), h("td", null, r[1])))))) });
  }
  App.showHelp = showHelp;

  function renderStatus() {
    const s = $("#statusbar"); s.innerHTML = ""; const b = State.busy;
    if (b && b.status === "running") s.append(h("span", { class: "spin" }), h("span", null, b.message), h("div", { class: "progress", style: { width: "160px" } }, h("i", { style: { width: Math.round(b.progress * 100) + "%" } })), h("span", { class: "num faint" }, Math.round(b.elapsed_s) + " s"));
    else s.append(ico("check"), h("span", null, "Ready"));
    s.append(h("span", { class: "grow" }), h("span", { class: "faint" }, `${State.scans.length} scan${State.scans.length === 1 ? "" : "s"} · ${Object.keys(State.results).length} analys${Object.keys(State.results).length === 1 ? "i" : "e"}s`));
    const okIcon = $("svg", s); if (okIcon) okIcon.style.cssText = "width:13px;height:13px;color:var(--ok)";
  }
  App.setBusy = (j) => { State.busy = j; renderStatus(); };

  /* ---------- rendering ---------- */
  App.cleanup = [];
  App.onCleanup = (f) => App.cleanup.push(f);
  App.render = () => {
    App.cleanup.splice(0).forEach((f) => { try { f(); } catch (e) { console.warn(e); } });
    renderRail(); renderTop(); renderStatus(); $("#banner-root").innerHTML = "";
    const v = $("#view"); v.innerHTML = ""; v.classList.remove("no-pad"); v.scrollTop = 0;
    const fn = App.views[State.view]; if (fn) fn(v); else v.append(h("div", { class: "empty" }, "Unknown view"));
  };
  App.chrome = () => { renderRail(); renderTop(); renderStatus(); };
  App.rerenderKeepScroll = () => { const v = $("#view"), y = v.scrollTop; App.render(); v.scrollTop = y; };

  /* ---------- shared widgets ---------- */
  App.tile = (k, v, unit, sub, cls) => h("div", { class: "tile " + (cls || "") }, h("div", { class: "k" }, k), h("div", { class: "v" }, v, unit ? h("small", null, unit) : null), sub ? h("div", { class: "s" }, sub) : null);
  App.card = (title, bodyEl, actions, iconName, opts) => h("div", { class: "card", style: opts && opts.style }, title ? h("div", { class: "card-h" }, h("h3", null, iconName ? ico(iconName) : null, title), actions ? h("div", { class: "row" }, actions) : null) : null, h("div", { class: "card-b" + (opts && opts.flush ? " flush" : "") }, bodyEl));
  App.pageHead = (title, desc, actions) => h("div", { class: "page-h" }, h("div", null, h("h1", null, title), desc ? h("p", null, desc) : null), actions ? h("div", { class: "row" }, actions) : null);
  App.empty = (iconName, title, text, actions) => h("div", { class: "empty" }, h("div", { class: "ico" }, ico(iconName)), h("h3", null, title), h("p", null, text), actions ? h("div", { class: "row" }, actions) : null);
  App.field = (label, input, hint) => h("div", { class: "field" }, h("label", null, label, hint ? h("span", { class: "hint" }, hint) : null), input);
  App.unitInput = (path, unit, opts) => {
    const [a, b] = path.split("."); const o = Object.assign({ step: "any" }, opts || {});
    const inp = h("input", { class: "input num", type: o.text ? "text" : "number", step: o.step, value: State.params[a][b], placeholder: o.placeholder || "",
      oninput: (e) => { State.params[a][b] = o.text ? e.target.value : (e.target.value === "" ? "" : +e.target.value); App.savePrm(); } });
    return h("div", { class: "input-unit" }, inp, unit ? h("span", { class: "u" }, unit) : null);
  };
  App.toggleRow = (label, path, hint) => { const [a, b] = path.split("."); return h("div", { class: "toggle-row" }, h("div", null, h("div", { style: { fontWeight: 560 } }, label), hint ? h("div", { class: "faint", style: { fontSize: "11.5px" } }, hint) : null),
    h("label", { class: "switch" }, h("input", { type: "checkbox", checked: State.params[a][b], onchange: (e) => { State.params[a][b] = e.target.checked; App.savePrm(); App.render(); } }), h("i"))); };
  App.selectInput = (value, opts, onchange, style) => h("select", { class: "input", style, onchange: (e) => onchange(e.target.value) }, opts.map(([v, l]) => h("option", { value: v, selected: String(v) === String(value) }, l)));
  App.download = (name, text, type) => { const a = h("a", { href: URL.createObjectURL(new Blob([text], { type: type || "text/csv" })), download: name }); document.body.append(a); a.click(); a.remove(); };
  App.palette = () => ({ accent: Charts.css("--accent"), info: Charts.css("--info"), ok: Charts.css("--ok"), warn: Charts.css("--warn"), bad: Charts.css("--bad"), text: Charts.css("--text") });

  /* ---------- scans ---------- */
  App.refreshScans = async () => { const d = await api("GET", "/api/scans"); State.scans = d.scans; if (!State.sel || !scanById(State.sel)) State.sel = State.scans.length ? State.scans[0].id : null; };
  App.addScans = (list) => { for (const s of list) if (!scanById(s.id)) State.scans.push(s); if (!State.sel || !scanById(State.sel)) State.sel = list.length ? list[0].id : State.sel; };
  App.removeScan = async (id) => { await api("DELETE", "/api/scans/" + id); State.scans = State.scans.filter((s) => s.id !== id); for (const [k, r] of Object.entries(State.results)) if (r.scan_id === id) delete State.results[k];
    if (State.sel === id) State.sel = State.scans.length ? State.scans[0].id : null; State.resultId = State.sel ? App.resultIdFor(State.sel) : null; State.pins = []; App.render(); };

  /* ---------- file browser modal ---------- */
  App.fileBrowser = ({ mode, onPick, title }) => {
    const st = { path: State.dir || (State.info && State.info.home) || "", items: [], sel: new Set(), scale: 1, parent: null };
    const list = h("div", { style: { minHeight: "280px", maxHeight: "46vh", overflow: "auto", border: "1px solid var(--border)", borderRadius: "8px", padding: "4px" } });
    const pathIn = h("input", { class: "input num", value: st.path, "aria-label": "Folder path", onkeydown: (e) => { if (e.key === "Enter") go(e.target.value); } });
    const foot = h("div", { class: "modal-f", style: { padding: 0, border: 0, marginTop: "12px" } });
    const mod = App.modal({ title: title || (mode === "dir" ? "Choose a folder" : "Add scans"), wide: true, body: h("div", { class: "stack tight" },
      h("div", { class: "row" }, h("button", { class: "btn sm", onclick: () => st.parent && go(st.parent), "aria-label": "Parent folder" }, ico("up"), "Up"), pathIn, h("button", { class: "btn sm", onclick: () => go(pathIn.value) }, "Go")), list,
      mode === "dir" ? null : h("div", { class: "row" }, h("span", { class: "muted" }, "File units"), App.selectInput(1, [[1, "metres (m)"], [0.001, "millimetres (mm)"], [0.01, "centimetres (cm)"]], (v) => (st.scale = +v), { width: "180px" }),
        h("span", { class: "faint" }, "Coordinates are never guessed: choose the unit the file was saved in.")), foot) });
    async function go(p) { try { const d = await api("GET", "/api/fs?path=" + encodeURIComponent(p)); st.path = d.path; st.parent = d.parent; st.items = d.items; State.dir = d.path; lsSet("dir", d.path); st.sel.clear(); draw(); } catch (e) { App.fail(e); } }
    function draw() {
      pathIn.value = st.path; list.innerHTML = "";
      if (!st.items.length) list.append(h("div", { class: "empty", style: { padding: "30px" } }, "No sub-folders or supported point-cloud files here."));
      st.items.forEach((it) => {
        const full = st.path.replace(/[\\/]$/, "") + "/" + it.name, on = st.sel.has(full);
        list.append(h("div", { class: "file-row " + it.kind + (on ? " sel" : ""), role: "button", tabindex: 0, onclick: () => { if (it.kind === "dir") return go(full); mode === "dir" ? null : (on ? st.sel.delete(full) : st.sel.add(full)); draw(); },
          onkeydown: (e) => { if (e.key === "Enter") e.target.click(); } }, ico(it.kind === "dir" ? "folder" : "cloud"), h("span", null, it.name), it.size != null ? h("span", { class: "sz num" }, fmtSize(it.size)) : null));
      });
      foot.innerHTML = "";
      if (mode === "dir") foot.append(h("span", { class: "muted grow" }, st.path), h("button", { class: "btn primary", onclick: () => { mod.close(); onPick(st.path); } }, "Use this folder"));
      else { const files = st.items.filter((i) => i.kind === "file");
        foot.append(h("button", { class: "btn sm", disabled: !files.length, onclick: () => { files.forEach((f) => st.sel.add(st.path.replace(/[\\/]$/, "") + "/" + f.name)); draw(); } }, "Select all files here"), h("span", { class: "grow" }),
          h("button", { class: "btn primary", disabled: !st.sel.size, onclick: () => { mod.close(); onPick([...st.sel], st.scale); } }, `Add ${st.sel.size || ""} file${st.sel.size === 1 ? "" : "s"}`)); }
    }
    go(st.path || "");
  };

  /* ---------- keyboard ---------- */
  document.addEventListener("keydown", (e) => { if ((e.ctrlKey || e.metaKey) && e.key === "Enter" && App.runAnalysis) { e.preventDefault(); App.runAnalysis(); } });
  window.addEventListener("resize", () => { /* canvases observe their own size */ });
  App.applyTheme = applyTheme;
})(window);
