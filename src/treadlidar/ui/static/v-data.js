"use strict";
(function () {
  const { h, ico, State, api, apiBin, fmt, fmtInt } = App;
  const cache = new Map();      // scan id -> Float32Array (display subsample)

  async function loadFiles(paths, scale) {
    try { const d = await api("POST", "/api/scans/load", { paths, scale }); App.addScans(d.scans); State.sel = d.scans[0].id; State.resultId = null; App.toast(`Loaded ${d.scans.length} scan${d.scans.length > 1 ? "s" : ""}`, "ok"); App.render(); }
    catch (e) { App.fail(e); }
  }
  async function loadDemo(kind) {
    try { App.toast("Generating simulated data…"); const d = await api("POST", "/api/scans/demo", { kind }); App.addScans(d.scans); State.sel = d.scans[0].id; State.resultId = null;
      State.params.tire.tread_half_width_mm = 95; App.savePrm(); App.toast("Tread half-width set to 95 mm, matching the simulated tire", "ok"); App.render(); }
    catch (e) { App.fail(e); }
  }
  App.loadDemo = loadDemo; App.loadFilesModal = () => App.fileBrowser({ onPick: loadFiles });

  function welcome(root) {
    const act = (icon, title, text, btn, fn, primary) => h("div", { class: "card", style: { padding: "20px", display: "flex", flexDirection: "column", gap: "10px" } },
      h("div", { class: "empty", style: { padding: 0, gap: "8px", textAlign: "left", justifyItems: "start" } }, h("div", { class: "ico" }, ico(icon)), h("h3", null, title), h("p", { style: { maxWidth: "none" } }, text)),
      h("div", { class: "grow" }), h("button", { class: "btn lg" + (primary ? " primary" : ""), onclick: fn }, btn));
    root.append(h("div", { style: { maxWidth: "1040px", margin: "28px auto 0" } },
      h("h1", { style: { fontSize: "26px", letterSpacing: "-0.02em" } }, "Measure tire tread depth from LiDAR"),
      h("p", { class: "muted", style: { margin: "8px 0 22px", maxWidth: "70ch", fontSize: "14px" } }, "Load a point cloud of a tire, let TreadLidar isolate the tread and detect the grooves, then pin any location in 3D. Accuracy is only ever claimed after you compare against real gauge readings."),
      h("div", { class: "grid3", style: { alignItems: "stretch" } },
        act("folder", "Open recorded scans", "Point clouds from the Unitree L2 recorder or any .npy, .xyz, .csv, .ply, .pcd file. Choose the file's unit explicitly.", "Browse files…", App.loadFilesModal, true),
        act("cube", "Try a simulated scan", "One synthetic tire patch with known groove depths. Good for learning the workflow. It says nothing about the real L2.", "Load demo scan", () => loadDemo("single")),
        act("ring", "Try a rotating wheel", "18 simulated views of an unevenly worn tire for the full-tire (360°) workflow.", "Load demo wheel", () => loadDemo("wheel"))),
      h("div", { style: { marginTop: "18px" } }, App.banner("info", "Local and private.", "Nothing leaves this computer: the app talks only to a service on 127.0.0.1."))));
  }

  App.views.data = function (root) {
    if (!State.scans.length) return welcome(root);
    root.classList.add("no-pad");
    const sc = App.curScan(), pickedForMerge = State.mergePick || (State.mergePick = new Set());
    const grid = h("div", { style: { display: "grid", gridTemplateColumns: "300px minmax(0,1fr) 340px", gap: "16px", padding: "16px 20px", height: "100%", minHeight: 0 } });
    // left: scans
    const list = h("div", { class: "stack tight", style: { overflow: "auto", flex: 1, padding: "12px" } },
      State.scans.map((s) => h("div", { class: "scan-card" + (s.id === State.sel ? " sel" : ""), role: "button", tabindex: 0, onclick: () => { State.sel = s.id; State.resultId = App.resultIdFor(s.id); App.render(); }, onkeydown: (e) => { if (e.key === "Enter") e.target.click(); } },
        h("input", { type: "checkbox", "aria-label": "Select for merge", checked: pickedForMerge.has(s.id), onclick: (e) => e.stopPropagation(), onchange: (e) => { e.target.checked ? pickedForMerge.add(s.id) : pickedForMerge.delete(s.id); App.render(); } }),
        h("div", { style: { minWidth: 0 } }, h("div", { class: "nm" }, s.name), h("div", { class: "meta" }, `${fmtInt(s.n_points)} points` + (s.wheel_angle_deg != null ? ` · ${s.wheel_angle_deg}°` : ""))),
        s.simulated ? h("span", { class: "badge warn" }, "SIM") : h("span", { class: "badge" }, "REAL"))));
    const left = h("div", { class: "card", style: { display: "flex", flexDirection: "column", minHeight: 0 } },
      h("div", { class: "card-h" }, h("h3", null, ico("layers"), "Scans"), h("div", { class: "row" }, h("button", { class: "btn sm primary", onclick: App.loadFilesModal }, ico("plus"), "Add files"))), list,
      h("div", { style: { padding: "10px 12px", borderTop: "1px solid var(--border)", display: "flex", gap: "8px" } },
        h("button", { class: "btn sm grow", onclick: () => loadDemo("single") }, "Demo scan"), h("button", { class: "btn sm grow", onclick: () => loadDemo("wheel") }, "Demo wheel")));
    // center: 3D preview
    const pane = h("div", { class: "pane", style: { height: "100%" }, "aria-label": "3D point cloud preview" });
    const info = h("span", { class: "chip" }, "Loading…");
    const colorBy = App.selectInput(State.colorBy || "height", [["height", "Colour: height"], ["range", "Colour: range from sensor"], ["flat", "Colour: uniform"]], (v) => { State.colorBy = v; paint(); }, { height: "24px", width: "180px", fontSize: "12px", padding: "0 8px" });
    const psz = h("input", { type: "range", min: 1, max: 8, step: 0.5, value: State.ptSize || 2.5, "aria-label": "Point size", style: { width: "90px" }, oninput: (e) => { State.ptSize = +e.target.value; viewer.setPointSize(State.ptSize); } });
    pane.append(h("div", { class: "overlay-tl" }, info, sc && sc.simulated ? h("span", { class: "chip", style: { color: "var(--warn)" } }, ico("alert"), "Simulated") : null, colorBy));
    pane.append(h("div", { class: "overlay-tr" }, h("div", { class: "tool-bar" },
      h("button", { class: "btn", title: "Frame the tire (densest region)", "aria-label": "Frame the tire", onclick: () => focusDense() }, ico("target")), h("button", { class: "btn", title: "Fit the whole scene", "aria-label": "Fit whole scene", onclick: () => viewer.fit(["raw"]) }, ico("focus")), h("button", { class: "btn", title: "Top view", "aria-label": "Top view", onclick: () => { viewer.fit(["raw"], true); viewer.cam.pitch = 1.5; viewer.render(); } }, ico("layers")))));
    pane.append(h("div", { class: "overlay-bl", style: { bottom: "10px", left: "88px" } }, h("span", { class: "chip" }, "Size", psz)));
    const viewer = new Viewer3D(pane); viewer.setPointSize(State.ptSize || 2.5); App.onCleanup(() => viewer.destroy());
    let pts = null;
    function paint() {
      if (!pts) return; const n = pts.length / 3, col = new Float32Array(n * 3), so = sc.sensor_origin, mode = State.colorBy || "height", val = new Float32Array(n);
      for (let i = 0; i < n; i++) val[i] = mode === "range" ? Math.hypot(pts[i * 3] - so[0], pts[i * 3 + 1] - so[1], pts[i * 3 + 2] - so[2]) : pts[i * 3 + 2];
      const sorted = Float32Array.from(val).sort(), lo = sorted[Math.floor(n * 0.01)], hi = sorted[Math.floor(n * 0.99)] || lo + 1;
      for (let i = 0; i < n; i++) { const c = mode === "flat" ? [150, 175, 200] : Charts.cmap("viridis", (val[i] - lo) / (hi - lo || 1)); col.set([c[0] / 255, c[1] / 255, c[2] / 255], i * 3); }
      viewer.setLayer("raw", { type: "points", positions: pts, colors: col, pickable: true }); viewer.setMarkers([{ p: so, label: "Sensor", color: "#3b82f6", r: 6 }]);
      if (!viewer.home) { focusDense(); }
    }
    // The tire is the densest region of a typical scan (ground and walls are sparse per volume): frame it first.
    function focusDense() {
      const n = pts.length / 3, vox = 0.08, m = new Map(); let best = null, bn = 0;
      for (let i = 0; i < n; i++) { const k = Math.floor(pts[i * 3] / vox) + "," + Math.floor(pts[i * 3 + 1] / vox) + "," + Math.floor(pts[i * 3 + 2] / vox); const e = m.get(k) || [0, 0, 0, 0]; e[0]++; e[1] += pts[i * 3]; e[2] += pts[i * 3 + 1]; e[3] += pts[i * 3 + 2]; m.set(k, e); if (e[0] > bn) { bn = e[0]; best = e; } }
      viewer.fit(["raw"]); const c = [best[1] / best[0], best[2] / best[0], best[3] / best[0]];
      if (bn > 6 * (n / Math.max(1, m.size))) { viewer.cam.t = c; viewer.cam.d = viewer.cam.d * 0.22; viewer.home = Object.assign(viewer.home, { t: c.slice(), d: viewer.cam.d }); viewer.render(); }
    }
    (async () => {
      try { let a = cache.get(sc.id), meta = null;
        if (!a) { const r = await apiBin(`/api/scans/${sc.id}/points?max=90000`); a = new Float32Array(r.buf); meta = r.meta; cache.set(sc.id, a); a.meta = meta; }
        pts = a; meta = a.meta; info.replaceChildren(meta.n < meta.n_total ? h("span", null, h("b", null, fmtInt(meta.n)), ` of ${fmtInt(meta.n_total)} pts · display only`) : h("span", null, h("b", null, fmtInt(meta.n_total)), " points"));
        paint(); State.previewed[sc.id] = true; App.chrome(); } catch (e) { App.fail(e); }
    })();
    // right: inspector
    const so = sc.sensor_origin, sz = sc.bbox_max.map((v, i) => v - sc.bbox_min[i]);
    const soIn = so.map((v, i) => h("input", { class: "input num", type: "number", step: "any", value: +v.toFixed(4), "aria-label": "Sensor " + "xyz"[i], onchange: async (e) => { const o = so.slice(); o[i] = +e.target.value; try { const d = await api("PATCH", "/api/scans/" + sc.id, { sensor_origin: o }); Object.assign(sc, d.scan); State.results = Object.fromEntries(Object.entries(State.results).filter(([, r]) => r.scan_id !== sc.id)); State.resultId = null; App.toast("Sensor origin updated; the analysis must be re-run", "ok"); App.render(); } catch (er) { App.fail(er); } } }));
    const angIn = h("input", { class: "input num", type: "number", step: "any", placeholder: "—", value: sc.wheel_angle_deg == null ? "" : sc.wheel_angle_deg, "aria-label": "Wheel angle", onchange: async (e) => { try { const d = await api("PATCH", "/api/scans/" + sc.id, { wheel_angle_deg: e.target.value }); Object.assign(sc, d.scan); } catch (er) { App.fail(er); } } });
    const detail = App.card("Scan details", h("div", { class: "stack" },
      h("div", { class: "tiles", style: { gridTemplateColumns: "1fr 1fr" } }, App.tile("Points", fmtInt(sc.n_points)), App.tile("Extent (m)", sz.map((v) => fmt(v, 1)).join(" × "), null, "x · y · z", "sm")),
      h("div", { class: "field" }, h("label", null, "Sensor position (m)", h("span", { class: "hint" }, sc.origin_from_sidecar ? "from recording" : "set manually")), h("div", { class: "grid3" }, soIn)),
      h("div", { class: "field" }, h("label", null, "Wheel angle", h("span", { class: "hint" }, "full-tire mode only")), h("div", { class: "input-unit" }, angIn, h("span", { class: "u" }, "°"))),
      sc.simulated ? App.banner("warn", "Simulated.", "Generated by the built-in simulator. Never use it as evidence about the real sensor.") : null,
      h("div", { class: "row" }, h("button", { class: "btn danger sm", onclick: () => App.removeScan(sc.id) }, ico("trash"), "Remove scan"))), null, "info");
    const merge = App.card("Register scans", h("div", { class: "stack", id: "register" },
      h("p", { class: "muted" }, "Optional. Only needed if the same tire was recorded in several files. With a fixed sensor the frames are simply combined."),
      h("div", { class: "seg", role: "group" }, ["concat", "icp"].map((m) => h("button", { "aria-pressed": (State.mergeMethod || "concat") === m, onclick: () => { State.mergeMethod = m; App.render(); } }, m === "concat" ? "Fixed sensor (combine)" : "ICP align"))),
      (State.mergeMethod === "icp") ? App.banner("warn", "ICP is weak on tread.", "A cylinder slides around its axis, so alignment along the circumference is poorly constrained. Prefer a fixed sensor pose.") : null,
      h("button", { class: "btn", disabled: pickedForMerge.size < 2, onclick: async () => { try { const d = await api("POST", "/api/scans/merge", { scan_ids: [...pickedForMerge], method: State.mergeMethod || "concat" }); App.addScans([d.scan]); State.sel = d.scan.id; pickedForMerge.clear(); State.merged = true;
        const rm = d.diagnostics ? d.diagnostics.map((x) => `scan ${x.scan}: rmse ${(x.rmse_m * 1e3).toFixed(2)} mm, fitness ${(x.fitness * 100).toFixed(0)}%`).join(" · ") : ""; App.toast(d.note + (rm ? " " + rm : ""), "ok"); App.render(); } catch (e) { App.fail(e); } } },
        ico("link"), pickedForMerge.size < 2 ? "Tick two or more scans to merge" : `Merge ${pickedForMerge.size} scans`)), null, "layers");
    const next = h("button", { class: "btn primary lg", style: { width: "100%" }, onclick: () => App.go("tread", "seg") }, "Continue to tread analysis", ico("chevron"));
    grid.append(left, pane, h("div", { class: "stack", style: { overflow: "auto", minHeight: 0, paddingRight: "2px" } }, detail, merge, next));
    root.append(grid);
    if (State.tab.data === "register") setTimeout(() => { const r = document.getElementById("register"); if (r) r.scrollIntoView({ block: "center" }); }, 0);
  };
})();
