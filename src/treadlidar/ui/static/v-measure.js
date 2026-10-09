"use strict";
(function () {
  const { h, ico, State, api, fmt, fmtInt } = App;
  let uid = 1;

  async function addPin(rid, s, w) {
    const m = await api("GET", `/api/results/${rid}/measure?s=${s}&w=${w}&r=${State.mradius || 4}`);
    if (!m.valid) { App.toast("No data at that location: " + (m.reason || ""), "bad"); return null; }
    const p = { id: uid++, rid, s_mm: s, w_mm: w, depth_mm: m.depth_mm, ref_dr_mm: m.reference_dr_mm, bottom_dr_mm: m.bottom_dr_mm, n_points: m.n_points, n_cells: m.n_cells,
      dmin: m.window_depth_min_mm, dmax: m.window_depth_max_mm, wref: m.world_reference, wbot: m.world_bottom };
    State.pins.push(p); State.selPin = p.id; return p;
  }
  const csv = () => "pin,s_mm,w_mm,tread_depth_mm,reference_radial_mm,groove_bottom_radial_mm,n_points\n" + State.pins.map((p, k) => [k + 1, p.s_mm.toFixed(2), p.w_mm.toFixed(2), p.depth_mm.toFixed(3), p.ref_dr_mm.toFixed(3), p.bottom_dr_mm.toFixed(3), p.n_points].join(",")).join("\n");

  App.views.measure = function (root) {
    root.classList.add("no-pad");
    const r = App.curResult();
    if (!r) { root.classList.remove("no-pad"); return root.append(App.empty("target", "Analyse a scan first", "Pins and regions are placed on the depth map produced by the tread analysis.", [h("button", { class: "btn primary", onclick: () => App.go("tread", "seg") }, "Go to Segment tire")])); }
    const sim = r.simulated;
    const grid = h("div", { style: { display: "grid", gridTemplateColumns: "minmax(0,1.15fr) minmax(0,1fr)", gridTemplateRows: "minmax(0,1fr)", gap: "16px", padding: "16px 20px", height: "100%", minHeight: 0 } });
    const left = h("div", { style: { display: "grid", gridTemplateRows: "minmax(0,1fr) 228px", gap: "12px", minHeight: 0 } }), right = h("div", { style: { display: "grid", gridTemplateRows: "minmax(0,1fr) minmax(250px,40%)", gap: "12px", minHeight: 0 } });
    // ---- depth map
    const mapPane = h("div", { class: "pane", style: { height: "100%" } }); const mode = State.mmode || "measure";
    const dm = new App.DepthMap(mapPane, { mode, selPin: State.selPin, onPick: async (s, w) => { try { await addPin(r.id, s, w); sync(); } catch (e) { App.fail(e); } },
      onRegion: async (reg) => { try { const q = await api("GET", `/api/results/${r.id}/region?s0=${reg.s0}&s1=${reg.s1}&w0=${reg.w0}&w1=${reg.w1}`); State.region = Object.assign({}, reg, { stats: q }); sync(); } catch (e) { App.fail(e); } } });
    App.onCleanup(() => dm.destroy());
    const tools = [["measure", "target", "Measure: click to pin a location"], ["region", "region", "Region: drag a box for statistics"], ["pan", "pan", "Pan: drag to move (or hold Shift)"]];
    const tb = h("div", { class: "tool-bar" }, tools.map(([m, ic, t]) => h("button", { class: "btn", title: t, "aria-label": t, "aria-pressed": mode === m, onclick: (e) => { State.mmode = m; dm.o.mode = m; tb.querySelectorAll("button").forEach((b) => b.setAttribute("aria-pressed", "false")); e.currentTarget.setAttribute("aria-pressed", "true"); mapPane.style.cursor = m === "pan" ? "grab" : "crosshair"; } }, ico(ic))));
    mapPane.style.cursor = mode === "pan" ? "grab" : "crosshair";
    mapPane.append(h("div", { class: "overlay-br" }, tb), h("div", { class: "overlay-bl", style: { flexWrap: "wrap", maxWidth: "88%" } }, dm.readout, ...App.mapControls(dm)));
    dm.load(r.id, r.report.grooves).then(() => { dm.pins = State.pins; dm.region = State.region; dm.draw(); }).catch(App.fail);
    // ---- cross-section
    const csBox = h("div", { style: { height: "150px", minWidth: 0 } }), csTitle = h("span", { class: "faint" }, "");
    const csChart = new Charts.Chart(csBox, { xLabel: "w [mm]", yLabel: "radial height [mm]", margin: { l: 46, r: 10, t: 8, b: 32 } }); App.onCleanup(() => csChart.destroy());
    const csCard = App.card("Cross-section at the selected pin", csBox, [csTitle], "ruler", { style: {} });
    async function drawCs() {
      const pin = State.pins.find((p) => p.id === State.selPin); const sMm = pin ? pin.s_mm : r.map.s0_mm + r.map.rows * r.map.cell_mm / 2;
      csTitle.textContent = pin ? `s = ${fmt(sMm, 1)} mm` : "no pin yet · showing the middle"; try { const p = await api("GET", `/api/results/${r.id}/profile?s=${sMm}&half=2.5`);
        const ser = [{ name: "raw points", type: "scatter", x: p.raw.w_mm, y: p.raw.dr_mm, color: "#8aa0b5", size: 1.8, opacity: .8 }, { name: "reference surface", type: "line", x: p.reference.w_mm, y: p.reference.dr_mm, color: "#22c55e" }, { name: "height-map", type: "line", x: p.heightmap.w_mm, y: p.heightmap.dr_mm, color: "#f43f5e", width: 1.3 }];
        if (pin) ser.push({ name: `depth ${fmt(pin.depth_mm, 2)} mm`, type: "line", x: [pin.w_mm, pin.w_mm], y: [pin.ref_dr_mm, pin.bottom_dr_mm], color: Charts.css("--accent"), width: 3.2, noHover: true });
        csChart.setSeries(ser); } catch (e) { /* transient */ }
    }
    left.append(mapPane, csCard);
    // ---- 3D
    const pane3 = h("div", { class: "pane", style: { height: "100%" } }); const viewer = new Viewer3D(pane3); App.onCleanup(() => viewer.destroy());
    pane3.append(h("div", { class: "overlay-tl" }, h("span", { class: "chip" }, ico("cube"), "Pins appear here with their depth")), h("div", { class: "overlay-tr" }, h("div", { class: "tool-bar" }, h("button", { class: "btn", title: "Reset view", "aria-label": "Reset view", onclick: () => viewer.reset() }, ico("focus")))));
    function markers() {
      const mk = [], sg = []; State.pins.forEach((p, k) => { const sel = p.id === State.selPin; mk.push({ p: p.wref, label: `${k + 1} · ${fmt(p.depth_mm, 1)} mm`, color: sel ? "#14b8a6" : "#3b82f6", r: sel ? 7 : 5.5 }); sg.push({ a: p.wref, b: p.wbot, color: "#14b8a6", dash: [4, 3] }); });
      viewer.setMarkers(mk, sg);
    }
    App.getMesh(r.id).then((m) => { viewer.setLayer("mesh", { type: "mesh", positions: m.v, indices: m.f, colors: App.depthColors(m.d, State.vmax) }); viewer.fit(["mesh"]); markers(); }).catch(App.fail);
    right.append(pane3);
    // ---- measurement list
    const list = h("div", { class: "stack tight", style: { overflow: "auto", padding: "12px" } });
    const hd = h("div", { class: "row" }, h("button", { class: "btn sm", title: "Add a pin at every longitudinal groove centre", onclick: async () => { try { for (const g of App.longi(r)) await addPin(r.id, g.s_center_m * 1e3, g.w_center_m * 1e3); sync(); } catch (e) { App.fail(e); } } }, ico("plus"), "Groove centres"),
      h("button", { class: "btn sm", disabled: !State.pins.length, onclick: () => { navigator.clipboard ? navigator.clipboard.writeText(csv()).then(() => App.toast("Copied as CSV", "ok")).catch(() => App.download("measurements.csv", csv())) : App.download("measurements.csv", csv()); } }, ico("copy"), "Copy"),
      h("button", { class: "btn sm", disabled: !State.pins.length, onclick: () => App.download("measurements.csv", csv()) }, ico("download"), "CSV"),
      h("span", { class: "grow" }), h("label", { class: "row", style: { gap: "5px" }, title: "Pins use the median of the cells inside this radius. A larger window is steadier but averages more of the surroundings." }, h("span", { class: "faint" }, "Window"), App.selectInput(State.mradius || 4, [[2, "r 2 mm"], [3, "r 3 mm"], [4, "r 4 mm"], [6, "r 6 mm"], [8, "r 8 mm"]], (v) => { State.mradius = +v; }, { height: "26px", width: "82px", fontSize: "12px", padding: "0 6px" })),
      h("button", { class: "btn sm ghost danger", disabled: !State.pins.length && !State.region, onclick: () => { State.pins = []; State.region = null; State.selPin = null; dm.region = null; dm.pins = State.pins; sync(); } }, "Clear"));
    const listCard = h("div", { class: "card", style: { display: "flex", flexDirection: "column", minHeight: 0 } }, h("div", { class: "card-h" }, h("h3", null, ico("target"), "Measurements"), sim ? h("span", { class: "badge warn" }, "simulated") : null), h("div", { style: { padding: "10px 12px", borderBottom: "1px solid var(--border)" } }, hd), list);
    right.append(listCard); grid.append(left, right); root.append(grid);
    function sync() {
      dm.pins = State.pins; dm.region = State.region; dm.o.selPin = State.selPin; dm.draw(); markers(); drawCs(); list.innerHTML = "";
      if (State.region && State.region.stats && State.region.stats.valid) { const q = State.region.stats; list.append(h("div", { class: "card", style: { background: "var(--info-soft)", borderColor: "transparent" } }, h("div", { class: "card-b", style: { padding: "10px 12px" } },
        h("div", { class: "row", style: { justifyContent: "space-between" } }, h("b", null, "Region"), h("button", { class: "btn ghost sm", onclick: () => { State.region = null; sync(); } }, ico("x"))),
        h("div", { class: "tiles", style: { gridTemplateColumns: "repeat(4,1fr)", margin: "6px 0" } }, App.tile("Mean", fmt(q.mean_mm), "mm"), App.tile("Median", fmt(q.median_mm), "mm"), App.tile("Min", fmt(q.min_mm), "mm"), App.tile("Max", fmt(q.max_mm), "mm")),
        h("div", { class: "faint", style: { fontSize: "11.5px" } }, `${fmtInt(q.n_cells)} cells · ${fmtInt(q.n_points)} points · σ ${fmt(q.std_mm)} mm · 5–95%: ${fmt(q.p05_mm, 1)}–${fmt(q.p95_mm, 1)} mm. Includes land, so the mean is below the groove depth.`)))); }
      else if (State.region) list.append(h("div", { class: "faint" }, State.region.stats ? State.region.stats.reason : ""));
      if (!State.pins.length) { if (!State.region) list.append(App.empty("target", "No measurements yet", "Pick the Measure tool and click a groove on the depth map, or add all groove centres.")); return; }
      list.append(h("div", { class: "faint", style: { fontSize: "11.5px" } }, "A pin uses only the few cells inside its window, so it is noisier than the per-groove depth in the Grooves table (which averages the whole groove). Use a larger window or the Grooves table for the steadiest numbers."));
      State.pins.forEach((p, k) => list.append(h("div", { class: "scan-card" + (p.id === State.selPin ? " sel" : ""), style: { gridTemplateColumns: "26px 1fr auto" }, role: "button", tabindex: 0, onclick: () => { State.selPin = p.id; sync(); }, onkeydown: (e) => { if (e.key === "Enter") e.target.click(); } },
        h("span", { class: "badge accent", style: { justifyContent: "center", height: "22px", width: "22px", padding: 0 } }, String(k + 1)),
        h("div", { style: { minWidth: 0 } }, h("div", { class: "row", style: { alignItems: "baseline", gap: "6px" } }, h("b", { style: { fontSize: "18px", letterSpacing: "-0.02em" }, class: "num" }, fmt(p.depth_mm, 2)), h("span", { class: "muted" }, "mm tread depth")),
          h("div", { class: "meta tnum" }, `reference ${p.ref_dr_mm >= 0 ? "+" : ""}${fmt(p.ref_dr_mm, 2)} mm · groove bottom ${fmt(p.depth_mm, 2)} mm below it`), h("div", { class: "meta tnum" }, `s ${fmt(p.s_mm, 1)} · w ${fmt(p.w_mm, 1)} mm · ${p.n_points} pts (${fmt(p.dmin, 1)}–${fmt(p.dmax, 1)})`)),
        h("button", { class: "btn ghost icon sm", "aria-label": "Remove measurement", onclick: (e) => { e.stopPropagation(); State.pins = State.pins.filter((x) => x !== p); if (State.selPin === p.id) State.selPin = State.pins.length ? State.pins[State.pins.length - 1].id : null; sync(); } }, ico("trash")))));
    }
    sync();
  };
})();
