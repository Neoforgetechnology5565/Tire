/* Minimal WebGL 3D viewer: point / mesh / line layers, orbit-pan-zoom, markers, scale bar, picking. */
"use strict";
(function (G) {
  const M = {
    persp(f, a, n, fa) { const t = 1 / Math.tan(f / 2), o = new Float32Array(16); o[0] = t / a; o[5] = t; o[10] = (fa + n) / (n - fa); o[11] = -1; o[14] = 2 * fa * n / (n - fa); return o; },
    look(e, c, u) { const z = norm(sub(e, c)), x = norm(cross(u, z)), y = cross(z, x), o = new Float32Array(16);
      o[0] = x[0]; o[4] = x[1]; o[8] = x[2]; o[12] = -dot(x, e); o[1] = y[0]; o[5] = y[1]; o[9] = y[2]; o[13] = -dot(y, e); o[2] = z[0]; o[6] = z[1]; o[10] = z[2]; o[14] = -dot(z, e); o[15] = 1; return o; },
    mul(a, b) { const o = new Float32Array(16); for (let i = 0; i < 4; i++) for (let j = 0; j < 4; j++) { let s = 0; for (let k = 0; k < 4; k++) s += a[k * 4 + j] * b[i * 4 + k]; o[i * 4 + j] = s; } return o; },
  };
  const sub = (a, b) => [a[0] - b[0], a[1] - b[1], a[2] - b[2]], dot = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
  const cross = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
  const norm = (a) => { const l = Math.hypot(a[0], a[1], a[2]) || 1; return [a[0] / l, a[1] / l, a[2] / l]; };
  const css = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();

  const VS_P = "attribute vec3 aPos;attribute vec3 aCol;uniform mat4 uVP;uniform float uSize;varying vec3 vCol;void main(){gl_Position=uVP*vec4(aPos,1.);gl_PointSize=uSize;vCol=aCol;}";
  const FS_P = "precision mediump float;varying vec3 vCol;uniform float uAlpha;void main(){vec2 c=gl_PointCoord-.5;float r=length(c);if(r>.5)discard;gl_FragColor=vec4(vCol,uAlpha*smoothstep(.5,.38,r));}";
  const VS_L = "attribute vec3 aPos;attribute vec3 aCol;uniform mat4 uVP;varying vec3 vCol;void main(){gl_Position=uVP*vec4(aPos,1.);vCol=aCol;}";
  const FS_L = "precision mediump float;varying vec3 vCol;void main(){gl_FragColor=vec4(vCol,1.);}";
  const VS_M = "attribute vec3 aPos;attribute vec3 aNor;attribute vec3 aCol;uniform mat4 uVP;varying vec3 vCol;varying vec3 vN;void main(){gl_Position=uVP*vec4(aPos,1.);vCol=aCol;vN=aNor;}";
  const FS_M = "precision mediump float;varying vec3 vCol;varying vec3 vN;uniform vec3 uL;void main(){vec3 n=normalize(vN);float d=abs(dot(n,normalize(uL)));float h=.5+.5*abs(n.z);gl_FragColor=vec4(vCol*(.38+.62*d)*(.9+.1*h),1.);}";

  function prog(gl, vs, fs) {
    const mk = (t, s) => { const x = gl.createShader(t); gl.shaderSource(x, s); gl.compileShader(x); if (!gl.getShaderParameter(x, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(x)); return x; };
    const p = gl.createProgram(); gl.attachShader(p, mk(gl.VERTEX_SHADER, vs)); gl.attachShader(p, mk(gl.FRAGMENT_SHADER, fs)); gl.linkProgram(p);
    if (!gl.getProgramParameter(p, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(p)); return p;
  }
  function normals(pos, idx) {
    const n = new Float32Array(pos.length);
    for (let t = 0; t < idx.length; t += 3) { const a = idx[t] * 3, b = idx[t + 1] * 3, c = idx[t + 2] * 3;
      const ux = pos[b] - pos[a], uy = pos[b + 1] - pos[a + 1], uz = pos[b + 2] - pos[a + 2], vx = pos[c] - pos[a], vy = pos[c + 1] - pos[a + 1], vz = pos[c + 2] - pos[a + 2];
      const nx = uy * vz - uz * vy, ny = uz * vx - ux * vz, nz = ux * vy - uy * vx;
      for (const k of [a, b, c]) { n[k] += nx; n[k + 1] += ny; n[k + 2] += nz; } }
    for (let i = 0; i < n.length; i += 3) { const l = Math.hypot(n[i], n[i + 1], n[i + 2]) || 1; n[i] /= l; n[i + 1] /= l; n[i + 2] /= l; }
    return n;
  }

  class Viewer3D {
    constructor(el, opt) {
      this.el = el; this.o = Object.assign({ axes: true, scale: true }, opt || {});
      el.style.position = el.style.position || "relative";
      this.cv = document.createElement("canvas"); this.ov = document.createElement("canvas"); this.lab = document.createElement("div");
      this.cv.style.cssText = "position:absolute;inset:0;width:100%;height:100%;touch-action:none;cursor:grab";
      this.ov.style.cssText = "position:absolute;inset:0;width:100%;height:100%;pointer-events:none";
      this.lab.style.cssText = "position:absolute;inset:0;pointer-events:none;overflow:hidden";
      el.append(this.cv, this.ov, this.lab);
      const gl = this.gl = this.cv.getContext("webgl", { antialias: true, alpha: false, preserveDrawingBuffer: true });
      this.ok = !!gl;
      if (!gl) { el.insertAdjacentHTML("beforeend", '<div style="position:absolute;inset:0;display:grid;place-items:center;color:var(--text-2)">WebGL is not available in this window.</div>'); return; }
      gl.getExtension('OES_element_index_uint'); this.pp = prog(gl, VS_P, FS_P); this.pl = prog(gl, VS_L, FS_L); this.pm = prog(gl, VS_M, FS_M);
      this.layers = {}; this.markers = []; this.segs = []; this.handlers = {};
      this.cam = { t: [0, 0, 0], d: 1, yaw: -0.9, pitch: 0.5 }; this.home = null; this.pointSize = 3;
      this.fov = 0.6; gl.enable(gl.DEPTH_TEST); gl.enable(gl.BLEND); gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);
      this._bind(); this.ro = new ResizeObserver(() => this.render()); this.ro.observe(el);
    }
    on(ev, f) { this.handlers[ev] = f; }
    _bind() {
      let drag = null, moved = 0;
      const c = this.cv;
      c.addEventListener("contextmenu", (e) => e.preventDefault());
      c.addEventListener("pointerdown", (e) => { c.setPointerCapture(e.pointerId); drag = { x: e.clientX, y: e.clientY, pan: e.button === 1 || e.button === 2 || e.shiftKey }; moved = 0; c.style.cursor = "grabbing"; });
      c.addEventListener("pointermove", (e) => {
        if (!drag) { if (this.handlers.hover) this.handlers.hover(this.pick(e, 10), e); return; }
        const dx = e.clientX - drag.x, dy = e.clientY - drag.y; drag.x = e.clientX; drag.y = e.clientY; moved += Math.abs(dx) + Math.abs(dy);
        if (drag.pan) { const k = this._mpp() , cam = this.cam, r = this._right(), u = this._up(); for (let i = 0; i < 3; i++) cam.t[i] += (-dx * r[i] + dy * u[i]) * k; }
        else { this.cam.yaw -= dx * 0.008; this.cam.pitch = Math.max(-1.5, Math.min(1.5, this.cam.pitch + dy * 0.008)); }
        this.render();
      });
      const up = (e) => { if (!drag) return; drag = null; c.style.cursor = "grab"; if (moved < 4 && this.handlers.pick) { const p = this.pick(e, 14); this.handlers.pick(p, e); } };
      c.addEventListener("pointerup", up); c.addEventListener("pointercancel", () => { drag = null; });
      c.addEventListener("wheel", (e) => { e.preventDefault(); this.cam.d *= Math.exp(e.deltaY * 0.0014); this.cam.d = Math.max(this.home ? this.home.d * 0.01 : 1e-3, this.cam.d); this.render(); }, { passive: false });
      c.addEventListener("dblclick", () => this.reset());
    }
    _eye() { const c = this.cam, cp = Math.cos(c.pitch); return [c.t[0] + c.d * cp * Math.cos(c.yaw), c.t[1] + c.d * cp * Math.sin(c.yaw), c.t[2] + c.d * Math.sin(c.pitch)]; }
    _right() { const e = this._eye(), z = norm(sub(e, this.cam.t)); return norm(cross([0, 0, 1], z)); }
    _up() { const e = this._eye(), z = norm(sub(e, this.cam.t)), x = norm(cross([0, 0, 1], z)); return cross(z, x); }
    _mpp() { return 2 * this.cam.d * Math.tan(this.fov / 2) / Math.max(1, this.H); }
    setLayer(name, L) {
      if (!this.ok) return; const gl = this.gl; this.removeLayer(name);
      const mk = (data, idx) => { const b = gl.createBuffer(); gl.bindBuffer(idx ? gl.ELEMENT_ARRAY_BUFFER : gl.ARRAY_BUFFER, b); gl.bufferData(idx ? gl.ELEMENT_ARRAY_BUFFER : gl.ARRAY_BUFFER, data, gl.STATIC_DRAW); return b; };
      const lay = Object.assign({ visible: true, alpha: 1, size: null }, L); lay.type = L.type;
      lay.bpos = mk(L.positions); lay.n = L.positions.length / 3;
      const col = L.colors || (() => { const c = L.color || [0.7, 0.75, 0.8], a = new Float32Array(lay.n * 3); for (let i = 0; i < lay.n; i++) a.set(c, i * 3); return a; })();
      lay.bcol = mk(col);
      if (L.type === "mesh") { lay.bnor = mk(normals(L.positions, L.indices)); lay.bidx = mk(L.indices, true); lay.ni = L.indices.length; }
      this.layers[name] = lay; this.render();
    }
    removeLayer(name) { const l = this.layers[name]; if (!l) return; const gl = this.gl; for (const k of ["bpos", "bcol", "bnor", "bidx"]) if (l[k]) gl.deleteBuffer(l[k]); delete this.layers[name]; }
    clear() { for (const k of Object.keys(this.layers)) this.removeLayer(k); this.markers = []; this.segs = []; this.lab.innerHTML = ""; this.render(); }
    show(name, v) { if (this.layers[name]) { this.layers[name].visible = v; this.render(); } }
    setPointSize(s) { this.pointSize = s; this.render(); }
    setMarkers(m, segs) { this.markers = m || []; this.segs = segs || []; this.render(); }
    bounds(names) {
      let lo = [1e30, 1e30, 1e30], hi = [-1e30, -1e30, -1e30];
      for (const k of names || Object.keys(this.layers)) { const l = this.layers[k]; if (!l || !l.positions) continue; const p = l.positions, st = Math.max(1, Math.floor(l.n / 20000));
        for (let i = 0; i < l.n; i += st) for (let a = 0; a < 3; a++) { const v = p[i * 3 + a]; if (v < lo[a]) lo[a] = v; if (v > hi[a]) hi[a] = v; } }
      return lo[0] > hi[0] ? null : { lo, hi };
    }
    fit(names, keepAngles) {
      const b = this.bounds(names); if (!b) return; const c = [0, 1, 2].map((i) => (b.lo[i] + b.hi[i]) / 2), r = Math.hypot(b.hi[0] - b.lo[0], b.hi[1] - b.lo[1], b.hi[2] - b.lo[2]) / 2 || 1;
      this.cam.t = c; this.cam.d = r / Math.sin(this.fov / 2) * 1.05; if (!keepAngles) { this.cam.yaw = -0.9; this.cam.pitch = 0.5; }
      this.home = { t: c.slice(), d: this.cam.d, yaw: this.cam.yaw, pitch: this.cam.pitch, names }; this.render();
    }
    lookAlong(dir, up) { const d = norm(dir); this.cam.yaw = Math.atan2(d[1], d[0]); this.cam.pitch = Math.asin(d[2]); this.render(); }
    reset() { if (this.home) { Object.assign(this.cam, { t: this.home.t.slice(), d: this.home.d, yaw: this.home.yaw, pitch: this.home.pitch }); this.render(); } }
    _vp() { const e = this._eye(), a = this.W / Math.max(1, this.H); return M.mul(M.persp(this.fov, a, this.cam.d * 0.005, this.cam.d * 200), M.look(e, this.cam.t, [0, 0, 1])); }
    project(p, vp) { vp = vp || this._vp(); const x = vp[0] * p[0] + vp[4] * p[1] + vp[8] * p[2] + vp[12], y = vp[1] * p[0] + vp[5] * p[1] + vp[9] * p[2] + vp[13], w = vp[3] * p[0] + vp[7] * p[1] + vp[11] * p[2] + vp[15];
      return w <= 0 ? null : [(x / w * 0.5 + 0.5) * this.W, (1 - (y / w * 0.5 + 0.5)) * this.H, w]; }
    pick(e, rad) {
      if (!this.ok) return null; const r = this.cv.getBoundingClientRect(), mx = e.clientX - r.left, my = e.clientY - r.top, vp = this._vp(); let best = null, bd = rad * rad;
      for (const [name, l] of Object.entries(this.layers)) { if (!l.visible || !l.pickable || !l.positions) continue; const p = l.positions, st = Math.max(1, Math.floor(l.n / 60000));
        for (let i = 0; i < l.n; i += st) { const x = vp[0] * p[i * 3] + vp[4] * p[i * 3 + 1] + vp[8] * p[i * 3 + 2] + vp[12], y = vp[1] * p[i * 3] + vp[5] * p[i * 3 + 1] + vp[9] * p[i * 3 + 2] + vp[13], w = vp[3] * p[i * 3] + vp[7] * p[i * 3 + 1] + vp[11] * p[i * 3 + 2] + vp[15];
          if (w <= 0) continue; const sx = (x / w * .5 + .5) * this.W, sy = (1 - (y / w * .5 + .5)) * this.H, d = (sx - mx) ** 2 + (sy - my) ** 2; if (d < bd) { bd = d; best = { layer: name, index: i, pos: [p[i * 3], p[i * 3 + 1], p[i * 3 + 2]] }; } } }
      return best;
    }
    render() {
      if (!this.ok) return; const gl = this.gl, r = this.el.getBoundingClientRect(), dpr = devicePixelRatio || 1; this.W = r.width; this.H = r.height;
      const pw = Math.round(r.width * dpr), ph = Math.round(r.height * dpr); if (this.cv.width !== pw || this.cv.height !== ph) { this.cv.width = pw; this.cv.height = ph; this.ov.width = pw; this.ov.height = ph; }
      gl.viewport(0, 0, pw, ph); const bg = css("--viewer-bg") || "#0f141a", m = /^#?([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(bg.replace(/\s/g, ""));
      const c = m ? [parseInt(m[1], 16), parseInt(m[2], 16), parseInt(m[3], 16)].map((v) => v / 255) : [0.06, 0.08, 0.1]; gl.clearColor(c[0], c[1], c[2], 1); gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
      const vp = this._vp(), L = norm(sub(this._eye(), this.cam.t)).map((v, i) => v + [0.25, 0.35, 0.5][i]);
      for (const l of Object.values(this.layers)) { if (!l.visible) continue;
        const useP = l.type === "points" ? this.pp : l.type === "mesh" ? this.pm : this.pl; gl.useProgram(useP); gl.uniformMatrix4fv(gl.getUniformLocation(useP, "uVP"), false, vp);
        const bind = (loc, buf) => { const a = gl.getAttribLocation(useP, loc); if (a < 0) return; gl.bindBuffer(gl.ARRAY_BUFFER, buf); gl.enableVertexAttribArray(a); gl.vertexAttribPointer(a, 3, gl.FLOAT, false, 0, 0); };
        bind("aPos", l.bpos); bind("aCol", l.bcol);
        if (l.type === "points") { gl.uniform1f(gl.getUniformLocation(useP, "uSize"), (l.size || this.pointSize) * dpr); gl.uniform1f(gl.getUniformLocation(useP, "uAlpha"), l.alpha); gl.drawArrays(gl.POINTS, 0, l.n); }
        else if (l.type === "lines") gl.drawArrays(gl.LINES, 0, l.n);
        else { bind("aNor", l.bnor); gl.uniform3fv(gl.getUniformLocation(useP, "uL"), L); gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, l.bidx); gl.drawElements(gl.TRIANGLES, l.ni, gl.UNSIGNED_INT, 0); } }
      this._overlay(vp, dpr);
    }
    _overlay(vp, dpr) {
      const g = this.ov.getContext("2d"); g.setTransform(dpr, 0, 0, dpr, 0, 0); g.clearRect(0, 0, this.W, this.H); const txt = css("--viewer-text"), accent = css("--accent");
      this.lab.innerHTML = "";
      for (const s of this.segs) { const a = this.project(s.a, vp), b = this.project(s.b, vp); if (!a || !b) continue; g.strokeStyle = s.color || accent; g.lineWidth = 2; g.setLineDash(s.dash || []); g.beginPath(); g.moveTo(a[0], a[1]); g.lineTo(b[0], b[1]); g.stroke(); g.setLineDash([]); }
      for (const m of this.markers) { const q = this.project(m.p, vp); if (!q) continue; g.strokeStyle = "#fff"; g.fillStyle = m.color || accent; g.lineWidth = 2; g.beginPath(); g.arc(q[0], q[1], m.r || 5.5, 0, 6.2832); g.fill(); g.stroke();
        if (m.label) { const d = document.createElement("div"); d.className = "pill-label"; d.textContent = m.label; d.style.left = q[0] + "px"; d.style.top = q[1] - 10 + "px"; this.lab.appendChild(d); } }
      if (this.o.axes) { const R = this._right(), U = this._up(), F = norm(sub(this._eye(), this.cam.t)), ox = 44, oy = this.H - 44, k = 24;
        [["x", [1, 0, 0], "#ef4444"], ["y", [0, 1, 0], "#22c55e"], ["z", [0, 0, 1], "#3b82f6"]].forEach(([n, a, col]) => { const sx = dot(a, R) * k, sy = -dot(a, U) * k; g.strokeStyle = col; g.fillStyle = col; g.lineWidth = 2; g.beginPath(); g.moveTo(ox, oy); g.lineTo(ox + sx, oy + sy); g.stroke(); g.font = "600 10px " + css("--font"); g.textAlign = "center"; g.textBaseline = "middle"; g.fillText(n.toUpperCase(), ox + sx * 1.3, oy + sy * 1.3); }); }
      if (this.o.scale) { const mpp = this._mpp(), targ = mpp * 90, p = Math.pow(10, Math.floor(Math.log10(targ))), f = targ / p, nice = (f < 1.5 ? 1 : f < 3.5 ? 2 : f < 7.5 ? 5 : 10) * p, px = nice / mpp, x = this.W - 20 - px, y = this.H - 18;
        g.strokeStyle = txt; g.fillStyle = txt; g.lineWidth = 1.5; g.beginPath(); g.moveTo(x, y - 4); g.lineTo(x, y); g.lineTo(x + px, y); g.lineTo(x + px, y - 4); g.stroke(); g.font = "11px " + css("--font"); g.textAlign = "center"; g.textBaseline = "bottom";
        g.fillText(nice >= 1 ? nice.toFixed(nice < 10 ? 1 : 0) + " m" : (nice * 1000 >= 1 ? (nice * 1000).toFixed(nice * 1000 < 10 ? 1 : 0) + " mm" : (nice * 1e6).toFixed(0) + " µm"), x + px / 2, y - 6); }
    }
    destroy() { if (!this.ok) return; this.ro.disconnect(); for (const k of Object.keys(this.layers)) this.removeLayer(k); this.cv.remove(); this.ov.remove(); this.lab.remove(); }
  }
  G.Viewer3D = Viewer3D;
})(window);
