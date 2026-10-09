"use strict";
(function () {
  const { h, ico, State, api, apiBin, fmt, fmtInt } = App;
  const F = State.fulltire; F.protocol = F.protocol || { n_positions: 8, limit_mm: 1.6, uncertainty_mm: "", expected_grooves: "" }; F.tab = F.tab || "map";
  const sortByAngle = (a, b) => (a.wheel_angle_deg ?? 1e9) - (b.wheel_angle_deg ?? 1e9);

  async function run() {
    const ids = [...F.pickIds]; if (ids.length < 2) return App.toast("Select at least two views", "bad");
    const ordered = State.scans.filter((s) => F.pickIds.has(s.id)).sort(sortByAngle).map((s) => s.id);
    const angles = ordered.map((id) => F.angles[id]); const haveAll = angles.every((a) => a !== "" && a != null && isFinite(+a));
    try {
      const out = await App.runJob(api("POST", "/api/fulltire", { scan_ids: ordered, angles: haveAll ? angles.map(Number) : null, blind_step_deg: F.blindStep || 20, circumference_mm: F.circumference || null, protocol: F.protocol, params: App.analysisParams() }));
      F.out = out; F.error = null; F.map = null; F.mesh = null; State.fulltireDone = true;
    } catch (e) { F.error = e.message; F.out = null; }
    App.render();
  }

  function ring(out) {
    const cov = out.coverage_deg, n = out.report.protocol.n_positions, S = 232, c = S / 2, R1 = 96, R2 = 112; let svg = `<svg viewBox="0 0 ${S} ${S}" width="${S}" height="${S}" role="img" aria-label="Coverage ring">`;
    const pt = (a, r) => [c + r * Math.sin(a * Math.PI / 180), c - r * Math.cos(a * Math.PI / 180)];
    for (let d = 0; d < 360; d += 3) { const v = (cov[d] + cov[d + 1] + cov[d + 2]) / 3, [x0, y0] = pt(d, R1), [x1, y1] = pt(d, R2), [x2, y2] = pt(d + 3, R2), [x3, y3] = pt(d + 3, R1);
      const col = v > 0.5 ? "var(--accent)" : v > 0.05 ? "var(--warn)" : "var(--surface-3)"; svg += `<path d="M${x0.toFixed(1)} ${y0.toFixed(1)}L${x1.toFixed(1)} ${y1.toFixed(1)}L${x2.toFixed(1)} ${y2.toFixed(1)}L${x3.toFixed(1)} ${y3.toFixed(1)}Z" fill="${col}" stroke="var(--surface)" stroke-width=".6"/>`; }
    for (let k = 0; k < n; k++) { const a = 360 * k / n, [x0, y0] = pt(a, R1 - 6), [x1, y1] = pt(a, R1 - 16); svg += `<line x1="${x0.toFixed(1)}" y1="${y0.toFixed(1)}" x2="${x1.toFixed(1)}" y2="${y1.toFixed(1)}" stroke="var(--text-2)" stroke-width="2" stroke-linecap="round"/>`; }
    [0, 90, 180, 270].forEach((a) => { const [x, y] = pt(a, R2 + 11); svg += `<text x="${x.toFixed(1)}" y="${y.toFixed(1)}" font-size="10" fill="var(--text-3)" text-anchor="middle" dominant-baseline="middle">${a}°</text>`; });
    const covered = cov.filter((v) => v > 0.5).length / 360 * 100;
    svg += `<text x="${c}" y="${c - 4}" text-anchor="middle" font-size="26" font-weight="700" fill="var(--text)">${covered.toFixed(0)}%</text><text x="${c}" y="${c + 16}" text-anchor="middle" font-size="11" fill="var(--text-3)">covered</text></svg>`;
    return h("div", { html: svg, style: { display: "grid", placeItems: "center" } });
  }

  async function mapView(out, host) {
    const pane = h("div", { class: "pane", style: { height: "340px" } }); host.append(pane);
    let ready = false; const cv = h("canvas", { style: { width: "100%", height: "100%" }, "aria-label": "Unrolled depth map of the whole tire" }); pane.append(cv); const ro = new ResizeObserver(() => ready && draw()); ro.observe(pane); App.onCleanup(() => ro.disconnect());
    const readout = h("span", { class: "chip num" }, "Hover the map"); pane.append(h("div", { class: "overlay-tr", style: { right: "84px", top: "2px" } }, readout, ...(() => { const cm = App.selectInput(State.cmap, Charts.cmapNames().map((n) => [n, n === "tread" ? "Tread" : n[0].toUpperCase() + n.slice(1)]), (v) => { State.cmap = v; bake(); draw(); }, { height: "24px", width: "110px", fontSize: "12px", padding: "0 8px" }); return [cm]; })()));
    if (!F.map) { const r = await apiBin(`/api/fulltires/${out.id}/map`); F.map = { D: new Float32Array(r.buf), meta: r.meta }; }
    const { D, meta } = F.map, off = document.createElement("canvas"); off.width = meta.rows; off.height = meta.cols;
    function bake() { const img = new ImageData(meta.rows, meta.cols); for (let i = 0; i < meta.rows; i++) for (let j = 0; j < meta.cols; j++) { const v = D[i * meta.cols + j], k = (j * meta.rows + i) * 4; if (!isFinite(v)) { img.data[k + 3] = 0; continue; } const c = Charts.cmap(State.cmap, Math.max(0, v) / State.vmax); img.data[k] = c[0]; img.data[k + 1] = c[1]; img.data[k + 2] = c[2]; img.data[k + 3] = 255; } off.getContext("2d").putImageData(img, 0, 0); }
    bake(); const L = 46, T = 22, Rm = 64, B = 24; let box = null; ready = true;
    function draw() { const r = pane.getBoundingClientRect(), dpr = devicePixelRatio || 1; cv.width = Math.round(r.width * dpr); cv.height = Math.round(r.height * dpr); const g = cv.getContext("2d"); g.setTransform(dpr, 0, 0, dpr, 0, 0); g.fillStyle = Charts.css("--viewer-bg"); g.fillRect(0, 0, r.width, r.height);
      const W = r.width - L - Rm, H = r.height - T - B; box = { x: L, y: T, w: W, h: H }; g.imageSmoothingEnabled = false; g.drawImage(off, L, T, W, H);
      const txt = Charts.css("--viewer-text"); g.fillStyle = txt; g.strokeStyle = txt; g.font = "11px " + Charts.css("--font"); g.textAlign = "center"; g.textBaseline = "top"; for (let a = 0; a <= 360; a += 45) { const x = L + a / 360 * W; g.beginPath(); g.moveTo(x + .5, T + H); g.lineTo(x + .5, T + H + 4); g.stroke(); g.fillText(a + "°", x, T + H + 6); }
      g.textAlign = "right"; g.textBaseline = "middle"; const wt = Charts.niceTicks(meta.w0_mm, meta.w0_mm + meta.cols * meta.cell_mm, 4); for (const t of wt.ticks) { const y = T + (t - meta.w0_mm) / (meta.cols * meta.cell_mm) * H; if (y < T || y > T + H) continue; g.fillText(Charts.fmtTick(t, wt.step), L - 6, y); }
      g.textAlign = "left"; g.textBaseline = "bottom"; g.fillText("angle around the tire (tire-fixed) →", L, T - 5);
      const n = out.report.protocol.n_positions; g.strokeStyle = "rgba(255,255,255,.55)"; g.setLineDash([3, 4]); for (let k = 0; k < n; k++) { const x = L + k / n * W; g.beginPath(); g.moveTo(x + .5, T); g.lineTo(x + .5, T + H); g.stroke(); } g.setLineDash([]);
      out.grooves.forEach((gr) => { const y = T + (gr.w_center_m * 1e3 - meta.w0_mm) / (meta.cols * meta.cell_mm) * H; g.fillStyle = "rgba(10,14,19,.8)"; g.fillRect(L + W + 4, y - 8, 30, 16); g.fillStyle = "#fff"; g.textAlign = "center"; g.textBaseline = "middle"; g.fillText("G" + gr.groove_index, L + W + 19, y); });
      const bx = r.width - 14, by = T, bh = Math.min(170, H), grad = g.createLinearGradient(0, by + bh, 0, by); for (let k = 0; k <= 10; k++) { const c = Charts.cmap(State.cmap, k / 10); grad.addColorStop(k / 10, `rgb(${c[0] | 0},${c[1] | 0},${c[2] | 0})`); } g.fillStyle = grad; g.fillRect(bx - 8, by, 8, bh); }
    cv.addEventListener("pointermove", (e) => { if (!box) return; const r = cv.getBoundingClientRect(), x = e.clientX - r.left, y = e.clientY - r.top; if (x < box.x || x > box.x + box.w || y < box.y || y > box.y + box.h) return readout.replaceChildren("outside the map");
      const i = Math.floor((x - box.x) / box.w * meta.rows), j = Math.floor((y - box.y) / box.h * meta.cols), v = D[i * meta.cols + j]; readout.replaceChildren(`${fmt((i + .5) / meta.rows * 360, 1)}° · w ${fmt(meta.w0_mm + (j + .5) * meta.cell_mm, 1)} mm · ` + (isFinite(v) ? `depth ${fmt(v, 2)} mm` : "not covered")); });
    draw();
  }

  async function ringView(out, host) {
    const pane = h("div", { class: "pane", style: { height: "340px" } }); host.append(pane); const viewer = new Viewer3D(pane); App.onCleanup(() => viewer.destroy());
    pane.append(h("div", { class: "overlay-tl" }, h("span", { class: "chip" }, "Closed-ring height field · drag to rotate")), h("div", { class: "overlay-tr" }, h("div", { class: "tool-bar" }, h("button", { class: "btn", "aria-label": "Reset view", title: "Reset view", onclick: () => viewer.reset() }, ico("focus")))));
    if (!F.mesh) { const r = await apiBin(`/api/fulltires/${out.id}/mesh`), nv = r.meta.nv, nf = r.meta.nf; F.mesh = { v: new Float32Array(r.buf, 0, nv * 3), d: new Float32Array(r.buf, nv * 12, nv), f: new Uint32Array(r.buf, nv * 16, nf * 3) }; }
    viewer.setLayer("mesh", { type: "mesh", positions: F.mesh.v, indices: F.mesh.f, colors: App.depthColors(F.mesh.d, State.vmax) }); viewer.fit(["mesh"]); viewer.cam.pitch = 0.62; viewer.cam.yaw = -1.12; viewer.cam.d *= 0.8; viewer.home = Object.assign(viewer.home, { yaw: viewer.cam.yaw, pitch: viewer.cam.pitch, d: viewer.cam.d }); viewer.render();
  }

  function notes(rep) {
    const keep = rep.warnings.filter((w) => /refinement (rejected|skipped)/.test(w)), other = rep.warnings.filter((w) => !/refinement (rejected|skipped)/.test(w));
    if (!keep.length && !other.length) return null;
    return App.card("Notes", h("div", { class: "stack tight" }, other.map((w) => h("div", { class: "banner warn", style: { fontSize: "12px" } }, ico("alert"), h("div", null, w))),
      keep.length ? h("div", { class: "banner info", style: { fontSize: "12px" } }, ico("info"), h("div", null, h("b", null, `${keep.length} view${keep.length > 1 ? "s" : ""} kept their entered wheel angle. `), "The pattern correlation with the neighbouring views was not confident enough to adjust them, so the angles you typed are used as they are. Accurate angles matter most for patterned tread.")) : null), null, "info");
  }
  function results(out) {
    if (F.error) return App.banner("bad", "Full-tire analysis failed.", F.error);
    if (!out) return h("div", { class: "card" }, h("div", { class: "card-b" }, App.empty("ring", "No full-tire result yet", "Select the views of the rotating wheel, give the tape-measured circumference and run. Neighbouring views need ≥ 25 % overlap.", [])));
    const rep = out.report, sm = rep.summary, lc = sm && sm.limit_check, cov = rep.coverage, sim = out.simulated;
    const statusCls = !lc ? "" : lc.status === "PASS" ? "ok" : lc.status === "FAIL" ? "bad" : "warn";
    const tiles = h("div", { class: "tiles", style: { gridTemplateColumns: "repeat(auto-fill,minmax(118px,1fr))" } }, App.tile("Circumference", fmt(rep.circumference_mm, 0), "mm", `Ø ${fmt(rep.outer_diameter_mm, 0)} mm`), App.tile("Measurements", sm ? String(sm.n_measurements) : "0", "", sm ? `${sm.n_missing} missing` : ""), App.tile("Min depth", sm ? fmt(sm.min_mm) : "–", "mm", sm ? `G${sm.min_at.groove_index} @ ${fmt(sm.min_at.angle_deg, 0)}°` : ""), App.tile("Mean depth", sm ? fmt(sm.mean_mm) : "–", "mm", sm ? `σ ${fmt(sm.std_mm)} mm` : ""),
      App.tile("Uneven wear", sm && sm.max_across_tread_range_mm != null ? fmt(sm.max_across_tread_range_mm, 1) : "–", "mm", "max across the tread"), App.tile("Shoulder wear", sm && sm.shoulder_minus_centre_mm != null ? fmt(sm.shoulder_minus_centre_mm, 1) : "–", "mm", "shoulder − centre"));
    const limit = lc ? h("div", { class: "card" }, h("div", { class: "card-b" }, h("div", { class: "row", style: { gap: "12px", alignItems: "flex-start" } }, h("span", { class: "badge " + statusCls, style: { height: "30px", fontSize: "14px", padding: "0 14px" } }, lc.status),
      h("div", null, h("b", null, `Limit check · ${lc.limit_mm} mm`), h("div", { class: "muted", style: { fontSize: "12px", marginTop: "2px" } }, lc.note), lc.guards && lc.guards.length ? h("div", { class: "stack tight", style: { marginTop: "8px" } }, lc.guards.map((gd) => h("div", { class: "banner warn", style: { fontSize: "12px" } }, ico("alert"), h("div", null, gd)))) : null,
        !lc.validated_uncertainty ? h("div", { class: "faint", style: { fontSize: "11.5px", marginTop: "6px" } }, "No validated measurement uncertainty was supplied, so PASS/FAIL is indicative only. Get the uncertainty from the Accuracy step on real data.") : null)))) : null;
    const segs = h("div", { class: "seg", role: "group" }, [["map", "Unrolled map"], ["ring", "3D ring"]].map(([v, l]) => h("button", { "aria-pressed": F.tab === v, onclick: () => { F.tab = v; App.render(); } }, l)));
    const host = h("div"); (F.tab === "map" ? mapView : ringView)(out, host).catch(App.fail);
    // protocol matrix + chart
    const grooves = rep.grooves, n = rep.protocol.n_positions, M = {}; rep.measurements.forEach((m) => { (M[m.groove_index] = M[m.groove_index] || [])[m.position_index] = m; });
    const head = h("tr", null, h("th", null, "Groove"), ...Array.from({ length: n }, (_, k) => h("th", { class: "num" }, fmt(360 * k / n, 0) + "°")), h("th", { class: "num" }, "min"), h("th", { class: "num" }, "mean"));
    const body = grooves.map((gr) => { const row = M[gr.groove_index] || [], vals = row.filter((m) => m && m.measured).map((m) => m.depth_mm); return h("tr", null, h("td", null, h("b", null, "G" + gr.groove_index), h("span", { class: "faint" }, ` ${fmt(gr.w_center_m * 1e3, 0)} mm`)),
      ...Array.from({ length: n }, (_, k) => { const m = row[k]; if (!m || !m.measured) return h("td", { class: "num faint" }, "–"); const c = Charts.cmap(State.cmap, Math.max(0, m.depth_mm) / State.vmax); return h("td", { class: "num", style: { background: `rgba(${c[0] | 0},${c[1] | 0},${c[2] | 0},.28)` } }, fmt(m.depth_mm, 2)); }),
      h("td", { class: "num", style: { fontWeight: 650 } }, vals.length ? fmt(Math.min(...vals), 2) : "–"), h("td", { class: "num" }, vals.length ? fmt(vals.reduce((a, b) => a + b, 0) / vals.length, 2) : "–")); });
    const chBox = h("div", { style: { height: "210px" } }); const chart = new Charts.Chart(chBox, { xLabel: "angle around the tire [°]", yLabel: "depth [mm]", margin: { l: 46, r: 12, t: 10, b: 34 }, xRange: [-10, 360], tip: (s, i) => `${s.name}<br>${fmt(s.x[i], 0)}°: ${fmt(s.y[i], 2)} mm` }); App.onCleanup(() => chart.destroy());
    setTimeout(() => { const ser = grooves.map((gr, k) => { const row = M[gr.groove_index] || []; return { name: "G" + gr.groove_index, type: "line", points: true, x: row.map((m) => m.angle_deg), y: row.map((m) => (m.measured ? m.depth_mm : NaN)), width: 1.8 }; }); ser.push({ type: "hline", y: rep.protocol.limit_mm, color: Charts.css("--bad"), dash: [5, 4], width: 1.2, noHover: true }); chart.setSeries(ser); }, 30);
    return h("div", { class: "stack loose" }, sim ? App.banner("warn", "Simulated data.", "The rotating-wheel demo is generated by the built-in simulator. It says nothing about the real L2.") : null,
      h("div", { style: { display: "grid", gridTemplateColumns: "minmax(0,1fr) 250px", gap: "16px", alignItems: "start" } }, h("div", { class: "stack" }, tiles, limit), ring(out)),
      rep.coverage.uncovered_arc_mm > 20 ? App.banner("warn", `${fmt(rep.coverage.uncovered_arc_mm, 0)} mm of the circumference is not covered.`, "Those positions are reported as missing, never interpolated.") : null,
      App.card("Whole-tire depth map", h("div", { class: "stack tight" }, host), [segs], "ring"),
      h("div", { style: { display: "grid", gridTemplateColumns: "minmax(0,1.05fr) minmax(0,1fr)", gap: "16px" } }, App.card("Depth around the circumference", chBox, null, "ruler"), App.card("Protocol measurements (mm)", h("div", { class: "tbl-wrap" }, h("table", { class: "tbl" }, h("thead", null, head), h("tbody", null, body))), null, "gauge", { flush: true })),
      notes(rep));
  }

  function inputs() {
    const wheel = State.scans.slice().sort(sortByAngle); if (!F.pickIds) { F.pickIds = new Set(wheel.filter((s) => s.wheel_angle_deg != null).map((s) => s.id)); wheel.forEach((s) => { if (F.angles[s.id] === undefined && s.wheel_angle_deg != null) F.angles[s.id] = s.wheel_angle_deg; }); const c = wheel.find((s) => s.circumference_m); if (c && !F.circumference) F.circumference = +(c.circumference_m * 1e3).toFixed(1); }
    const P = F.protocol, setP = (k, v) => { P[k] = v; };
    const row = (s) => h("div", { class: "row", style: { padding: "3px 0" } }, h("input", { type: "checkbox", checked: F.pickIds.has(s.id), "aria-label": "Use " + s.name, onchange: (e) => { e.target.checked ? F.pickIds.add(s.id) : F.pickIds.delete(s.id); App.render(); } }),
      h("span", { class: "grow", style: { overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }, title: s.name }, s.name), h("div", { class: "input-unit", style: { width: "92px" } }, h("input", { class: "input num", type: "number", step: "any", placeholder: "angle", value: F.angles[s.id] ?? "", "aria-label": "Wheel angle of " + s.name, oninput: (e) => { F.angles[s.id] = e.target.value; } }), h("span", { class: "u" }, "°")));
    return h("div", { class: "card", style: { display: "flex", flexDirection: "column", height: "100%", minHeight: 0 } }, h("div", { class: "card-h" }, h("h3", null, ico("ring"), "Rotating wheel"), h("span", { class: "badge" }, `${F.pickIds.size} views`)),
      h("div", { style: { overflow: "auto", padding: "12px 14px", flex: 1 } }, h("div", { class: "stack" },
        h("div", null, h("div", { class: "row", style: { justifyContent: "space-between", marginBottom: "6px" } }, h("div", { class: "section-t", style: { margin: 0 } }, "Views and wheel angles"), h("button", { class: "btn sm ghost", onclick: () => { F.pickIds = new Set(State.scans.filter((s) => s.wheel_angle_deg != null).map((s) => s.id)); App.render(); } }, "All wheel views")),
          State.scans.length ? h("div", { style: { maxHeight: "300px", overflow: "auto", border: "1px solid var(--border)", borderRadius: "8px", padding: "4px 10px" } }, wheel.map(row)) : null,
          h("div", { class: "faint", style: { fontSize: "11.5px", marginTop: "6px" } }, "Angle = how far the wheel was turned from the first view (positive: the tread at the sensor moves downward). Leave blank to assume an equal step.")),
        App.field("Tread half-width", App.unitInput("tire.tread_half_width_mm", "mm"), "half the tread width"),
        App.field("Tape-measured circumference", h("div", { class: "input-unit" }, h("input", { class: "input num", type: "number", step: "any", value: F.circumference, placeholder: "e.g. 1885", oninput: (e) => { F.circumference = e.target.value; } }), h("span", { class: "u" }, "mm")), "strongly recommended"),
        h("div", { class: "section-t" }, "Protocol"),
        h("div", { class: "grid2" }, App.field("Positions around", h("input", { class: "input num", type: "number", min: 2, max: 72, value: P.n_positions, oninput: (e) => setP("n_positions", +e.target.value) })), App.field("Limit", h("div", { class: "input-unit" }, h("input", { class: "input num", type: "number", step: "0.1", value: P.limit_mm, oninput: (e) => setP("limit_mm", +e.target.value) }), h("span", { class: "u" }, "mm")))),
        h("div", { class: "grid2" }, App.field("Expected grooves", h("input", { class: "input num", type: "number", min: 1, value: P.expected_grooves, placeholder: "needed for PASS", oninput: (e) => setP("expected_grooves", e.target.value) })), App.field("Validated uncertainty", h("div", { class: "input-unit" }, h("input", { class: "input num", type: "number", step: "0.05", value: P.uncertainty_mm, placeholder: "—", oninput: (e) => setP("uncertainty_mm", e.target.value) }), h("span", { class: "u" }, "mm")))),
        h("div", { class: "faint", style: { fontSize: "11.5px" } }, "A PASS is withheld unless the groove count is verified. The tire-analysis parameters are shared with the Tread step."))),
      h("div", { style: { padding: "12px 14px", borderTop: "1px solid var(--border)" } }, h("button", { class: "btn primary lg", style: { width: "100%" }, disabled: F.pickIds.size < 2 || (State.busy && State.busy.status === "running"), onclick: run }, ico("play"), "Run full-tire analysis")));
  }

  App.views.fulltire = function (root) {
    root.classList.add("no-pad");
    if (State.scans.length < 2) { root.classList.remove("no-pad"); return root.append(App.empty("ring", "Full-tire mode needs several views", "Record the wheel in steps (for example every 20°) with a fixed sensor, or load the simulated demo wheel.", [h("button", { class: "btn primary", onclick: () => App.loadDemo("wheel") }, "Load demo wheel"), h("button", { class: "btn", onclick: App.loadFilesModal }, "Add files…")])); }
    root.append(h("div", { style: { display: "grid", gridTemplateColumns: "360px minmax(0,1fr)", gap: "16px", padding: "16px 20px", height: "100%", minHeight: 0 } }, inputs(), h("div", { style: { overflow: "auto", minHeight: 0, paddingRight: "2px" } },
      App.pageHead("Whole tire (360°)", "Stitches the views of a rotating wheel into one depth map and measures every groove at fixed positions around the tire."), results(F.out))));
  };
})();
