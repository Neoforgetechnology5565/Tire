"use strict";
(function () {
  const { h, ico, State, api, fmt, fmtInt } = App;
  const A = State.accuracy;

  const MEANING = {
    A: ["Suitable", "The measured depth stays within the ±1.0 mm target (95 % of single measurements) with good repeatability, on real data."],
    B: ["Usable, limited", "Works, but the achieved accuracy is worse than ±1.0 mm. State the achieved figure honestly."],
    C: ["Insufficient", "The sensor at this set-up cannot give usable tread depth. Do not hide this result."],
    INCONCLUSIVE: ["Inconclusive", "Not enough paired measurements or repeated scans to judge."],
    NOT_ASSESSED: ["Not assessed", "The data is not marked as real. Simulated or unknown data can never produce a statement about the Unitree L2."],
  };

  async function run() {
    const ids = [...A.pickIds]; if (!ids.length) return App.toast("Tick at least one scan", "bad");
    const ref = A.rows.filter((r) => r.ref_depth_mm !== "" && r.ref_depth_mm != null).map((r) => ({ groove_index: +r.groove_index, ref_depth_mm: +r.ref_depth_mm }));
    if (!ref.length) return App.toast("Enter at least one gauge reading", "bad");
    try { const out = await App.runJob(api("POST", "/api/validate", { scan_ids: ids, reference: ref, origin: A.origin, params: App.analysisParams(), tire_id: State.tireId })); A.out = out.validation; A.error = null; State.validated = true; }
    catch (e) { A.error = e.message; A.out = null; }
    App.render();
  }
  function pasteModal() {
    const ta = h("textarea", { class: "input", rows: 8, placeholder: "groove_index,ref_depth_mm\n1,7.62\n2,7.95\n3,8.04\n4,7.55" });
    const m = App.modal({ title: "Paste gauge readings (CSV)", body: h("div", { class: "stack tight" }, h("p", { class: "muted" }, "One row per groove, numbered 1…N from the left as seen from the sensor. A header line is optional."), ta),
      footer: [h("button", { class: "btn", onclick: () => m.close() }, "Cancel"), h("button", { class: "btn primary", onclick: () => {
        const rows = ta.value.split(/\r?\n/).map((l) => l.trim()).filter((l) => l && !/[a-z]/i.test(l)).map((l) => l.split(/[,;\t ]+/)); const parsed = rows.map((c) => ({ groove_index: +c[0], ref_depth_mm: c[1] })).filter((r) => isFinite(r.groove_index) && r.ref_depth_mm !== undefined && isFinite(+r.ref_depth_mm));
        if (!parsed.length) return App.toast("No readable rows", "bad"); A.rows = parsed; m.close(); App.render(); } }, "Use these readings")] });
  }

  function inputs() {
    const scans = State.scans; if (!A.pickIds) A.pickIds = new Set(scans.map((s) => s.id));
    const anySim = scans.some((s) => A.pickIds.has(s.id) && s.simulated);
    if (anySim && A.origin === "real") A.origin = "simulated";
    const ngrooves = App.curResult() ? App.longi(App.curResult()).length : 0;
    const checks = [[A.pickIds.size >= 3, `≥ 3 repeated scans of the same tire (${A.pickIds.size} ticked)`], [A.rows.filter((r) => r.ref_depth_mm !== "").length * Math.max(1, A.pickIds.size) >= 10, "≥ 10 paired measurements (grooves × scans)"], [A.origin === "real", "Data marked as real (physical L2 on a physical tire)"]];
    return h("div", { class: "card", style: { display: "flex", flexDirection: "column", height: "100%", minHeight: 0 } }, h("div", { class: "card-h" }, h("h3", null, ico("ruler"), "Inputs")),
      h("div", { style: { overflow: "auto", padding: "14px", flex: 1 } }, h("div", { class: "stack" },
        h("div", null, h("div", { class: "section-t" }, "1 · Scans of the same tire"), h("div", { class: "stack tight" }, scans.map((s) => h("label", { class: "row", style: { padding: "5px 2px", cursor: "pointer" } },
          h("input", { type: "checkbox", checked: A.pickIds.has(s.id), onchange: (e) => { e.target.checked ? A.pickIds.add(s.id) : A.pickIds.delete(s.id); App.render(); } }), h("span", { class: "grow", style: { overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" } }, s.name), s.simulated ? h("span", { class: "badge warn" }, "SIM") : h("span", { class: "badge" }, "REAL"))))),
        h("div", null, h("div", { class: "section-t" }, "2 · Where does the data come from?"), h("div", { class: "seg", role: "group" }, [["real", "Real"], ["simulated", "Simulated"], ["unknown", "Unknown"]].map(([v, l]) => h("button", { "aria-pressed": A.origin === v, disabled: v === "real" && anySim, title: v === "real" && anySim ? "A selected scan is marked simulated" : "", style: v === "real" && anySim ? { opacity: .4, cursor: "not-allowed" } : {}, onclick: () => { A.origin = v; App.render(); } }, l))),
          anySim ? h("div", { class: "faint", style: { fontSize: "11.5px", marginTop: "6px" } }, "A selected scan is simulated, so “Real” is locked.") : null),
        h("div", null, h("div", { class: "row", style: { justifyContent: "space-between", marginBottom: "8px" } }, h("div", { class: "section-t", style: { margin: 0 } }, "3 · Gauge readings (mm)"), h("div", { class: "row", style: { gap: "4px" } }, h("button", { class: "btn sm ghost", onclick: pasteModal }, "Paste CSV"), anySim && A.origin !== "real" ? h("button", { class: "btn sm ghost", title: "Fill the simulator's true depths (8.0 mm)", onclick: () => { A.rows = [1, 2, 3, 4].map((i) => ({ groove_index: i, ref_depth_mm: 8 })); App.render(); } }, "Demo readings") : null, ngrooves ? h("button", { class: "btn sm ghost", title: "Use the groove count found in the analysis", onclick: () => { while (A.rows.length < ngrooves) A.rows.push({ groove_index: A.rows.length + 1, ref_depth_mm: "" }); A.rows = A.rows.slice(0, ngrooves); App.render(); } }, `${ngrooves} grooves`) : null)),
          h("div", { class: "stack tight" }, A.rows.map((r, k) => h("div", { class: "row" }, h("span", { class: "badge accent", style: { minWidth: "56px", justifyContent: "center" } }, "Groove " + r.groove_index), h("div", { class: "input-unit grow" }, h("input", { class: "input num", type: "number", step: "0.01", placeholder: "gauge depth", value: r.ref_depth_mm, "aria-label": "Gauge depth groove " + r.groove_index, oninput: (e) => { r.ref_depth_mm = e.target.value; } }), h("span", { class: "u" }, "mm")),
            h("button", { class: "btn ghost icon sm", "aria-label": "Remove row", onclick: () => { A.rows.splice(k, 1); A.rows.forEach((x, i) => (x.groove_index = i + 1)); App.render(); } }, ico("x")))),
            h("button", { class: "btn sm", style: { alignSelf: "flex-start" }, onclick: () => { A.rows.push({ groove_index: A.rows.length + 1, ref_depth_mm: "" }); App.render(); } }, ico("plus"), "Add groove")),
          h("div", { class: "faint", style: { fontSize: "11.5px", marginTop: "8px" } }, "Number the grooves 1…N from the left as seen from the sensor (+w). Use a calibrated digital gauge at the same spots; record its own uncertainty.")),
        h("div", { class: "card", style: { background: "var(--surface-2)", boxShadow: "none" } }, h("div", { class: "card-b", style: { padding: "10px 12px" } }, h("div", { class: "section-t" }, "Needed for a verdict"), h("div", { class: "stack tight" }, checks.map(([ok, t]) => h("div", { class: "row", style: { alignItems: "flex-start", gap: "8px" } }, h("span", { class: "badge " + (ok ? "ok" : ""), style: { padding: "0 4px" } }, ico(ok ? "check" : "x")), h("span", { class: ok ? "" : "muted" }, t)))))))),
      h("div", { style: { padding: "12px 14px", borderTop: "1px solid var(--border)" } }, h("button", { class: "btn primary lg", style: { width: "100%" }, disabled: State.busy && State.busy.status === "running", onclick: run }, ico("play"), "Run validation")));
  }

  function results(v) {
    if (A.error) return h("div", { class: "stack" }, App.banner("bad", "Validation could not run.", A.error));
    if (!v) return h("div", { class: "card" }, h("div", { class: "card-b" }, App.empty("ruler", "No validation yet", "Tick the repeated scans, enter the gauge readings and run the validation. The verdict is only ever produced here.", [])));
    const f = v.feasibility, key = f.result, [ttl, txt] = MEANING[key] || [key, ""], a = v.accuracy_single_scan, rp = v.repeatability, sim = v.data_origin !== "real";
    const verdict = h("div", { class: "verdict " + key }, h("div", { class: "big" }, ["A", "B", "C"].includes(key) ? key : key === "INCONCLUSIVE" ? "?" : "n/a"), h("div", { class: "grow" },
      h("div", { class: "row", style: { gap: "8px" } }, h("h2", { style: { fontSize: "18px" } }, ["A", "B", "C"].includes(key) ? `Result ${key} · ${ttl}` : ttl), sim ? h("span", { class: "badge warn" }, "origin: " + v.data_origin) : h("span", { class: "badge info" }, "real data")),
      h("p", { class: "muted", style: { margin: "4px 0 6px" } }, txt), f.summary && ["A", "B", "C"].includes(key) ? h("p", null, f.summary) : f.summary ? h("p", { class: "faint" }, f.summary) : null,
      f.result && ["A", "B", "C"].includes(key) ? h("div", { class: "row", style: { marginTop: "8px", gap: "8px" } }, h("span", { class: "badge " + (f.achievable_tight ? "ok" : "bad") }, ico(f.achievable_tight ? "check" : "x"), "±0.5 mm " + (f.achievable_tight ? "achieved" : "not achieved")), h("span", { class: "badge " + (f.achievable_loose ? "ok" : "bad") }, ico(f.achievable_loose ? "check" : "x"), "±1.0 mm " + (f.achievable_loose ? "achieved" : "not achieved")), f.resolved_groove_fraction != null ? h("span", { class: "badge" }, `${Math.round(f.resolved_groove_fraction * 100)} % grooves resolved`) : null) : null,
      (f.notes || []).map((n) => h("div", { class: "faint", style: { marginTop: "4px", fontSize: "12px" } }, "• " + n))));
    if (!a) return h("div", { class: "stack" }, verdict, v.excluded_scans.length ? App.banner("warn", "Scans excluded.", v.excluded_scans.map((e) => `${e.scan_id}: ${e.reason}`).join(" · ")) : null);
    const T = (k, val, u, s, cls) => App.tile(k, val, u, s, cls);
    const tiles = h("div", { class: "tiles" }, T("Pairs", fmtInt(a.n), "", `${v.n_scans_used} scans`), T("Bias", (a.bias_mm >= 0 ? "+" : "") + fmt(a.bias_mm), "mm", "LiDAR − gauge"), T("MAE", fmt(a.mae_mm), "mm"), T("RMSE", fmt(a.rmse_mm), "mm"), T("Std. dev.", fmt(a.std_mm), "mm"), T("Max |error|", fmt(a.max_abs_error_mm), "mm"),
      T("95 % limit", "±" + fmt(a.loa95_halfwidth_mm), "mm", "|bias| + 1.96 σ"), T("Repeatability", rp.pooled_std_mm != null ? fmt(rp.pooled_std_mm) : "–", "mm", "pooled SD over scans"), T("Within ±0.5 / ±1.0", `${Math.round(a.frac_within_0p5mm * 100)} / ${Math.round(a.frac_within_1p0mm * 100)}`, "%"), a.bias_ci_mm ? T("Bias 95 % CI", `${fmt(a.bias_ci_mm[0], 2)} … ${fmt(a.bias_ci_mm[1], 2)}`, "mm", null, "sm") : null);
    const mk = (t) => { const b = h("div", { style: { height: "230px", minWidth: 0 } }); return { b, c: h("div", { class: "card" }, h("div", { class: "card-h" }, h("h3", null, t)), h("div", { class: "card-b", style: { padding: "8px 10px 4px" } }, b)) }; };
    const c1 = mk("LiDAR vs gauge"), c2 = mk("Error vs gauge depth"), c3 = mk("Repeatability by groove");
    setTimeout(() => {
      const ref = v.pairs.map((p) => p.ref_mm), lid = v.pairs.map((p) => p.lidar_mm), err = v.pairs.map((p) => p.error_mm), lo = Math.min(...ref, ...lid) - 0.8, hi = Math.max(...ref, ...lid) + 0.8, pal = App.palette();
      const ch1 = new Charts.Chart(c1.b, { xLabel: "gauge depth [mm]", yLabel: "LiDAR depth [mm]", margin: { l: 46, r: 10, t: 8, b: 34 }, xRange: [lo, hi], yRange: [lo, hi], legend: false });
      ch1.setSeries([{ type: "band", x: [lo, hi], y: [lo - 1, hi - 1], y2: [lo + 1, hi + 1], color: pal.accent, opacity: .1 }, { type: "line", x: [lo, hi], y: [lo, hi], color: pal.text, width: 1, dash: [4, 3], noHover: true }, { name: "measurement", type: "scatter", x: ref, y: lid, color: pal.accent, size: 3.6, opacity: .85 }]); App.onCleanup(() => ch1.destroy());
      const ch2 = new Charts.Chart(c2.b, { xLabel: "gauge depth [mm]", yLabel: "error [mm]", margin: { l: 46, r: 10, t: 8, b: 34 }, yRange: [Math.min(-1.3, ...err) - .2, Math.max(1.3, ...err) + .2], legend: false });
      const xr = [Math.min(...ref) - .5, Math.max(...ref) + .5];
      ch2.setSeries([{ type: "band", x: xr, y: [-1, -1], y2: [1, 1], color: pal.warn, opacity: .1 }, { type: "band", x: xr, y: [-.5, -.5], y2: [.5, .5], color: pal.ok, opacity: .16 }, { type: "hline", y: a.bias_mm, color: pal.bad, width: 1.2, dash: [5, 3] }, { name: "error", type: "scatter", x: ref, y: err, color: pal.info, size: 3.6, opacity: .85 }]); App.onCleanup(() => ch2.destroy());
      const M = v.depth_matrix_mm, idx = v.groove_indices, ser = []; M.forEach((row) => ser.push({ name: "scan", type: "scatter", x: idx.map((g) => g), y: row, color: pal.accent, size: 3.4, opacity: .55, noHover: false }));
      const ch3 = new Charts.Chart(c3.b, { xLabel: "groove (left → right)", yLabel: "depth [mm]", margin: { l: 46, r: 10, t: 8, b: 34 }, xRange: [idx[0] - .6, idx[idx.length - 1] + .6], legend: false, tip: (s, i) => `groove ${s.x[i]}<br>${fmt(s.y[i], 2)} mm` });
      ser.push({ name: "gauge", type: "scatter", x: idx, y: v.reference_mm, color: pal.bad, size: 6, opacity: 1 }); ch3.setSeries(ser); App.onCleanup(() => ch3.destroy());
    }, 30);
    const pairs = h("table", { class: "tbl" }, h("thead", null, h("tr", null, ["Scan", "Groove", "Gauge mm", "LiDAR mm", "Error mm"].map((t, i) => h("th", { class: i > 1 ? "num" : "" }, t)))), h("tbody", null, v.pairs.map((p) => h("tr", null, h("td", null, p.scan_id), h("td", null, p.groove_index), h("td", { class: "num" }, fmt(p.ref_mm)), h("td", { class: "num" }, fmt(p.lidar_mm)), h("td", { class: "num", style: { color: Math.abs(p.error_mm) > 1 ? "var(--bad)" : Math.abs(p.error_mm) > .5 ? "var(--warn)" : "var(--ok)", fontWeight: 600 } }, (p.error_mm >= 0 ? "+" : "") + fmt(p.error_mm))))));
    return h("div", { class: "stack loose" }, verdict, v.excluded_scans.length ? App.banner("warn", "Some scans were excluded.", v.excluded_scans.map((e) => `${e.scan_id}: ${e.reason}`).join(" · ")) : null, tiles,
      h("div", { style: { display: "grid", gridTemplateColumns: "repeat(3, minmax(0,1fr))", gap: "12px" } }, c1.c, c2.c, c3.c),
      App.card("Paired measurements", h("div", { class: "tbl-wrap", style: { maxHeight: "260px" } }, pairs), [h("button", { class: "btn sm", onclick: () => App.download("validation_pairs.csv", "scan,groove,gauge_mm,lidar_mm,error_mm\n" + v.pairs.map((p) => [p.scan_id, p.groove_index, p.ref_mm, p.lidar_mm, p.error_mm].join(",")).join("\n")) }, ico("download"), "CSV")], null, { flush: true }));
  }

  App.views.accuracy = function (root) {
    root.classList.add("no-pad");
    if (!State.scans.length) { root.classList.remove("no-pad"); return root.append(App.empty("ruler", "No scans loaded", "Load several repeated scans of the same tire first.", [h("button", { class: "btn primary", onclick: () => App.go("data", "load") }, "Load scans")])); }
    if (!A.rows.length) A.rows.push({ groove_index: 1, ref_depth_mm: "" });
    root.append(h("div", { style: { display: "grid", gridTemplateColumns: "360px minmax(0,1fr)", gap: "16px", padding: "16px 20px", height: "100%", minHeight: 0 } }, inputs(), h("div", { style: { overflow: "auto", minHeight: 0, paddingRight: "2px" } },
      App.pageHead("Accuracy and repeatability", "Compare LiDAR depths with real gauge readings. This is the only place the app states whether the L2 is suitable, and it refuses to do so for simulated data."), results(A.out))));
  };
})();
