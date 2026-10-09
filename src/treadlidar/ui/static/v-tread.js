"use strict";
(function () {
  const { h, ico, State, api, apiBin, fmt, fmtInt } = App;
  const cache = { dm: new Map(), mesh: new Map(), pts: new Map(), lines: new Map() };
  App.cache = cache;
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  /* ================= analysis runner ================= */
  App.analysisParams = () => JSON.parse(JSON.stringify(State.params));
  App.runAnalysis = async function () {
    const sc = App.curScan(); if (!sc) return App.toast("Load a scan first", "bad");
    if (State.busy && State.busy.status === "running") return;
    State.runError = null;
    try {
      const out = await App.runJob(api("POST", "/api/analyze", { scan_ids: [sc.id], params: App.analysisParams(), tire_id: State.tireId }));
      const r = out.results[0]; State.results[r.id] = r; State.resultId = r.id; State.pins = []; State.region = null;
      if (!State.autoCollapsed) { State.autoCollapsed = true; State.paramsOpen = false; }
      const n = r.report.warnings.length; App.toast(`Analysis done: ${r.report.grooves.filter((g) => g.kind === "longitudinal").length} longitudinal grooves, mean depth ${fmt(r.report.mean_tread_depth_mm)} mm` + (n ? ` · ${n} warning${n > 1 ? "s" : ""}` : ""), n ? "" : "ok");
    } catch (e) { State.runError = e.message; App.toast(e.message, "bad"); }
    App.render();
  };

  /* ================= data fetchers ================= */
  const f32 = (b, off, n) => new Float32Array(b, off, n);
  App.getDepthMap = async (rid) => { if (!cache.dm.has(rid)) { const r = await apiBin(`/api/results/${rid}/depthmap`); cache.dm.set(rid, { D: new Float32Array(r.buf), meta: r.meta }); } return cache.dm.get(rid); };
  App.getMesh = async (rid) => { if (!cache.mesh.has(rid)) { const r = await apiBin(`/api/results/${rid}/mesh`), nv = r.meta.nv, nf = r.meta.nf;
    cache.mesh.set(rid, { v: f32(r.buf, 0, nv * 3), d: f32(r.buf, nv * 12, nv), f: new Uint32Array(r.buf, nv * 16, nf * 3), nv, nf }); } return cache.mesh.get(rid); };
  App.getPoints = async (rid) => { if (!cache.pts.has(rid)) { const r = await apiBin(`/api/results/${rid}/points?max=120000`), n = r.meta.n; cache.pts.set(rid, { v: f32(r.buf, 0, n * 3), d: f32(r.buf, n * 12, n), n, total: r.meta.n_total }); } return cache.pts.get(rid); };
  App.getGrooveLines = async (rid) => { if (!cache.lines.has(rid)) { const r = await apiBin(`/api/results/${rid}/groovelines`); cache.lines.set(rid, new Float32Array(r.buf)); } return cache.lines.get(rid); };
  App.depthColors = (d, vmax, cmap, extra) => { const c = new Float32Array(d.length * 3); for (let i = 0; i < d.length; i++) { const x = Charts.cmap(cmap || State.cmap, Math.max(0, d[i]) / vmax); c[i * 3] = x[0] / 255; c[i * 3 + 1] = x[1] / 255; c[i * 3 + 2] = x[2] / 255; } return c; };

  /* ================= DepthMap canvas component ================= */
  class DepthMap {
    constructor(el, o) {
      this.el = el; this.o = Object.assign({ mode: "view", showGrooves: true, cmap: State.cmap, vmax: State.vmax }, o || {});
      this.cv = h("canvas", { style: { width: "100%", height: "100%", display: "block", touchAction: "none" }, "aria-label": "Depth map" }); el.append(this.cv); this.g = this.cv.getContext("2d");
      this.readout = h("span", { class: "chip num" }, "Hover the map"); this.pins = []; this.region = null; this.grooves = []; this.view = null; this.D = null;
      this.ro = new ResizeObserver(() => this.draw()); this.ro.observe(el); this._bind();
    }
    async load(rid, grooves) {
      const { D, meta } = await App.getDepthMap(rid); this.D = D; this.m = meta; this.grooves = grooves || []; this.rid = rid;
      const off = document.createElement("canvas"); off.width = meta.cols; off.height = meta.rows; this.off = off; this.bake(); this.fit(); this.draw();
    }
    bake() {
      const { rows, cols } = this.m, img = new ImageData(cols, rows), D = this.D; const inv = 1 / this.o.vmax;
      for (let i = 0; i < rows * cols; i++) { const v = D[i]; if (!isFinite(v)) { img.data[i * 4 + 3] = 0; continue; } const c = Charts.cmap(this.o.cmap, Math.max(0, v) * inv); img.data[i * 4] = c[0]; img.data[i * 4 + 1] = c[1]; img.data[i * 4 + 2] = c[2]; img.data[i * 4 + 3] = 255; }
      this.off.getContext("2d").putImageData(img, 0, 0);
    }
    setStyle(o) { Object.assign(this.o, o); if (this.D) this.bake(); this.draw(); }
    size() { const r = this.el.getBoundingClientRect(); return [r.width, r.height]; }
    fit() { const [W, H] = this.size(), mL = 54, mT = 46, mR = 70, mB = 14; const sc = Math.min((W - mL - mR) / this.m.cols, (H - mT - mB) / this.m.rows); this.view = { s: sc, x: mL + ((W - mL - mR) - this.m.cols * sc) / 2, y: mT + ((H - mT - mB) - this.m.rows * sc) / 2 }; this.fitScale = sc; }
    toData(px, py) { const v = this.view, jx = (px - v.x) / v.s, iy = (py - v.y) / v.s; return { j: jx, i: iy, w: this.m.w0_mm + jx * this.m.cell_mm, s: this.m.s0_mm + iy * this.m.cell_mm }; }
    toScreen(w, s) { const v = this.view; return [v.x + (w - this.m.w0_mm) / this.m.cell_mm * v.s, v.y + (s - this.m.s0_mm) / this.m.cell_mm * v.s]; }
    valueAt(d) { const i = Math.floor(d.i), j = Math.floor(d.j); if (i < 0 || j < 0 || i >= this.m.rows || j >= this.m.cols) return null; const v = this.D[i * this.m.cols + j]; return isFinite(v) ? v : NaN; }
    _bind() {
      let drag = null; const c = this.cv, pos = (e) => { const r = c.getBoundingClientRect(); return [e.clientX - r.left, e.clientY - r.top]; };
      c.addEventListener("wheel", (e) => { if (!this.view) return; e.preventDefault(); const [x, y] = pos(e), k = Math.exp(-e.deltaY * 0.0016), v = this.view, ns = Math.min(this.fitScale * 40, Math.max(this.fitScale * 0.5, v.s * k)), f = ns / v.s; v.x = x - (x - v.x) * f; v.y = y - (y - v.y) * f; v.s = ns; this.draw(); }, { passive: false });
      c.addEventListener("pointerdown", (e) => { if (!this.view) return; c.setPointerCapture(e.pointerId); const [x, y] = pos(e); drag = { x, y, x0: x, y0: y, pan: this.o.mode === "pan" || e.button === 1 || e.button === 2 || e.shiftKey, vx: this.view.x, vy: this.view.y }; });
      c.addEventListener("contextmenu", (e) => e.preventDefault());
      c.addEventListener("pointermove", (e) => { if (!this.view) return; const [x, y] = pos(e), d = this.toData(x, y), v = this.valueAt(d);
        this.readout.replaceChildren(v == null ? "outside the map" : `s ${fmt(d.s, 1)} mm · w ${fmt(d.w, 1)} mm · ` + (isFinite(v) ? `depth ${fmt(v, 2)} mm` : "no data"));
        if (!drag) return; if (drag.pan) { this.view.x = drag.vx + (x - drag.x0); this.view.y = drag.vy + (y - drag.y0); } else if (this.o.mode === "region") { drag.x = x; drag.y = y; this.tmp = [drag.x0, drag.y0, x, y]; } this.draw(); });
      c.addEventListener("pointerup", (e) => { if (!drag || !this.view) return; const [x, y] = pos(e), moved = Math.hypot(x - drag.x0, y - drag.y0) > 4; const dr = drag; drag = null; this.tmp = null;
        if (dr.pan) { this.draw(); return; }
        if (this.o.mode === "measure" && !moved) { const d = this.toData(x, y); if (this.valueAt(d) != null && this.o.onPick) this.o.onPick(d.s, d.w); }
        else if (this.o.mode === "region" && moved) { const a = this.toData(dr.x0, dr.y0), b = this.toData(x, y); this.region = { s0: Math.min(a.s, b.s), s1: Math.max(a.s, b.s), w0: Math.min(a.w, b.w), w1: Math.max(a.w, b.w) }; if (this.o.onRegion) this.o.onRegion(this.region); }
        this.draw(); });
      c.addEventListener("dblclick", () => { this.fit(); this.draw(); });
    }
    draw() {
      const [W, H] = this.size(), dpr = devicePixelRatio || 1; if (this.cv.width !== Math.round(W * dpr) || this.cv.height !== Math.round(H * dpr)) { this.cv.width = Math.round(W * dpr); this.cv.height = Math.round(H * dpr); }
      const g = this.g; g.setTransform(dpr, 0, 0, dpr, 0, 0); g.fillStyle = Charts.css("--viewer-bg"); g.fillRect(0, 0, W, H); if (!this.view || !this.D) return;
      const v = this.view, m = this.m, txt = Charts.css("--viewer-text");
      g.imageSmoothingEnabled = false; g.drawImage(this.off, v.x, v.y, m.cols * v.s, m.rows * v.s);
      // rulers
      g.font = "11px " + Charts.css("--font"); g.fillStyle = txt; g.strokeStyle = txt; g.lineWidth = 1; g.globalAlpha = .9;
      const wt = Charts.niceTicks(m.w0_mm, m.w0_mm + m.cols * m.cell_mm, Math.max(3, W / 90)), st = Charts.niceTicks(m.s0_mm, m.s0_mm + m.rows * m.cell_mm, Math.max(3, H / 60));
      g.textAlign = "center"; g.textBaseline = "bottom"; for (const t of wt.ticks) { const [x] = this.toScreen(t, 0); if (x < 40 || x > W - 62) continue; g.beginPath(); g.moveTo(x + .5, 36); g.lineTo(x + .5, 41); g.stroke(); g.fillText(Charts.fmtTick(t, wt.step), x, 33); }
      g.textAlign = "right"; g.textBaseline = "middle"; for (const t of st.ticks) { const [, y] = this.toScreen(0, t); if (y < 44 || y > H - 8) continue; g.beginPath(); g.moveTo(46, y + .5); g.lineTo(51, y + .5); g.stroke(); g.fillText(Charts.fmtTick(t, st.step), 42, y); }
      g.textAlign = "left"; g.textBaseline = "top"; g.fillText("w along wheel axis [mm] →", 54, 8); g.save(); g.translate(10, H / 2); g.rotate(-Math.PI / 2); g.textAlign = "center"; g.fillText("s along circumference [mm] →", 0, 0); g.restore(); g.globalAlpha = 1;
      // grooves
      if (this.o.showGrooves) for (const gr of this.grooves) { if (gr.kind === "other" || !gr.centerline_mm || gr.centerline_mm.length < 1) continue; const cl = gr.centerline_mm; g.strokeStyle = "rgba(255,255,255,.85)"; g.lineWidth = 1.5; g.setLineDash([5, 4]); g.beginPath();
        cl.forEach((p, k) => { const [x, y] = this.toScreen(p[1], p[0]); k ? g.lineTo(x, y) : g.moveTo(x, y); }); g.stroke(); g.setLineDash([]);
        const mid = cl[Math.floor(cl.length / 2)], [x, y] = this.toScreen(mid[1], mid[0]), lab = (gr.kind === "longitudinal" ? "G" + gr.position_index : "L" + gr.id) + "  " + fmt(gr.depth_m * 1e3, 1);
        g.font = "600 11px " + Charts.css("--font"); const tw = g.measureText(lab).width; g.fillStyle = "rgba(10,14,19,.78)"; g.beginPath(); g.roundRect(x - tw / 2 - 5, y - 9, tw + 10, 18, 5); g.fill(); g.fillStyle = "#fff"; g.textAlign = "center"; g.textBaseline = "middle"; g.fillText(lab, x, y + .5); }
      // region
      const reg = this.tmp ? (() => { const a = this.toData(this.tmp[0], this.tmp[1]), b = this.toData(this.tmp[2], this.tmp[3]); return { s0: a.s, s1: b.s, w0: a.w, w1: b.w }; })() : this.region;
      if (reg) { const [x0, y0] = this.toScreen(Math.min(reg.w0, reg.w1), Math.min(reg.s0, reg.s1)), [x1, y1] = this.toScreen(Math.max(reg.w0, reg.w1), Math.max(reg.s0, reg.s1)); g.fillStyle = "rgba(59,130,246,.18)"; g.strokeStyle = "#60a5fa"; g.lineWidth = 1.5; g.setLineDash([6, 4]); g.fillRect(x0, y0, x1 - x0, y1 - y0); g.strokeRect(x0, y0, x1 - x0, y1 - y0); g.setLineDash([]); }
      // pins
      this.pins.forEach((p, k) => { const [x, y] = this.toScreen(p.w_mm, p.s_mm); const sel = p.id === this.o.selPin; g.fillStyle = sel ? "#fff" : "#0b1017"; g.strokeStyle = sel ? "#0a8c7b" : "#fff"; g.lineWidth = 2; g.beginPath(); g.arc(x, y, 9, 0, 6.283); g.fill(); g.stroke(); g.fillStyle = sel ? "#0a8c7b" : "#fff"; g.font = "700 10.5px " + Charts.css("--font"); g.textAlign = "center"; g.textBaseline = "middle"; g.fillText(String(k + 1), x, y + .5); });
      // colourbar
      const bx = W - 46, by = 48, bh = Math.min(240, H - 70), grad = g.createLinearGradient(0, by + bh, 0, by); for (let k = 0; k <= 10; k++) { const c = Charts.cmap(this.o.cmap, k / 10); grad.addColorStop(k / 10, `rgb(${c[0] | 0},${c[1] | 0},${c[2] | 0})`); }
      g.fillStyle = grad; g.fillRect(bx, by, 12, bh); g.strokeStyle = txt; g.strokeRect(bx + .5, by + .5, 12, bh); g.fillStyle = txt; g.textAlign = "left"; g.textBaseline = "middle"; g.font = "11px " + Charts.css("--font");
      const ct = Charts.niceTicks(0, this.o.vmax, 5); for (const t of ct.ticks) { const y = by + bh - t / this.o.vmax * bh; g.fillText(Charts.fmtTick(t, ct.step), bx + 17, y); } g.textBaseline = "bottom"; g.fillText("mm", bx, by - 5);
    }
    destroy() { this.ro.disconnect(); }
  }
  App.DepthMap = DepthMap;

  /* ================= small helpers shared by tabs ================= */
  const R = () => App.curResult();
  const longi = (r) => r.report.grooves.filter((g) => g.kind === "longitudinal").sort((a, b) => a.w_center_m - b.w_center_m);
  App.longi = longi;
  function mapControls(dm, onChange) {
    const cm = App.selectInput(State.cmap, Charts.cmapNames().map((n) => [n, n === "tread" ? "Tread (green→red)" : n[0].toUpperCase() + n.slice(1)]), (v) => { State.cmap = v; dm.setStyle({ cmap: v }); onChange && onChange(); }, { height: "24px", width: "150px", fontSize: "12px", padding: "0 8px" });
    const vm = h("input", { type: "range", min: 2, max: 16, step: 0.5, value: State.vmax, "aria-label": "Colour scale maximum", style: { width: "80px" }, oninput: (e) => { State.vmax = +e.target.value; vml.textContent = State.vmax + " mm"; dm.setStyle({ vmax: State.vmax }); onChange && onChange(); } });
    const vml = h("b", null, State.vmax + " mm");
    return [cm, h("span", { class: "chip" }, "Scale max", vm, vml)];
  }
  App.mapControls = mapControls;

  /* ================= left: parameters ================= */
  const PRESETS = { car: { name: "Passenger car", tire: { tread_half_width_mm: 100, radius_min_mm: 250, radius_max_mm: 400 } }, suv: { name: "SUV / light truck", tire: { tread_half_width_mm: 120, radius_min_mm: 300, radius_max_mm: 500 } }, truck: { name: "Truck (large)", tire: { tread_half_width_mm: 140, radius_min_mm: 420, radius_max_mm: 650 } } };
  function paramsCollapsed() {
    return h("div", { class: "card", style: { display: "flex", flexDirection: "column", alignItems: "center", gap: "10px", padding: "10px 0", height: "100%" } },
      h("button", { class: "btn icon", title: "Show parameters", "aria-label": "Show parameters", onclick: () => { State.paramsOpen = true; App.render(); } }, ico("sliders")),
      h("button", { class: "btn primary icon", title: "Run analysis (Ctrl/⌘ + Enter)", "aria-label": "Run analysis", disabled: !App.curScan(), onclick: App.runAnalysis }, ico("play")),
      h("div", { class: "faint", style: { writingMode: "vertical-rl", transform: "rotate(180deg)", fontSize: "11px", letterSpacing: ".08em", textTransform: "uppercase", marginTop: "6px" } }, "Parameters"));
  }
  function paramsPanel() {
    if (State.paramsOpen === false) return paramsCollapsed();
    const P = State.params, smv = h("b", { class: "num", style: { minWidth: "40px", textAlign: "right" } }, P.recon.smoothing_sigma ? "σ " + P.recon.smoothing_sigma : "off"),
      smw = h("div", { class: "banner warn", style: { display: P.recon.smoothing_sigma ? "" : "none", fontSize: "12px" } }, ico("alert"), h("div", null, h("b", null, "Smoothing reduces depth. "), "In tests σ = 1 cell turned 8.0 mm grooves into 7.4 mm.")), sec = (t) => h("div", { class: "section-t", style: { marginTop: "14px" } }, t);
    const run = h("button", { class: "btn primary lg grow", disabled: !App.curScan() || (State.busy && State.busy.status === "running"), onclick: App.runAnalysis, title: "Ctrl/⌘ + Enter" }, ico("play"), "Run analysis");
    return h("div", { class: "card", style: { display: "flex", flexDirection: "column", height: "100%", minHeight: 0 } },
      h("div", { class: "card-h" }, h("h3", null, ico("sliders"), "Parameters"), h("div", { class: "row" }, h("button", { class: "btn ghost sm", title: "Hide the parameter panel", onclick: () => { State.paramsOpen = false; App.render(); } }, "Hide"), h("button", { class: "btn ghost sm", onclick: () => { for (const k of Object.keys(P)) Object.assign(P[k], JSON.parse(JSON.stringify(DEFAULT_PARAMS_JS()[k]))); App.savePrm(); App.render(); } }, "Reset"))),
      h("div", { style: { overflow: "auto", padding: "12px 14px", flex: 1 } }, h("div", { class: "stack tight" },
        App.field("Tire preset", App.selectInput("", [["", "Choose a preset…"], ...Object.entries(PRESETS).map(([k, v]) => [k, v.name])], (v) => { if (v) { Object.assign(P.tire, PRESETS[v].tire); App.savePrm(); App.render(); } })),
        sec("Tire geometry"),
        App.field("Wheel axis direction", App.unitInput("tire.axis_hint", "", { text: true, placeholder: "auto, or e.g. 0,1,0" }), "optional"),
        App.field("Tread half-width", App.unitInput("tire.tread_half_width_mm", "mm"), "half the tread width"),
        h("div", { class: "grid2" }, App.field("Radius min", App.unitInput("tire.radius_min_mm", "mm")), App.field("Radius max", App.unitInput("tire.radius_max_mm", "mm"))),
        App.field("Expected longitudinal grooves", App.unitInput("tire.expected_grooves", ""), "used by checks"),
        sec("Filtering"),
        App.toggleRow("Remove outliers", "filter.outlier_enabled", "Statistical filter on the tread points"),
        P.filter.outlier_enabled ? h("div", { class: "grid2" }, App.field("Neighbours k", App.unitInput("filter.outlier_k", "")), App.field("Std ratio", App.unitInput("filter.outlier_std", "σ"))) : null,
        h("div", { class: "faint", style: { fontSize: "11.5px" } }, "The tread is never downsampled; display subsampling is for drawing only."),
        sec("Surface"),
        App.field("Cell size", h("div", { class: "row" }, h("div", { class: "seg" }, ["auto", "manual"].map((m) => h("button", { "aria-pressed": (P.recon.cell_mm === "auto") === (m === "auto"), onclick: () => { P.recon.cell_mm = m === "auto" ? "auto" : 3; App.savePrm(); App.render(); } }, m))),
          P.recon.cell_mm === "auto" ? null : h("div", { class: "grow" }, App.unitInput("recon.cell_mm", "mm")))),
        App.field("Smoothing", h("div", { class: "row" }, h("input", { type: "range", min: 0, max: 3, step: 0.25, value: P.recon.smoothing_sigma, "aria-label": "Smoothing sigma", oninput: (e) => { P.recon.smoothing_sigma = +e.target.value; smv.textContent = P.recon.smoothing_sigma ? "σ " + P.recon.smoothing_sigma : "off"; smw.style.display = P.recon.smoothing_sigma ? "" : "none"; App.savePrm(); } }),
          smv), "keep off to preserve groove depth"), smw,
        sec("Detection"),
        App.field("Groove threshold", App.unitInput("detect.threshold_mm", "mm"), "min. depth below reference"),
        App.field("Noise guard", App.unitInput("detect.min_threshold_sigma", "× σ"), "raises threshold automatically"),
        h("div", { class: "grid2" }, App.field("Reference", App.selectInput(P.detect.ref_method, [["global_poly", "Crown polynomial"], ["rib_local", "Per-rib lines"]], (v) => { P.detect.ref_method = v; App.savePrm(); })), App.field("Poly. degree", App.selectInput(P.detect.poly_degree, [[1, "1"], [2, "2"], [3, "3"], [4, "4"]], (v) => { P.detect.poly_degree = +v; App.savePrm(); }))))),
      h("div", { style: { padding: "12px 14px", borderTop: "1px solid var(--border)", display: "flex" } }, run));
  }
  const DEFAULT_PARAMS_JS = () => ({ tire: { axis_hint: "", tread_half_width_mm: 120, radius_min_mm: 250, radius_max_mm: 500, expected_grooves: "" }, filter: { outlier_enabled: false, outlier_k: 16, outlier_std: 3 }, recon: { cell_mm: "auto", smoothing_sigma: 0, edge_jump_mm: 30 }, detect: { threshold_mm: 1.6, min_threshold_sigma: 3, ref_method: "global_poly", poly_degree: 2 } });

  /* ================= right: summary ================= */
  function summaryPanel(r) {
    if (!r) return h("div", { class: "card" }, h("div", { class: "card-b" }, App.empty("gauge", "No analysis yet", "Choose parameters and press Run analysis. Typical runtime: 2 to 10 seconds.")));
    const rep = r.report, L = longi(r), lat = rep.grooves.filter((g) => g.kind === "lateral"), d = rep.density, bad = rep.resolvability.filter((x) => !x.resolved);
    const sec = h("div", { class: "stack" },
      r.simulated ? App.banner("warn", "Simulated data.", "These numbers describe the algorithm on synthetic tire data, not the Unitree L2.") : null,
      h("div", { class: "tiles", style: { gridTemplateColumns: "1fr 1fr" } },
        App.tile("Mean depth", fmt(rep.mean_tread_depth_mm), "mm", `${L.length} longitudinal grooves`), App.tile("Min / max", `${fmt(rep.min_tread_depth_mm, 1)} / ${fmt(rep.max_tread_depth_mm, 1)}`, "mm"),
        App.tile("Land noise σ", fmt(rep.reference_surface.sigma_land_mm), "mm", "incl. surface roughness"), App.tile("Density", fmt(d.density_per_cm2_mean, 0), "pts/cm²", `spacing ${fmt(d.effective_spacing_mm, 1)} mm`),
        App.tile("Lateral grooves", String(lat.length)), App.tile("Tire radius", rep.geometry.radius_determined ? fmt(rep.geometry.fitted_radius_mm, 0) : "n/a", rep.geometry.radius_determined ? "mm" : null, rep.geometry.radius_determined ? "fitted, unvalidated" : "not determinable")),
      bad.length ? App.banner("warn", `${bad.length} groove${bad.length > 1 ? "s" : ""} not resolved.`, "Too few points across the width or depth too close to the noise. Do not trust those depths (see Density).") : (rep.resolvability.length ? App.banner("ok", "All grooves resolved", "at this noise and density.") : null),
      rep.warnings.length ? h("div", null, h("div", { class: "section-t" }, `Warnings (${rep.warnings.length})`), h("div", { class: "stack tight" }, rep.warnings.map((w) => h("div", { class: "banner warn", style: { fontSize: "12px" } }, ico("alert"), h("div", null, w))))) : null);
    return h("div", { class: "card", style: { maxHeight: "100%", overflow: "auto" } }, h("div", { class: "card-h" }, h("h3", null, ico("gauge"), "Result"), h("span", { class: "badge" }, r.name)), h("div", { class: "card-b" }, sec));
  }

  /* ================= centre tabs ================= */
  function needRun(txt) { return h("div", { class: "pane", style: { display: "grid", placeItems: "center", height: "100%", background: "var(--surface)" } }, App.empty("play", "Run the analysis first", txt || "Set the tire parameters on the left and press Run analysis.", [h("button", { class: "btn primary", onclick: App.runAnalysis }, ico("play"), "Run analysis")])); }

  function tabSeg(r) {
    if (!r) return needRun("Segmentation separates the tire from the ground, walls and other objects before anything is measured.");
    const wrap = h("div", { style: { display: "grid", gridTemplateRows: "minmax(0,1fr) auto", gap: "12px", height: "100%", minHeight: 0 } });
    const pane = h("div", { class: "pane", style: { height: "100%" } }); const viewer = new Viewer3D(pane); App.onCleanup(() => viewer.destroy());
    pane.append(h("div", { class: "overlay-tl" }, h("span", { class: "chip" }, h("span", { style: { width: "9px", height: "9px", borderRadius: "50%", background: "#8aa0b5", display: "inline-block" } }), "Removed / background"), h("span", { class: "chip" }, h("span", { style: { width: "9px", height: "9px", borderRadius: "50%", background: "var(--accent)", display: "inline-block" } }), "Tread points (colour = depth)")),
      h("div", { class: "overlay-tr" }, h("div", { class: "tool-bar" }, h("button", { class: "btn", title: "Focus the tread", "aria-label": "Focus the tread", onclick: () => viewer.fit(["tread"]) }, ico("target")), h("button", { class: "btn", title: "Whole scene", "aria-label": "Whole scene", onclick: () => viewer.fit(["raw"]) }, ico("focus")))));
    (async () => { try { const sc = App.scan(r.scan_id), rawr = await apiBin(`/api/scans/${sc.id}/points?max=60000`), raw = new Float32Array(rawr.buf);
      const col = new Float32Array(raw.length); for (let i = 0; i < col.length; i += 3) { col[i] = 0.55; col[i + 1] = 0.63; col[i + 2] = 0.71; }
      viewer.setLayer("raw", { type: "points", positions: raw, colors: col, alpha: 0.35, size: 1.6 });
      const tp = await App.getPoints(r.id); viewer.setLayer("tread", { type: "points", positions: tp.v, colors: App.depthColors(tp.d, State.vmax), size: 2.4, pickable: false });
      viewer.setMarkers([{ p: sc.sensor_origin, label: "Sensor", color: "#3b82f6", r: 6 }]); viewer.fit(["tread"]); } catch (e) { App.fail(e); } })();
    const n = r.report.n_points, seg = r.report.segmentation, steps = [["Input points", n.input, "all returns"], ["After range filter", r.report.preprocess.n_after_range, "min/max range"], ["After ground removal", seg.n_after_ground, seg.n_ground_removed != null ? `${fmtInt(seg.n_ground_removed)} ground points removed` : "ground plane removal"],
      ["Tire cluster", n.tire_candidate, `${seg.n_clusters} cluster${seg.n_clusters === 1 ? "" : "s"} found; the largest is kept`], ["Tread band", n.tread_band, "within the fitted cylinder band and tread width"], ["Analysed", n.analysed, n.removed_by_outlier_filter ? `${n.removed_by_outlier_filter} removed by the outlier filter` : "no points removed by filtering"]];
    const max = n.input;
    const funnel = h("div", { class: "card" }, h("div", { class: "card-b", style: { padding: "12px 14px" } }, h("div", { style: { display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(190px, 1fr))", gap: "10px 22px" } },
      steps.map(([k, v, s]) => h("div", null, h("div", { class: "row", style: { justifyContent: "space-between" } }, h("span", { style: { fontWeight: 560 } }, k), h("span", { class: "num" }, fmtInt(v))), h("div", { class: "progress", style: { margin: "4px 0 3px", height: "5px" } }, h("i", { style: { width: Math.max(1.5, v / max * 100) + "%" } })), h("div", { class: "faint", style: { fontSize: "11.5px" } }, s))))));
    wrap.append(pane, funnel); return wrap;
  }

  function tabSurface(r) {
    if (!r) return needRun("The surface is built directly from the measured heights, without smoothing, so groove edges stay sharp.");
    const wrap = h("div", { style: { display: "grid", gridTemplateRows: "minmax(0,1fr) auto", gap: "12px", height: "100%", minHeight: 0 } });
    const pane = h("div", { class: "pane", style: { height: "100%" } }); const viewer = new Viewer3D(pane); App.onCleanup(() => viewer.destroy());
    const lay = State.layers || (State.layers = { mesh: true, pts: false, grooves: true });
    let mesh, pts, lines; const paint = () => { if (mesh) viewer.setLayer("mesh", { type: "mesh", positions: mesh.v, indices: mesh.f, colors: App.depthColors(mesh.d, State.vmax), visible: lay.mesh, pickable: false }); if (pts) viewer.setLayer("pts", { type: "points", positions: pts.v, colors: App.depthColors(pts.d, State.vmax), size: 2.2, visible: lay.pts }); if (lines && lines.length) viewer.setLayer("grooves", { type: "lines", positions: lines, color: [1, 1, 1], visible: lay.grooves }); };
    const toggle = (k, label) => h("label", { class: "chip", style: { cursor: "pointer" } }, h("input", { type: "checkbox", checked: lay[k], onchange: (e) => { lay[k] = e.target.checked; viewer.show(k === "pts" ? "pts" : k, lay[k]); } }), label);
    const cm = App.selectInput(State.cmap, Charts.cmapNames().map((n) => [n, n === "tread" ? "Tread" : n[0].toUpperCase() + n.slice(1)]), (v) => { State.cmap = v; paint(); }, { height: "24px", width: "110px", fontSize: "12px", padding: "0 8px" });
    pane.append(h("div", { class: "overlay-tl" }, toggle("mesh", "Surface"), toggle("pts", "Points"), toggle("grooves", "Groove centrelines"), cm),
      h("div", { class: "overlay-tr" }, h("div", { class: "tool-bar" }, h("button", { class: "btn", title: "Reset view", "aria-label": "Reset view", onclick: () => viewer.reset() }, ico("focus")), h("button", { class: "btn", title: "Top view", "aria-label": "Top view", onclick: () => { viewer.reset(); viewer.cam.pitch = 1.45; viewer.render(); } }, ico("layers")))));
    (async () => { try { [mesh, pts, lines] = await Promise.all([App.getMesh(r.id), App.getPoints(r.id), App.getGrooveLines(r.id)]); paint(); viewer.fit(["mesh"]); } catch (e) { App.fail(e); } })();
    // comparison + cross-section
    const st = r.report.depth_by_stage.filter((x) => x.kind === "longitudinal").sort((a, b) => 0), L = longi(r);
    const cmpRows = L.map((g, k) => { const x = r.report.depth_by_stage.find((y) => y.groove_id === g.id) || {}; const d1 = x.filtered_points_mm - x.raw_points_mm, d2 = x.reconstructed_mm - x.raw_points_mm; return h("tr", null, h("td", null, "G" + (k + 1)), h("td", { class: "num" }, fmt(x.raw_points_mm)), h("td", { class: "num" }, fmt(x.filtered_points_mm)), h("td", { class: "num" }, fmt(x.reconstructed_mm)), h("td", { class: "num" }, h("span", { class: "badge " + (Math.abs(d2) > 0.3 ? "warn" : "ok") }, (d2 >= 0 ? "+" : "") + fmt(d2)))); });
    const cmp = App.card("Raw vs filtered vs reconstructed", h("div", { class: "stack tight" }, h("div", { class: "tbl-wrap" }, h("table", { class: "tbl compact" }, h("thead", null, h("tr", null, ["Groove", "Raw", "Filtered", "Surface", "Δ"].map((t, i) => h("th", { class: i ? "num" : "" }, t)))), h("tbody", null, cmpRows))),
      h("div", { class: "faint", style: { fontSize: "11.5px" } }, "Depth in mm per groove at each stage. A large negative Δ means smoothing is flattening the grooves." + (State.params.recon.smoothing_sigma > 0 ? " Smoothing is ON." : " Smoothing is off."))), null, "layers", { style: {} });
    const cs = h("div", { style: { height: "190px", minWidth: 0 } }); const slider = h("input", { type: "range", min: 0, max: 1000, value: 500, "aria-label": "Slice position" });
    const csCard = App.card("Cross-section: do the grooves survive?", h("div", { class: "stack tight" }, cs, h("div", { class: "row" }, h("span", { class: "faint" }, "Slice"), slider)), null, "ruler"); const ch = new Charts.Chart(cs, { xLabel: "w [mm]", yLabel: "radial height [mm]", margin: { l: 46, r: 10, t: 8, b: 32 } }); App.onCleanup(() => ch.destroy());
    const smin = r.map.s0_mm, smax = r.map.s0_mm + r.map.rows * r.map.cell_mm;
    async function slice() { const sMm = smin + (smax - smin) * (slider.value / 1000); try { const p = await api("GET", `/api/results/${r.id}/profile?s=${sMm}&half=2.5`); ch.setSeries([{ name: "raw points", type: "scatter", x: p.raw.w_mm, y: p.raw.dr_mm, color: "#8aa0b5", size: 1.8, opacity: .8 }, { name: "reference surface", type: "line", x: p.reference.w_mm, y: p.reference.dr_mm, color: "#22c55e", width: 1.6 }, { name: "height-map / surface", type: "line", x: p.heightmap.w_mm, y: p.heightmap.dr_mm, color: "#f43f5e", width: 1.4 }]); } catch (e) { /* transient */ } }
    slider.addEventListener("input", slice); setTimeout(slice, 60);
    wrap.append(pane, h("div", { style: { display: "grid", gridTemplateColumns: "minmax(0,1.3fr) minmax(0,1fr)", gap: "12px" } }, cmp, csCard)); return wrap;
  }

  function tabGrooves(r) {
    if (!r) return needRun("The depth map shows how far each point lies below the local unworn tread surface.");
    const wrap = h("div", { style: { display: "grid", gridTemplateRows: "minmax(0,1fr) auto", gap: "12px", height: "100%", minHeight: 0 } });
    const pane = h("div", { class: "pane", style: { height: "100%" } }); const dm = new DepthMap(pane, { mode: "view" }); App.onCleanup(() => dm.destroy());
    const showG = h("label", { class: "chip", style: { cursor: "pointer" } }, h("input", { type: "checkbox", checked: true, onchange: (e) => dm.setStyle({ showGrooves: e.target.checked }) }), "Grooves");
    pane.append(h("div", { class: "overlay-bl", style: { flexWrap: "wrap", maxWidth: "75%" } }, dm.readout, showG, ...mapControls(dm)), h("div", { class: "overlay-br" }, h("span", { class: "chip faint" }, "Scroll to zoom · drag to pan · double-click to fit")));
    dm.load(r.id, r.report.grooves).catch(App.fail);
    pane.querySelector("canvas").addEventListener("pointerdown", () => { dm.o.mode = "pan"; }); 
    const rows = r.report.grooves.filter((g) => g.kind !== "other").sort((a, b) => (a.kind === b.kind ? a.w_center_m - b.w_center_m : a.kind < b.kind ? 1 : -1));
    const tbl = h("table", { class: "tbl" }, h("thead", null, h("tr", null, ["", "Kind", "Position w", "Width", "Length", "Depth", "Range", "Points in core"].map((t, i) => h("th", { class: i > 1 ? "num" : "" }, t)))),
      h("tbody", null, rows.map((g) => { const res = r.report.resolvability.find((x) => x.groove_id === g.id); return h("tr", null, h("td", null, h("b", null, g.kind === "longitudinal" ? "G" + g.position_index : "L" + g.id)), h("td", null, g.kind, " ", res && !res.resolved ? h("span", { class: "badge warn" }, "unresolved") : null), h("td", { class: "num" }, fmt(g.w_center_m * 1e3, 1), " mm"), h("td", { class: "num" }, fmt(g.width_m * 1e3, 1), " mm"), h("td", { class: "num" }, fmt(g.length_m * 1e3, 0), " mm"), h("td", { class: "num" }, h("b", null, fmt(g.depth_m * 1e3, 2)), " mm"), h("td", { class: "num faint" }, fmt(g.depth_min_m * 1e3, 1), "–", fmt(g.depth_max_m * 1e3, 1)), h("td", { class: "num" }, fmtInt(g.n_points_core))); })));
    wrap.append(pane, h("div", { class: "card", style: { maxHeight: "210px", overflow: "auto" } }, tbl)); return wrap;
  }

  function tabDensity(r) {
    if (!r) return needRun("Density and noise decide whether the sensor can resolve the grooves at all.");
    const d = r.report.density, rs = r.report.resolvability, c = State.info.pipeline_defaults;
    const tiles = h("div", { class: "tiles" }, App.tile("NN spacing", fmt(d.nn_median_mm, 2), "mm", "median, 3D"), App.tile("Effective spacing", fmt(d.effective_spacing_mm, 2), "mm", "1/√density"), App.tile("Surface density", fmt(d.density_per_cm2_mean, 1), "pts/cm²", `median cell ${fmt(d.density_per_cm2_median_cell, 1)}`),
      App.tile("Land noise (σ)", fmt(r.report.reference_surface.sigma_land_mm, 2), "mm", "upper bound: noise + roughness"), App.tile("Cell scatter", fmt(d.cell_noise_std_mm, 2), "mm", `${fmtInt(d.n_cells)} land cells`), App.tile("Empty cells", fmt(d.empty_cell_fraction_in_bbox * 100, 0), "%", "within the map"));
    const rows = rs.map((x) => h("tr", null, h("td", null, h("b", null, x.kind === "longitudinal" ? "G" + (R().report.grooves.find((g) => g.id === x.groove_id) || {}).position_index : "L" + x.groove_id)), h("td", null, x.kind), h("td", { class: "num" }, fmt(x.width_mm, 1)), h("td", { class: "num" }, fmt(x.depth_mm, 2)), h("td", { class: "num" }, fmt(x.points_across_width, 1)), h("td", { class: "num" }, fmtInt(x.points_in_core)), h("td", { class: "num" }, fmt(x.depth_over_noise, 1), "×"), h("td", { class: "num" }, "±", fmt(x.depth_random_uncertainty_mm, 2)), h("td", null, x.resolved ? h("span", { class: "badge ok" }, ico("check"), "resolved") : h("span", { class: "badge bad" }, ico("alert"), x.plausible_width === false ? "implausible" : !x.resolved_width ? "too few points" : "near noise"))));
    return h("div", { class: "stack", style: { overflow: "auto", height: "100%", paddingBottom: "4px" } }, tiles,
      App.card("Can the sensor resolve each groove?", h("div", { class: "stack tight" }, h("div", { class: "tbl-wrap" }, h("table", { class: "tbl" }, h("thead", null, h("tr", null, ["", "Kind", "Width mm", "Depth mm", "Points across", "Points in core", "Depth / noise", "Random σ", "Verdict"].map((t, i) => h("th", { class: i > 1 && i < 8 ? "num" : "" }, t)))), h("tbody", null, rows))),
        h("div", { class: "faint", style: { fontSize: "11.5px", maxWidth: "90ch" } }, `A groove counts as resolved with ≥ ${c.density.min_points_across_groove} points across its width and depth ≥ ${c.density.min_depth_over_noise}× the single-point noise. The random σ covers independent noise only: systematic effects (beam footprint, occlusion in narrow grooves, range bias on rubber) are what the Accuracy step measures against a gauge.`)), null, "ruler"));
  }

  /* ================= view ================= */
  App.views.tread = function (root) {
    root.classList.add("no-pad");
    const r = R(), sc = App.curScan();
    if (!sc) { root.classList.remove("no-pad"); return root.append(App.empty("cloud", "No scan loaded", "Load a scan first.", [h("button", { class: "btn primary", onclick: () => App.go("data", "load") }, "Go to Load scan")])); }
    if (State.runError) $("#banner-root").append(App.banner("bad", "Analysis failed.", State.runError));
    const tabs = [["seg", "Segmentation", tabSeg], ["surface", "Surface", tabSurface], ["grooves", "Grooves", tabGrooves], ["density", "Density", tabDensity]];
    const cur = tabs.find((t) => t[0] === State.tab.tread) || tabs[0];
    const centre = h("div", { style: { display: "grid", gridTemplateRows: "auto minmax(0,1fr)", gap: "12px", height: "100%", minHeight: 0 } },
      h("div", { class: "tabs", role: "tablist" }, tabs.map((t) => h("button", { role: "tab", "aria-selected": t[0] === cur[0], onclick: () => { State.tab.tread = t[0]; App.render(); } }, t[1]))),
      h("div", { style: { minHeight: 0 }, role: "tabpanel" }, cur[2](r)));
    root.append(h("div", { class: "split", style: { gridTemplateColumns: (State.paramsOpen === false ? "56px" : "300px") + " minmax(0,1fr) 340px", padding: "16px 20px", height: "100%", minHeight: 0, alignItems: "stretch" } }, paramsPanel(), centre, h("div", { style: { minHeight: 0, overflow: "auto" } }, summaryPanel(r))));
  };
  const $ = (s, root) => (root || document).querySelector(s);
})();
