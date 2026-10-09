"use strict";
(function () {
  const { h, ico, State, api, fmt, fmtInt, fmtSize } = App;
  const E = State.exportSt = State.exportSt || { dir: "", tire: "TIRE_001", scan: "", out: null, ftDir: "", ftOut: null };

  const FORMATS = [["*_points.ply", "Point cloud", "Tread points with normals, depth colours and per-point depth (mm)"], ["*_mesh.ply", "Mesh (PLY)", "Binary mesh with vertex colours and depth; metadata in the header"], ["*_mesh.stl", "Mesh (STL)", "Binary STL for CAD / printing"], ["*_mesh.obj", "Mesh (OBJ)", "With vertex normals"], ["*_report.json", "Report (JSON)", "Depth statistics, grooves, density, resolvability, raw-vs-filtered-vs-reconstructed, warnings"], ["*_grooves.csv", "Grooves (CSV)", "One row per detected groove"], ["*_depth_map.png, *_cross_section.png", "Figures", "Depth map and cross-section"]];
  const folderRow = (key, label) => h("div", { class: "field" }, h("label", null, label), h("div", { class: "row" }, h("input", { class: "input num", value: E[key], placeholder: "Choose or type a folder (it is created if missing)", "aria-label": label, oninput: (e) => { E[key] = e.target.value; } }),
    h("button", { class: "btn", onclick: () => App.fileBrowser({ mode: "dir", onPick: (p) => { E[key] = p; App.render(); }, title: "Choose output folder" }) }, ico("folder"), "Browse")));
  const fileList = (o) => h("div", { class: "stack tight" }, h("div", { class: "row" }, ico("check"), h("b", null, `Written to ${o.dir}`)), h("div", { class: "card", style: { boxShadow: "none" } }, h("table", { class: "tbl" }, h("tbody", null, o.files.map((f) => h("tr", null, h("td", { style: { width: "34px" } }, ico("file")), h("td", null, f.name), h("td", { class: "num faint" }, fmtSize(f.size))))))));

  App.views.export = function (root) {
    const r = App.curResult(), ft = State.fulltire.out;
    root.append(App.pageHead("Export", "Write the reconstruction and reports to a folder you choose, or download everything as one zip."));
    if (!r && !ft) return root.append(App.empty("download", "Nothing to export yet", "Run the tread analysis (or the full-tire analysis) first.", [h("button", { class: "btn primary", onclick: () => App.go("tread", "seg") }, "Go to Segment tire")]));
    const cards = [];
    if (r) {
      E.scan = E.scan || r.name;
      cards.push(App.card("Single scan · " + r.name, h("div", { class: "stack" }, r.simulated ? App.banner("warn", "Simulated data.", "A note file stating this is written next to the exports.") : null,
        h("div", { class: "grid2" }, App.field("Tire ID", h("input", { class: "input", value: E.tire, oninput: (e) => { E.tire = e.target.value; } })), App.field("Scan ID", h("input", { class: "input", value: E.scan, oninput: (e) => { E.scan = e.target.value; } }))), folderRow("dir", "Output folder"),
        h("div", { class: "row" }, h("button", { class: "btn primary", onclick: async () => { try { E.out = await api("POST", `/api/results/${r.id}/export`, { dir: E.dir, tire_id: E.tire, scan_id: E.scan }); State.exported = true; App.toast("Exported " + E.out.files.length + " files", "ok"); App.render(); } catch (e) { App.fail(e); } } }, ico("download"), "Export all formats"),
          h("a", { class: "btn", href: `/api/results/${r.id}/bundle.zip`, onclick: (e) => { e.preventDefault(); fetch(`/api/results/${r.id}/bundle.zip`, { headers: { "X-Token": new URLSearchParams(location.search).get("t") } }).then((x) => x.blob()).then((b) => { const a = h("a", { href: URL.createObjectURL(b), download: "treadlidar_export.zip" }); document.body.append(a); a.click(); a.remove(); State.exported = true; App.chrome(); }).catch(App.fail); } }, ico("zip"), "Download .zip")),
        E.out ? fileList(E.out) : null), null, "cube"));
      cards.push(App.card("What is written", h("table", { class: "tbl" }, h("thead", null, h("tr", null, h("th", null, "File"), h("th", null, "Format"), h("th", null, "Contents"))), h("tbody", null, FORMATS.map((f) => h("tr", null, h("td", { class: "mono" }, f[0]), h("td", null, f[1]), h("td", { class: "muted", style: { whiteSpace: "normal" } }, f[2]))))), null, "file", { flush: true }));
    }
    if (ft) cards.push(App.card("Full tire", h("div", { class: "stack" }, ft.simulated ? App.banner("warn", "Simulated data.", "The rotating-wheel demo says nothing about the real L2.") : null, folderRow("ftDir", "Output folder"),
      h("div", { class: "faint", style: { fontSize: "12px" } }, "Writes the closed-ring mesh (PLY, STL, OBJ), the protocol (JSON and CSV) and the unrolled map (PNG)."),
      h("div", { class: "row" }, h("button", { class: "btn primary", onclick: async () => { try { E.ftOut = await api("POST", `/api/fulltires/${ft.id}/export`, { dir: E.ftDir }); State.exported = true; App.toast("Exported " + E.ftOut.files.length + " files", "ok"); App.render(); } catch (e) { App.fail(e); } } }, ico("download"), "Export full tire")), E.ftOut ? fileList(E.ftOut) : null), null, "ring"));
    root.append(h("div", { class: "stack loose", style: { maxWidth: "900px" } }, cards));
  };

  /* ================= Sensor check (tool) ================= */
  const S = State.sensor = State.sensor || { tool: "plane", tol: 10, known: "", out: null, err: null, roi: { x: "", y: "", z: "", r: "" } };
  App.views.sensor = function (root) {
    root.append(App.pageHead("Sensor check", "Characterise the L2 on simple targets, without a tire. If it cannot measure an 8 mm step to about ±1 mm here, no tire algorithm can fix that."));
    const sc = App.curScan();
    const how = App.card("How to record the target", h("div", { class: "stack tight" }, h("div", null, h("b", null, "Flat target. "), "A matte, rigid board at the working distance (0.4 to 1.0 m). Gives the range noise, point spacing and density."), h("div", null, h("b", null, "Step target. "), "Stacked gauge blocks or a machined step of known height (2, 4, 6, 8 mm), dark and matte like rubber. Gives the step error directly."),
      h("div", { class: "faint" }, "Load the recording as a scan; the tool analyses the whole loaded cloud, so crop it to the target first. Repeat at several distances and put the results into config/sensor_l2.yaml.")), null, "info");
    const run = async () => { try { const R = S.roi, roi = R.r !== "" && R.x !== "" ? { center: [+R.x, +R.y || 0, +R.z || 0], radius_m: +R.r } : null; S.out = await api("POST", "/api/tools", { tool: S.tool, scan_id: sc.id, tol_mm: S.tol, known_mm: S.known, roi }); S.err = null; } catch (e) { S.err = e.message; S.out = null; } App.render(); };
    const form = App.card("Run a check", h("div", { class: "stack" }, sc ? null : App.banner("warn", "No scan loaded.", "Load the target recording first."),
      h("div", { class: "seg", role: "group" }, [["plane", "Flat target noise"], ["step", "Step height"]].map(([v, l]) => h("button", { "aria-pressed": S.tool === v, onclick: () => { S.tool = v; S.out = null; App.render(); } }, l))),
      h("div", { class: "field" }, h("label", null, "Scan", h("span", { class: "hint" }, "from the top bar")), h("div", { class: "input num", style: { display: "flex", alignItems: "center" } }, sc ? sc.name : "—")),
      App.field("Inlier tolerance", h("div", { class: "input-unit" }, h("input", { class: "input num", type: "number", step: "any", value: S.tol, oninput: (e) => { S.tol = +e.target.value; } }), h("span", { class: "u" }, "mm")), "set above ~4σ"),
      S.tool === "step" ? App.field("Known step height", h("div", { class: "input-unit" }, h("input", { class: "input num", type: "number", step: "any", value: S.known, placeholder: "optional", oninput: (e) => { S.known = e.target.value; } }), h("span", { class: "u" }, "mm"))) : null,
      h("div", { class: "field" }, h("label", null, "Crop to a sphere (optional)", h("span", { class: "hint" }, "centre x, y, z · radius, in metres")), h("div", { class: "grid2", style: { gridTemplateColumns: "repeat(4, 1fr)" } }, ["x", "y", "z", "r"].map((k) => h("input", { class: "input num", type: "number", step: "any", placeholder: k === "r" ? "radius" : k, "aria-label": "Crop " + k, value: S.roi[k], oninput: (e) => { S.roi[k] = e.target.value; } })))),
      h("button", { class: "btn primary", disabled: !sc, onclick: run }, ico("play"), "Run check")), null, "gauge");
    let res = null;
    if (S.err) res = App.banner("bad", "Check failed.", S.err);
    else if (S.out && S.out.tool === "plane") { const o = S.out; res = App.card("Flat target result", h("div", { class: "stack" }, h("div", { class: "tiles" }, App.tile("Range noise (σ)", fmt(o.noise_std_mm, 2), "mm", `robust (MAD) ${fmt(o.noise_mad_mm, 2)} mm`), App.tile("Peak to peak", fmt(o.peak_to_peak_mm, 2), "mm"), App.tile("Point spacing", fmt(o.nn_spacing_median_mm, 2), "mm", "median nearest neighbour"), App.tile("Density", fmt(o.density_per_cm2, 1), "pts/cm²"), App.tile("Distance", fmt(o.mean_distance_m, 2), "m"), App.tile("Inliers", fmtInt(o.n_points))),
      App.banner(o.noise_std_mm <= 1 ? "ok" : o.noise_std_mm <= 2 ? "info" : "warn", "Reading it.", `A single point scatters by about ±${fmt(o.noise_std_mm, 1)} mm on a flat surface at ${fmt(o.mean_distance_m, 2)} m. Tread depths of 8 mm are ${fmt(8 / Math.max(o.noise_std_mm, 1e-6), 1)}× that noise, shallower grooves proportionally less. Averaging many points helps random noise but not bias.`)), null, "gauge"); }
    else if (S.out && S.out.tool === "step") { const o = S.out; res = App.card("Step target result", h("div", { class: "stack" }, h("div", { class: "tiles" }, App.tile("Measured step", fmt(Math.abs(o.step_mm), 2), "mm", "± " + fmt(o.std_error_mm, 2) + " standard error"), o.known_mm != null ? App.tile("Known step", fmt(o.known_mm, 2), "mm") : null, o.error_mm != null ? App.tile("Error", (o.error_mm >= 0 ? "+" : "") + fmt(o.error_mm, 2), "mm", "measured − known", Math.abs(o.error_mm) <= 0.5 ? "" : "") : null, App.tile("Noise each side", `${fmt(o.noise_each_side_mm[0], 1)} / ${fmt(o.noise_each_side_mm[1], 1)}`, "mm"), App.tile("Points each side", `${fmtInt(o.n_each_side[0])} / ${fmtInt(o.n_each_side[1])}`)),
      o.error_mm != null ? App.banner(Math.abs(o.error_mm) <= 0.5 ? "ok" : Math.abs(o.error_mm) <= 1 ? "info" : "warn", "Reading it.", `The L2 reads this ${fmt(o.known_mm, 1)} mm step ${o.error_mm >= 0 ? "too high" : "too low"} by ${fmt(Math.abs(o.error_mm), 2)} mm. This is the closest predictor of tread-depth error, before any tire effects.`) : null), null, "gauge"); }
    root.append(h("div", { style: { display: "grid", gridTemplateColumns: "minmax(300px,380px) minmax(0,1fr)", gap: "16px", alignItems: "start", maxWidth: "1100px" } }, h("div", { class: "stack" }, form, how), h("div", null, res || App.card("No result yet", App.empty("gauge", "Run a check", "Pick the tool, set the tolerance and run it on the loaded target recording."), null, "info"))));
  };
})();
