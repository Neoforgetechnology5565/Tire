/* Colormaps + a small canvas chart library (no dependencies, works offline). */
"use strict";
(function (G) {
  const hex = (h) => [parseInt(h.slice(1, 3), 16), parseInt(h.slice(3, 5), 16), parseInt(h.slice(5, 7), 16)];
  const STOPS = {
    tread: ["#006837", "#1a9850", "#66bd63", "#a6d96a", "#d9ef8b", "#ffffbf", "#fee08b", "#fdae61", "#f46d43", "#d73027", "#a50026"].map(hex),
    viridis: ["#440154", "#482878", "#3e4989", "#31688e", "#26828e", "#1f9e89", "#35b779", "#6dcd59", "#b4de2c", "#fde725"].map(hex),
    turbo: ["#30123b", "#4662d7", "#36aaf9", "#1ae4b6", "#72fe5e", "#c7ef34", "#faba39", "#f66b19", "#ca2a04", "#7a0403"].map(hex),
    gray: ["#10151a", "#f1f5f9"].map(hex),
  };
  function cmap(name, t) {
    const s = STOPS[name] || STOPS.tread;
    t = Math.min(1, Math.max(0, t));
    const x = t * (s.length - 1), i = Math.min(s.length - 2, Math.floor(x)), f = x - i;
    return [s[i][0] + (s[i + 1][0] - s[i][0]) * f, s[i][1] + (s[i + 1][1] - s[i][1]) * f, s[i][2] + (s[i + 1][2] - s[i][2]) * f];
  }
  const cmapNames = () => Object.keys(STOPS);
  function cmapCss(name, dir) {
    const s = STOPS[name] || STOPS.tread;
    return `linear-gradient(${dir || "to top"}, ${s.map((c, i) => `rgb(${c}) ${(100 * i / (s.length - 1)).toFixed(1)}%`).join(",")})`;
  }
  const css = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();

  function niceStep(span, n) {
    const raw = span / Math.max(1, n), p = Math.pow(10, Math.floor(Math.log10(raw))), f = raw / p;
    return (f < 1.5 ? 1 : f < 3.5 ? 2 : f < 7.5 ? 5 : 10) * p;
  }
  function niceTicks(lo, hi, n) {
    if (!(hi > lo)) { hi = lo + 1; }
    const st = niceStep(hi - lo, n), t = [];
    for (let v = Math.ceil(lo / st - 1e-9) * st; v <= hi + st * 1e-6; v += st) t.push(+v.toPrecision(12));
    return { ticks: t, step: st };
  }
  const fmtTick = (v, st) => { const d = Math.max(0, -Math.floor(Math.log10(st) + 1e-9)); return v.toFixed(Math.min(d, 4)); };
  const PALETTE = ["#14b8a6", "#3b82f6", "#f59e0b", "#f43f5e", "#8b5cf6", "#06b6d4", "#84cc16"];

  /* Tooltip singleton */
  let tipEl = null;
  function tip(html, x, y) {
    if (!tipEl) { tipEl = document.createElement("div"); tipEl.className = "tooltip"; document.body.appendChild(tipEl); }
    if (html == null) { tipEl.style.display = "none"; return; }
    tipEl.innerHTML = html; tipEl.style.display = "block";
    const r = tipEl.getBoundingClientRect();
    tipEl.style.left = Math.min(innerWidth - r.width - 8, x + 14) + "px";
    tipEl.style.top = Math.min(innerHeight - r.height - 8, y + 14) + "px";
  }

  class Chart {
    constructor(el, opt) {
      this.el = el; this.o = Object.assign({ margin: { l: 54, r: 16, t: 14, b: 40 }, legend: true, xLabel: "", yLabel: "", grid: true }, opt || {});
      this.series = []; this.hover = null;
      this.c = document.createElement("canvas"); this.c.style.cssText = "width:100%;height:100%;display:block";
      el.appendChild(this.c); this.ctx = this.c.getContext("2d");
      this.ro = new ResizeObserver(() => this.draw()); this.ro.observe(el);
      this.c.addEventListener("mousemove", (e) => this.onMove(e));
      this.c.addEventListener("mouseleave", () => { this.hover = null; tip(null); this.draw(); });
    }
    setSeries(s, ranges) { this.series = s; if (ranges) Object.assign(this.o, ranges); this.draw(); }
    bounds() {
      let x0 = Infinity, x1 = -Infinity, y0 = Infinity, y1 = -Infinity;
      for (const s of this.series) {
        if (s.type === "hline") { y0 = Math.min(y0, s.y); y1 = Math.max(y1, s.y); continue; }
        if (s.type === "vline") { x0 = Math.min(x0, s.x); x1 = Math.max(x1, s.x); continue; }
        for (let i = 0; i < s.x.length; i++) {
          const x = s.x[i], y = s.y[i]; if (!isFinite(x) || !isFinite(y)) continue;
          x0 = Math.min(x0, x); x1 = Math.max(x1, x); y0 = Math.min(y0, y); y1 = Math.max(y1, y);
          if (s.y2) { y0 = Math.min(y0, s.y2[i]); y1 = Math.max(y1, s.y2[i]); }
        }
      }
      if (!isFinite(x0)) { x0 = 0; x1 = 1; } if (!isFinite(y0)) { y0 = 0; y1 = 1; }
      const px = (x1 - x0) * 0.04 || 0.5, py = (y1 - y0) * 0.08 || 0.5;
      return { x0: this.o.xRange ? this.o.xRange[0] : x0 - px, x1: this.o.xRange ? this.o.xRange[1] : x1 + px,
               y0: this.o.yRange ? this.o.yRange[0] : y0 - py, y1: this.o.yRange ? this.o.yRange[1] : y1 + py };
    }
    layout() {
      const r = this.el.getBoundingClientRect(), dpr = devicePixelRatio || 1;
      const W = Math.max(40, r.width), H = Math.max(40, r.height);
      if (this.c.width !== Math.round(W * dpr) || this.c.height !== Math.round(H * dpr)) { this.c.width = Math.round(W * dpr); this.c.height = Math.round(H * dpr); }
      this.W = W; this.H = H; this.dpr = dpr;
      const m = this.o.margin; this.pl = m.l; this.pt = m.t; this.pw = W - m.l - m.r; this.ph = H - m.t - m.b;
      this.b = this.bounds();
    }
    X(v) { return this.pl + (v - this.b.x0) / (this.b.x1 - this.b.x0) * this.pw; }
    Y(v) { return this.pt + this.ph - (v - this.b.y0) / (this.b.y1 - this.b.y0) * this.ph; }
    draw() {
      this.layout(); const g = this.ctx, o = this.o; g.setTransform(this.dpr, 0, 0, this.dpr, 0, 0); g.clearRect(0, 0, this.W, this.H);
      const text = css("--text-2"), faint = css("--text-3"), grid = css("--border");
      g.font = "11px " + css("--font"); g.textBaseline = "middle";
      const xt = niceTicks(this.b.x0, this.b.x1, Math.max(3, this.pw / 80)), yt = niceTicks(this.b.y0, this.b.y1, Math.max(3, this.ph / 40));
      g.lineWidth = 1;
      if (o.grid) { g.strokeStyle = grid; g.beginPath(); for (const v of yt.ticks) { const y = Math.round(this.Y(v)) + .5; g.moveTo(this.pl, y); g.lineTo(this.pl + this.pw, y); } for (const v of xt.ticks) { const x = Math.round(this.X(v)) + .5; g.moveTo(x, this.pt); g.lineTo(x, this.pt + this.ph); } g.stroke(); }
      g.fillStyle = faint; g.textAlign = "right"; for (const v of yt.ticks) g.fillText(fmtTick(v, yt.step), this.pl - 7, this.Y(v));
      g.textAlign = "center"; g.textBaseline = "top"; for (const v of xt.ticks) g.fillText(fmtTick(v, xt.step), this.X(v), this.pt + this.ph + 6);
      g.fillStyle = text; g.textBaseline = "alphabetic";
      if (o.xLabel) g.fillText(o.xLabel, this.pl + this.pw / 2, this.H - 6);
      if (o.yLabel) { g.save(); g.translate(13, this.pt + this.ph / 2); g.rotate(-Math.PI / 2); g.textAlign = "center"; g.fillText(o.yLabel, 0, 0); g.restore(); }
      g.save(); g.beginPath(); g.rect(this.pl, this.pt, this.pw, this.ph); g.clip();
      this.series.forEach((s, k) => {
        const col = s.color || PALETTE[k % PALETTE.length]; g.strokeStyle = col; g.fillStyle = col; g.lineWidth = s.width || 1.6; g.setLineDash(s.dash || []);
        g.globalAlpha = s.opacity == null ? 1 : s.opacity;
        if (s.type === "hline") { const y = this.Y(s.y); g.beginPath(); g.moveTo(this.pl, y); g.lineTo(this.pl + this.pw, y); g.stroke(); }
        else if (s.type === "vline") { const x = this.X(s.x); g.beginPath(); g.moveTo(x, this.pt); g.lineTo(x, this.pt + this.ph); g.stroke(); }
        else if (s.type === "band") { g.globalAlpha = s.opacity == null ? .14 : s.opacity; g.beginPath(); s.x.forEach((x, i) => { i ? g.lineTo(this.X(x), this.Y(s.y[i])) : g.moveTo(this.X(x), this.Y(s.y[i])); }); for (let i = s.x.length - 1; i >= 0; i--) g.lineTo(this.X(s.x[i]), this.Y(s.y2[i])); g.closePath(); g.fill(); }
        else if (s.type === "hband") { g.globalAlpha = s.opacity == null ? .12 : s.opacity; g.fillRect(this.pl, this.Y(s.y2), this.pw, this.Y(s.y) - this.Y(s.y2)); }
        else if (s.type === "scatter") { const r = s.size || 3; for (let i = 0; i < s.x.length; i++) { if (!isFinite(s.y[i])) continue; g.beginPath(); g.arc(this.X(s.x[i]), this.Y(s.y[i]), r, 0, 6.2832); g.fill(); } }
        else { g.beginPath(); let pen = false; for (let i = 0; i < s.x.length; i++) { if (!isFinite(s.y[i])) { pen = false; continue; } const x = this.X(s.x[i]), y = this.Y(s.y[i]); if (s.type === "step" && pen) g.lineTo(x, this.py); (pen ? g.lineTo : g.moveTo).call(g, x, y); pen = true; this.py = y; } g.stroke();
          if (s.points) { for (let i = 0; i < s.x.length; i++) { if (!isFinite(s.y[i])) continue; g.beginPath(); g.arc(this.X(s.x[i]), this.Y(s.y[i]), s.size || 2.6, 0, 6.2832); g.fill(); } } }
        g.setLineDash([]); g.globalAlpha = 1;
      });
      g.restore();
      g.strokeStyle = css("--border-strong"); g.strokeRect(this.pl + .5, this.pt + .5, this.pw, this.ph);
      if (o.legend) { const named = this.series.filter((s) => s.name); let x = this.pl + 8; g.textBaseline = "middle"; g.textAlign = "left";
        named.forEach((s) => { const k = this.series.indexOf(s), col = s.color || PALETTE[k % PALETTE.length], w = g.measureText(s.name).width;
          if (x + w + 30 > this.pl + this.pw) return; g.fillStyle = css("--surface"); g.globalAlpha = .85; g.fillRect(x - 4, this.pt + 4, w + 28, 18); g.globalAlpha = 1;
          g.strokeStyle = col; g.fillStyle = col; g.lineWidth = 2; g.setLineDash(s.dash || []); g.beginPath();
          if (s.type === "scatter") { g.arc(x + 6, this.pt + 13, 3.5, 0, 6.2832); g.fill(); } else { g.moveTo(x, this.pt + 13); g.lineTo(x + 12, this.pt + 13); g.stroke(); } g.setLineDash([]);
          g.fillStyle = text; g.fillText(s.name, x + 17, this.pt + 13); x += w + 32; }); }
      if (this.hover) { const h = this.hover; g.strokeStyle = faint; g.setLineDash([3, 3]); g.beginPath(); g.moveTo(this.X(h.x), this.pt); g.lineTo(this.X(h.x), this.pt + this.ph); g.stroke(); g.setLineDash([]); g.fillStyle = h.color; g.strokeStyle = css("--surface"); g.lineWidth = 2; g.beginPath(); g.arc(this.X(h.x), this.Y(h.y), 4.5, 0, 6.2832); g.fill(); g.stroke(); }
    }
    onMove(e) {
      const r = this.c.getBoundingClientRect(), mx = e.clientX - r.left, my = e.clientY - r.top; let best = null, bd = 1e9;
      this.series.forEach((s, k) => { if (!s.x || s.type === "band" || s.type === "hband" || s.noHover) return;
        for (let i = 0; i < s.x.length; i++) { if (!isFinite(s.y[i])) continue; const dx = this.X(s.x[i]) - mx, dy = this.Y(s.y[i]) - my;
          const d = s.type === "scatter" ? Math.hypot(dx, dy) : Math.abs(dx) + Math.abs(dy) * .15; if (d < bd) { bd = d; best = { s, i, k }; } } });
      if (best && bd < 28) { const s = best.s, col = s.color || PALETTE[best.k % PALETTE.length]; this.hover = { x: s.x[best.i], y: s.y[best.i], color: col };
        const f = this.o.tip ? this.o.tip(s, best.i) : `<b>${s.name || ""}</b><br>${this.o.xLabel || "x"}: ${(+s.x[best.i]).toFixed(2)}<br>${this.o.yLabel || "y"}: ${(+s.y[best.i]).toFixed(2)}`; tip(f, e.clientX, e.clientY); }
      else { this.hover = null; tip(null); }
      this.draw();
    }
    destroy() { this.ro.disconnect(); this.c.remove(); tip(null); }
  }
  G.Charts = { Chart, cmap, cmapNames, cmapCss, tip, css, niceTicks, fmtTick, PALETTE };
})(window);
